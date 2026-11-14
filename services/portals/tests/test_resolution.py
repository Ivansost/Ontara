from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import hashlib
from threading import Event
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import mongomock
import pytest

from ontara_portals.config import Settings
from ontara_portals.main import create_app
from ontara_portals.store import Conflict, MongoStore


ADMIN = "resolution-test-presenter-" + "a" * 32
AUTH = {"Authorization": f"Bearer {ADMIN}"}
RUN = "resolution-run-001"


@pytest.fixture
def receiver():
    store = MongoStore(mongomock.MongoClient()["ontara_demo"])
    settings = Settings("mongodb://unused", ADMIN, "resolution-test-signing-" + "b" * 32, "http://testserver")
    with TestClient(create_app(settings, store)) as client:
        yield client, store


def submission(reference="resolution-create-001", **changes):
    return {"runId": RUN, "clientReference": reference,
            "payloadDigest": hashlib.sha256(reference.encode()).hexdigest(), "formVersion": 1,
            "values": {"location": "Synthetic test road", "description": "Synthetic test pothole"}, **changes}


def create(client, reference="resolution-create-001", portal="roads"):
    response = client.post(f"/v1/portals/{portal}/tickets", json=submission(reference))
    assert response.status_code == 201, response.text
    return response.json()


def capability(receipt):
    return {key: values[0] for key, values in parse_qs(urlsplit(receipt["ticketUrl"]).query).items()}


def mark_path(receipt, run=RUN, portal="roads"):
    return f'/internal/v1/runs/{run}/portals/{portal}/tickets/{receipt["ticketId"]}/resolution'


def status(client, receipt, **changes):
    return client.get(f'/v1/portals/roads/tickets/{receipt["ticketId"]}/status',
                      params={**capability(receipt), **changes})


def mark(client, receipt, **changes):
    return client.post(mark_path(receipt), headers=AUTH,
                       json={"resolutionId": "resolution-stable-001", "expectedTicketVersion": 1, **changes})


def update_payload(receipt, reference="resolution-update-001"):
    return submission(reference, accessToken=capability(receipt)["accessToken"],
                      values={"location": "Approved synthetic road", "additionalDetails": "Approved synthetic detail"})


def test_resolution_requires_presenter_auth_and_scoped_existing_acceptance(receiver):
    client, store = receiver
    receipt = create(client)
    body = {"resolutionId": "resolution-stable-001", "expectedTicketVersion": 1}
    for headers in ({}, {"Authorization": "Bearer incorrect"},
                    {"Authorization": f'Bearer {capability(receipt)["accessToken"]}'}):
        assert client.post(mark_path(receipt), headers=headers, json=body).status_code == 401
    assert client.post(mark_path(receipt, run="another-run-001"), headers=AUTH, json=body).status_code == 404
    assert client.post(mark_path({"ticketId": "RDS-NOT-PRESENT"}), headers=AUTH, json=body).status_code == 404
    assert client.post(mark_path(receipt, portal="graffiti"), headers=AUTH, json=body).status_code == 422
    assert client.post(f'/v1/portals/roads/tickets/{receipt["ticketId"]}/resolution', json=body).status_code == 404
    store.tickets.update_one({"ticketId": receipt["ticketId"]}, {"$set": {"receipts": []}})
    assert mark(client, receipt).status_code == 409
    assert "resolution" not in store.tickets.find_one({"ticketId": receipt["ticketId"]})


def test_resolution_rejects_mismatched_acceptance_and_missing_run(receiver):
    client, store = receiver
    receipt = create(client)
    store.tickets.update_one({"ticketId": receipt["ticketId"]}, {"$set": {"receipts.0.ticketId": "RDS-DIFFERENT"}})
    assert mark(client, receipt).status_code == 409
    store.runs.delete_one({"_id": RUN})
    assert mark(client, receipt).status_code == 404


@pytest.mark.parametrize("changes", [
    {"status": "repaired"}, {"isDemo": False}, {"simulated": False}, {"physicalRepairVerified": True},
    {"isDemo": "true"}, {"simulated": 1}, {"physicalRepairVerified": 0},
    {"expectedTicketVersion": 0}, {"expectedTicketVersion": "1"}, {"expectedTicketVersion": True},
    {"resolutionId": "bad id"}, {"resolutionId": 1234}, {"resolvedAt": "caller-invented-time"},
    {"message": "Actually repaired"}, {"ticketId": "RDS-OTHER"},
])
def test_resolution_rejects_invalid_or_contradictory_input(receiver, changes):
    client, store = receiver
    receipt = create(client)
    before = store.tickets.find_one({"ticketId": receipt["ticketId"]})
    assert mark(client, receipt, **changes).status_code == 422
    assert store.tickets.find_one({"ticketId": receipt["ticketId"]}) == before


