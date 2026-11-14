from __future__ import annotations

import logging
import threading
from datetime import timedelta

import httpx
from pymongo import ReturnDocument

from .config import Settings
from .service import CaseService
from .storage import now

LOGGER = logging.getLogger("ontara.dispatch")


class DispatchCoordinator:
    """A restartable notifier; the Atlas job and worker lease remain authoritative."""

    def __init__(self, db, settings: Settings, cases: CaseService):
        self.db, self.settings, self.cases = db, settings, cases
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="ontara-dispatch", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                LOGGER.warning("Dispatch notification deferred (%s)", type(exc).__name__)
            self.stop.wait(5)

    def tick(self) -> bool:
        stamp = now()
        job = self.db.jobs.find_one_and_update({"$and": [
            {"$or": [{"state": "queued"}, {"state": "leased", "leaseUntil": {"$lte": stamp}}]},
            {"$or": [{"nextDispatchAt": {"$exists": False}}, {"nextDispatchAt": {"$lte": stamp}}]},
        ]},
            {"$set": {"nextDispatchAt": stamp + timedelta(seconds=30), "lastDispatchAt": stamp}, "$inc": {"dispatchAttempts": 1}},
            sort=[("createdAt", 1)], return_document=ReturnDocument.AFTER)
        if not job:
            return False
        # Multiple or retried notifications are safe: only one fenced worker can lease.
        with httpx.Client(timeout=15) as client:
            response = client.post(self.settings.dispatch_url, json={"caseId": job["caseId"], "jobId": job["id"]},
                                   headers={"Authorization": f"Bearer {self.settings.internal_token}"})
            response.raise_for_status()
        return True
