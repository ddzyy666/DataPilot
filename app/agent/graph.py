from time import perf_counter

from langgraph.graph import END, START, StateGraph
from sqlalchemy import Engine

from app.agent.nodes import TextToSQLGraphNodes
from app.agent.state import TextToSQLGraphState
from app.db.base import engine
from app.llm.client import OpenAICompatibleClient
from app.schemas.query import QueryResponse, StageTimings
from app.services.text_to_sql import TextToSQLService


class LangGraphTextToSQLService:
    def __init__(
        self,
        llm_client: OpenAICompatibleClient | None = None,
        target_engine: Engine = engine,
        enable_sql_review: bool | None = None,
    ) -> None:
        service_kwargs = {
            "llm_client": llm_client,
            "target_engine": target_engine,
        }
        if enable_sql_review is not None:
            service_kwargs["enable_sql_review"] = enable_sql_review
        self.service = TextToSQLService(**service_kwargs)
        self.nodes = TextToSQLGraphNodes(self.service)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(TextToSQLGraphState)
        builder.add_node("load_schema", self.nodes.load_schema)
        builder.add_node("generate_sql", self.nodes.generate_sql)
        builder.add_node("review_sql", self.nodes.review_sql)
        builder.add_node("execute_sql", self.nodes.execute_sql)
        builder.add_node("repair_sql", self.nodes.repair_sql)
        builder.add_node("raise_execution_error", self.nodes.raise_execution_error)

        builder.add_edge(START, "load_schema")
        builder.add_edge("load_schema", "generate_sql")
        builder.add_conditional_edges(
            "generate_sql",
            self.nodes.route_after_generation,
            {"review": "review_sql", "execute": "execute_sql"},
        )
        builder.add_edge("review_sql", "execute_sql")
        builder.add_conditional_edges(
            "execute_sql",
            self.nodes.route_after_execution,
            {
                "success": END,
                "repair": "repair_sql",
                "failed": "raise_execution_error",
            },
        )
        builder.add_edge("repair_sql", "execute_sql")
        builder.add_edge("raise_execution_error", END)
        return builder.compile()

    async def generate(self, question: str) -> QueryResponse:
        started_at = perf_counter()
        state = await self.graph.ainvoke(
            {
                "question": question,
                "repair_attempts": 0,
                "reviewed": False,
                "review_passed": None,
                "review_issues": [],
                "review_checks": {},
                "was_review_corrected": False,
                "generation_llm_ms": 0.0,
                "review_llm_ms": 0.0,
                "repair_llm_ms": 0.0,
                "sql_execution_ms": 0.0,
            }
        )
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
            question=question,
            sql=state["sql"],
            explanation=state.get("explanation", ""),
            assumptions=state.get("assumptions", []),
            schema_context=state["schema_context"],
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