def test_status_requires_exact_ticket_capability_and_does_not_count_as_lookup(receiver):
    client, store = receiver
    receipt = create(client)
    before = list(store.requests.find())
    read = status(client, receipt)
    assert read.status_code == 200
    assert read.json() == {"runId": RUN, "portalId": "roads", "ticketId": receipt["ticketId"],
                           "ticketVersion": 1, "status": "acknowledged", "isDemo": True,
                           "simulated": True, "physicalRepairVerified": False,
                           "resolution": None, "updateAllowed": True}
    assert status(client, receipt, accessToken="invalid").status_code == 404
    assert status(client, receipt, accessToken=ADMIN).status_code == 404
    assert status(client, receipt, runId="another-run-001").status_code == 404
    assert status(client, {**receipt, "ticketId": "RDS-ABSENT"}).status_code == 404
    assert client.get(f'/v1/portals/roads/tickets/{receipt["ticketId"]}/status', headers=AUTH,
                      params={"runId": RUN}).status_code == 422
    assert client.get(f'/v1/portals/graffiti/tickets/{receipt["ticketId"]}/status',
                      params=capability(receipt)).status_code == 422
    assert list(store.requests.find()) == before


def test_resolution_is_immutable_idempotent_and_changes_only_embedded_record(receiver):
    client, store = receiver
    receipt = create(client)
    unrelated = create(client, reference="unrelated-create-001", portal="graffiti")
    before_ticket = store.tickets.find_one({"ticketId": receipt["ticketId"]})
    before_unrelated = store.tickets.find_one({"ticketId": unrelated["ticketId"]})
    other_collections = {name: list(store.db[name].find()) for name in
                         ("demo_runs", "demo_requests", "demo_form_snapshots", "demo_admin_events")}
    response = mark(client, receipt)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record == {"schemaVersion": 1, "resolutionId": "resolution-stable-001", "runId": RUN,
                      "portalId": "roads", "ticketId": receipt["ticketId"], "resolvedAt": record["resolvedAt"],
                      "status": "resolved", "isDemo": True, "simulated": True,
                      "physicalRepairVerified": False, "ticketVersion": 1,
                      "message": "The simulated demo authority marked this report resolved. Physical repair has not been verified."}
    assert datetime.fromisoformat(record["resolvedAt"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert mark(client, receipt).json() == record
    assert mark(client, receipt, resolutionId="different-resolution-001").status_code == 409
    assert mark(client, receipt, expectedTicketVersion=2).status_code == 409
    read = status(client, receipt).json()
    assert (read["status"], read["updateAllowed"], read["resolution"]) == ("resolved", False, record)
    assert read["ticketVersion"] == record["ticketVersion"]
    rendered = client.get(receipt["ticketUrl"])
    assert "Resolved in demo" in rendered.text
    assert "simulated demo authority" in rendered.text
    assert "Physical repair has not been verified" in rendered.text
    assert "Provide more information for this ticket" not in rendered.text
    after = store.tickets.find_one({"ticketId": receipt["ticketId"]})
    assert after.pop("resolution") == record
    assert after == before_ticket
    assert store.tickets.find_one({"ticketId": unrelated["ticketId"]}) == before_unrelated
    assert {name: list(store.db[name].find()) for name in other_collections} == other_collections


def test_resolution_id_cannot_be_reused_for_another_ticket(receiver):
    client, _ = receiver
    first = create(client)
    second = create(client, reference="second-create-001")
    assert mark(client, first).status_code == 200
    assert mark(client, second).status_code == 409
    assert status(client, second).json()["status"] == "acknowledged"


def test_resolved_ticket_rejects_new_updates_but_replays_exact_old_acceptance(receiver):
    client, store = receiver
    receipt = create(client)
    update = update_payload(receipt)
    path = f'/v1/portals/roads/tickets/{receipt["ticketId"]}/update'
    accepted = client.post(path, json=update)
    assert accepted.status_code == 201
    assert mark(client, receipt).status_code == 409  # Stale ticket version cannot be closed.
    assert client.post(f"/internal/v1/runs/{RUN}/portals/roads/form-version", headers=AUTH,
                       json={"version": 2, "expectedVersion": 1}).status_code == 200
    assert mark(client, receipt, expectedTicketVersion=2).status_code == 200
    before = deepcopy(store.tickets.find_one({"ticketId": receipt["ticketId"]}))
    assert client.get(receipt["updateUrl"]).status_code == 409
    replay = client.post(path, json=update)
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**accepted.json(), "deduplicated": True}
    html_replay = client.post(f'/portals/roads/tickets/{receipt["ticketId"]}/update',
                             data={**{key: update[key] for key in ("runId", "clientReference", "payloadDigest", "accessToken")},
                                   "formVersion": "1", **update["values"]})
    assert html_replay.status_code == 200
    assert accepted.json()["receiptId"] in html_replay.text
    assert client.post(path, json=update_payload(receipt, "new-after-resolution-001")).status_code == 409
    assert client.post(path, json={**update, "values": {"location": "Changed facts"}}).status_code == 409
    assert client.post(path, json={**update, "accessToken": "incorrect"}).status_code == 404
    assert store.tickets.find_one({"ticketId": receipt["ticketId"]}) == before
    assert store.requests.count_documents({"action": "update"}) == 6
    assert len(before["updates"]) == 1


def test_resolution_wins_race_and_prevents_inflight_update_acceptance(receiver, monkeypatch):
    client, store = receiver
    receipt = create(client)
    original_write = store.tickets.find_one_and_update
    reached, release = Event(), Event()

    def delayed_update(query, mutation, **kwargs):
        if "$push" in mutation:
            reached.set()
            assert release.wait(5)
        return original_write(query, mutation, **kwargs)

    monkeypatch.setattr(store.tickets, "find_one_and_update", delayed_update)
    envelope = {**update_payload(receipt), "portalId": "roads"}
    factory = lambda ticket_id, token: {"receiptId": "RCP-INFLIGHT-UPDATE", "acceptedAt": "2026-11-14T20:00:00Z"}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.update_ticket, envelope, envelope["values"], "f" * 64,
                             receipt["ticketId"], capability(receipt)["accessToken"], factory)
        assert reached.wait(5)
        try:
            resolved = store.resolve_ticket(RUN, "roads", receipt["ticketId"], "resolution-race-001", 1)
        finally:
            release.set()
        with pytest.raises(Conflict, match="resolved"):
            future.result(timeout=5)
    ticket = store.tickets.find_one({"ticketId": receipt["ticketId"]})
    assert ticket["version"] == 1 and len(ticket["receipts"]) == 1 and ticket["updates"] == []
    assert ticket["resolution"] == resolved


