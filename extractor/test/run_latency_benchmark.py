#!/usr/bin/env python3
"""Measure first and subsequent request latency against the local model."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "test" / "results" / "latency_benchmark"
sys.path.insert(0, str(ROOT))

from app.extractor import ExtractionError, extract_text_with_metrics  # noqa: E402


def main() -> int:
    text = "Компания Альфа ищет CRM-сервис. Бюджет до ста тысяч рублей."
    results = []
    for index in range(3):
        started = time.perf_counter()
        try:
            result, metrics = extract_text_with_metrics(text)
            error = None
            model_metrics = metrics.__dict__
        except (ExtractionError, ValueError, OSError) as exc:
            result = None
            model_metrics = None
            error = f"{type(exc).__name__}: {exc}"
        results.append({
            "request_number": index + 1,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "result_shape_valid": isinstance(result, dict),
            "model_metrics": model_metrics,
            "error": error,
        })
    report = {
        "case": "latency-first-and-subsequent",
        "input_chars": len(text),
        "requests": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / "latency-last-run.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved report: {output}")
    return 0 if all(item["error"] is None for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
