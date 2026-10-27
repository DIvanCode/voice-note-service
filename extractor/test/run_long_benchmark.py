#!/usr/bin/env python3
"""Benchmark extraction on a transcript representative of a five-minute call."""

import json
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "test" / "test_configs"
RESULTS_DIR = ROOT / "test" / "results" / "long_transcript_benchmark"
sys.path.insert(0, str(ROOT))

from app.extractor import (
    LAST_STARTUP_MS,
    ExtractionError,
    extract_text_with_metrics,
    validate_result,
)  # noqa: E402

SPEECH_RATE_WPM = 155


def main() -> int:
    transcript = (CONFIG_DIR / "long-transcript.txt").read_text(encoding="utf-8")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    word_count = len(transcript.split())
    estimated_minutes = word_count / SPEECH_RATE_WPM
    started = time.perf_counter()
    before = system_metrics()
    peak = dict(before)
    stop_sampling = threading.Event()

    def sample() -> None:
        while not stop_sampling.wait(0.25):
            current = system_metrics()
            for key in ("process_rss_kb", "gpu_memory_used_mb"):
                if isinstance(current.get(key), int):
                    peak[key] = max(int(peak.get(key, 0)), current[key])

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        actual, metrics = extract_text_with_metrics(transcript)
        error = None
    except (ExtractionError, ValueError, OSError) as exc:
        actual = None
        metrics = None
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    stop_sampling.set()
    sampler.join(timeout=1)
    after = system_metrics()
    report = {
        "case": "five-minute-transcript",
        "input_chars": len(transcript),
        "input_words": word_count,
        "speech_rate_wpm": SPEECH_RATE_WPM,
        "estimated_speech_minutes": round(estimated_minutes, 2),
        "elapsed_ms": elapsed_ms,
        "model_startup_ms": LAST_STARTUP_MS,
        "model_metrics": metrics.__dict__ if metrics else None,
        "system_before": before,
        "system_after": after,
        "system_peak": peak,
        "within_three_minute_target": elapsed_ms <= 180000,
        "valid_shape": actual is not None and _has_valid_shape(actual),
        "actual": actual,
        "error": error,
    }
    output = RESULTS_DIR / "long-last-run.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved report: {output}")
    return 0 if report["valid_shape"] else 1


def _has_valid_shape(value: object) -> bool:
    try:
        validate_result(value)
    except ValueError:
        return False
    return True


def system_metrics() -> dict[str, object]:
    metrics: dict[str, object] = {}
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text().splitlines():
            if line.startswith("VmRSS:"):
                metrics["process_rss_kb"] = int(line.split()[1])
    try:
        import subprocess

        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        used, total = output.split(",", 1)
        metrics["gpu_memory_used_mb"] = int(used.strip())
        metrics["gpu_memory_total_mb"] = int(total.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        metrics["gpu_memory_available"] = False
    return metrics


if __name__ == "__main__":
    raise SystemExit(main())
