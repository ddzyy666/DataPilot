import json
import re
from time import perf_counter
from typing import Any

from sqlalchemy import Engine

from app.core.config import settings
from app.db.base import engine
from app.db.metadata import inspect_schema
from app.llm.client import OpenAICompatibleClient
from app.llm.prompts import (
    build_sql_repair_messages,
    build_sql_review_messages,
    build_text_to_sql_messages,
)
from app.schemas.query import QueryResponse, StageTimings
from app.services.schema_formatter import format_schema_for_prompt
from app.services.sql_executor import SQLExecutionError, SQLExecutor


class SQLSafetyError(ValueError):
    pass


class TextToSQLService:
    def __init__(
        self,
        llm_client: OpenAICompatibleClient | None = None,
        target_engine: Engine = engine,
    ) -> None:
        self.llm_client = llm_client or OpenAICompatibleClient()
        self.target_engine = target_engine
        self.sql_executor = SQLExecutor(target_engine, max_rows=settings.query_max_rows)
        self.max_repair_attempts = settings.query_max_repair_attempts
        self.enable_sql_review = settings.query_enable_sql_review

    async def generate(self, question: str) -> QueryResponse:
        total_started_at = perf_counter()

        schema_started_at = perf_counter()
        schema = inspect_schema(self.target_engine)
        schema_context = format_schema_for_prompt(schema)
        schema_processing_ms = self._elapsed_ms(schema_started_at)

        messages = build_text_to_sql_messages(question, schema_context)

        stage_started_at = perf_counter()
        raw_content = await self.llm_client.complete(messages)
        sql_generation_llm_ms = self._elapsed_ms(stage_started_at)

        payload = self._parse_model_json(raw_content)

        sql = str(payload.get("sql", "")).strip()
        self._validate_readonly_sql(sql)

        reviewed = False
        review_passed: bool | None = None
        review_issues: list[str] = []
        review_checks: dict[str, bool] = {}
        was_review_corrected = False
        review_llm_call_ms = 0.0

        if self.enable_sql_review:
            reviewed = True

            review_messages = build_sql_review_messages(question, schema_context, sql)

            stage_started_at = perf_counter()
            review_content = await self.llm_client.complete(review_messages)
            review_llm_call_ms = self._elapsed_ms(stage_started_at)

            review_payload = self._parse_model_json(review_content)

            if not isinstance(review_payload.get("is_correct"), bool):
                raise ValueError("SQL 审核器没有返回合法的 is_correct 字段。")

            expected_checks = {
                "metric_correct",
                "dimensions_correct",
                "filters_correct",
                "joins_correct",
                "output_correct",
            }
            raw_checks = review_payload.get("checks")
            if not isinstance(raw_checks, dict):
                raise ValueError("SQL 审核器没有返回合法的 checks 字段。")
            if not expected_checks.issubset(raw_checks):
                raise ValueError("SQL 审核器返回的 checks 字段不完整。")
            if any(not isinstance(raw_checks[name], bool) for name in expected_checks):
                raise ValueError("SQL 审核器的检查结果必须是布尔值。")
            review_checks = {name: raw_checks[name] for name in sorted(expected_checks)}
            review_passed = review_payload["is_correct"] and all(review_checks.values())

            issues = review_payload.get("issues", [])
            if not isinstance(issues, list):
                issues = [str(issues)]
            review_issues = [str(item) for item in issues]

            if not review_passed:
                corrected_sql = str(review_payload.get("corrected_sql") or "").strip()
                self._validate_readonly_sql(corrected_sql)
                sql = corrected_sql
                was_review_corrected = True

                review_explanation = str(review_payload.get("explanation", "")).strip()
                if review_explanation:
                    payload["explanation"] = review_explanation

        execution_time_ms = 0.0
        repair_llm_call_ms = 0.0
        repair_attempts = 0

        while True:
            try:
                execution = self.sql_executor.execute(sql)
                execution_time_ms += execution.execution_time_ms
                break
            except SQLExecutionError as exc:
                execution_time_ms += exc.execution_time_ms
                if repair_attempts >= self.max_repair_attempts:
                    raise

                repair_attempts += 1

                repair_messages = build_sql_repair_messages(
                    question=question,
                    schema_context=schema_context,
                    failed_sql=sql,
                    database_error=exc.database_error,
                )

                stage_started_at = perf_counter()
                repaired_content = await self.llm_client.complete(repair_messages)
                repair_llm_call_ms += self._elapsed_ms(stage_started_at)

                payload = self._parse_model_json(repaired_content)

                sql = str(payload.get("sql", "")).strip()
                self._validate_readonly_sql(sql)

        assumptions = payload.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]

        total_ms = self._elapsed_ms(total_started_at)
        llm_total_ms = round(
            sql_generation_llm_ms + review_llm_call_ms + repair_llm_call_ms,
            2,
        )
        other_processing_ms = round(
            max(0.0, total_ms - schema_processing_ms - llm_total_ms - execution_time_ms),
            2,
        )

        return QueryResponse(
            question=question,
            sql=sql,
            explanation=str(payload.get("explanation", "")).strip(),
            assumptions=[str(item) for item in assumptions],
            schema_context=schema_context,
            columns=execution.columns,
            rows=execution.rows,
            row_count=execution.row_count,
            truncated=execution.truncated,
            execution_time_ms=execution_time_ms,
            was_repaired=repair_attempts > 0,
            repair_attempts=repair_attempts,
            reviewed=reviewed,
            review_passed=review_passed,
            review_issues=review_issues,
            review_checks=review_checks,
            was_review_corrected=was_review_corrected,
            timings=StageTimings(
                schema_processing_ms=schema_processing_ms,
                llm_total_ms=llm_total_ms,
                sql_execution_ms=execution_time_ms,
                other_processing_ms=other_processing_ms,
                total_ms=total_ms,
            ),
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)

    def _parse_model_json(self, raw_content: str) -> dict[str, Any]:
        content = raw_content.strip()
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or start >= end:
                raise ValueError("模型没有返回合法 JSON。") from None
            try:
                payload = json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError("模型没有返回合法 JSON。") from exc

        if not isinstance(payload, dict):
            raise TypeError("模型 JSON 响应必须是对象。")
        return payload

    def _validate_readonly_sql(self, sql: str) -> None:
        normalized = re.sub(r"\s+", " ", sql).strip().lower()
        if not normalized:
            raise SQLSafetyError("模型没有生成 SQL。")
        if not normalized.startswith(("select ", "with ")):
            raise SQLSafetyError("当前阶段只允许生成 SELECT/WITH 查询。")

        statements = [item.strip() for item in sql.split(";") if item.strip()]
        if len(statements) != 1:
            raise SQLSafetyError("每次只允许执行一条 SQL 查询。")

        forbidden_keywords = {
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
            "create",
            "replace",
            "truncate",
        }
        tokens = set(re.findall(r"[a-z_]+", normalized))
        used_forbidden_keywords = sorted(tokens & forbidden_keywords)
        if used_forbidden_keywords:
            joined_keywords = ", ".join(used_forbidden_keywords)
            raise SQLSafetyError(f"SQL 包含危险关键字: {joined_keywords}")
