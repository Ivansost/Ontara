"""Controlled AgentMail integration used by the case API."""

from __future__ import annotations

from typing import Any

from .config import MailSettings
from .provider import AgentMailProvider
from .service import MailService
from .store import MongoMailStore


def create_mail_service(db: Any, case_service: Any, artifact_store: Any = None,
                        settings: MailSettings | None = None) -> MailService:
    settings = settings or MailSettings.from_env()
    settings.validate()
    store = MongoMailStore(db)
    store.ensure_indexes()
    return MailService(store, AgentMailProvider(settings.api_key), case_service, settings, artifact_store)


def build_router(service: MailService) -> Any:
    """Mount with the API's existing internal Bearer dependency. Never mount publicly."""
    from fastapi import APIRouter
    router = APIRouter(prefix="/internal/v1/mail", tags=["internal-mail"])

    @router.get("/status")
    def mail_status(case_id: str | None = None) -> dict[str, Any]:
        return service.status(case_id)

    @router.post("/poll")
    def mail_poll() -> dict[str, Any]:
        return service.tick()

    # No generic email endpoint and no endpoint for creating fictional portal receipts.
    return router


__all__ = ["MailSettings", "MailService", "MongoMailStore", "create_mail_service", "build_router"]
