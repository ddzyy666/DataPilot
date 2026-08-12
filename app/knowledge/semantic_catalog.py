from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    name: str
    description: str
    aliases: tuple[str, ...]
    expression: str
    required_tables: tuple[str, ...]
    default_filters: tuple[str, ...] = ()
    time_field: str | None = None
    output_name: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DimensionDefinition:
    key: str
    name: str
    description: str
    aliases: tuple[str, ...]
    expression: str
    required_tables: tuple[str, ...]
    group_by: str | None = None
    output_name: str | None = None


METRICS = (
    MetricDefinition(
        key="sales_amount",
        name="销售额",
        description="已支付订单的商品成交总金额",
        aliases=("已支付销售额", "销售额", "成交额", "营收", "收入", "消费金额"),
        expression="ROUND(SUM(order_items.quantity * order_items.unit_price), 2)",
        required_tables=("orders", "order_items"),
        default_filters=("orders.status = 'paid'",),
        time_field="orders.created_at",
        output_name="sales_amount",
        notes=("必须使用订单明细成交单价 unit_price，不能使用 products.price。",),
    ),
    MetricDefinition(
        key="sales_quantity",
        name="商品销量",
        description="已支付订单实际售出的商品件数",
        aliases=("商品销量", "销售数量", "销售件数", "销量"),
        expression="SUM(order_items.quantity)",
        required_tables=("orders", "order_items"),
        default_filters=("orders.status = 'paid'",),
        time_field="orders.created_at",
        output_name="quantity_sold",
        notes=("销量不是订单数，也不是订单明细行数。",),
    ),
    MetricDefinition(
        key="order_count",
        name="订单数量",
        description="订单记录数量",
        aliases=("订单总数", "订单数量", "多少订单", "多少笔订单", "订单数"),
        expression="COUNT(DISTINCT orders.id)",
        required_tables=("orders",),
        time_field="orders.created_at",
        output_name="order_count",
        notes=("关联订单明细后必须使用 DISTINCT，避免一笔订单被重复计数。",),
    ),
    MetricDefinition(
        key="paid_order_count",
        name="已支付订单数",
        description="业务状态为 paid 的订单数量",
        aliases=("已支付订单数量", "已支付订单数", "已支付订单", "支付订单数"),
        expression="COUNT(DISTINCT orders.id)",
        required_tables=("orders",),
        default_filters=("orders.status = 'paid'",),
        time_field="orders.created_at",
        output_name="paid_order_count",
    ),
    MetricDefinition(
        key="customer_count",
        name="客户数",
        description="去重后的客户数量",
        aliases=("客户数量", "客户总数", "多少名客户", "客户数", "用户数"),
        expression="COUNT(DISTINCT customers.id)",
        required_tables=("customers",),
        time_field="customers.created_at",
        output_name="customer_count",
    ),
    MetricDefinition(
        key="product_count",
        name="商品种类数",
        description="products 表中的 SKU 数量",
        aliases=("商品种类数", "商品数量", "多少种商品", "SKU数量", "SKU数"),
        expression="COUNT(DISTINCT products.id)",
        required_tables=("products",),
        output_name="product_count",
        notes=("只有明确提到商品分类时才统计 categories。",),
    ),
    MetricDefinition(
        key="payment_rate",
        name="支付成功率",
        description="已支付订单占全部订单的百分比",
        aliases=("支付成功率", "支付率", "订单支付率"),
        expression=(
            "ROUND(100.0 * SUM(CASE WHEN orders.status = 'paid' THEN 1 ELSE 0 END) "
            "/ COUNT(orders.id), 2)"
        ),
        required_tables=("orders",),
        time_field="orders.created_at",
        output_name="payment_rate",
    ),
    MetricDefinition(
        key="cancellation_rate",
        name="订单取消率",
        description="已取消订单占全部订单的百分比",
        aliases=("订单取消率", "取消率"),
        expression=(
            "ROUND(100.0 * SUM(CASE WHEN orders.status = 'cancelled' THEN 1 ELSE 0 END) "
            "/ COUNT(orders.id), 2)"
        ),
        required_tables=("orders",),
        time_field="orders.created_at",
        output_name="cancellation_rate",
    ),
    MetricDefinition(
        key="average_order_amount",
        name="平均订单金额",
        description="先按已支付订单汇总金额，再计算订单金额平均值",
        aliases=("平均订单金额", "客单价", "订单平均金额"),
        expression="ROUND(AVG(order_total), 2)",
        required_tables=("orders", "order_items"),
        default_filters=("orders.status = 'paid'",),
        time_field="orders.created_at",
        output_name="avg_order_amount",
        notes=("必须先按 orders.id 汇总 order_total，再在外层计算 AVG。",),
    ),
    MetricDefinition(
        key="average_payment_hours",
        name="平均支付耗时",
        description="订单从创建到支付的平均小时数",
        aliases=("平均支付耗时", "支付平均耗时", "平均需要多少小时"),
        expression=(
            "ROUND(AVG((julianday(orders.paid_at) - "
            "julianday(orders.created_at)) * 24), 2)"
        ),
        required_tables=("orders",),
        default_filters=("orders.status = 'paid'", "orders.paid_at IS NOT NULL"),
        time_field="orders.created_at",
        output_name="avg_payment_hours",
    ),
)


