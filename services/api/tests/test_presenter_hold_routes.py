from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import now


class MailControls:
    """Route tests use a control double; durable HELD semantics have mail-owned tests."""

    def __init__(self, db):
        self.db = db
        self.calls = []

    def get_authority_followup_hold(self, case_id):
        case = self.db.cases.find_one({"id": case_id})
        controls = case.get("demoControls") or {}
        return {"caseId": case_id, "held": controls.get("holdAuthorityFollowUp", False),
                "portalConfirmation": controls.get("portalConfirmation")}

    def set_authority_followup_hold(self, case_id, held, *, portal_confirmation=None):
        self.calls.append((held, portal_confirmation))
        self.db.cases.update_one({"id": case_id}, {"$set": {"demoControls.holdAuthorityFollowUp": held,
            "demoControls.portalConfirmation": portal_confirmation}})
        return self.get_authority_followup_hold(case_id)

    def on_receipt_verified(self, *_):
        pass

    def close(self):
        pass


def road_report():
    return {"issueId": "roads-pothole", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region",
        "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True},
        "answers": {"immediateDanger": "No", "roadPosition": "At curb", "travelDirection": "Northbound", "description": "Synthetic pothole for the presenter-control route test."}}


def test_internal_hold_readback_and_actual_same_run_form_gate(store, settings, cases, monkeypatch):
    app = create_app(replace(settings, portal_base_url="https://portals.example"), store)
    headers = {"Authorization": f"Bearer {settings.internal_token}"}
    with TestClient(app) as client:
        app.state.case_service = cases
        controls = MailControls(store.db)
        app.state.mail_service = controls
        created = client.post("/v1/cases", json=road_report())
        assert created.status_code == 201
        case = created.json()
        endpoint = f"/internal/v1/cases/{case['id']}/follow-up-hold"
        assert client.get(endpoint).status_code == 401
        assert client.post(endpoint, json={"held": True}).status_code == 401
        assert client.post("/v1/cases", json={**road_report(), "demoControls": {"holdAuthorityFollowUp": True}}).status_code == 422
        held = client.post(endpoint, json={"held": True}, headers=headers)
        assert held.status_code == 200 and held.json()["held"] is True
        client.post(f"/internal/v1/cases/{case['id']}/fault-next-create", json={"armed": True}, headers=headers).raise_for_status()
        status = client.get(endpoint, headers=headers).json()
        assert status["held"] and status["nextCreateFaultArmed"]
        assert "demoControls" not in client.get(f"/v1/cases/{case['id']}").json()
        assert client.post(endpoint, json={"held": False}, headers=headers).status_code == 409
        approved = client.post(f"/v1/cases/{case['id']}/approve", json={"version": 1})
        assert approved.status_code == 200
        assert client.post(endpoint, json={"held": True}, headers=headers).status_code == 409
        leased = client.post("/internal/v1/jobs/lease", json={"workerId": "route-test", "caseId": case["id"]}, headers=headers).json()
        job, operation = leased["job"], leased["operation"]
        guard = {"workerId": job["workerId"], "leaseToken": job["leaseToken"], "jobId": job["id"]}
        client.post(f"/internal/v1/operations/{operation['id']}/transition", json={**guard, "expectedState": "prepared", "state": "dispatch_started"}, headers=headers).raise_for_status()
        client.post(f"/internal/v1/operations/{operation['id']}/receipt", json={**guard, "receipt": {
            "ticketId": "unit-ticket", "receiptId": "unit-receipt", "runId": case["runId"], "portalId": "roads",
            "clientReference": operation["id"], "payloadDigest": operation["payloadDigest"], "action": "create",
            "acceptedAt": now().isoformat(), "receiptUrl": "https://portals.example/receipt", "ticketUrl": "https://portals.example/ticket"}}, headers=headers).raise_for_status()
        portal_version = [1]
        requests = []
        actual_client = httpx.Client
        def portal(request):
            requests.append(request)
            assert request.url.host == "portals.example"
            assert request.url.path == "/v1/portals/roads/form"
            assert request.url.params["runId"] == case["runId"] and request.url.params["action"] == "update"
            return httpx.Response(200, json={"portalId": "roads", "action": "update", "formVersion": portal_version[0], "snapshotDigest": "a" * 64})
        monkeypatch.setattr("app.main.httpx.Client", lambda **kwargs: actual_client(transport=httpx.MockTransport(portal), **kwargs))
        assert client.post(endpoint, json={"held": False}, headers=headers).status_code == 409
        assert controls.get_authority_followup_hold(case["id"])["held"] is True
        portal_version[0] = 2
        released = client.post(endpoint, json={"held": False}, headers=headers)
        assert released.status_code == 200 and released.json()["held"] is False
        assert released.json()["portalConfirmation"]["snapshotDigest"] == "a" * 64
        assert released.json()["portalConfirmation"]["runId"] == case["runId"]
        assert client.post(endpoint, json={"held": False}, headers=headers).status_code == 200
        assert client.post(endpoint, json={"held": False, "portalUrl": "https://untrusted.example"}, headers=headers).status_code == 422
        assert len(requests) == 3
        stored = store.db.cases.find_one({"id": case["id"]})
        assert stored["version"] == 1 and stored["approvedVersion"] == 1
        assert stored["receipt"]["receiptId"] == "unit-receipt"
        client.post(f"/v1/cases/{case['id']}/cancel", json={}).raise_for_status()
        assert client.get(endpoint, headers=headers).status_code == 409


def test_hold_control_rejects_non_demo(store, settings, cases):
    app = create_app(settings, store)
    with TestClient(app) as client:
        app.state.case_service = cases
        app.state.mail_service = MailControls(store.db)
        case = client.post("/v1/cases", json=road_report()).json()
        store.db.cases.update_one({"id": case["id"]}, {"$set": {"route.demo": False}})
        response = client.post(f"/internal/v1/cases/{case['id']}/follow-up-hold", json={"held": True},
                               headers={"Authorization": f"Bearer {settings.internal_token}"})
        assert response.status_code == 409
