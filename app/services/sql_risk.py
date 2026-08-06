from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


@dataclass(slots=True)
class SQLRiskAssessment:
    level: str
    reasons: list[str]
    requires_confirmation: bool


class SQLRiskAssessor:
    def __init__(self, require_confirmation_for_high_risk: bool = True) -> None:
        self.require_confirmation_for_high_risk = require_confirmation_for_high_risk

    def assess(self, sql: str, dialect: str = "sqlite") -> SQLRiskAssessment:
        try:
            expression = parse_one(sql, read=dialect)
        except ParseError:
            return SQLRiskAssessment(
                level="high",
                reasons=["SQL无法解析"],
                requires_confirmation=self.require_confirmation_for_high_risk,
            )

        join_count = sum(1 for _ in expression.find_all(exp.Join))
        has_cte = any(True for _ in expression.find_all(exp.CTE))
        has_window = any(True for _ in expression.find_all(exp.Window))
        has_subquery = any(True for _ in expression.find_all(exp.Subquery))
        has_recursive = bool(
            expression.args.get("with_")
            and expression.args["with_"].args.get("recursive")
        )
        has_data_wildcard = any(
            not isinstance(star.parent, exp.Count) for star in expression.find_all(exp.Star)
        )

        reasons: list[str] = []
        if join_count:
            reasons.append(f"包含 {join_count} 个 JOIN")
        if has_cte:
            reasons.append("包含 CTE")
        if has_window:
            reasons.append("包含窗口函数")
        if has_subquery:
            reasons.append("包含子查询")
        if has_recursive:
            reasons.append("包含递归查询")
        if has_data_wildcard:
            reasons.append("包含数据通配符")

        high_risk = (
            has_recursive
            or has_window
            or join_count >= 3
            or (has_cte and join_count >= 2)
        )
        medium_risk = join_count > 0 or has_cte or has_subquery or has_data_wildcard
        level = "high" if high_risk else "medium" if medium_risk else "low"
        return SQLRiskAssessment(
            level=level,
            reasons=reasons,
            requires_confirmation=(
                level == "high" and self.require_confirmation_for_high_risk
            ),
        )
