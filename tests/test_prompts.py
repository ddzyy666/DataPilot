from app.llm.prompts import (
    build_sql_repair_messages,
    build_sql_review_messages,
    build_text_to_sql_messages,
)


def test_business_rules_are_injected_into_all_llm_prompts() -> None:
    generation = build_text_to_sql_messages("统计销售额", "表: orders")
    review = build_sql_review_messages("统计销售额", "表: orders", "SELECT 1")
    repair = build_sql_repair_messages(
        "统计销售额",
        "表: orders",
        "SELECT missing FROM orders",
        "no such column",
    )

    for messages in (generation, review, repair):
        assert "销售额 = SUM(order_items.quantity * order_items.unit_price)" in messages[1][
            "content"
        ]
        assert "orders.status = 'paid'" in messages[1]["content"]
