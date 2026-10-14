#!/usr/bin/env python3
"""Compare sequential and concurrent extraction against the local model."""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "test" / "test_configs"
RESULTS_DIR = ROOT / "test" / "results" / "parallel_benchmark"
sys.path.insert(0, str(ROOT))

from app.extractor import ExtractionError, extract_text, validate_result  # noqa: E402


def run_one(case: dict[str, object]) -> dict[str, object]:
    started = time.perf_counter()
    try:
        actual = extract_text(str(case["text"]))
        error = None
    except (ExtractionError, ValueError, OSError) as exc:
        actual = None
        error = f"{type(exc).__name__}: {exc}"
    return {
        "id": case["id"],
        "input_chars": len(str(case["text"])),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "valid_shape": actual is not None and _has_valid_shape(actual),
        "exact_expected_match": actual == case["expected"],
        "error": error,
    }


def _has_valid_shape(value: object) -> bool:
    try:
        validate_result(value)
    except ValueError:
        return False
    return True


def run_batch(cases: list[dict[str, object]], workers: int) -> dict[str, object]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, cases))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "workers": workers,
        "total_elapsed_ms": elapsed_ms,
        "results": results,
        "successful": sum(item["error"] is None for item in results),
        "exact_matches": sum(item["exact_expected_match"] for item in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="number of simultaneous requests (default: 4)",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=0,
        help="number of cases to repeat (0 means all cases)",
    )
    args = parser.parse_args()
    if args.workers < 1 or args.cases < 0:
        parser.error("--workers must be >= 1 and --cases must be >= 0")

    cases = json.loads((CONFIG_DIR / "cases.json").read_text(encoding="utf-8"))
    selected = cases if args.cases == 0 else (cases * args.cases)[:args.cases]
    sequential = run_batch(selected, workers=1)
    parallel = run_batch(selected, workers=args.workers)
    speedup = (
        round(sequential["total_elapsed_ms"] / parallel["total_elapsed_ms"], 2)
        if parallel["total_elapsed_ms"]
        else None
    )
    report = {
        "workers": args.workers,
        "request_count": len(selected),
        "sequential": sequential,
        "parallel": parallel,
        "speedup": speedup,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / "parallel-last-run.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    #print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved report: {output}")
    return 0 if parallel["successful"] == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
