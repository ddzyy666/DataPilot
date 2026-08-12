import json
from typing import Any

from app.knowledge.business_rules import BUSINESS_RULES

QUESTION_ANALYSIS_SYSTEM_PROMPT = """你是 DataPilot 的数据分析问题完整性检查器。
判断用户问题是否已经包含生成 SQL 所必需的信息。

只有当不同理解会实质改变查询指标、分组维度、必要筛选条件或结果范围，且无法从业务规则和数据库结构确定时，才要求澄清。
不要因为用户没有提供可选条件而追问，例如没有指定时间范围时，通常应理解为全部时间。
不要追问数据库中不存在、也不影响 SQL 生成的信息。

只返回 JSON，不要返回 Markdown：
{
  "is_complete": true,
  "clarification_question": null,
  "missing_information": [],
  "options": []
}

如果必须澄清，is_complete 设为 false，每次只提出一个最关键的问题，并最多提供 4 个简短选项。
"""

RESULT_ANALYSIS_SYSTEM_PROMPT = """你是 DataPilot 的查询结果解读器。
根据用户问题、SQL、程序计算的数据画像和结果样本，生成简洁的中文结论。

要求：
1. 只能引用输入中明确存在的数据，不得编造原因、趋势或业务背景。
2. 数值以程序给出的 numeric_summary 和结果样本为准，不要自行重新计算。
3. 如果结果被截断，必须提醒结论只基于当前返回数据。
4. summary 用一到两句话回答用户问题。
5. insights 最多返回三条；没有可靠洞察时返回空数组。
6. 只返回 JSON，不要返回 Markdown。

JSON 格式：
{
  "summary": "查询结果总结",
  "insights": ["关键发现1", "关键发现2"]
}
"""

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


def _context(question: str, schema_context: str, semantic_context: str = "") -> str:
    return (
        f"业务规则如下：\n{BUSINESS_RULES}\n\n"
        f"业务语义层如下：\n{semantic_context or '未提供专用语义定义。'}\n\n"
        f"数据库结构如下：\n{schema_context}\n\n"
        f"用户问题：{question}"
    )


def build_text_to_sql_messages(
    question: str,
    schema_context: str,
    semantic_context: str = "",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TEXT_TO_SQL_SYSTEM_PROMPT},
        {"role": "user", "content": _context(question, schema_context, semantic_context)},
    ]


def build_question_analysis_messages(
    question: str,
    schema_context: str,
    conversation_history: list[dict[str, str]],
    semantic_context: str = "",
) -> list[dict[str, str]]:
    history = "\n".join(
        f"{item['role']}：{item['content']}" for item in conversation_history
    ) or "无"
    return [
        {"role": "system", "content": QUESTION_ANALYSIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{_context(question, schema_context, semantic_context)}\n\n"
                f"此前的澄清记录：\n{history}"
            ),
        },
    ]


def build_result_analysis_messages(
    *,
    question: str,
    sql: str,
    profile: dict[str, Any],
    sample_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": RESULT_ANALYSIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"已执行SQL：\n{sql}\n\n"
                "程序计算的数据画像：\n"
                f"{json.dumps(profile, ensure_ascii=False, default=str)}\n\n"
                "查询结果样本：\n"
                f"{json.dumps(sample_rows, ensure_ascii=False, default=str)}"
            ),
        },
    ]


def build_sql_repair_messages(
    question: str,
    schema_context: str,
    failed_sql: str,
    database_error: str,
    semantic_context: str = "",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TEXT_TO_SQL_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{_context(question, schema_context, semantic_context)}\n\n"
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
    semantic_context: str = "",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SQL_REVIEW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{_context(question, schema_context, semantic_context)}\n\n"
                f"待审核 SQL：\n{candidate_sql}"
            ),
        },
    ]
