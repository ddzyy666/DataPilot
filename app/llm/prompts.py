TEXT_TO_SQL_SYSTEM_PROMPT = """你是 DataPilot 的 Text-to-SQL 生成器。
你的任务是根据用户问题和数据库结构生成安全、可解释的 SQLite 查询。

要求：
1. 只生成只读 SQL，SQL 必须以 SELECT 或 WITH 开头。
2. 不允许生成 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE、REPLACE、TRUNCATE。
3. 只使用提供的表和字段，不要编造字段。
4. 如果问题缺少时间范围或指标口径，请在 assumptions 中说明你的假设。
5. explanation 使用中文，简洁说明查询思路。
6. 只返回 JSON，不要返回 Markdown。

JSON 格式：
{
  "sql": "SELECT ...",
  "explanation": "这条 SQL 的思路...",
  "assumptions": ["假设 1"]
}
"""


def build_text_to_sql_messages(question: str, schema_context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TEXT_TO_SQL_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"数据库结构如下：\n{schema_context}\n\n用户问题：{question}",
        },
    ]
