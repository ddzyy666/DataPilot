from app.llm.client import OpenAICompatibleClient
from app.services.result_analyzer import ResultAnalyzer


def test_result_profile_calculates_numeric_facts_in_code() -> None:
    analyzer = ResultAnalyzer(OpenAICompatibleClient())

    profile = analyzer.build_profile(
        ["region", "sales_amount"],
        [
            {"region": "华东", "sales_amount": 120.5},
            {"region": "华南", "sales_amount": 79.5},
        ],
        truncated=False,
    )

    assert profile["numeric_summary"]["sales_amount"] == {
        "min": 79.5,
        "max": 120.5,
        "sum": 200.0,
        "average": 100.0,
    }


def test_chart_recommendation_uses_line_chart_for_time_dimension() -> None:
    analyzer = ResultAnalyzer(OpenAICompatibleClient())

    chart = analyzer.recommend_chart(
        ["order_month", "sales_amount"],
        [
            {"order_month": "2026-01", "sales_amount": 100},
            {"order_month": "2026-02", "sales_amount": 120},
        ],
    )

    assert chart is not None
    assert chart["type"] == "line"
    assert chart["x_field"] == "order_month"
    assert chart["y_fields"] == ["sales_amount"]


def test_chart_recommendation_uses_bar_chart_for_category_dimension() -> None:
    analyzer = ResultAnalyzer(OpenAICompatibleClient())

    chart = analyzer.recommend_chart(
        ["region", "sales_amount"],
        [
            {"region": "华东", "sales_amount": 100},
            {"region": "华南", "sales_amount": 120},
        ],
    )

    assert chart is not None
    assert chart["type"] == "bar"
