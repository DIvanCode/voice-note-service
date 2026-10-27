#!/usr/bin/env python3
"""Run extraction benchmark cases against the local model."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "test" / "test_configs"
RESULTS_DIR = ROOT / "test" / "results" / "quality_benchmark"
sys.path.insert(0, str(ROOT))

from app.extractor import ExtractionError, extract_text  # noqa: E402


def main() -> int:
    cases = json.loads((CONFIG_DIR / "cases.json").read_text(encoding="utf-8"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            actual = extract_text(case["text"])
            error = None
        except (ExtractionError, ValueError, OSError) as exc:
            actual = None
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        results.append({
            "id": case["id"],
            "input_chars": len(case["text"]),
            "elapsed_ms": elapsed_ms,
            "valid_shape": isinstance(actual, dict),
            "exact_expected_match": actual == case["expected"],
            "actual": actual,
            "error": error,
        })
        print(json.dumps(results[-1], ensure_ascii=False))

    output = RESULTS_DIR / "last-run.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = sum(item["exact_expected_match"] for item in results)
    field_total = len(results) * 6
    field_matches = sum(
        sum(item["actual"].get(field) == cases[index]["expected"].get(field)
            for field in ("client", "problem", "product", "budget", "deadline", "next_step"))
        if isinstance(item["actual"], dict) else 0
        for index, item in enumerate(results)
    )
    summary = {
        "case_count": len(results),
        "exact_matches": passed,
        "exact_match_rate": round(passed / len(results), 3) if results else 0,
        "field_matches": field_matches,
        "field_accuracy": round(field_matches / field_total, 3) if field_total else 0,
        "valid_shape_rate": round(sum(item["valid_shape"] for item in results) / len(results), 3)
        if results else 0,
        "max_elapsed_ms": max((item["elapsed_ms"] for item in results), default=0),
        "results": results,
    }
    quality_output = RESULTS_DIR / "quality-last-run.json"
    quality_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Completed: {passed}/{len(results)} exact matches; field accuracy={summary['field_accuracy']:.1%}")
    print(f"Saved report: {output}")
    print(f"Saved quality report: {quality_output}")
    return 0 if passed == len(results) and summary["valid_shape_rate"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
