import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.llm.client import OpenAICompatibleClient
from app.llm.prompts import build_result_analysis_messages


@dataclass(slots=True)
class ResultNarrative:
    summary: str
    insights: list[str]


class ResultAnalyzer:
    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        max_rows_for_llm: int = 20,
    ) -> None:
        self.llm_client = llm_client
        self.max_rows_for_llm = max(1, max_rows_for_llm)

    def build_profile(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        *,
        truncated: bool,
    ) -> dict[str, Any]:
        numeric_columns = [
            column
            for column in columns
            if any(self._is_number(row.get(column)) for row in rows)
        ]
        numeric_summary: dict[str, dict[str, float]] = {}
        for column in numeric_columns:
            values = [
                float(row[column])
                for row in rows
                if self._is_number(row.get(column))
            ]
            if values:
                numeric_summary[column] = {
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "sum": round(sum(values), 4),
                    "average": round(sum(values) / len(values), 4),
                }
        return {
            "row_count": len(rows),
            "columns": columns,
            "numeric_summary": numeric_summary,
            "truncated": truncated,
        }

    def recommend_chart(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        numeric_columns = [
            column
            for column in columns
            if any(self._is_number(row.get(column)) for row in rows)
        ]
        if len(rows) == 1 and numeric_columns:
            return {
                "type": "metric",
                "title": "核心指标",
                "x_field": None,
                "y_fields": [numeric_columns[0]],
                "reason": "结果只有一行数值，适合使用指标卡展示。",
            }

        dimension_columns = [column for column in columns if column not in numeric_columns]
        if dimension_columns and numeric_columns:
            x_field = dimension_columns[0]
            chart_type = "line" if self._looks_temporal(x_field) else "bar"
            return {
                "type": chart_type,
                "title": "查询结果可视化",
                "x_field": x_field,
                "y_fields": numeric_columns[:3],
                "reason": (
                    "横轴字段具有时间特征，适合展示趋势。"
                    if chart_type == "line"
                    else "结果包含分类维度和数值指标，适合进行横向比较。"
                ),
            }

        return {
            "type": "table",
            "title": "查询结果",
            "x_field": None,
            "y_fields": [],
            "reason": "结果缺少明确的分类与数值组合，使用表格展示更准确。",
        }

    async def analyze_narrative(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> ResultNarrative:
        if not rows:
            return ResultNarrative(summary="查询成功，但没有返回符合条件的数据。", insights=[])

        messages = build_result_analysis_messages(
            question=question,
            sql=sql,
            profile=profile,
            sample_rows=rows[: self.max_rows_for_llm],
        )
        content = await self.llm_client.complete(messages)
        payload = self._parse_json(content)
        summary = str(payload.get("summary") or "").strip()
        insights = payload.get("insights", [])
        if not summary:
            raise ValueError("结果分析器没有返回 summary。")
        if not isinstance(insights, list):
            raise TypeError("结果分析器没有返回合法的 insights 字段。")
        return ResultNarrative(
            summary=summary,
            insights=[str(item) for item in insights[:3]],
        )

    @staticmethod
    def fallback_summary(row_count: int) -> str:
        return f"查询执行成功，共返回 {row_count} 行数据。"

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        normalized = content.strip()
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            start = normalized.find("{")
            end = normalized.rfind("}")
            if start == -1 or end == -1 or start >= end:
                raise ValueError("结果分析器没有返回合法 JSON。") from None
            try:
                payload = json.loads(normalized[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError("结果分析器没有返回合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise TypeError("结果分析器的 JSON 响应必须是对象。")
        return payload

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    @staticmethod
    def _looks_temporal(column: str) -> bool:
        normalized = column.lower()
        return any(
            token in normalized
            for token in ("date", "time", "year", "month", "day", "日期", "时间", "年", "月")
        )
