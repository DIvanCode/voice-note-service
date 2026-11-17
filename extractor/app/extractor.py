"""Direct Python interface to the local llama.cpp model."""

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model.json"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    MODEL_CONFIG = json.load(config_file)


def config_value(name: str, default: str) -> str:
    value = os.getenv(name, str(MODEL_CONFIG.get(name.lower(), default)))
    if name in {"LLAMA_SERVER", "MODEL_PATH"} and not os.path.isabs(value):
        value = str(ROOT / value)
    return value


SCHEMA_PATH = ROOT / "config" / "schema-v1.json"
PROMPT_PATH = ROOT / "config" / "extraction-v1.txt"
LLAMA_URL = config_value("LLAMA_URL", "http://127.0.0.1:8080").rstrip("/")
LLAMA_SERVER = config_value("LLAMA_SERVER", str(ROOT / "llama.cpp" / "build" / "bin" / "llama-server"))
MODEL_PATH = config_value("MODEL_PATH", str(ROOT / "models" / "Qwen3-8B-Q4_K_M.gguf"))
LLAMA_HOST = config_value("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(config_value("LLAMA_PORT", "8080"))
LLAMA_CONTEXT = config_value("LLAMA_CONTEXT", "4096")
LLAMA_BATCH = config_value("LLAMA_BATCH", "64")
LLAMA_UBATCH = config_value("LLAMA_UBATCH", "32")
LLAMA_GPU_LAYERS = config_value("LLAMA_GPU_LAYERS", "0")
LLAMA_PARALLEL_SLOTS = config_value("LLAMA_PARALLEL_SLOTS", "1")
MAX_TEXT_CHARS = int(config_value("MAX_TEXT_CHARS", "50000"))
UPSTREAM_TIMEOUT = float(config_value("UPSTREAM_TIMEOUT", "180"))
LLAMA_STARTUP_TIMEOUT = float(config_value("LLAMA_STARTUP_TIMEOUT", "300"))
FIELDS = ("lead", "topic", "description", "next_step", "deadline", "additional_info")
LOGGER = logging.getLogger(__name__)
LAST_STARTUP_MS: float | None = None

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    SCHEMA = json.load(schema_file)
with PROMPT_PATH.open(encoding="utf-8") as prompt_file:
    SYSTEM_PROMPT = prompt_file.read().rstrip()


def log(message: str, level: int = logging.INFO) -> None:
    LOGGER.log(level, message)


def log_configuration() -> None:
    log("Active model configuration:")
    for name, value in (
        ("model", MODEL_PATH),
        ("llama_server", LLAMA_SERVER),
        ("llama_url", LLAMA_URL),
        ("context", LLAMA_CONTEXT),
        ("batch", LLAMA_BATCH),
        ("ubatch", LLAMA_UBATCH),
        ("gpu_layers", LLAMA_GPU_LAYERS),
        ("parallel_slots", LLAMA_PARALLEL_SLOTS),
        ("max_text_chars", MAX_TEXT_CHARS),
        ("upstream_timeout", UPSTREAM_TIMEOUT),
    ):
        log(f"  {name}={value}")


def check_llama() -> bool:
    try:
        with urlopen(f"{LLAMA_URL}/health", timeout=5) as response:
            if response.status == HTTPStatus.OK:
                log(f"llama.cpp is available: {LLAMA_URL}")
                return True
            log(f"llama.cpp returned HTTP {response.status}", logging.WARNING)
    except (HTTPError, URLError, TimeoutError) as exc:
        log(f"llama.cpp is not available yet: {exc}", logging.DEBUG)
    return False


def start_llama() -> subprocess.Popen[bytes] | None:
    global LAST_STARTUP_MS
    if check_llama():
        log("Using an already running llama.cpp instance")
        return None
    if not Path(LLAMA_SERVER).is_file():
        raise RuntimeError(f"llama-server was not found: {LLAMA_SERVER}")
    if not Path(MODEL_PATH).is_file():
        raise RuntimeError(f"Model file was not found: {MODEL_PATH}")

    command = [
        LLAMA_SERVER, "-m", MODEL_PATH,
        "--host", LLAMA_HOST, "--port", str(LLAMA_PORT),
        "-c", LLAMA_CONTEXT, "-b", LLAMA_BATCH, "-ub", LLAMA_UBATCH,
        "-ngl", LLAMA_GPU_LAYERS, "-np", LLAMA_PARALLEL_SLOTS, "--jinja",
    ]
    log(f"Starting llama.cpp with model: {MODEL_PATH}")
    started = time.monotonic()
    runtime_dir = str(Path(LLAMA_SERVER).resolve().parent)
    environment = os.environ.copy()
    existing_library_path = environment.get("LD_LIBRARY_PATH")
    environment["LD_LIBRARY_PATH"] = (
        f"{runtime_dir}:{existing_library_path}"
        if existing_library_path
        else runtime_dir
    )
    process = subprocess.Popen(
        command,
        stdout=None,
        stderr=subprocess.STDOUT,
        env=environment,
    )
    deadline = time.monotonic() + LLAMA_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited with code {process.returncode}")
        if check_llama():
            LAST_STARTUP_MS = round((time.monotonic() - started) * 1000, 1)
            log(f"Model loaded in {LAST_STARTUP_MS} ms")
            log("Model loaded; llama.cpp is ready for requests")
            return process
        time.sleep(2)
    process.terminate()
    raise RuntimeError(f"llama.cpp did not start within {LLAMA_STARTUP_TIMEOUT} seconds")


def stop_llama(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    log("Stopping llama.cpp")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log("llama.cpp did not stop in time; killing the process", logging.WARNING)
        process.kill()
        process.wait()


def validate_result(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError("model result has missing or additional fields")
    for field in FIELDS:
        if value[field] is not None and not isinstance(value[field], str):
            raise ValueError(f"field {field!r} must be a string or null")
    return value  # type: ignore[return-value]


class ExtractionError(RuntimeError):
    """Base error for model extraction failures."""


class ModelUnavailableError(ExtractionError):
    """The llama.cpp server could not be reached."""


class InvalidModelResponseError(ExtractionError):
    """The model returned invalid JSON or a result outside the contract."""


class InputValidationError(ValueError):
    """The transcript does not satisfy the input contract."""


@dataclass(frozen=True)
class ExtractionMetrics:
    elapsed_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    prompt_tokens_per_second: float | None
    completion_tokens_per_second: float | None


def _request_body(text: str) -> bytes:
    body = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"/no_think\nРасшифровка:\n{text}"},
        ],
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "lead_extraction", "schema": SCHEMA},
        },
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _call_llama_once(text: str) -> tuple[dict[str, str | None], dict[str, object]]:
    request = Request(
        f"{LLAMA_URL}/v1/chat/completions",
        data=_request_body(text),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=UPSTREAM_TIMEOUT) as response:
            upstream = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ModelUnavailableError("llama.cpp is unavailable") from exc

    try:
        result = validate_result(json.loads(upstream["choices"][0]["message"]["content"]))
        return result, upstream.get("timings", {})
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidModelResponseError(
            "llama.cpp returned invalid JSON or a result outside the schema"
        ) from exc


