import asyncio
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from sqlalchemy import Engine

from app.agent.nodes import TextToSQLGraphNodes
from app.agent.state import TextToSQLGraphState
from app.core.config import settings
from app.db.base import engine
from app.llm.client import OpenAICompatibleClient
from app.schemas.query import QueryResponse, StageTimings
from app.services.sql_risk import SQLRiskAssessor
from app.services.text_to_sql import TextToSQLService


class LangGraphTextToSQLService:
    def __init__(
        self,
        llm_client: OpenAICompatibleClient | None = None,
        target_engine: Engine = engine,
        enable_sql_review: bool | None = None,
        checkpoint_path: str | None = None,
    ) -> None:
        service_kwargs: dict[str, Any] = {
            "llm_client": llm_client,
            "target_engine": target_engine,
        }
        if enable_sql_review is not None:
            service_kwargs["enable_sql_review"] = enable_sql_review
        self.service = TextToSQLService(**service_kwargs)
        self.risk_assessor = SQLRiskAssessor(
            settings.query_require_confirmation_for_high_risk
        )
        self.nodes = TextToSQLGraphNodes(self.service, self.risk_assessor)
        self.checkpoint_path = checkpoint_path
        self._checkpoint_connection: aiosqlite.Connection | None = None
        self._graph: Any | None = None
        self._initialization_lock = asyncio.Lock()

        if checkpoint_path is None:
            self._graph = self._build_graph(InMemorySaver())

    @property
    def graph(self):
        if self._graph is None:
            raise RuntimeError("LangGraph尚未完成异步初始化。")
        return self._graph

    async def _ensure_graph(self):
        if self._graph is not None:
            return self._graph
        async with self._initialization_lock:
            if self._graph is None:
                checkpoint_path = Path(self.checkpoint_path or settings.checkpoint_database_path)
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                self._checkpoint_connection = await aiosqlite.connect(str(checkpoint_path))
                checkpointer = AsyncSqliteSaver(self._checkpoint_connection)
                self._graph = self._build_graph(checkpointer)
        return self._graph

    def _build_graph(self, checkpointer):
        builder = StateGraph(TextToSQLGraphState)
        builder.add_node("load_schema", self.nodes.load_schema)
        builder.add_node("generate_sql", self.nodes.generate_sql)
        builder.add_node("review_sql", self.nodes.review_sql)
        builder.add_node("assess_risk", self.nodes.assess_risk)
        builder.add_node("human_approval", self.nodes.human_approval)
        builder.add_node("reject_query", self.nodes.reject_query)
        builder.add_node("execute_sql", self.nodes.execute_sql)
        builder.add_node("repair_sql", self.nodes.repair_sql)
        builder.add_node("raise_execution_error", self.nodes.raise_execution_error)

        builder.add_edge(START, "load_schema")
        builder.add_edge("load_schema", "generate_sql")
        builder.add_conditional_edges(
            "generate_sql",
            self.nodes.route_after_generation,
            {"review": "review_sql", "execute": "assess_risk"},
        )
        builder.add_edge("review_sql", "assess_risk")
        builder.add_conditional_edges(
            "assess_risk",
            self.nodes.route_after_risk,
            {"approval": "human_approval", "execute": "execute_sql"},
        )
        builder.add_conditional_edges(
            "human_approval",
            self.nodes.route_after_approval,
            {"execute": "execute_sql", "rejected": "reject_query"},
        )
        builder.add_edge("reject_query", END)
        builder.add_conditional_edges(
            "execute_sql",
            self.nodes.route_after_execution,
            {
                "success": END,
                "repair": "repair_sql",
                "failed": "raise_execution_error",
            },
        )
        builder.add_edge("repair_sql", "assess_risk")
        builder.add_edge("raise_execution_error", END)
        return builder.compile(checkpointer=checkpointer)

    async def generate(self, question: str, request_id: str | None = None) -> QueryResponse:
        graph = await self._ensure_graph()
        thread_id = request_id or str(uuid4())
        started_at = perf_counter()
        state = await graph.ainvoke(
            {
                "request_id": thread_id,
                "question": question,
                "repair_attempts": 0,
                "reviewed": False,
                "review_passed": None,
                "review_issues": [],
                "review_checks": {},
                "was_review_corrected": False,
                "confirmed": None,
                "status": "completed",
                "risk_level": "low",
                "risk_reasons": [],
                "requires_confirmation": False,
                "generation_llm_ms": 0.0,
                "review_llm_ms": 0.0,
                "repair_llm_ms": 0.0,
                "sql_execution_ms": 0.0,
            },
            config=self._thread_config(thread_id),
        )
        return self._to_response(state, started_at)

    async def resume(
        self,
        request_id: str,
        *,
        approved: bool,
        edited_sql: str | None = None,
    ) -> QueryResponse:
        graph = await self._ensure_graph()
        snapshot = await graph.aget_state(self._thread_config(request_id))
        if not snapshot.values or "human_approval" not in snapshot.next:
            raise ValueError("没有找到等待人工确认的查询，或该查询已经处理。")
        started_at = perf_counter()
        state = await graph.ainvoke(
            Command(resume={"approved": approved, "edited_sql": edited_sql}),
            config=self._thread_config(request_id),
        )
        return self._to_response(state, started_at)

    async def close(self) -> None:
        if self._checkpoint_connection is not None:
            await self._checkpoint_connection.close()
            self._checkpoint_connection = None
            self._graph = None

    @staticmethod
    def _thread_config(request_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": request_id}}

    def _to_response(self, state: dict[str, Any], started_at: float) -> QueryResponse:
        interrupted = bool(state.get("__interrupt__"))
        status = "waiting_for_confirmation" if interrupted else state.get("status", "completed")
        total_ms = round((perf_counter() - started_at) * 1000, 2)
        llm_total_ms = round(
            state.get("generation_llm_ms", 0.0)
            + state.get("review_llm_ms", 0.0)
            + state.get("repair_llm_ms", 0.0),
            2,
        )
        schema_ms = state.get("schema_processing_ms", 0.0)
        sql_ms = state.get("sql_execution_ms", 0.0)
        other_ms = round(max(0.0, total_ms - llm_total_ms - schema_ms - sql_ms), 2)

        return QueryResponse(
            request_id=state.get("request_id", ""),
            status=status,
            risk_level=state.get("risk_level", "low"),
            risk_reasons=state.get("risk_reasons", []),
            requires_confirmation=interrupted,
            question=state.get("question", ""),
            sql=state.get("sql", ""),
            explanation=state.get("explanation", ""),
            assumptions=state.get("assumptions", []),
            schema_context=state.get("schema_context", ""),
            columns=state.get("columns", []),
            rows=state.get("rows", []),
            row_count=state.get("row_count", 0),
            truncated=state.get("truncated", False),
            execution_time_ms=sql_ms,
            was_repaired=state.get("repair_attempts", 0) > 0,
            repair_attempts=state.get("repair_attempts", 0),
            reviewed=state.get("reviewed", False),
            review_passed=state.get("review_passed"),
            review_issues=state.get("review_issues", []),
            review_checks=state.get("review_checks", {}),
            was_review_corrected=state.get("was_review_corrected", False),
            timings=StageTimings(
                schema_processing_ms=schema_ms,
                llm_total_ms=llm_total_ms,
                sql_execution_ms=sql_ms,
                other_processing_ms=other_ms,
                total_ms=total_ms,
            ),
        )
