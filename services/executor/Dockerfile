FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY services/agent /app/services/agent
COPY services/executor /app/services/executor
RUN pip install --no-cache-dir '/app/services/agent[fallback]' /app/services/executor \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn ontara_executor.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
