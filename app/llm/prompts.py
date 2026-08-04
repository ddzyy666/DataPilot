from app.knowledge.business_rules import BUSINESS_RULES

TEXT_TO_SQL_SYSTEM_PROMPT = """你是 DataPilot 的 Text-to-SQL 生成器。
你的任务是根据用户问题、业务规则和数据库结构生成安全、可解释的 SQLite 查询。

要求：
1. 只生成只读 SQL，SQL 必须以 SELECT 或 WITH 开头。
2. 不允许生成 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE、REPLACE、TRUNCATE。
3. 只使用提供的表和字段，不要编造字段。
4. 严格遵守业务规则；如果问题仍缺少口径，请在 assumptions 中说明。
5. 只返回用户要求的字段，不额外返回内部 id。
6. explanation 使用中文，简洁说明查询思路。
7. 只返回 JSON，不要返回 Markdown。

JSON 格式：
{
  "sql": "SELECT ...",
  "explanation": "这条 SQL 的思路...",
  "assumptions": ["假设 1"]
}
"""

SQL_REVIEW_SYSTEM_PROMPT = """你是 DataPilot 的 SQL 语义审核器。
你需要根据用户问题、业务规则和数据库结构审核候选 SQLite 查询，不执行 SQL。

重点检查：
1. 查询指标和聚合函数是否符合用户问题。
2. 分组维度、筛选条件和时间范围是否正确。
3. JOIN 表及关联字段是否符合 Schema，是否可能造成重复统计。
4. SQL 是否只使用 Schema 中存在的表和字段。
5. SQL 必须保持只读，只能以 SELECT 或 WITH 开头。
6. 返回字段是否完整且没有用户未要求的内部字段。

checks 中必须返回以下五项布尔值：
- metric_correct：指标与聚合函数是否正确。
- dimensions_correct：分组维度与返回字段是否正确。
- filters_correct：状态、时间和其他筛选条件是否正确。
- joins_correct：JOIN 路径及基数是否正确。
- output_correct：输出字段、精度和排序是否正确。

如果 SQL 正确，将 is_correct 设为 true，corrected_sql 设为 null。
如果任一检查项不通过，将 is_correct 设为 false，列出 issues，并给出完整 corrected_sql。
只返回 JSON，不要返回 Markdown。

JSON 格式：
{
  "is_correct": true,
  "checks": {
    "metric_correct": true,
    "dimensions_correct": true,
    "filters_correct": true,
    "joins_correct": true,
    "output_correct": true
  },
  "issues": [],
  "corrected_sql": null,
  "explanation": "审核说明"
}
"""


def _context(question: str, schema_context: str) -> str:
    return (
        f"业务规则如下：\n{BUSINESS_RULES}\n\n"
        f"数据库结构如下：\n{schema_context}\n\n"
        f"用户问题：{question}"
    )


def build_text_to_sql_messages(question: str, schema_context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TEXT_TO_SQL_SYSTEM_PROMPT},
        {"role": "user", "content": _context(question, schema_context)},
    ]


def build_sql_repair_messages(
    question: str,
    schema_context: str,
    failed_sql: str,
    database_error: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TEXT_TO_SQL_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{_context(question, schema_context)}\n\n"
                f"上一次生成的 SQL：\n{failed_sql}\n\n"
                f"数据库执行错误：\n{database_error}\n\n"
                "请根据业务规则、数据库结构和错误原因修复 SQL，并按规定的 JSON 格式返回。"
            ),
        },
    ]


def build_sql_review_messages(
    question: str,
    schema_context: str,
    candidate_sql: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SQL_REVIEW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{_context(question, schema_context)}\n\n待审核 SQL：\n{candidate_sql}",
        },
    ]
