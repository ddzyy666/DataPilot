from time import perf_counter
from typing import Literal

from langgraph.types import interrupt

from app.agent.state import TextToSQLGraphState
from app.db.metadata import inspect_schema
from app.llm.client import LLMConfigurationError, LLMResponseError
from app.llm.prompts import (
    build_question_analysis_messages,
    build_sql_repair_messages,
    build_sql_review_messages,
    build_text_to_sql_messages,
)
from app.services.result_analyzer import ResultAnalyzer
from app.services.schema_formatter import format_schema_for_prompt
from app.services.semantic_layer import SemanticLayer
from app.services.sql_executor import SQLExecutionError
from app.services.sql_risk import SQLRiskAssessor
from app.services.text_to_sql import TextToSQLService


class TextToSQLGraphNodes:
    def __init__(
        self,
        service: TextToSQLService,
        risk_assessor: SQLRiskAssessor,
        *,
        enable_clarification: bool,
        max_clarification_rounds: int,
        enable_result_analysis: bool,
        result_analysis_max_rows: int,
    ) -> None:
        self.service = service
        self.risk_assessor = risk_assessor
        self.enable_clarification = enable_clarification
        self.max_clarification_rounds = max(0, max_clarification_rounds)
        self.enable_result_analysis = enable_result_analysis
        self.result_analyzer = ResultAnalyzer(
            service.llm_client,
            max_rows_for_llm=result_analysis_max_rows,
        )
        self.semantic_layer = SemanticLayer()

    async def load_schema(self, state: TextToSQLGraphState) -> dict:
        started_at = perf_counter()
        schema = self.service.permission_policy.filter_schema(
            inspect_schema(self.service.target_engine)
        )
        return {
            "schema_context": format_schema_for_prompt(schema),
            "schema_processing_ms": self._elapsed_ms(started_at),
        }

    async def resolve_semantics(self, state: TextToSQLGraphState) -> dict:
        match = self.semantic_layer.match(state["effective_question"])
        return {
            "semantic_context": self.semantic_layer.format_for_prompt(match),
            "matched_metrics": match.metric_keys,
            "matched_dimensions": match.dimension_keys,
        }

    async def analyze_question(self, state: TextToSQLGraphState) -> dict:
        if not self.enable_clarification or self.max_clarification_rounds == 0:
            return {
                "requires_clarification": False,
                "clarification_question": None,
                "clarification_options": [],
            }

        messages = build_question_analysis_messages(
            state["effective_question"],
            state["schema_context"],
            state.get("conversation_history", []),
            state.get("semantic_context", ""),
        )
        started_at = perf_counter()
        raw_content = await self.service.llm_client.complete(messages)
        elapsed_ms = self._elapsed_ms(started_at)
        payload = self.service._parse_model_json(raw_content)
        if not isinstance(payload.get("is_complete"), bool):
            raise TypeError("问题完整性分析器没有返回合法的 is_complete 字段。")

        options = payload.get("options", [])
        if not isinstance(options, list):
            raise TypeError("问题完整性分析器没有返回合法的 options 字段。")
        clarification_question = str(
            payload.get("clarification_question") or ""
        ).strip()
        can_clarify = (
            not payload["is_complete"]
            and state.get("clarification_count", 0) < self.max_clarification_rounds
        )
        if can_clarify and not clarification_question:
            raise ValueError("问题完整性分析器要求澄清，但没有返回澄清问题。")
        return {
            "requires_clarification": can_clarify,
            "clarification_question": clarification_question if can_clarify else None,
            "clarification_options": (
                [str(item) for item in options[:4]] if can_clarify else []
            ),
            "clarification_llm_ms": round(
                state.get("clarification_llm_ms", 0.0) + elapsed_ms,
                2,
            ),
        }

    async def clarify_question(self, state: TextToSQLGraphState) -> dict:
        decision = interrupt(
            {
                "request_id": state["request_id"],
                "question": state["question"],
                "clarification_question": state["clarification_question"],
                "options": state.get("clarification_options", []),
                "message": "需要补充信息后才能准确生成SQL。",
            }
        )
        if not isinstance(decision, dict):
            raise TypeError("澄清结果必须是包含 answer 字段的对象。")
        answer = str(decision.get("answer") or "").strip()
        if not answer:
            raise ValueError("澄清回答不能为空。")

        history = [*state.get("conversation_history", [])]
        history.extend(
            [
                {
                    "role": "assistant",
                    "content": state.get("clarification_question") or "",
                },
                {"role": "user", "content": answer},
            ]
        )
        user_answers = [
            item["content"] for item in history if item.get("role") == "user"
        ]
        effective_question = state["question"]
        if user_answers:
            effective_question += "\n用户补充信息：" + "；".join(user_answers)
        return {
            "effective_question": effective_question,
            "conversation_history": history,
            "clarification_count": state.get("clarification_count", 0) + 1,
            "requires_clarification": False,
            "clarification_question": None,
            "clarification_options": [],
            "status": "completed",
            "semantic_context": "",
            "matched_metrics": [],
            "matched_dimensions": [],
        }

    async def generate_sql(self, state: TextToSQLGraphState) -> dict:
        messages = build_text_to_sql_messages(
            state["effective_question"],
            state["schema_context"],
            state.get("semantic_context", ""),
        )
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
            state["effective_question"],
            state["schema_context"],
            state["sql"],
            state.get("semantic_context", ""),
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
            "status": "completed",
        }

    async def analyze_result(self, state: TextToSQLGraphState) -> dict:
        profile = self.result_analyzer.build_profile(
            state.get("columns", []),
            state.get("rows", []),
            truncated=state.get("truncated", False),
        )
        chart = self.result_analyzer.recommend_chart(
            state.get("columns", []),
            state.get("rows", []),
        )
        if not self.enable_result_analysis:
            return {
                "result_summary": self.result_analyzer.fallback_summary(
                    state.get("row_count", 0)
                ),
                "insights": [],
                "chart": chart,
                "data_profile": profile,
                "result_analysis_error": None,
            }

        started_at = perf_counter()
        try:
            narrative = await self.result_analyzer.analyze_narrative(
                question=state["effective_question"],
                sql=state["sql"],
                columns=state.get("columns", []),
                rows=state.get("rows", []),
                profile=profile,
            )
        except (
            LLMConfigurationError,
            LLMResponseError,
            ValueError,
            TypeError,
        ) as exc:
            return {
                "result_summary": self.result_analyzer.fallback_summary(
                    state.get("row_count", 0)
                ),
                "insights": [],
                "chart": chart,
                "data_profile": profile,
                "result_analysis_error": str(exc),
                "result_analysis_llm_ms": self._elapsed_ms(started_at),
            }
        return {
            "result_summary": narrative.summary,
            "insights": narrative.insights,
            "chart": chart,
            "data_profile": profile,
            "result_analysis_error": None,
            "result_analysis_llm_ms": self._elapsed_ms(started_at),
        }

    async def assess_risk(self, state: TextToSQLGraphState) -> dict:
        assessment = self.risk_assessor.assess(
            state["sql"],
            dialect=self.service.target_engine.dialect.name,
        )
        requires_confirmation = assessment.requires_confirmation and not bool(
            state.get("confirmed")
        )
        return {
            "risk_level": assessment.level,
            "risk_reasons": assessment.reasons,
            "requires_confirmation": requires_confirmation,
        }

    async def human_approval(self, state: TextToSQLGraphState) -> dict:
        decision = interrupt(
            {
                "request_id": state["request_id"],
                "question": state["question"],
                "sql": state["sql"],
                "risk_level": state["risk_level"],
                "risk_reasons": state["risk_reasons"],
                "message": "该SQL风险较高，请确认是否执行。",
            }
        )
        if not isinstance(decision, dict) or not isinstance(decision.get("approved"), bool):
            raise TypeError("人工确认结果必须包含布尔类型的 approved 字段。")

        approved = decision["approved"]
        updates: dict = {
            "confirmed": approved,
            "status": "completed" if approved else "rejected",
            "requires_confirmation": False,
        }
        edited_sql = decision.get("edited_sql")
        if approved and edited_sql:
            sql = str(edited_sql).strip()
            self.service._validate_readonly_sql(sql)
            self.service.permission_policy.validate(sql)
            updates["sql"] = sql
        return updates

    async def reject_query(self, state: TextToSQLGraphState) -> dict:
        return {
            "status": "rejected",
            "requires_confirmation": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
        }

    async def repair_sql(self, state: TextToSQLGraphState) -> dict:
        messages = build_sql_repair_messages(
            question=state["effective_question"],
            schema_context=state["schema_context"],
            failed_sql=state["sql"],
            database_error=state["execution_error"] or "未知数据库错误",
            semantic_context=state.get("semantic_context", ""),
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
            "confirmed": None,
        }

    async def raise_execution_error(self, state: TextToSQLGraphState) -> dict:
        raise SQLExecutionError(
            state.get("execution_error") or "未知数据库错误",
            state.get("sql_execution_ms", 0.0),
        )

    def route_after_generation(self, state: TextToSQLGraphState) -> Literal["review", "execute"]:
        return "review" if self.service.enable_sql_review else "execute"

    def route_after_question_analysis(
        self, state: TextToSQLGraphState
    ) -> Literal["clarify", "generate"]:
        return "clarify" if state.get("requires_clarification") else "generate"

    def route_after_execution(self, state: TextToSQLGraphState) -> Literal[
        "success", "repair", "failed"
    ]:
        if state.get("execution_error") is None:
            return "success"
        if state.get("repair_attempts", 0) < self.service.max_repair_attempts:
            return "repair"
        return "failed"

    def route_after_risk(self, state: TextToSQLGraphState) -> Literal["approval", "execute"]:
        return "approval" if state.get("requires_confirmation") else "execute"

    def route_after_approval(self, state: TextToSQLGraphState) -> Literal[
        "execute", "rejected"
    ]:
        return "execute" if state.get("confirmed") else "rejected"

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)
