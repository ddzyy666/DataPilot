from app.evaluation.benchmark import load_cases, normalize_rows, validate_gold_answers


def test_benchmark_contains_50_valid_gold_answers() -> None:
    cases = load_cases()

    assert len(cases) == 50
    assert [case["id"] for case in cases] == list(range(1, 51))

    validated = validate_gold_answers(cases)

    assert len(validated) == 50


def test_normalize_rows_ignores_row_and_column_order() -> None:
    first = [{"name": "华东", "count": 10}, {"name": "华南", "count": 8}]
    second = [{"count": 8, "name": "华南"}, {"count": 10, "name": "华东"}]

    assert normalize_rows(first) == normalize_rows(second)
