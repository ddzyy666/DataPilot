from app.services.semantic_layer import SemanticLayer


def test_sales_amount_by_region_matches_metric_dimension_and_join_path() -> None:
    layer = SemanticLayer()

    match = layer.match("统计2025年每个地区的已支付销售额")

    assert match.metric_keys == ["sales_amount"]
    assert match.dimension_keys == ["region"]
    assert "orders.customer_id = customers.id" in match.join_relationships
    assert "customers.region_id = regions.id" in match.join_relationships


def test_paid_order_count_shadows_generic_order_count() -> None:
    layer = SemanticLayer()

    match = layer.match("已支付订单一共有多少笔？")

    assert match.metric_keys == ["paid_order_count"]


def test_sales_quantity_is_not_confused_with_order_count() -> None:
    layer = SemanticLayer()

    match = layer.match("统计每种商品在已支付订单中的销量")

    assert match.metric_keys == ["sales_quantity"]
    assert match.dimension_keys == ["product"]


def test_monthly_order_count_matches_time_dimension() -> None:
    layer = SemanticLayer()

    match = layer.match("按月份统计订单数量")

    assert match.metric_keys == ["order_count"]
    assert match.dimension_keys == ["order_month"]


def test_semantic_prompt_contains_business_formula_and_default_filter() -> None:
    layer = SemanticLayer()
    match = layer.match("统计各地区销售额")

    context = layer.format_for_prompt(match)

    assert "SUM(order_items.quantity * order_items.unit_price)" in context
    assert "orders.status = 'paid'" in context
    assert "regions.name" in context
