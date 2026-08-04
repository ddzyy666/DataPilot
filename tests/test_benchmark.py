import json

from app.evaluation.benchmark import (
    load_cases,
    normalize_rows,
    recalculate_report,
    validate_gold_answers,
)


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


def test_normalize_rows_treats_equivalent_numbers_as_equal() -> None:
    assert normalize_rows([{"amount": 100}]) == normalize_rows([{"amount": 100.0}])


def test_recalculate_report_updates_summary(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {"total": 1, "passed": 0},
                "results": [
                    {
                        "passed": False,
                        "expected_rows": [{"amount": 100.0}],
                        "actual_rows": [{"amount": 100}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = recalculate_report(report_path)

    assert report["summary"]["passed"] == 1
    assert report["summary"]["accuracy"] == 1