DIMENSIONS = (
    DimensionDefinition(
        key="region",
        name="地区",
        description="客户所属地区",
        aliases=("地区", "区域"),
        expression="regions.name",
        required_tables=("regions", "customers"),
        group_by="regions.id, regions.name",
        output_name="region_name",
    ),
    DimensionDefinition(
        key="category",
        name="商品分类",
        description="商品所属分类",
        aliases=("商品分类", "产品分类", "品类", "分类"),
        expression="categories.name",
        required_tables=("categories", "products"),
        group_by="categories.id, categories.name",
        output_name="category_name",
    ),
    DimensionDefinition(
        key="product",
        name="商品",
        description="具体 SKU 商品",
        aliases=("每种商品", "各商品", "按商品", "商品排名", "商品名称"),
        expression="products.name",
        required_tables=("products",),
        group_by="products.id, products.name",
        output_name="product_name",
    ),
    DimensionDefinition(
        key="customer",
        name="客户",
        description="具体客户",
        aliases=("每名客户", "各客户", "按客户", "客户排名", "客户名称"),
        expression="customers.name",
        required_tables=("customers",),
        group_by="customers.id, customers.name",
        output_name="customer_name",
    ),
    DimensionDefinition(
        key="order_status",
        name="订单状态",
        description="paid、cancelled 或 pending",
        aliases=("订单状态", "各种状态", "各状态", "状态"),
        expression="orders.status",
        required_tables=("orders",),
        group_by="orders.status",
        output_name="status",
    ),
    DimensionDefinition(
        key="order_month",
        name="订单月份",
        description="按订单创建时间划分的自然月",
        aliases=("按月份", "每月", "月度", "月份"),
        expression="strftime('%Y-%m', orders.created_at)",
        required_tables=("orders",),
        group_by="strftime('%Y-%m', orders.created_at)",
        output_name="order_month",
    ),
    DimensionDefinition(
        key="order_year",
        name="订单年份",
        description="按订单创建时间划分的年份",
        aliases=("按年份", "每年", "年度", "年份"),
        expression="strftime('%Y', orders.created_at)",
        required_tables=("orders",),
        group_by="strftime('%Y', orders.created_at)",
        output_name="order_year",
    ),
    DimensionDefinition(
        key="order_date",
        name="订单日期",
        description="按订单创建时间划分的自然日",
        aliases=("按日期", "每日", "每天", "日期"),
        expression="date(orders.created_at)",
        required_tables=("orders",),
        group_by="date(orders.created_at)",
        output_name="order_date",
    ),
)


JOIN_RELATIONSHIPS = (
    "customers.region_id = regions.id",
    "orders.customer_id = customers.id",
    "order_items.order_id = orders.id",
    "order_items.product_id = products.id",
    "products.category_id = categories.id",
)
