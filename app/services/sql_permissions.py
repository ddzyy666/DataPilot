from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


class SQLPermissionError(ValueError):
    pass


def _split_policy_values(raw_value: str) -> set[str]:
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}


@dataclass(slots=True)
class SQLPermissionPolicy:
    allowed_tables: set[str]
    denied_columns: set[str]
    dialect: str = "sqlite"

    @classmethod
    def from_strings(
        cls,
        allowed_tables: str,
        denied_columns: str,
        dialect: str = "sqlite",
    ) -> "SQLPermissionPolicy":
        return cls(
            allowed_tables=_split_policy_values(allowed_tables),
            denied_columns=_split_policy_values(denied_columns),
            dialect=dialect,
        )

    def validate(self, sql: str) -> None:
        try:
            expression = parse_one(sql, read=self.dialect)
        except ParseError as exc:
            raise SQLPermissionError("SQL 无法解析，拒绝执行。") from exc

        cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
        physical_tables: set[str] = set()
        alias_to_table: dict[str, str] = {}

        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name in cte_names:
                continue
            physical_tables.add(table_name)
            alias_to_table[table.alias_or_name.lower()] = table_name

        denied_tables = sorted(physical_tables - self.allowed_tables)
        if denied_tables:
            raise SQLPermissionError(f"无权访问数据表: {', '.join(denied_tables)}")

        denied_column_names = {item.rsplit(".", 1)[-1] for item in self.denied_columns}
        for star in expression.find_all(exp.Star):
            if isinstance(star.parent, exp.Count):
                continue
            referenced_tables = physical_tables
            if isinstance(star.parent, exp.Column) and star.parent.table:
                qualifier = star.parent.table.lower()
                referenced_tables = {alias_to_table.get(qualifier, qualifier)}
            if any(
                denied.rsplit(".", 1)[0] in referenced_tables
                for denied in self.denied_columns
                if "." in denied
            ):
                raise SQLPermissionError("通配符查询可能暴露受限字段，拒绝执行。")

        for column in expression.find_all(exp.Column):
            column_name = column.name.lower()
            qualifier = column.table.lower()

            if column_name == "*":
                continue

            if qualifier:
                table_name = alias_to_table.get(qualifier, qualifier)
                if f"{table_name}.{column_name}" in self.denied_columns:
                    raise SQLPermissionError(f"无权访问字段: {table_name}.{column_name}")
            elif column_name in denied_column_names:
                raise SQLPermissionError(f"无权访问字段: {column_name}")

    def filter_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        filtered_tables: list[dict[str, Any]] = []
        for table in schema["tables"]:
            table_name = str(table["name"]).lower()
            if table_name not in self.allowed_tables:
                continue

            columns = [
                column
                for column in table["columns"]
                if f"{table_name}.{str(column['name']).lower()}" not in self.denied_columns
            ]
            visible_column_names = {str(column["name"]).lower() for column in columns}
            foreign_keys = [
                foreign_key
                for foreign_key in table["foreign_keys"]
                if all(str(name).lower() in visible_column_names for name in foreign_key["columns"])
                and str(foreign_key["referred_table"]).lower() in self.allowed_tables
                and not any(
                    f"{str(foreign_key['referred_table']).lower()}.{str(name).lower()}"
                    in self.denied_columns
                    for name in foreign_key["referred_columns"]
                )
            ]
            filtered_tables.append(
                {
                    **table,
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                }
            )

        return {
            **schema,
            "table_count": len(filtered_tables),
            "tables": filtered_tables,
        }
