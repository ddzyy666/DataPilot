from typing import Any


def format_schema_for_prompt(schema: dict[str, Any]) -> str:
    lines = [
        f"数据库方言: {schema['dialect']}",
        f"数据表数量: {schema['table_count']}",
    ]

    for table in schema["tables"]:
        lines.append("")
        lines.append(f"表: {table['name']}")
        lines.append("字段:")

        for column in table["columns"]:
            markers: list[str] = []
            if column["primary_key"]:
                markers.append("主键")
            if not column["nullable"]:
                markers.append("非空")

            marker_text = f" ({', '.join(markers)})" if markers else ""
            lines.append(f"- {column['name']} {column['type']}{marker_text}")

        if table["foreign_keys"]:
            lines.append("外键:")
            for foreign_key in table["foreign_keys"]:
                source_columns = ", ".join(foreign_key["columns"])
                target_columns = ", ".join(foreign_key["referred_columns"])
                lines.append(
                    f"- {source_columns} -> {foreign_key['referred_table']}.{target_columns}"
                )

    return "\n".join(lines)
