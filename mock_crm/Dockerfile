FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /app

# Keep dependency installation as a separate build step: if PyPI/DNS fails,
# BuildKit will show that failure instead of conflating it with user creation.
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    'fastapi>=0.115,<1' \
    'uvicorn>=0.32,<1'

COPY mock_crm /app/mock_crm

# Docker supports numeric UID:GID directly. No useradd, passwd package or
# writable /etc is needed; the process remains unprivileged under Compose.
USER 10001:10001

CMD ["uvicorn", "mock_crm.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