def extract_text_with_metrics(
    text: str,
) -> tuple[dict[str, str | None], ExtractionMetrics]:
    """Extract structured fields from a transcript using the running model."""
    if not isinstance(text, str) or not text.strip():
        raise InputValidationError("text must be a non-empty string")
    if len(text) > MAX_TEXT_CHARS:
        raise InputValidationError(f"text is longer than {MAX_TEXT_CHARS} characters")

    log(f"Model request started: input length is {len(text)} characters")
    started = time.monotonic()
    for attempt in range(2):
        try:
            result, timings = _call_llama_once(text)
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            usage = {
                **timings,
                "prompt_tokens": timings.get("prompt_n"),
                "completion_tokens": timings.get("predicted_n"),
                "prompt_tokens_per_second": timings.get("prompt_per_second"),
                "completion_tokens_per_second": timings.get("predicted_per_second"),
            }
            log(
                f"Model response passed schema validation in "
                f"{elapsed_ms} ms; "
                f"prompt_tokens={usage['prompt_tokens']}, "
                f"completion_tokens={usage['completion_tokens']}, "
                f"completion_tokens_per_second={usage['completion_tokens_per_second']}"
            )
            return result, ExtractionMetrics(
                elapsed_ms=elapsed_ms,
                prompt_tokens=_as_int(usage["prompt_tokens"]),
                completion_tokens=_as_int(usage["completion_tokens"]),
                prompt_tokens_per_second=_as_float(usage["prompt_tokens_per_second"]),
                completion_tokens_per_second=_as_float(usage["completion_tokens_per_second"]),
            )
        except InvalidModelResponseError:
            if attempt == 0:
                log("Invalid structured response; retrying once", logging.WARNING)
                continue
            raise


def extract_text(text: str) -> dict[str, str | None]:
    """Extract structured fields from a transcript using the running model."""
    result, _ = extract_text_with_metrics(text)
    return result


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_float(value: object) -> float | None:
    return value if isinstance(value, (int, float)) else None
