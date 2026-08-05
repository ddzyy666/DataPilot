import pytest

from app.services.sql_permissions import SQLPermissionError, SQLPermissionPolicy


def build_policy() -> SQLPermissionPolicy:
    return SQLPermissionPolicy.from_strings(
        allowed_tables="customers,orders,order_items",
        denied_columns="customers.email,customers.phone",
    )


def test_permission_policy_allows_cte_using_allowed_tables() -> None:
    build_policy().validate(
        "WITH paid AS (SELECT id FROM orders WHERE status = 'paid') SELECT COUNT(*) FROM paid"
    )


def test_permission_policy_rejects_denied_table() -> None:
    with pytest.raises(SQLPermissionError, match="secret_table"):
        build_policy().validate("SELECT id FROM secret_table")


def test_permission_policy_resolves_alias_for_denied_column() -> None:
    with pytest.raises(SQLPermissionError, match="customers.email"):
        build_policy().validate("SELECT c.email FROM customers AS c")


def test_permission_policy_rejects_wildcard_that_may_expose_denied_column() -> None:
    with pytest.raises(SQLPermissionError, match="通配符"):
        build_policy().validate("SELECT * FROM customers")


def test_permission_policy_allows_count_star() -> None:
    build_policy().validate("SELECT COUNT(*) FROM customers")


def test_permission_policy_filters_denied_schema_items() -> None:
    schema = {
        "dialect": "sqlite",
        "table_count": 2,
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id"},
                    {"name": "email"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "secret_table",
                "columns": [{"name": "secret"}],
                "foreign_keys": [],
            },
        ],
    }

    filtered = build_policy().filter_schema(schema)

    assert filtered["table_count"] == 1
    assert filtered["tables"][0]["name"] == "customers"
    assert filtered["tables"][0]["columns"] == [{"name": "id"}]
