import json
import re
from typing import Any

from sqlalchemy import Engine

from app.db.base import engine
from app.db.metadata import inspect_schema
from app.llm.client import OpenAICompatibleClient
from app.llm.prompts import build_text_to_sql_messages
from app.schemas.query import QueryResponse
from app.services.schema_formatter import format_schema_for_prompt


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

    async def generate(self, question: str) -> QueryResponse:
        schema = inspect_schema(self.target_engine)
        schema_context = format_schema_for_prompt(schema)
        messages = build_text_to_sql_messages(question, schema_context)
        raw_content = await self.llm_client.complete(messages)
        payload = self._parse_model_json(raw_content)

        sql = str(payload.get("sql", "")).strip()
        self._validate_readonly_sql(sql)

        assumptions = payload.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]

        return QueryResponse(
            question=question,
            sql=sql,
            explanation=str(payload.get("explanation", "")).strip(),
            assumptions=[str(item) for item in assumptions],
            schema_context=schema_context,
        )

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
