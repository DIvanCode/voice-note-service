#!/usr/bin/env python3
"""Run the complete local test suite and collect one reproducible result set."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(__file__).resolve().parent / "results" / "full_test_run"
sys.path.insert(0, str(ROOT))

from app.extractor import (  # noqa: E402
    MODEL_CONFIG,
    MODEL_PATH,
    check_llama,
    log,
    log_configuration,
    start_llama,
    stop_llama,
)


TEST_COMMANDS = [
    ("unit_tests", [sys.executable, "-m", "unittest", "discover", "-s", "test", "-p", "test_*.py", "-v"]),
    ("quality_benchmark", [sys.executable, "test/run_benchmark.py"]),
    ("long_transcript_benchmark", [sys.executable, "test/run_long_benchmark.py"]),
    ("latency_benchmark", [sys.executable, "test/run_latency_benchmark.py"]),
    (
        "parallel_benchmark",
        [
            sys.executable,
            "test/run_parallel_benchmark.py",
            "--workers",
            os.getenv("FULL_TEST_WORKERS", "2"),
            "--cases",
            os.getenv("FULL_TEST_CASES", "2"),
        ],
    ),
]
NON_BLOCKING_TESTS: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def collect_system_info() -> dict[str, object]:
    info: dict[str, object] = {
        "timestamp": now(),
        "python": sys.version,
        "platform": sys.platform,
        "cwd": str(ROOT),
    }
    try:
        info["cpu_count"] = os.cpu_count()
        info["load_average"] = os.getloadavg()
    except OSError:
        pass
    try:
        info["git_revision"] = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        info["git_revision"] = None
    try:
        info["nvidia_smi"] = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        info["nvidia_smi"] = None
    return info


def run_command(name: str, command: list[str]) -> dict[str, object]:
    started = time.perf_counter()
    log(f"Running full test: {name}")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (RESULTS / f"{name}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    result = {
        "name": name,
        "command": command,
        "return_code": completed.returncode,
        "passed": completed.returncode == 0,
        "blocking": name not in NON_BLOCKING_TESTS,
        "elapsed_ms": elapsed_ms,
        "stdout_file": f"{name}.stdout.log",
        "stderr_file": f"{name}.stderr.log",
    }
    write_json(RESULTS / f"{name}.summary.json", result)
    log(f"Finished {name}: return_code={completed.returncode}, elapsed_ms={elapsed_ms}")
    return result


def copy_reports() -> None:
    report_names = (
        "last-run.json",
        "quality-last-run.json",
        "parallel-last-run.json",
        "long-last-run.json",
        "latency-last-run.json",
    )
    for name in report_names:
        source_dirs = {
            "last-run.json": "quality_benchmark",
            "quality-last-run.json": "quality_benchmark",
            "parallel-last-run.json": "parallel_benchmark",
            "long-last-run.json": "long_transcript_benchmark",
            "latency-last-run.json": "latency_benchmark",
        }
        source = ROOT / "test" / "results" / source_dirs[name] / name
        if source.is_file():
            RESULTS.mkdir(parents=True, exist_ok=True)
            (RESULTS / name).write_bytes(source.read_bytes())


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for path in RESULTS.iterdir():
        if path.is_file():
            path.unlink()

    log("Starting full test run")
    log_configuration()
    write_json(RESULTS / "configuration.json", MODEL_CONFIG)
    write_json(RESULTS / "system.json", collect_system_info())
    if Path(MODEL_PATH).is_file():
        checksum = subprocess.check_output(["sha256sum", str(MODEL_PATH)], text=True).split()[0]
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "model.sha256").write_text(f"{checksum}  {MODEL_PATH}\n", encoding="utf-8")

    llama_process = None
    test_results: list[dict[str, object]] = []
    started = time.perf_counter()
    try:
        llama_process = start_llama()
        if not check_llama():
            raise RuntimeError("llama.cpp did not become ready")
        for name, command in TEST_COMMANDS:
            test_results.append(run_command(name, command))
        copy_reports()
    except Exception as exc:
        log(f"Full test run failed: {exc}")
        write_json(
            RESULTS / "fatal-error.json",
            {"timestamp": now(), "error": f"{type(exc).__name__}: {exc}"},
        )
        test_results.append({"name": "orchestrator", "passed": False, "error": str(exc)})
    finally:
        stop_llama(llama_process)

    summary = {
        "started_at": now(),
        "total_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "model_started_by_runner": llama_process is not None,
        "all_blocking_tests_passed": all(
            item.get("passed", False)
            for item in test_results
            if item.get("blocking", True)
        ),
        "non_blocking_tests": [
            item["name"] for item in test_results if not item.get("blocking", True)
        ],
        "tests": test_results,
        "results_directory": str(RESULTS),
    }
    write_json(RESULTS / "summary.json", summary)
    log(
        "Full test run finished: "
        f"all_blocking_tests_passed={summary['all_blocking_tests_passed']}"
    )
    return 0 if summary["all_blocking_tests_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
