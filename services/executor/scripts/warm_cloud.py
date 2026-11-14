"""Warm the four verified cloud services with readiness GETs only."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time

from dotenv import dotenv_values
import httpx


# Pin destinations before attaching the internal credential. No redirects are
# followed, and the token is attached only to executor browser readiness.
ORIGINS = {
    "web": ("ONTARA_WEB_URL", "https://ontara-web-35iy.onrender.com"),
    "api": ("BACKEND_BASE_URL", "https://ontara-api-35iy.onrender.com"),
    "portals": ("PORTALS_BASE_URL", "https://ontara-portals-35iy.onrender.com"),
    "executor": ("EXECUTOR_BASE_URL", "https://ontara-executor-35iy.onrender.com"),
}
PATHS = {
    "web": "/api/health",
    "api": "/readyz",
    "portals": "/healthz",
    "executor": "/internal/v1/readyz",
}


def configuration(filename: Path) -> tuple[dict[str, str], str]:
    if not filename.is_file():
        raise ValueError("invalid_private_config")
    values = dotenv_values(filename, interpolate=False)
    urls = {}
    for service, (key, verified_origin) in ORIGINS.items():
        origin = (values.get(key) or "").rstrip("/")
        if origin != verified_origin:
            raise ValueError("invalid_private_config")
        urls[service] = origin + PATHS[service]
    token = values.get("ONTARA_INTERNAL_TOKEN") or ""
    if not token or any(char.isspace() for char in token):
        raise ValueError("invalid_private_config")
    return urls, token


def is_ready(service: str, body: dict) -> bool:
    if service == "web":
        return body.get("service") == "ontara-web" and body.get("status") == "ok"
    if service == "api":
        return body.get("ok") is True and body.get("database") == "ready" and body.get("dispatchConfigured") is True
    if service == "portals":
        return body.get("service") == "ontara-portals" and body.get("status") == "ok" and body.get("isDemo") is True and body.get("persistence") == "mongodb"
    return body.get("status") == "ready" and body.get("chromium") is True and body.get("browserChannel") == "pinned-chromium" and body.get("maxActiveBrowserTasks") == 1


async def warm(urls: dict[str, str], token: str, budget: int) -> bool:
    deadline = time.monotonic() + budget
    statuses = dict.fromkeys(urls, "not_ready")

    async def probe(service: str, client: httpx.AsyncClient) -> None:
        headers = {"Authorization": "Bearer " + token} if service == "executor" else {}
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                # The outer timeout bounds an entire request, including a slow
                # body, rather than only individual socket operations.
                async with asyncio.timeout(min(20, remaining)):
                    response = await client.get(urls[service], headers=headers)
                    if response.status_code == 200:
                        body = response.json()
                        if isinstance(body, dict) and is_ready(service, body):
                            statuses[service] = "ready"
                            print(json.dumps({"service": service, "status": "ready"}), flush=True)
                            return
                    # Configuration/authentication failures need correction;
                    # only transient failures receive cold-start retries.
                    if 300 <= response.status_code < 500 and response.status_code not in {408, 429}:
                        return
            except (httpx.HTTPError, TimeoutError, ValueError):
                pass
            await asyncio.sleep(max(0, min(5, deadline - time.monotonic())))

    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        await asyncio.gather(*(probe(service, client) for service in urls))
    ready = all(status == "ready" for status in statuses.values())
    print(json.dumps({"status": "ready" if ready else "not_ready", "services": statuses}), flush=True)
    return ready


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-env", type=Path, default=Path.home() / ".config/ontara/cloud.env")
    parser.add_argument("--budget-seconds", type=int, default=360, choices=range(1, 361), metavar="1..360")
    args = parser.parse_args()
    try:
        urls, token = configuration(args.private_env)
    except (OSError, ValueError):
        print(json.dumps({"status": "not_ready", "reason": "invalid_private_config"}))
        raise SystemExit(2) from None
    try:
        ready = asyncio.run(warm(urls, token, args.budget_seconds))
    except KeyboardInterrupt:
        print(json.dumps({"status": "not_ready", "reason": "interrupted"}))
        raise SystemExit(1) from None
    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
