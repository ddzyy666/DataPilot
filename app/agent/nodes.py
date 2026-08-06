from time import perf_counter
from typing import Literal

from app.agent.state import TextToSQLGraphState
from app.db.metadata import inspect_schema
from app.llm.prompts import (
    build_sql_repair_messages,
    build_sql_review_messages,
    build_text_to_sql_messages,
)
from app.services.schema_formatter import format_schema_for_prompt
from app.services.sql_executor import SQLExecutionError
from app.services.text_to_sql import TextToSQLService


class TextToSQLGraphNodes:
    def __init__(self, service: TextToSQLService) -> None:
        self.service = service

    async def load_schema(self, state: TextToSQLGraphState) -> dict:
        started_at = perf_counter()
        schema = self.service.permission_policy.filter_schema(
            inspect_schema(self.service.target_engine)
        )
        return {
            "schema_context": format_schema_for_prompt(schema),
            "schema_processing_ms": self._elapsed_ms(started_at),
        }

    async def generate_sql(self, state: TextToSQLGraphState) -> dict:
        messages = build_text_to_sql_messages(state["question"], state["schema_context"])
        started_at = perf_counter()
        raw_content = await self.service.llm_client.complete(messages)
        elapsed_ms = self._elapsed_ms(started_at)
        payload = self.service._parse_model_json(raw_content)
        sql = str(payload.get("sql", "")).strip()
        self.service._validate_readonly_sql(sql)
        assumptions = payload.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        return {
            "sql": sql,
            "explanation": str(payload.get("explanation", "")).strip(),
            "assumptions": [str(item) for item in assumptions],
            "generation_llm_ms": elapsed_ms,
        }

    async def review_sql(self, state: TextToSQLGraphState) -> dict:
        messages = build_sql_review_messages(
            state["question"],
            state["schema_context"],
            state["sql"],
        )
        started_at = perf_counter()
        raw_content = await self.service.llm_client.complete(messages)
        elapsed_ms = self._elapsed_ms(started_at)
        payload = self.service._parse_model_json(raw_content)

        if not isinstance(payload.get("is_correct"), bool):
            raise TypeError("SQL 审核器没有返回合法的 is_correct 字段。")
        expected_checks = {
            "metric_correct",
            "dimensions_correct",
            "filters_correct",
            "joins_correct",
            "output_correct",
        }
        raw_checks = payload.get("checks")
        if not isinstance(raw_checks, dict):
            raise TypeError("SQL 审核器没有返回合法的 checks 字段。")
        if not expected_checks.issubset(raw_checks):
            raise ValueError("SQL 审核器返回的 checks 字段不完整。")
        if any(not isinstance(raw_checks[name], bool) for name in expected_checks):
            raise ValueError("SQL 审核器的检查结果必须是布尔值。")

        checks = {name: raw_checks[name] for name in sorted(expected_checks)}
        review_passed = payload["is_correct"] and all(checks.values())
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]

        updates: dict = {
            "reviewed": True,
            "review_passed": review_passed,
            "review_checks": checks,
            "review_issues": [str(item) for item in issues],
            "review_llm_ms": elapsed_ms,
            "was_review_corrected": False,
        }
        if not review_passed:
            corrected_sql = str(payload.get("corrected_sql") or "").strip()
            self.service._validate_readonly_sql(corrected_sql)
            updates["sql"] = corrected_sql
            updates["was_review_corrected"] = True
            explanation = str(payload.get("explanation", "")).strip()
            if explanation:
                updates["explanation"] = explanation
        return updates

    async def execute_sql(self, state: TextToSQLGraphState) -> dict:
        accumulated_ms = state.get("sql_execution_ms", 0.0)
        try:
            result = self.service.sql_executor.execute(state["sql"])
        except SQLExecutionError as exc:
            return {
                "execution_error": exc.database_error,
                "sql_execution_ms": round(accumulated_ms + exc.execution_time_ms, 2),
            }
        return {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "execution_error": None,
            "sql_execution_ms": round(accumulated_ms + result.execution_time_ms, 2),
        }

    async def repair_sql(self, state: TextToSQLGraphState) -> dict:
        messages = build_sql_repair_messages(
            question=state["question"],
            schema_context=state["schema_context"],
            failed_sql=state["sql"],
            database_error=state["execution_error"] or "未知数据库错误",
        )
        started_at = perf_counter()
        raw_content = await self.service.llm_client.complete(messages)
        elapsed_ms = self._elapsed_ms(started_at)
        payload = self.service._parse_model_json(raw_content)
        sql = str(payload.get("sql", "")).strip()
        self.service._validate_readonly_sql(sql)
        assumptions = payload.get("assumptions", state.get("assumptions", []))
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        return {
            "sql": sql,
            "explanation": str(payload.get("explanation", state.get("explanation", ""))).strip(),
            "assumptions": [str(item) for item in assumptions],
            "repair_attempts": state.get("repair_attempts", 0) + 1,
            "repair_llm_ms": round(state.get("repair_llm_ms", 0.0) + elapsed_ms, 2),
            "execution_error": None,
        }

    async def raise_execution_error(self, state: TextToSQLGraphState) -> dict:
        raise SQLExecutionError(
            state.get("execution_error") or "未知数据库错误",
            state.get("sql_execution_ms", 0.0),
        )

    def route_after_generation(self, state: TextToSQLGraphState) -> Literal["review", "execute"]:
        return "review" if self.service.enable_sql_review else "execute"

    def route_after_execution(self, state: TextToSQLGraphState) -> Literal[
        "success", "repair", "failed"
    ]:
        if state.get("execution_error") is None:
            return "success"
        if state.get("repair_attempts", 0) < self.service.max_repair_attempts:
            return "repair"
        return "failed"

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)
