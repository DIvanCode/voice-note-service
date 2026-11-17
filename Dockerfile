FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home bot \
    && mkdir -p /cache \
    && chown 10001:10001 /cache

WORKDIR /app
COPY pyproject.toml README.md ./
COPY bot ./bot
COPY extractor ./extractor

# CPU-only Torch avoids large CUDA downloads on the VM.
RUN python -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir .

USER 10001:10001
CMD ["python", "-m", "bot.main"]
