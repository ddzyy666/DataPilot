# DataPilot 5 分钟面试演示脚本

## 演示前检查

```powershell
docker compose up -d --build
docker compose ps
```

确认以下页面可访问：

- 工作台：http://localhost:8080
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

如果本机尚未完成 Docker 联调，使用 Conda 和 Vite 启动，不要在面试现场临时排查镜像问题。

## 0:00–0:30 项目定位

> DataPilot 是一个面向业务人员的 Text-to-SQL Agent。它不是只让模型生成 SQL，而是加入业务语义、
> 安全审核、人工确认、失败修复、结果分析和自动评测，形成完整的数据分析闭环。

## 0:30–1:00 单指标查询

输入：

```text
一共有多少订单？
```

展示指标卡、生成 SQL、命中的 `order_count` 语义指标，以及 LLM、SQL 和请求总耗时。

## 1:00–1:40 分类与趋势图

```text
按订单状态统计订单数量。
按月份统计订单数量，月份字段命名为 order_month。
```

展示系统如何根据分类字段选择柱状图，根据时间字段选择折线图。

## 1:40–2:30 业务语义层

```text
各地区的销售额是多少？
```

说明销售额不是简单字段名：只统计 `paid` 订单，使用
`order_items.quantity * order_items.unit_price`，并通过客户关联地区。

## 2:30–3:10 多轮澄清

```text
销量最好的产品是什么？
```

如果系统发起澄清，选择“按照销售金额”或“按照销售件数”。展示 LangGraph interrupt、request_id 和
checkpoint 恢复，而不是重新发起一个无状态请求。

## 3:10–4:00 人工确认

```text
按地区和商品分类统计销售额，并计算每个地区内的分类排名。
```

展示风险等级、Agent 暂停、SQL 查看或修改、批准或拒绝，以及修改后的 SQL 重新校验。
模型输出有随机性；如果没有触发高风险，直接通过 API 文档和代码展示确认接口，不要现场反复尝试。

## 4:00–4:30 查询结果分析

展示中文总结、关键洞察、数值画像和图表推荐。强调数值画像由程序计算，模型不负责凭空计算核心数字。

## 4:30–5:00 工程化证据

```powershell
python -m pytest -q
datapilot-benchmark --gold-only
```

> 项目当前有 56 个自动化测试和 50 条结果级评测问题，最佳准确率 92%。我保留失败样例做回归，
> 下一步会补充真实 PostgreSQL 数据源、RBAC 和线上可观测性。

## 演示失败时的降级方案

- 模型超时：展示审计错误、重试配置和已有 benchmark 报告。
- 前端图表异常：展示结果表和 API JSON，说明图表层是可降级消费者。
- Docker 未启动：提前准备 Conda 后端和 Vite 前端两个终端。
- SQL 没触发审批：展示 LangGraph 测试用例、风险规则和确认 API。
