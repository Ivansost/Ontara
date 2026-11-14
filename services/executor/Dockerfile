FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
# The Playwright driver's Node binary needs libatomic before its own dependency
# installer can run on the slim Debian base used by Render's linux/amd64 build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY services/agent /app/services/agent
COPY services/executor /app/services/executor
RUN pip install --no-cache-dir '/app/services/agent[fallback]' /app/services/executor
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn ontara_executor.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
