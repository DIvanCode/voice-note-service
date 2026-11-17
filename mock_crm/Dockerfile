FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN python -m pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.32,<1' \
    && useradd --system --uid 10001 --no-create-home crm
COPY mock_crm /app/mock_crm
USER 10001:10001
CMD ["uvicorn", "mock_crm.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
