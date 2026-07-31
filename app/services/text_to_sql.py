import json
import re
from time import perf_counter
from typing import Any

from sqlalchemy import Engine

from app.core.config import settings
from app.db.base import engine
from app.db.metadata import inspect_schema
from app.llm.client import OpenAICompatibleClient
from app.llm.prompts import build_sql_repair_messages, build_text_to_sql_messages
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

    async def generate(self, question: str) -> QueryResponse:
        total_started_at = perf_counter()

        stage_started_at = perf_counter()
        schema = inspect_schema(self.target_engine)
        schema_inspection_ms = self._elapsed_ms(stage_started_at)

        stage_started_at = perf_counter()
        schema_context = format_schema_for_prompt(schema)
        schema_formatting_ms = self._elapsed_ms(stage_started_at)

        stage_started_at = perf_counter()
        messages = build_text_to_sql_messages(question, schema_context)
        prompt_building_ms = self._elapsed_ms(stage_started_at)

        stage_started_at = perf_counter()
        raw_content = await self.llm_client.complete(messages)
        llm_call_ms = self._elapsed_ms(stage_started_at)

        stage_started_at = perf_counter()
        payload = self._parse_model_json(raw_content)
        response_parsing_ms = self._elapsed_ms(stage_started_at)

        stage_started_at = perf_counter()
        sql = str(payload.get("sql", "")).strip()
        self._validate_readonly_sql(sql)
        sql_validation_ms = self._elapsed_ms(stage_started_at)

        execution_time_ms = 0.0
        repair_prompt_building_ms = 0.0
        repair_llm_call_ms = 0.0
        repair_response_parsing_ms = 0.0
        repair_sql_validation_ms = 0.0
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

                stage_started_at = perf_counter()
                repair_messages = build_sql_repair_messages(
                    question=question,
                    schema_context=schema_context,
                    failed_sql=sql,
                    database_error=exc.database_error,
                )
                repair_prompt_building_ms += self._elapsed_ms(stage_started_at)

                stage_started_at = perf_counter()
                repaired_content = await self.llm_client.complete(repair_messages)
                repair_llm_call_ms += self._elapsed_ms(stage_started_at)

                stage_started_at = perf_counter()
                payload = self._parse_model_json(repaired_content)
                repair_response_parsing_ms += self._elapsed_ms(stage_started_at)

                stage_started_at = perf_counter()
                sql = str(payload.get("sql", "")).strip()
                self._validate_readonly_sql(sql)
                repair_sql_validation_ms += self._elapsed_ms(stage_started_at)

        assumptions = payload.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]

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
            timings=StageTimings(
                schema_inspection_ms=schema_inspection_ms,
                schema_formatting_ms=schema_formatting_ms,
                prompt_building_ms=prompt_building_ms,
                llm_call_ms=llm_call_ms,
                response_parsing_ms=response_parsing_ms,
                sql_validation_ms=sql_validation_ms,
                sql_execution_ms=execution_time_ms,
                repair_prompt_building_ms=repair_prompt_building_ms,
                repair_llm_call_ms=repair_llm_call_ms,
                repair_response_parsing_ms=repair_response_parsing_ms,
                repair_sql_validation_ms=repair_sql_validation_ms,
                total_ms=self._elapsed_ms(total_started_at),
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
