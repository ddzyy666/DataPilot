from dataclasses import asdict, dataclass
from typing import Any

from app.knowledge.semantic_catalog import (
    DIMENSIONS,
    JOIN_RELATIONSHIPS,
    METRICS,
    DimensionDefinition,
    MetricDefinition,
)


@dataclass(slots=True)
class SemanticMatch:
    metrics: list[MetricDefinition]
    dimensions: list[DimensionDefinition]
    join_relationships: list[str]

    @property
    def metric_keys(self) -> list[str]:
        return [metric.key for metric in self.metrics]

    @property
    def dimension_keys(self) -> list[str]:
        return [dimension.key for dimension in self.dimensions]

    def as_dict(self) -> dict[str, Any]:
        return {
            "metrics": [asdict(metric) for metric in self.metrics],
            "dimensions": [asdict(dimension) for dimension in self.dimensions],
            "join_relationships": self.join_relationships,
        }


class SemanticLayer:
    def match(self, question: str) -> SemanticMatch:
        normalized = question.casefold().replace(" ", "")
        metrics = [
            definition
            for definition in METRICS
            if self._matches_metric(normalized, definition)
        ]
        dimensions = [
            definition
            for definition in DIMENSIONS
            if self._matches_alias(normalized, definition.aliases)
        ]

        metrics = self._remove_shadowed_metrics(metrics)
        required_tables = {
            table
            for definition in [*metrics, *dimensions]
            for table in definition.required_tables
        }
        joins = [
            relationship
            for relationship in JOIN_RELATIONSHIPS
            if self._relationship_is_relevant(relationship, required_tables)
        ]
        return SemanticMatch(metrics=metrics, dimensions=dimensions, join_relationships=joins)

    def format_for_prompt(self, match: SemanticMatch) -> str:
        if not match.metrics and not match.dimensions:
            return "未匹配到专用业务指标或维度，请依据全局业务规则与 Schema 生成查询。"

        lines = ["本次问题命中的业务语义定义（优先级高于模型推测）："]
        for metric in match.metrics:
            lines.extend(
                [
                    f"指标 [{metric.key}] {metric.name}：{metric.description}",
                    f"- 标准表达式: {metric.expression}",
                    f"- 涉及表: {', '.join(metric.required_tables)}",
                    f"- 建议输出别名: {metric.output_name or metric.key}",
                ]
            )
            if metric.default_filters:
                lines.append(f"- 默认筛选: {' AND '.join(metric.default_filters)}")
            if metric.time_field:
                lines.append(f"- 默认时间字段: {metric.time_field}")
            lines.extend(f"- 注意: {note}" for note in metric.notes)

        for dimension in match.dimensions:
            lines.extend(
                [
                    f"维度 [{dimension.key}] {dimension.name}：{dimension.description}",
                    f"- 标准字段: {dimension.expression}",
                    f"- 分组表达式: {dimension.group_by or dimension.expression}",
                    f"- 建议输出别名: {dimension.output_name or dimension.key}",
                ]
            )
        if match.join_relationships:
            lines.append("相关 JOIN 关系：")
            lines.extend(f"- {relationship}" for relationship in match.join_relationships)
        return "\n".join(lines)

    @staticmethod
    def _matches_alias(question: str, aliases: tuple[str, ...]) -> bool:
        return any(alias.casefold().replace(" ", "") in question for alias in aliases)

    @classmethod
    def _matches_metric(
        cls,
        question: str,
        definition: MetricDefinition,
    ) -> bool:
        if not cls._matches_alias(question, definition.aliases):
            return False
        if definition.key == "paid_order_count":
            return any(token in question for token in ("多少", "数量", "订单数", "总数", "几笔"))
        return True

    @staticmethod
    def _remove_shadowed_metrics(
        metrics: list[MetricDefinition],
    ) -> list[MetricDefinition]:
        keys = {metric.key for metric in metrics}
        if "paid_order_count" in keys:
            return [metric for metric in metrics if metric.key != "order_count"]
        return metrics

    @staticmethod
    def _relationship_is_relevant(
        relationship: str,
        required_tables: set[str],
    ) -> bool:
        left, right = relationship.split(" = ")
        return left.split(".")[0] in required_tables and right.split(".")[0] in required_tables
