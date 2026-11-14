from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from .browser import BrowserTools
from .contracts import BrowserContext, BrowserResult, InspectRequest, SubmitRequest
from .security import TargetPolicy, UnsafeTarget
from .supervisor import ChildSupervisor
from .engine_dispatch import EngineDispatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.browser = BrowserTools(TargetPolicy())
    app.state.supervisor = ChildSupervisor()
    app.state.engine = EngineDispatcher()
    yield
    await app.state.supervisor.close()
    await app.state.engine.close()
    await app.state.browser.close()


app = FastAPI(title="Ontara execution tools", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)


async def authorize(authorization: str | None = Header(default=None)):
    expected = os.environ.get("ONTARA_INTERNAL_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Execution authentication is not configured")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(401, "Internal authorization required")


@app.middleware("http")
async def request_limits(request: Request, call_next):
    try:
        if int(request.headers.get("content-length", "0")) > 256000:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
    except ValueError:
        return JSONResponse({"detail": "Invalid content length"}, status_code=400)
    return await call_next(request)


@app.exception_handler(UnsafeTarget)
async def target_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=422)


@app.exception_handler(ValueError)
async def validation_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=422)


@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "ontara-executor", "runtimeMode": os.environ.get("ONTARA_RUNTIME_MODE", "engine")}


@app.get("/internal/v1/readyz", dependencies=[Depends(authorize)])
async def ready(request: Request):
    async with request.app.state.browser.page() as page:
        await page.set_content("<title>Ontara browser readiness</title>")
        title = await page.title()
    return {"status": "ready", "chromium": title == "Ontara browser readiness", "browserVersion": request.app.state.browser._browser.version, "browserChannel": os.environ.get("ONTARA_LOCAL_BROWSER_CHANNEL", "pinned-chromium"), "maxActiveBrowserTasks": 1, "runtimeMode": os.environ.get("ONTARA_RUNTIME_MODE", "engine")}


@app.post("/internal/v1/browser/inspect", response_model=BrowserResult, dependencies=[Depends(authorize)])
async def inspect(body: InspectRequest, request: Request):
    return await request.app.state.browser.inspect(body)


@app.post("/internal/v1/browser/submit", response_model=BrowserResult, dependencies=[Depends(authorize)])
async def submit(body: SubmitRequest, request: Request):
    return await request.app.state.browser.submit(body)


@app.post("/internal/v1/browser/reconcile", response_model=BrowserResult, dependencies=[Depends(authorize)])
async def reconcile(body: BrowserContext, request: Request):
    return await request.app.state.browser.reconcile(body)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobId: str | None = Field(default=None, max_length=200)
    caseId: str | None = Field(default=None, max_length=200)
    recover: bool = True


@app.post("/internal/v1/run", status_code=202, dependencies=[Depends(authorize)])
async def run(body: RunRequest, request: Request):
    try:
        runtime = request.app.state.engine if os.environ.get("ONTARA_RUNTIME_MODE", "engine") == "engine" else request.app.state.supervisor
        return await runtime.start(job_id=body.jobId, case_id=body.caseId, recover=body.recover)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from None


@app.get("/internal/v1/runs/{task_id}", dependencies=[Depends(authorize)])
async def run_status(task_id: str, request: Request):
    task = request.app.state.supervisor.tasks.get(task_id) or request.app.state.engine.tasks.get(task_id)
    if not task:
        raise HTTPException(404, "No active supervisor status; durable work remains in the case API")
    return task