def test_update_wins_race_and_stale_resolution_does_not_close_changed_ticket(receiver, monkeypatch):
    client, store = receiver
    receipt = create(client)
    original_write = store.tickets.find_one_and_update
    reached, release = Event(), Event()

    def delayed_resolution(query, mutation, **kwargs):
        if "resolution" in mutation.get("$set", {}):
            reached.set()
            assert release.wait(5)
        return original_write(query, mutation, **kwargs)

    monkeypatch.setattr(store.tickets, "find_one_and_update", delayed_resolution)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.resolve_ticket, RUN, "roads", receipt["ticketId"], "resolution-race-001", 1)
        assert reached.wait(5)
        try:
            update = client.post(f'/v1/portals/roads/tickets/{receipt["ticketId"]}/update', json=update_payload(receipt))
            assert update.status_code == 201, update.text
        finally:
            release.set()
        with pytest.raises(Conflict, match="concurrently"):
            future.result(timeout=5)
    ticket = store.tickets.find_one({"ticketId": receipt["ticketId"]})
    assert ticket["version"] == 2 and len(ticket["receipts"]) == 2 and "resolution" not in ticket


def test_identical_concurrent_resolution_marks_return_single_original_record(receiver):
    client, store = receiver
    receipt = create(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.resolve_ticket(RUN, "roads", receipt["ticketId"],
                                                               "resolution-concurrent-001", 1), range(2)))
    assert results[0] == results[1]
    assert store.tickets.count_documents({"resolution.resolutionId": "resolution-concurrent-001"}) == 1
