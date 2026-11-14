from dataclasses import replace
from datetime import timedelta

import httpx

from app.dispatch import DispatchCoordinator
from app.models import ApprovalRequest, CaseCreate, LeaseRequest
from app.storage import now


def test_restart_notifier_rediscovers_expired_leased_job(cases, store, settings, monkeypatch):
    created = cases.create_case("resident", CaseCreate(issueId="graffiti-wall", location={
        "municipalityId": "milton-town", "upperTierId": "halton-region", "fixtureId": "milton-public-wall",
        "incidentAddress": "Synthetic municipal public wall, Milton", "confirmed": True}, answers={
        "immediateDanger": "No", "surfaceType": "Public wall", "offensiveContent": "Not sure", "description": "Synthetic public wall graffiti."}))
    cases.approve(created["id"], "resident", ApprovalRequest(version=1))
    leased = cases.lease_job(LeaseRequest(workerId="dead-process", caseId=created["id"]))
    store.db.jobs.update_one({"id": leased["job"]["id"]}, {"$set": {"leaseUntil": now() - timedelta(seconds=1)}})
    requests = []
    real_client = httpx.Client
    def receive(request):
        requests.append(request)
        return httpx.Response(202, json={"accepted": True})
    monkeypatch.setattr("app.dispatch.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(receive), **kwargs))
    notifier = DispatchCoordinator(store.db, replace(settings, dispatch_url="https://executor.example/internal/v1/run"), cases)
    assert notifier.tick() is True and len(requests) == 1
    assert leased["job"]["id"].encode() in requests[0].content
    # Notification cannot reset an uncertain operation or grant a new lease itself.
    assert store.db.jobs.find_one({"id": leased["job"]["id"]})["state"] == "leased"
    assert notifier.tick() is False
