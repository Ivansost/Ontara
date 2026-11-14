from datetime import datetime, timezone
import secrets
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class MongoStore:
    """Only the receiver holds this database handle. Acceptance is one atomic document write."""

    def __init__(self, database: Any):
        self.db = database
        self.tickets = database["demo_tickets"]
        self.runs = database["demo_runs"]
        self.requests = database["demo_requests"]
        self.snapshots = database["demo_form_snapshots"]
        self.audit = database["demo_admin_events"]

    def ensure_indexes(self) -> None:
        self.tickets.create_index([("runId", ASCENDING), ("portalId", ASCENDING), ("clientReference", ASCENDING)], unique=True, name="unique_create_reference")
        self.tickets.create_index([("runId", ASCENDING), ("portalId", ASCENDING), ("receipts.clientReference", ASCENDING)], unique=True, name="unique_operation_reference")
        self.tickets.create_index("ticketId", unique=True)
        self.requests.create_index([("runId", ASCENDING), ("portalId", ASCENDING), ("action", ASCENDING)])
        self.snapshots.create_index([("portalId", ASCENDING), ("action", ASCENDING), ("formVersion", ASCENDING)], unique=True)

    def get_run(self, run_id: str) -> dict | None:
        return self.runs.find_one({"_id": run_id}, {"_id": False})

    def ensure_run(self, run_id: str, label: str = "Synthetic demo run") -> dict:
        self.runs.update_one({"_id": run_id}, {"$setOnInsert": {"runId": run_id, "label": label, "createdAt": now(), "formVersions": {"roads": 1, "graffiti": 1}}}, upsert=True)
        return self.get_run(run_id)

    def form_version(self, run_id: str, portal_id: str, action: str) -> int:
        if action == "create":
            return 1
        run = self.get_run(run_id)
        return (run or {}).get("formVersions", {}).get(portal_id, 1)

    def change_form_version(self, run_id: str, portal_id: str, version: int, expected_version: int) -> dict:
        run = self.runs.find_one_and_update({"_id": run_id, f"formVersions.{portal_id}": expected_version}, {"$set": {f"formVersions.{portal_id}": version, "modifiedAt": now()}}, return_document=ReturnDocument.AFTER)
        if not run:
            if not self.get_run(run_id):
                raise NotFound("Run not found; create this run explicitly first")
            raise Conflict("Form version changed; reload before applying this control")
        self.audit.insert_one({"runId": run_id, "portalId": portal_id, "action": "change_form_version", "fromVersion": expected_version, "toVersion": version, "at": now()})
        run.pop("_id", None)
        return run

    def save_snapshot(self, schema: dict, html: str) -> None:
        query = {key: schema[key] for key in ("portalId", "action", "formVersion")}
        self.snapshots.update_one(query, {"$setOnInsert": {**schema, "html": html, "createdAt": now(), "visibility": "demo_research"}}, upsert=True)

    def begin_request(self, run_id: str, portal_id: str, action: str, reference: str, digest: str) -> str:
        request_id = secrets.token_hex(16)
        self.requests.insert_one({"_id": request_id, "requestId": request_id, "runId": run_id, "portalId": portal_id, "action": action, "clientReference": reference, "payloadDigest": digest, "receivedAt": now(), "outcome": "received"})
        return request_id

    def finish_request(self, request_id: str, outcome: str, receipt_id: str | None = None) -> None:
        self.requests.update_one({"_id": request_id}, {"$set": {"outcome": outcome, "receiptId": receipt_id, "finishedAt": now()}})

    def lookup(self, run_id: str, portal_id: str, reference: str) -> tuple[dict, dict] | None:
        ticket = self.tickets.find_one({"runId": run_id, "portalId": portal_id, "receipts.clientReference": reference})
        if not ticket:
            return None
        receipt = next((receipt for receipt in ticket["receipts"] if receipt["clientReference"] == reference), None)
        return (ticket, receipt) if receipt else None

    def ticket(self, run_id: str, portal_id: str, ticket_id: str, token: str) -> dict:
        ticket = self.tickets.find_one({"runId": run_id, "portalId": portal_id, "ticketId": ticket_id})
        if not ticket or not secrets.compare_digest(ticket["accessToken"].encode(), token.encode()):
            raise NotFound("Ticket not found or access token is invalid")
        return ticket

    @staticmethod
    def check_existing(existing: tuple[dict, dict], digest: str, form_digest: str, action: str, ticket_id: str | None = None) -> tuple[dict, dict, bool]:
        ticket, receipt = existing
        if receipt["payloadDigest"] != digest or receipt["formPayloadDigest"] != form_digest or receipt["action"] != action or (ticket_id and ticket["ticketId"] != ticket_id):
            raise Conflict("Client reference already exists with a different payload or action")
        return ticket, receipt, True

    def create_ticket(self, envelope: dict, values: dict, form_digest: str, receipt_factory) -> tuple[dict, dict, bool]:
        run_id, portal_id, reference, digest = (envelope[key] for key in ("runId", "portalId", "clientReference", "payloadDigest"))
        existing = self.lookup(run_id, portal_id, reference)
        if existing:
            return self.check_existing(existing, digest, form_digest, "create")
        ticket_id = ("RDS" if portal_id == "roads" else "GRA") + "-" + secrets.token_hex(6).upper()
        token = secrets.token_urlsafe(32)
        receipt = receipt_factory(ticket_id, token)
        ticket = {"ticketId": ticket_id, "runId": run_id, "portalId": portal_id, "clientReference": reference, "payloadDigest": digest, "accessToken": token, "createdAt": receipt["acceptedAt"], "updatedAt": receipt["acceptedAt"], "status": "Acknowledged — DEMO", "version": 1, "initialValues": values, "currentValues": values, "receipts": [receipt], "updates": []}
        try:
            self.tickets.insert_one(ticket)
        except DuplicateKeyError:
            existing = self.lookup(run_id, portal_id, reference)
            if existing:
                return self.check_existing(existing, digest, form_digest, "create")
            raise Conflict("Reference conflicts with an existing operation") from None
        return ticket, receipt, False

    def update_ticket(self, envelope: dict, values: dict, form_digest: str, ticket_id: str, token: str, receipt_factory) -> tuple[dict, dict, bool]:
        run_id, portal_id, reference, digest = (envelope[key] for key in ("runId", "portalId", "clientReference", "payloadDigest"))
        ticket = self.ticket(run_id, portal_id, ticket_id, token)
        for _ in range(4):
            existing = self.lookup(run_id, portal_id, reference)
            if existing:
                return self.check_existing(existing, digest, form_digest, "update", ticket_id)
            receipt = receipt_factory(ticket_id, token)
            try:
                updated = self.tickets.find_one_and_update({"_id": ticket["_id"], "version": ticket["version"], "receipts.clientReference": {"$ne": reference}}, {"$set": {"currentValues": values, "updatedAt": receipt["acceptedAt"]}, "$inc": {"version": 1}, "$push": {"receipts": receipt, "updates": {"values": values, "receiptId": receipt["receiptId"], "formVersion": envelope["formVersion"], "at": receipt["acceptedAt"]}}}, return_document=ReturnDocument.AFTER)
            except DuplicateKeyError:
                raise Conflict("Reference conflicts with another ticket") from None
            if updated:
                return updated, receipt, False
            ticket = self.ticket(run_id, portal_id, ticket_id, token)
        raise Conflict("Ticket changed concurrently; reconcile this operation before retrying")

    def evidence(self, run_id: str) -> dict:
        if not self.get_run(run_id):
            raise NotFound("Run not found")
        portals = {}
        for portal_id in ("roads", "graffiti"):
            scope = {"runId": run_id, "portalId": portal_id}
            tickets = list(self.tickets.find(scope, {"_id": False, "accessToken": False, "initialValues": False, "currentValues": False, "updates": False}))
            safe_tickets = []
            update_count = 0
            for ticket in tickets:
                update_count += sum(receipt["action"] == "update" for receipt in ticket["receipts"])
                # Evidence carries no update capability, contact fields or URLs containing it.
                safe_tickets.append({key: ticket[key] for key in ("ticketId", "clientReference", "payloadDigest", "version", "status", "createdAt")})
            portals[portal_id] = {"createRequestCount": self.requests.count_documents({**scope, "action": "create"}), "ticketCount": len(tickets), "updateRequestCount": self.requests.count_documents({**scope, "action": "update"}), "acceptedUpdateCount": update_count, "lookupRequestCount": self.requests.count_documents({**scope, "action": "lookup"}), "tickets": safe_tickets, "formVersion": self.form_version(run_id, portal_id, "update")}
        return {"runId": run_id, "portals": portals, "observedAt": now(), "counterPurpose": "Presenter evidence only. Executors must obtain acceptance through the receiving interface."}
