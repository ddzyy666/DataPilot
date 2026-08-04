import argparse
import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.db.base import engine
from app.services.sql_executor import SQLExecutor
from app.services.text_to_sql import TextToSQLService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "text_to_sql_50.json"
DEFAULT_REPORT = PROJECT_ROOT / "benchmarks" / "benchmark_report.json"


def load_cases(dataset_path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    with dataset_path.open(encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list):
        raise TypeError("评测集必须是 JSON 数组。")
    return cases


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return round(float(value), 6)
    if isinstance(value, Decimal):
        return round(float(value), 6)
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def normalize_rows(rows: list[dict[str, Any]]) -> list[str]:
    normalized_rows = []
    for row in rows:
        values = [_normalize_value(value) for value in row.values()]
        serialized_values = sorted(
            json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values
        )
        normalized_rows.append(json.dumps(serialized_values, ensure_ascii=False))
    return sorted(normalized_rows)


def validate_gold_answers(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    executor = SQLExecutor(engine, max_rows=1000)
    validated = []
    for case in cases:
        result = executor.execute(str(case["expected_sql"]))
        validated.append(
            {
                **case,
                "expected_columns": result.columns,
                "expected_rows": result.rows,
                "expected_row_count": result.row_count,
            }
        )
    return validated


async def run_benchmark(cases: list[dict[str, Any]]) -> dict[str, Any]:
    service = TextToSQLService()
    executor = SQLExecutor(engine, max_rows=1000)
    results: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        expected = executor.execute(str(case["expected_sql"]))
        item: dict[str, Any] = {
            "id": case["id"],
            "question": case["question"],
            "difficulty": case["difficulty"],
            "category": case["category"],
            "expected_sql": case["expected_sql"],
            "expected_rows": expected.rows,
        }
        try:
            response = await service.generate(str(case["question"]))
            passed = normalize_rows(response.rows) == normalize_rows(expected.rows)
            item.update(
                {
                    "passed": passed,
                    "generated_sql": response.sql,
                    "actual_rows": response.rows,
                    "was_review_corrected": response.was_review_corrected,
                    "was_repaired": response.was_repaired,
                    "timings": response.timings.model_dump(),
                }
            )
        except Exception as exc:  # noqa: BLE001 - benchmark must continue after one failure
            item.update(
                {
                    "passed": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )
        results.append(item)
        print(f"[{index:02d}/{len(cases):02d}] {'PASS' if item['passed'] else 'FAIL'} {case['question']}")

    passed_count = sum(1 for item in results if item["passed"])
    return {
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "accuracy": round(passed_count / len(results), 4) if results else 0,
        },
        "results": results,
    }


def recalculate_report(report_path: Path) -> dict[str, Any]:
    with report_path.open(encoding="utf-8") as file:
        report = json.load(file)

    results = report.get("results", [])
    for item in results:
        item["passed"] = bool(
            not item.get("error")
            and normalize_rows(item.get("actual_rows", []))
            == normalize_rows(item.get("expected_rows", []))
        )

    passed_count = sum(1 for item in results if item["passed"])
    report["summary"] = {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "accuracy": round(passed_count / len(results), 4) if results else 0,
    }
    return report


def _json_default(value: Any) -> Any:
    normalized = _normalize_value(value)
    if normalized is value:
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 DataPilot 50 题 Text-to-SQL 评测")
    parser.add_argument("--limit", type=int, default=50, help="最多运行多少道题")
    parser.add_argument("--gold-only", action="store_true", help="只验证标准 SQL，不调用模型")
    parser.add_argument("--recalculate", action="store_true", help="重新计算已有报告的通过率")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT, help="评测报告路径")
    args = parser.parse_args()

    if args.recalculate:
        report = recalculate_report(args.output)
    elif args.gold_only:
        cases = load_cases()[: args.limit]
        validated = validate_gold_answers(cases)
        report: dict[str, Any] = {
            "summary": {"total": len(validated), "gold_sql_valid": len(validated)},
            "results": validated,
        }
    else:
        cases = load_cases()[: args.limit]
        report = asyncio.run(run_benchmark(cases))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"评测报告：{args.output}")


if __name__ == "__main__":
    main()
