BUSINESS_RULES = """DataPilot 电商数据库业务口径：
1. “商品数量”“多少种商品”默认指 products 表中的 SKU 数量；只有明确说“商品分类”时才统计 categories。
2. 销售额 = SUM(order_items.quantity * order_items.unit_price)。
3. “已支付订单”必须使用 orders.status = 'paid'；不要用 paid_at IS NOT NULL 替代业务状态。
4. 订单按年、月、日统计时默认使用 orders.created_at；paid_at 只用于支付时间和支付耗时。
5. 支付耗时（小时）= (julianday(paid_at) - julianday(created_at)) * 24。
6. “按日期”必须使用 date(created_at) 分组，不能直接按完整时间戳分组。
7. 商品销量 = SUM(order_items.quantity)，不是订单明细行数。
8. 支付成功率 = paid 订单数 / 全部订单数 * 100。
9. 金额、平均值、比率默认使用 ROUND(..., 2) 保留两位小数。
10. 只返回用户要求的业务字段，不额外返回内部 id；用户要求名称时必须返回对应名称。
11. Top-N 必须使用确定性排序；主指标相同时增加名称或 id 作为第二排序字段。
12. 多表聚合前检查 JOIN 是否造成重复计数；计算平均订单金额时先按订单汇总，再求平均。
"""
