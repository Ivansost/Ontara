"""Mail-owned collections in the authoritative application Atlas database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode()).hexdigest()


class MongoMailStore:
    def __init__(self, database: Any):
        self.db = database
        self.outbox = database.outbox
        self.messages = database.mail_messages
        self.events = database.mail_events
        self.polls = database.mail_poll_cursors

    def ensure_indexes(self) -> None:
        self.outbox.create_index([("kind", 1), ("state", 1), ("nextAttemptAt", 1)], name="mail_ready")
        self.outbox.create_index([("kind", 1), ("correlationToken", 1)], name="mail_correlation", unique=True, partialFilterExpression={"kind": "email"})
        self.outbox.create_index([("caseId", 1), ("operationId", 1)], name="mail_case_operation")
        self.messages.create_index([("inboxId", 1), ("providerMessageId", 1)], name="mail_provider_identity", unique=True)
        self.messages.create_index([("caseId", 1), ("createdAt", 1)], name="mail_case_history")
        self.events.create_index([("kind", 1), ("processingState", 1), ("leaseUntil", 1)], name="mail_event_processing")

    def enqueue(self, item: dict[str, Any]) -> dict[str, Any]:
        try:
            self.outbox.insert_one(item.copy())
        except DuplicateKeyError:
            existing = self.outbox.find_one({"_id": item["_id"]})
            if not existing or existing.get("payloadDigest") != item["payloadDigest"]:
                raise ValueError("An existing mail operation cannot be reused with different content") from None
            return existing
        return item

    def get(self, outbox_id: str) -> dict[str, Any] | None:
        return self.outbox.find_one({"_id": outbox_id, "kind": "email"})

    def freeze_sent_time(self, outbox_id: str, when: datetime, evidence: str) -> None:
        """First verified SENT observation anchors a scripted timer permanently."""
        self.outbox.update_one({"_id": outbox_id, "kind": "email", "sentAt": {"$exists": False}},
            {"$set": {"sentAt": when, "sentEvidence": evidence}})

    def by_token(self, token: str) -> dict[str, Any] | None:
        return self.outbox.find_one({"kind": "email", "correlationToken": token})

    def by_provider_id(self, message_id: str) -> dict[str, Any] | None:
        return self.outbox.find_one({"kind": "email", "providerMessageId": message_id})

    def for_case_purpose(self, case_id: str, purpose: str) -> dict[str, Any] | None:
        return self.outbox.find_one({"kind": "email", "caseId": case_id, "purpose": purpose}, sort=[("createdAt", -1)])

    def control_case(self, case_id: str) -> dict[str, Any] | None:
        """Read only the fields needed for private presenter controls, never owner tokens."""
        return self.db.cases.find_one({"id": case_id}, {"_id": 0, "id": 1, "runId": 1, "route": 1,
            "location": 1, "stage": 1, "version": 1, "approvedVersion": 1, "currentOperationId": 1,
            "receipt": 1, "cancelledAt": 1, "demoControls": 1})

    def authority_followup_held(self, case_id: str) -> bool:
        case = self.control_case(case_id)
        return bool(case and (case.get("demoControls") or {}).get("holdAuthorityFollowUp") is True)

    def authority_followup_staged(self, case_id: str) -> bool:
        case = self.control_case(case_id)
        controls = (case or {}).get("demoControls") or {}
        # Existing queued/held historical intents remain usable. New cases need
        # an authenticated preapproval hold to opt into the advanced story.
        return bool(controls.get("authorityFollowUpStaged") is True or controls.get("holdAuthorityFollowUp") is True
                    or self.for_case_purpose(case_id, "AUTHORITY_QUESTION"))

    def set_control_hold(self, case: dict[str, Any], held: bool, confirmation: dict[str, Any] | None = None) -> bool:
        """CAS one private case subtree; report facts/version/authorization remain untouched."""
        now = utcnow()
        event = {"id": "authority-followup:" + ("held:" if held else "released:") + case["id"],
                 "held": held, "at": now}
        query: dict[str, Any] = {"id": case["id"], "cancelledAt": None}
        values: dict[str, Any] = {"demoControls.holdAuthorityFollowUp": held}
        if held:
            query.update({"version": case["version"], "stage": "draft", "approvedVersion": None,
                          "currentOperationId": None, "receipt": None,
                          "demoControls.holdAuthorityFollowUp": {"$ne": True}})
            values["demoControls.authorityFollowUpHeldAt"] = now
            values["demoControls.authorityFollowUpStaged"] = True
        else:
            query.update({"runId": case["runId"], "demoControls.holdAuthorityFollowUp": True})
            values.update({"demoControls.authorityFollowUpReleasedAt": now,
                           "demoControls.authorityFollowUpPortalConfirmation": confirmation})
            event["portalConfirmation"] = confirmation
        result = self.db.cases.update_one(query, {"$set": values,
            "$push": {"demoControls.authorityFollowUpAudit": {"$each": [event], "$slice": -2}}})
        if result.modified_count:
            # The embedded audit was committed atomically with the flag. This separate
            # event is an idempotent operational index, not the authoritative control.
            self.event(event["id"], {"kind": "mail_presenter_control", "caseId": case["id"],
                                     "held": held, "portalConfirmation": confirmation})
        return bool(result.modified_count)

    def hold_candidates(self, case_id: str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"kind": "email", "purpose": "AUTHORITY_QUESTION",
                                 "state": {"$in": ["QUEUED", "HELD", "OUTCOME_UNKNOWN"]}}
        if case_id:
            query["caseId"] = case_id
        return list(self.outbox.find(query))

    def transition_hold(self, item: dict[str, Any], held: bool) -> bool:
        """Conditional state change never overrides an active sending lease."""
        now = utcnow()
        target = "HELD" if held else ("OUTCOME_UNKNOWN" if item.get("observedDuringHold") else "QUEUED")
        if item["state"] == target:
            return False
        return bool(self.outbox.update_one(
            {"_id": item["_id"], "state": item["state"], "purpose": "AUTHORITY_QUESTION",
             "$or": [{"leaseUntil": {"$exists": False}}, {"leaseUntil": {"$lte": now}}]},
            {"$set": {"state": target, "holdReason": "presenter" if held else None,
                      "nextAttemptAt": now, "updatedAt": now}},
        ).modified_count)

    def recover_stale_sends(self, now: datetime) -> int:
        return self.outbox.update_many(
            {"kind": "email", "state": "SENDING", "leaseUntil": {"$lte": now}},
            {"$set": {"state": "OUTCOME_UNKNOWN", "nextAttemptAt": now, "updatedAt": now,
                      "lastError": "worker_stopped_during_send"}, "$unset": {"leaseOwner": "", "leaseUntil": ""}},
        ).modified_count

    def due(self, now: datetime, limit: int = 10, *, purposes: set[str] | None = None) -> list[dict[str, Any]]:
        query = {"kind": "email", "state": {"$in": ["QUEUED", "OUTCOME_UNKNOWN"]},
                                     "nextAttemptAt": {"$lte": now},
                                     "$or": [{"leaseUntil": {"$exists": False}}, {"leaseUntil": {"$lte": now}}]}
        if purposes is not None:
            query["purpose"] = {"$in": sorted(purposes)}
        return list(self.outbox.find(query)
                    .sort("createdAt", 1).limit(limit))

    def claim(self, outbox_id: str, expected_state: str, owner: str, lease_seconds: int) -> dict[str, Any] | None:
        now = utcnow()
        update: dict[str, Any] = {"leaseOwner": owner, "leaseUntil": now + timedelta(seconds=lease_seconds), "updatedAt": now}
        if expected_state == "QUEUED":
            update["state"] = "SENDING"
        return self.outbox.find_one_and_update(
            {"_id": outbox_id, "kind": "email", "state": expected_state,
             "$or": [{"leaseUntil": {"$exists": False}}, {"leaseUntil": {"$lte": now}}]},
            {"$set": update}, return_document=ReturnDocument.AFTER,
        )

    def patch(self, outbox_id: str, values: dict[str, Any], *, owner: str | None = None, release: bool = True) -> bool:
        query: dict[str, Any] = {"_id": outbox_id, "kind": "email"}
        if owner:
            query["leaseOwner"] = owner
        update: dict[str, Any] = {"$set": {**values, "updatedAt": utcnow()}}
        if release:
            update["$unset"] = {"leaseOwner": "", "leaseUntil": ""}
        return bool(self.outbox.update_one(query, update).matched_count)

    def event(self, event_id: str, values: dict[str, Any]) -> None:
        self.events.update_one({"_id": event_id}, {"$setOnInsert": {**values, "createdAt": utcnow()}}, upsert=True)

    def save_message(self, message: dict[str, Any], *, case_id: str | None = None, operation_id: str | None = None,
                     outbox_id: str | None = None, direction: str = "incoming") -> str:
        message_id = stable_id(message["inbox_id"], message["message_id"])
        # Only explicitly selected message fields are retained. Authentication headers, cookies,
        # provider request metadata and arbitrary SDK objects cannot leak into Atlas.
        document = {
            "_id": message_id, "provider": "agentmail", "providerMessageId": message["message_id"],
            "providerThreadId": message["thread_id"], "inboxId": message["inbox_id"],
            "direction": direction, "from": message.get("from", ""), "to": message.get("to", []),
            "cc": message.get("cc", []), "bcc": message.get("bcc", []),
            "subject": message.get("subject", ""), "text": message.get("text", ""),
            "html": message.get("html"), "extractedText": message.get("extracted_text"),
            "inReplyTo": message.get("in_reply_to"), "references": message.get("references", []),
            "attachments": message.get("attachments", []), "attachmentArtifactIds": [],
            "correlationHeader": {k: v for k, v in (message.get("headers") or {}).items()
                                  if k.lower() in {"x-ontara-correlation", "message-id", "in-reply-to", "references"}},
            "authenticationResults": message.get("authentication_results", {}),
            "timestamp": message.get("timestamp"), "providerCreatedAt": message.get("created_at"),
            "caseId": case_id, "operationId": operation_id, "outboxId": outbox_id,
            "visibility": "case" if case_id else "restricted", "createdAt": utcnow(),
        }
        self.messages.update_one({"_id": message_id}, {"$setOnInsert": document,
                                 "$set": {"labels": message.get("labels", []), "lastObservedAt": utcnow()}}, upsert=True)
        if case_id:
            self.messages.update_one({"_id": message_id}, {"$set": {"caseId": case_id, "operationId": operation_id,
                                      "outboxId": outbox_id, "visibility": "case"}})
        return message_id

    def claim_received_event(self, message_id: str, owner: str, lease_seconds: int) -> dict[str, Any] | None:
        event_id = "received:" + message_id
        now = utcnow()
        self.event(event_id, {"kind": "mail_received", "messageId": message_id, "processingState": "PENDING"})
        return self.events.find_one_and_update(
            {"_id": event_id, "$or": [{"processingState": "PENDING"},
                                        {"processingState": "PROCESSING", "leaseUntil": {"$lte": now}}]},
            {"$set": {"processingState": "PROCESSING", "leaseOwner": owner,
                      "leaseUntil": now + timedelta(seconds=lease_seconds)}}, return_document=ReturnDocument.AFTER,
        )

    def finish_received_event(self, event_id: str, owner: str, state: str, **values: Any) -> None:
        self.events.update_one({"_id": event_id, "leaseOwner": owner},
                               {"$set": {"processingState": state, "processedAt": utcnow(), **values},
                                "$unset": {"leaseOwner": "", "leaseUntil": ""}})

    def retry_pending_received(self) -> list[dict[str, Any]]:
        now = utcnow()
        return list(self.events.find({"kind": "mail_received", "$or": [{"processingState": "PENDING"},
                            {"processingState": "PROCESSING", "leaseUntil": {"$lte": now}}]}).limit(100))

    def cursor(self, inbox_id: str) -> datetime | None:
        document = self.polls.find_one({"_id": inbox_id})
        return document.get("lastCompletedAt") if document else None

    def advance_cursor(self, inbox_id: str, started_at: datetime) -> None:
        self.polls.update_one({"_id": inbox_id}, {"$max": {"lastCompletedAt": started_at},
                              "$set": {"updatedAt": utcnow()}}, upsert=True)

    def send_count_today(self) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.events.count_documents({"kind": "mail_send_attempt", "createdAt": {"$gte": start}})

    def reserve_send_budget(self, outbox_id: str, budget: int) -> bool:
        """Atomically reserve a local send slot. UTC days conservatively cap this app's sends."""
        day = utcnow().strftime("%Y-%m-%d")
        budget_id = "send-budget:" + day
        self.polls.update_one({"_id": budget_id}, {"$setOnInsert": {"count": 0}}, upsert=True)
        reserved = self.polls.find_one_and_update({"_id": budget_id, "count": {"$lt": budget}},
                                               {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER)
        return reserved is not None

    def summary(self, case_id: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"kind": "email"}
        if case_id:
            query["caseId"] = case_id
        records = list(self.outbox.find(query, {"_id": 0, "id": 1, "caseId": 1, "operationId": 1,
                        "purpose": 1, "state": 1, "deliveryState": 1, "providerMessageId": 1,
                        "providerThreadId": 1, "receivingEvidence": 1, "lastError": 1, "updatedAt": 1,
                        "holdReason": 1, "attemptCount": 1, "sentAt": 1, "sentEvidence": 1,
                        "createdAt": 1, "nextAttemptAt": 1, "receivedAt": 1, "scriptedDemo": 1, "scriptedDueAt": 1}).limit(100))
        return {"provider": "agentmail", "controlledDemo": True, "outbox": records,
                "messagesStored": self.messages.count_documents({"caseId": case_id} if case_id else {})}
