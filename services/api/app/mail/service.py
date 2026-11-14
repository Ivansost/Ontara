"""Genuine controlled mail, durable send intent and idempotent resident questions."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import MailSettings, address
from .provider import AgentMailProvider, ProviderFailure
from .store import MongoMailStore, stable_id, utcnow

TOKEN = re.compile(r"\[Ontara DEMO ([a-f0-9]{32})\]")
BAD_LABELS = {"spam", "trash", "blocked", "unauthenticated"}
CONTROLLED_ROUTES = {"halton-region", "milton-town"}


def as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)
    return dict(value)


def iso(value: datetime) -> str:
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat().replace("+00:00", "Z")


class MailService:
    def __init__(self, store: MongoMailStore, provider: AgentMailProvider, case_service: Any,
                 settings: MailSettings, artifact_store: Any = None):
        self.store, self.provider, self.case_service = store, provider, case_service
        self.settings, self.artifact_store = settings, artifact_store
        self.worker_id = "mail-" + uuid4().hex
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def _context(self, case_id: str, operation_id: str, *, action: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        case = as_dict(self.case_service.get_case_internal(case_id))
        operation = as_dict(self.case_service.get_operation_internal(operation_id))
        if operation.get("caseId") != case_id or operation.get("state") != "receipt_verified":
            raise ValueError("Mail requires this case's verified portal operation")
        if action and operation.get("action") != action:
            raise ValueError("Mail purpose does not match the verified portal operation")
        if operation.get("recipientId") not in CONTROLLED_ROUTES:
            raise ValueError("Mail is limited to the two controlled demo authorities")
        route = operation.get("route") or {}
        if route.get("demo") is not True or route.get("id") not in {"halton-roads-demo", "milton-graffiti-demo"}:
            raise ValueError("Mail requires an explicitly labelled controlled demo route")
        if case.get("cancelledAt") or case.get("status") in {"cancelled", "stopped"}:
            raise ValueError("The resident cancelled this case")
        return case, operation

    def _enqueue(self, *, case_id: str, operation: dict[str, Any], purpose: str,
                 sender: str, recipients: list[str], subject: str, text: str,
                 receipt_id: str, in_reply_to: str | None = None, held: bool = False) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"state": "DISABLED", "purpose": purpose}
        if (operation.get("receipt") or {}).get("receiptId") != receipt_id:
            raise ValueError("Mail receipt reference must match the saved verified portal receipt")
        self.settings.require_participants(sender, recipients)
        operation_id = operation.get("id", operation.get("_id"))
        outbox_id = "mail_" + stable_id(case_id, operation_id, purpose)[:32]
        token = stable_id(outbox_id, "correlation")[:32]
        subject = f"[Ontara DEMO {token}] {subject}"
        text = text + f"\n\nControlled Ontara demonstration. No real municipality was contacted.\nCorrelation: {token}\n"
        immutable = {"senderInboxId": sender, "recipients": recipients, "subject": subject, "text": text,
                     "caseId": case_id, "operationId": operation_id, "purpose": purpose,
                     "receiptId": receipt_id, "inReplyTo": in_reply_to}
        now = utcnow()
        item = {"_id": outbox_id, "id": outbox_id, "kind": "email", "provider": "agentmail",
                **immutable, "payloadDigest": stable_id(json.dumps(immutable, sort_keys=True)),
                "correlationToken": token, "providerLabel": "ontara-" + token,
                "state": "HELD" if held else "QUEUED", "holdReason": "presenter" if held else None,
                "deliveryState": "UNVERIFIED", "attemptCount": 0,
                "nextAttemptAt": now, "createdAt": now, "updatedAt": now,
                "caseVersion": operation.get("caseVersion"), "visibility": "case", "controlledDemo": True}
        return self.store.enqueue(item)

    def enqueue_authority_question(self, case_id: str, operation_id: str, receipt_id: str) -> dict[str, Any]:
        _, operation = self._context(case_id, operation_id, action="create")
        if operation.get("portalId") != "roads":
            return {"state": "NOT_APPLICABLE", "purpose": "AUTHORITY_QUESTION"}
        ticket = operation.get("externalTicketId") or (operation.get("receipt") or {}).get("ticketId")
        if not ticket:
            raise ValueError("Authority mail requires the verified external ticket ID")
        return self._enqueue(
            case_id=case_id, operation=operation, purpose="AUTHORITY_QUESTION",
            sender=self.settings.authority_inbox_id, recipients=[self.settings.ontara_inbox_id],
            subject=f"Simulated authority requests a landmark — {ticket}", receipt_id=receipt_id,
            held=self.store.authority_followup_held(case_id),
            text=(f"SIMULATED AUTHORITY — compressed waiting period for this demonstration.\n"
                  f"Regarding acknowledged demo ticket {ticket}: please provide the nearest landmark "
                  "so the road location can be confirmed. Ontara must ask the resident and receive "
                  "approval before updating the existing ticket."),
        )

    def _controlled_hold_case(self, case_id: str) -> dict[str, Any]:
        case = self.store.control_case(case_id)
        if not case:
            raise ValueError("Existing synthetic case not found")
        route = case.get("route") or {}
        if (route.get("demo") is not True or route.get("id") != "halton-roads-demo"
                or route.get("portalId") != "roads" or (route.get("recipient") or {}).get("id") != "halton-region"
                or (case.get("location") or {}).get("fixtureId") != "halton-regional-road"):
            raise ValueError("Presenter mail hold is limited to the controlled Roads fixture")
        if case.get("cancelledAt") or case.get("stage") == "cancelled":
            raise ValueError("This case has been cancelled")
        return case

    def get_authority_followup_hold(self, case_id: str) -> dict[str, Any]:
        case = self._controlled_hold_case(case_id)
        controls = case.get("demoControls") or {}
        outbox = self.store.for_case_purpose(case_id, "AUTHORITY_QUESTION")
        return {"caseId": case_id, "held": controls.get("holdAuthorityFollowUp") is True,
                "heldAt": controls.get("authorityFollowUpHeldAt"),
                "releasedAt": controls.get("authorityFollowUpReleasedAt"),
                "portalConfirmation": controls.get("authorityFollowUpPortalConfirmation"),
                "authorityOutbox": {"id": outbox["id"], "state": outbox["state"],
                                     "attemptCount": outbox.get("attemptCount", 0)} if outbox else None}

    def set_authority_followup_hold(self, case_id: str, held: bool, *,
                                    portal_confirmation: dict[str, Any] | None = None) -> dict[str, Any]:
        """Private presenter control; never changes resident authorization or report facts.

        The API owns authentication and obtains v2 confirmation from its configured
        portal origin. This method validates the saved case/receipt and persists only
        the private control subtree through an atomic conditional update.
        """
        if not isinstance(held, bool):
            raise ValueError("held must be a boolean")
        case = self._controlled_hold_case(case_id)
        controls = case.get("demoControls") or {}
        if held:
            if (case.get("stage") != "draft" or case.get("approvedVersion") is not None
                    or case.get("currentOperationId") or case.get("receipt")
                    or self.store.db.operations.find_one({"caseId": case_id}, {"_id": 1})):
                raise ValueError("Hold must be set on an unused unapproved Roads draft before approval")
            if controls.get("holdAuthorityFollowUp") is not True and not self.store.set_control_hold(case, True):
                raise ValueError("Case changed while setting the mail hold; reload before continuing")
        else:
            operation = self.store.db.operations.find_one({"caseId": case_id, "action": "create", "state": "receipt_verified",
                "portalId": "roads", "recipientId": "halton-region", "runId": case.get("runId")})
            receipt = (operation or {}).get("receipt") or {}
            if (not operation or receipt.get("runId") != case.get("runId") or not receipt.get("ticketId")
                    or receipt.get("ticketId") != (case.get("receipt") or {}).get("ticketId")):
                raise ValueError("Release requires this run's saved verified initial receipt")
            proof = portal_confirmation or {}
            if (proof.get("runId") != case.get("runId") or proof.get("portalId") != "roads"
                    or proof.get("action") != "update" or proof.get("formVersion") != 2
                    or not isinstance(proof.get("snapshotDigest"), str)
                    or not re.fullmatch(r"[a-fA-F0-9]{64}", proof["snapshotDigest"])
                    or not proof.get("verifiedAt")):
                raise ValueError("Release requires configured-portal confirmation of this run's v2 follow-up form")
            safe_proof = {key: proof[key] for key in ("runId", "portalId", "action", "formVersion", "snapshotDigest", "verifiedAt")}
            if controls.get("holdAuthorityFollowUp") is True and not self.store.set_control_hold(case, False, safe_proof):
                latest = self._controlled_hold_case(case_id)
                if (latest.get("demoControls") or {}).get("holdAuthorityFollowUp") is True:
                    raise ValueError("Case changed while releasing the mail hold; reload before continuing")
            self.release_authority_followup(case_id)
        return self.get_authority_followup_hold(case_id)

    def release_authority_followup(self, case_id: str) -> int:
        """Repair a released case's pending outbox; clearing the durable flag is required."""
        self._controlled_hold_case(case_id)
        if self.store.authority_followup_held(case_id):
            return 0
        return self.refresh_authority_holds(case_id)

    def refresh_authority_holds(self, case_id: str | None = None) -> int:
        changed = 0
        for item in self.store.hold_candidates(case_id):
            held = self.store.authority_followup_held(item["caseId"])
            if held or item["state"] == "HELD":
                changed += int(self.store.transition_hold(item, held))
        return changed

    def enqueue_authority_response(self, case_id: str, operation_id: str, receipt_id: str) -> dict[str, Any]:
        _, operation = self._context(case_id, operation_id, action="update")
        payload = operation.get("payload", {})
        landmark = payload.get("answers", {}).get("nearestLandmark")
        if not isinstance(landmark, str) or not landmark.strip():
            raise ValueError("The verified approved update must contain nearestLandmark")
        question = self.store.for_case_purpose(case_id, "AUTHORITY_QUESTION")
        if not question or question.get("deliveryState") != "RECEIVED":
            raise ValueError("No genuine received authority question is correlated to this case")
        ticket = operation.get("externalTicketId") or (operation.get("receipt") or {}).get("ticketId")
        return self._enqueue(
            case_id=case_id, operation=operation, purpose="AUTHORITY_RESPONSE",
            sender=self.settings.ontara_inbox_id, recipients=[self.settings.authority_inbox_id],
            subject=f"Resident-approved landmark update — {ticket}", receipt_id=receipt_id,
            in_reply_to=question.get("providerMessageId"),
            text=(f"Regarding demo ticket {ticket}: the resident approved this nearest landmark: {landmark.strip()}.\n"
                  f"The existing demo portal ticket acknowledged the approved update (receipt {receipt_id})."),
        )

    def enqueue_resident_notification(self, case_id: str, operation_id: str, receipt_id: str) -> dict[str, Any]:
        _, operation = self._context(case_id, operation_id)
        ticket = operation.get("externalTicketId") or (operation.get("receipt") or {}).get("ticketId")
        action = operation.get("action")
        return self._enqueue(
            case_id=case_id, operation=operation, purpose="RESIDENT_NOTIFICATION",
            sender=self.settings.ontara_inbox_id, recipients=[self.settings.resident_inbox_id],
            subject=f"Demo {'follow-up' if action == 'update' else 'report'} acknowledged — {ticket}", receipt_id=receipt_id,
            text=(f"The controlled demo portal acknowledged your {'follow-up update' if action == 'update' else 'report'}.\n"
                  f"Ticket: {ticket}\nVerified receipt: {receipt_id}\n"
                  "This confirms reporting progress. Repair of the issue has not been verified.\n"
                  "This notification goes only to the controlled test resident inbox."),
        )

    def on_receipt_verified(self, case_id: str, operation: dict[str, Any], receipt: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.settings.enabled:
            return []
        operation, receipt = as_dict(operation), as_dict(receipt)
        operation_id = operation.get("id", operation.get("_id"))
        receipt_id = receipt.get("receiptId", receipt.get("id"))
        if not operation_id or not receipt_id:
            raise ValueError("Verified mail callbacks require operation and receipt identifiers")
        if operation.get("action") == "create":
            return [self.enqueue_authority_question(case_id, operation_id, receipt_id)]
        if operation.get("portalId") != "roads":
            return [self.enqueue_resident_notification(case_id, operation_id, receipt_id)]
        # Follow-up mail is an acknowledgement of a verified portal update, not the action itself.
        result = [self.enqueue_authority_response(case_id, operation_id, receipt_id)]
        result.append(self.enqueue_resident_notification(case_id, operation_id, receipt_id))
        return result

    def reconcile_receipt_outbox(self, limit: int = 20) -> dict[str, int]:
        """Replay interrupted backend callbacks from authoritative verified operations.

        This reads backend-owned operation documents and writes only mail-owned records.
        Provider availability cannot undo or fail a saved portal receipt.
        """
        result = {"scheduled": 0, "pending": 0}
        if not self.settings.enabled:
            return result
        for operation in self.store.db.operations.find({"state": "receipt_verified", "recipientId": {"$in": sorted(CONTROLLED_ROUTES)}}).sort("updatedAt", 1):
            operation_id = operation.get("id", operation.get("_id"))
            hook_id = "receipt-hook:" + operation_id
            if self.store.events.find_one({"_id": hook_id, "processingState": "PROCESSED"}):
                continue
            try:
                self.on_receipt_verified(operation["caseId"], operation, operation.get("receipt") or {})
                self.store.event(hook_id, {"kind": "mail_receipt_hook", "processingState": "PROCESSED",
                                          "caseId": operation["caseId"], "operationId": operation_id})
                result["scheduled"] += 1
            except Exception:
                result["pending"] += 1
            if result["scheduled"] + result["pending"] >= limit:
                break
        return result

    def _find_reconciled_sent(self, item: dict[str, Any]) -> dict[str, Any] | None:
        found: list[dict[str, Any]] = []
        for preview in self.provider.messages(item["senderInboxId"], labels=[item["providerLabel"]]):
            message = self.provider.get_message(item["senderInboxId"], preview["message_id"])
            if self._matches(item, message, received=False):
                found.append(message)
        if len(found) > 1:
            raise ProviderFailure("multiple_sent_candidates")
        return found[0] if found else None

    def _matches(self, item: dict[str, Any], message: dict[str, Any], *, received: bool) -> bool:
        if address(message.get("from", "")) != item["senderInboxId"]:
            return False
        participants = [address(value) for key in ("to", "cc", "bcc") for value in message.get(key, [])]
        if set(participants) != set(item["recipients"]):
            return False
        if set(message.get("labels", [])) & BAD_LABELS:
            return False
        if received and ("received" not in message.get("labels", []) or message.get("inbox_id") not in item["recipients"]):
            return False
        if not received and ("sent" not in message.get("labels", []) or message.get("inbox_id") != item["senderInboxId"]):
            return False
        if message.get("subject") != item["subject"]:
            return False
        # Require the intended payload and correlation marker as well as the provider-observed roles.
        # Email text never chooses recipients, URLs, question IDs, or executable actions.
        return item["text"].strip() in (message.get("text") or "").strip()

    def _mark_sent(self, item: dict[str, Any], result: dict[str, Any], *, reconciled: bool = False) -> None:
        self.store.patch(item["_id"], {"state": "SENT", "providerMessageId": result["message_id"],
                         "providerThreadId": result["thread_id"], "sentAt": utcnow(), "reconciled": reconciled,
                         "lastError": None}, owner=self.worker_id)
        self.store.event("sent:" + item["_id"], {"kind": "mail_sent", "caseId": item["caseId"],
                         "operationId": item["operationId"], "outboxId": item["_id"],
                         "providerMessageId": result["message_id"], "providerThreadId": result["thread_id"],
                         "evidence": "provider_send_accepted", "reconciled": reconciled})
        if item.get("lastAttemptId"):
            self.store.event("attempt-result:" + item["lastAttemptId"] + ":SENT", {
                "kind": "mail_send_result", "attemptId": item["lastAttemptId"], "state": "SENT",
                "outboxId": item["_id"], "caseId": item["caseId"], "operationId": item["operationId"],
                "providerMessageId": result["message_id"], "reconciled": reconciled})
        # A provider send result is SENT only. Receiving-inbox proof is recorded independently.

    def process_outbox_once(self, limit: int = 10) -> dict[str, int]:
        counts = {"sent": 0, "reconciled": 0, "unknown": 0, "failed": 0}
        if not self.settings.enabled:
            return counts
        now = utcnow()
        self.store.recover_stale_sends(now)
        self.refresh_authority_holds()
        for candidate in self.store.due(now, limit):
            state = candidate["state"]
            item = self.store.claim(candidate["_id"], state, self.worker_id, self.settings.lease_seconds)
            if not item:
                continue
            try:
                self.settings.require_participants(item["senderInboxId"], item["recipients"])
                self._context(item["caseId"], item["operationId"])
                if item["purpose"] == "AUTHORITY_QUESTION" and self.store.authority_followup_held(item["caseId"]):
                    self.store.patch(item["_id"], {"state": "HELD", "holdReason": "presenter"}, owner=self.worker_id)
                    continue
                if state == "OUTCOME_UNKNOWN":
                    message = self._find_reconciled_sent(item)
                    if message:
                        self._mark_sent(item, message, reconciled=True)
                        self.store.save_message(message, case_id=item["caseId"], operation_id=item["operationId"],
                                                outbox_id=item["_id"], direction="outgoing")
                        counts["reconciled"] += 1
                    else:
                        # Absence from an eventually consistent provider list does not prove non-send.
                        self.store.patch(item["_id"], {"nextAttemptAt": now + timedelta(seconds=15),
                                         "lastError": "send_outcome_unresolved_no_resend"}, owner=self.worker_id)
                        counts["unknown"] += 1
                    continue
                if not self.store.reserve_send_budget(item["_id"], self.settings.daily_send_budget):
                    self.store.patch(item["_id"], {"state": "QUEUED", "lastError": "local_free_send_budget_reached",
                                     "nextAttemptAt": now + timedelta(minutes=15)}, owner=self.worker_id)
                    continue
                attempt = uuid4().hex
                self.store.event("attempt:" + attempt, {"kind": "mail_send_attempt", "caseId": item["caseId"],
                                 "operationId": item["operationId"], "outboxId": item["_id"],
                                 "attemptId": attempt, "senderInboxId": item["senderInboxId"],
                                 "recipients": item["recipients"], "state": "SENDING"})
                self.store.patch(item["_id"], {"attemptCount": item.get("attemptCount", 0) + 1,
                                 "lastAttemptId": attempt}, owner=self.worker_id, release=False)
                item["lastAttemptId"] = attempt
                result = self.provider.send(item)
                self._mark_sent(item, result)
                counts["sent"] += 1
                # Fetch and preserve actual provider content; a restart also catches this from the inbox.
                try:
                    message = self.provider.get_message(item["senderInboxId"], result["message_id"])
                    self.store.save_message(message, case_id=item["caseId"], operation_id=item["operationId"],
                                            outbox_id=item["_id"], direction="outgoing")
                except ProviderFailure:
                    pass
            except ProviderFailure as error:
                values: dict[str, Any] = {"lastError": error.code, "nextAttemptAt": now + timedelta(seconds=15)}
                if state == "OUTCOME_UNKNOWN" or error.ambiguous:
                    values["state"] = "OUTCOME_UNKNOWN"
                    counts["unknown"] += 1
                elif error.retryable and error.code == "provider_http_429":
                    # A definitive rate-limit rejection is safe to retry with unchanged intent.
                    values["state"] = "QUEUED"
                    values["nextAttemptAt"] = now + timedelta(minutes=1)
                else:
                    values["state"] = "NEEDS_ASSISTANCE"
                    counts["failed"] += 1
                self.store.patch(item["_id"], values, owner=self.worker_id)
                if item.get("lastAttemptId"):
                    self.store.event("attempt-result:" + item["lastAttemptId"] + ":" + values["state"], {
                        "kind": "mail_send_result", "attemptId": item["lastAttemptId"], "state": values["state"],
                        "outboxId": item["_id"], "caseId": item["caseId"], "operationId": item["operationId"],
                        "errorCode": error.code})
            except ValueError:
                self.store.patch(item["_id"], {"state": "CANCELLED", "lastError": "case_or_scope_no_longer_authorized"},
                                 owner=self.worker_id)
                counts["failed"] += 1
        return counts

    def _correlate(self, message: dict[str, Any]) -> dict[str, Any] | None:
        item = self.store.by_provider_id(message["message_id"])
        if item:
            return item
        match = TOKEN.search(message.get("subject", ""))
        return self.store.by_token(match.group(1)) if match else None

    def _store_attachments(self, message: dict[str, Any], item: dict[str, Any], stored_id: str) -> None:
        attachments = message.get("attachments", [])
        if not attachments:
            return
        if self.artifact_store is None:
            raise ProviderFailure("attachment_storage_unavailable", retryable=True)
        from app.models import ArtifactUpload
        artifact_ids = []
        for attachment in attachments:
            if attachment.get("size", 0) > self.settings.max_attachment_bytes:
                raise ProviderFailure("attachment_too_large")
            data, metadata = self.provider.get_attachment(message["inbox_id"], message["message_id"],
                                                         attachment["attachment_id"], self.settings.max_attachment_bytes)
            artifact_id = "mail_file_" + stable_id(stored_id, attachment["attachment_id"])[:32]
            result = as_dict(self.artifact_store.put(ArtifactUpload(
                id=artifact_id, filename=attachment.get("filename") or "mail-attachment",
                mime_type=attachment.get("content_type") or metadata.get("content_type") or "application/octet-stream",
                content_base64=base64.b64encode(data).decode(), visibility="case", case_id=item["caseId"],
                source_version="1", operation_id=item["operationId"], expected_sha256=hashlib.sha256(data).hexdigest(),
            )))
            if result.get("state", result.get("status")) != "ready":
                raise ProviderFailure("attachment_not_ready", retryable=True)
            artifact_ids.append(artifact_id)
        self.store.messages.update_one({"_id": stored_id}, {"$set": {"attachmentArtifactIds": artifact_ids,
                                        "attachmentStorageState": "ready"}})

    def process_received_message(self, message: dict[str, Any]) -> str:
        item = self._correlate(message)
        # Unrelated inbox content is never imported, interpreted or acted upon.
        if not item:
            return "unrelated"
        stored_id = self.store.save_message(message, case_id=item["caseId"], operation_id=item["operationId"],
                                            outbox_id=item["_id"])
        event = self.store.claim_received_event(stored_id, self.worker_id, self.settings.lease_seconds)
        if not event:
            return "duplicate"
        try:
            if not self._matches(item, message, received=True):
                self.store.finish_received_event(event["_id"], self.worker_id, "IGNORED", reason="participant_or_payload_mismatch")
                return "ignored"
            self._context(item["caseId"], item["operationId"])
            if item["purpose"] == "AUTHORITY_QUESTION" and self.store.authority_followup_held(item["caseId"]):
                # Preserve the genuine message but do not schedule inspection before
                # the presenter barrier. Unexpected receiving evidence also prevents
                # a later release from blindly sending another copy.
                self.store.patch(item["_id"], {"state": "HELD", "holdReason": "presenter",
                                 "observedDuringHold": True}, release=False)
                self.store.finish_received_event(event["_id"], self.worker_id, "PENDING", lastError="presenter_mail_hold")
                return "pending"
            self._store_attachments(message, item, stored_id)
            evidence = {"inboxId": message["inbox_id"], "providerMessageId": message["message_id"],
                        "providerThreadId": message["thread_id"], "observedAt": utcnow(),
                        "evidence": "message_read_from_controlled_receiving_inbox"}
            # Receiving proof can close the send-acknowledgement gap after a sending process died.
            self.store.patch(item["_id"], {"state": "SENT", "deliveryState": "RECEIVED",
                             "providerMessageId": message["message_id"], "receivingEvidence": evidence,
                             "receivedAt": utcnow()}, release=False)
            if item["purpose"] == "AUTHORITY_QUESTION":
                from app.models import FollowUpInspectionRequest
                operation = as_dict(self.case_service.get_operation_internal(item["operationId"]))
                # Mail schedules read-only inspection. Current DOM + retrieved verified memory
                # determine the missing authored question; email never authorizes a portal write.
                self.case_service.request_follow_up_inspection(item["caseId"], FollowUpInspectionRequest(
                    source_event_id=event["_id"],
                    reason="The simulated authority emailed a request for location details. Inspect the existing demo ticket.",
                    external_ticket_id=operation.get("externalTicketId") or (operation.get("receipt") or {}).get("ticketId"),
                    operation_id=item["operationId"],
                ))
            self.store.finish_received_event(event["_id"], self.worker_id, "PROCESSED", caseId=item["caseId"],
                                            operationId=item["operationId"], outboxId=item["_id"], receivingEvidence=evidence)
            return "processed"
        except ProviderFailure as error:
            self.store.finish_received_event(event["_id"], self.worker_id,
                                            "PENDING" if error.retryable else "NEEDS_ASSISTANCE", lastError=error.code)
            return "pending" if error.retryable else "needs_assistance"
        except Exception as error:
            # Do not retain str(error): provider/driver exceptions can include private request data.
            self.store.finish_received_event(event["_id"], self.worker_id, "PENDING", lastError=type(error).__name__)
            return "pending"

    def poll_once(self, *, full_catchup: bool = False) -> dict[str, int]:
        counts = {"processed": 0, "duplicate": 0, "ignored": 0, "unrelated": 0, "pending": 0,
                  "needs_assistance": 0, "errors": 0}
        if not self.settings.enabled:
            return counts
        # Durable pending events must be revisited even after their provider-list cursor has advanced.
        for event in self.store.retry_pending_received():
            stored = self.store.messages.find_one({"_id": event["messageId"]})
            if stored:
                try:
                    message = self.provider.get_message(stored["inboxId"], stored["providerMessageId"])
                    counts[self.process_received_message(message)] += 1
                except ProviderFailure:
                    counts["errors"] += 1
        for inbox in self.settings.role_inboxes:
            started = utcnow()
            cursor = None if full_catchup else self.store.cursor(inbox)
            after = iso(cursor - timedelta(seconds=self.settings.catchup_overlap_seconds)) if cursor else None
            try:
                for preview in self.provider.messages(inbox, after=after):
                    if not self._correlate(preview):
                        counts["unrelated"] += 1
                        continue
                    message = self.provider.get_message(inbox, preview["message_id"])
                    if "received" in message.get("labels", []):
                        counts[self.process_received_message(message)] += 1
                    elif "sent" in message.get("labels", []):
                        item = self._correlate(message)
                        if item:
                            self.store.save_message(message, case_id=item["caseId"], operation_id=item["operationId"],
                                                    outbox_id=item["_id"], direction="outgoing")
                self.store.advance_cursor(inbox, started)
            except ProviderFailure:
                counts["errors"] += 1
        return counts

    def tick(self) -> dict[str, Any]:
        return {"receiptReplay": self.reconcile_receipt_outbox(), "outbox": self.process_outbox_once(), "poll": self.poll_once()}

    def start(self) -> None:
        if not self.settings.enabled or (self.thread and self.thread.is_alive()):
            return
        self.stop_event.clear()
        def work() -> None:
            first = True
            while not self.stop_event.is_set():
                try:
                    self.reconcile_receipt_outbox()
                    self.process_outbox_once()
                    self.poll_once(full_catchup=first)
                    first = False
                except Exception as error:
                    self.store.event("worker-error:" + uuid4().hex, {"kind": "mail_worker_error", "errorClass": type(error).__name__})
                self.stop_event.wait(self.settings.poll_seconds)
        self.thread = threading.Thread(target=work, name="ontara-mail", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)
        self.provider.close()

    def status(self, case_id: str | None = None) -> dict[str, Any]:
        return {"enabled": self.settings.enabled, "controlledDemo": True,
                "workerRunning": bool(self.thread and self.thread.is_alive()), **self.store.summary(case_id)}
