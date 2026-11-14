"""Register the optional browser voice input on the existing private case API."""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import threading

from fastapi import APIRouter, FastAPI, HTTPException, Request

from .models import VoiceAnswer, VoiceBind, VoiceStart
from .provider import VoiceSettings
from .service import VoiceService


def register_voice(app: FastAPI) -> None:
    router = APIRouter(prefix="/v1/voice", tags=["Browser voice"])

    def service() -> VoiceService:
        if not getattr(app.state, "database_ready", False):
            raise HTTPException(503, "The saved reporting service is not ready")
        target = getattr(app.state, "voice_service", None)
        if target is None:
            target = VoiceService(app.state.db, app.state.case_service, VoiceSettings.load())
            app.state.voice_service = target
        return target

    @router.get("/availability")
    def availability():
        configured = VoiceSettings.load().configured
        return {"available": configured, "audioRecording": False, "maxDurationSeconds": 180,
                "message": "Use voice to fill in the same report questions." if configured else "Voice is not enabled here. Use the written form."}

    @router.post("/sessions", status_code=201)
    def start(body: VoiceStart, request: Request):
        return service().start(request.state.owner_key, body)

    @router.get("/sessions/{session_id}")
    def read(session_id: str, request: Request):
        return service().read(session_id, request.state.owner_key)

    @router.post("/sessions/{session_id}/answers")
    def answer(session_id: str, body: VoiceAnswer, request: Request):
        return service().answer(session_id, request.state.owner_key, body)

    @router.post("/sessions/{session_id}/bind")
    def bind(session_id: str, body: VoiceBind, request: Request):
        return service().bind(session_id, request.state.owner_key, body)

    @router.post("/sessions/{session_id}/finish")
    def finish(session_id: str, request: Request):
        return service().finish(session_id, request.state.owner_key)

    @router.get("/cases/{case_id}/history")
    def history(case_id: str, request: Request):
        return service().case_history(case_id, request.state.owner_key)

    app.include_router(router)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan_with_transcript_catchup(current: FastAPI):
        # Preserve the API's existing Atlas/mail/dispatch lifecycle. This small
        # reader catches up private transcripts; it is not a second case agent.
        async with previous_lifespan(current):
            stopped = threading.Event()
            worker = None
            if getattr(current.state, "database_ready", False) and VoiceSettings.load().configured:
                target = service()
                def reconcile():
                    while not stopped.wait(15):
                        try:
                            target.reconcile_pending()
                        except Exception as exc:
                            logging.getLogger("ontara.voice").warning("Voice transcript catch-up pending (%s)", type(exc).__name__)
                worker = threading.Thread(target=reconcile, name="ontara-voice-transcripts", daemon=True)
                worker.start()
            try:
                yield
            finally:
                stopped.set()
                if worker:
                    worker.join(timeout=1)

    app.router.lifespan_context = lifespan_with_transcript_catchup
