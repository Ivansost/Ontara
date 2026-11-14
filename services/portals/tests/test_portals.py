import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import mongomock
import pytest

from ontara_portals.config import Settings
from ontara_portals.main import create_app
from ontara_portals.store import MongoStore


TOKEN = "test-presenter-token-" + "a" * 32


@pytest.fixture
def receiver():
    database = mongomock.MongoClient()["ontara_demo"]
    store = MongoStore(database)
    settings = Settings("mongodb://unused", TOKEN, "test-receipt-secret-" + "b" * 32, "http://testserver")
    return settings, store


@pytest.fixture
def client(receiver):
    settings, store = receiver
    with TestClient(create_app(settings, store)) as browser:
        yield browser


def submission(run="test-run-0001", reference="operation-create-001", **changes):
    result = {"runId": run, "clientReference": reference, "payloadDigest": hashlib.sha256(reference.encode()).hexdigest(), "formVersion": 1, "values": {"location": "Synthetic Regional Road 25 near Example Drive, northbound curb lane", "description": "Synthetic pothole for the hackathon demonstration"}}
    return {**result, **changes}


def create(client, portal="roads", data=None):
    result = client.post(f"/v1/portals/{portal}/tickets", json=data or submission())
    assert result.status_code == 201, result.text
    return result.json()


def evidence(client, run="test-run-0001"):
    result = client.get(f"/internal/v1/runs/{run}/evidence", headers={"Authorization": f"Bearer {TOKEN}"})
    assert result.status_code == 200, result.text
    return result.json()


def access_token(receipt):
    return parse_qs(urlsplit(receipt["updateUrl"]).query)["accessToken"][0]


def lookup_query(data):
    return {key: data[key] for key in ("runId", "clientReference", "payloadDigest")}


def test_create_and_dedup_count_requests_separately(client):
    first = create(client)
    duplicate = client.post("/v1/portals/roads/tickets", json=submission())
    assert duplicate.status_code == 200
    assert duplicate.json()["receiptId"] == first["receiptId"]
    assert duplicate.json()["ticketId"] == first["ticketId"]
    counts = evidence(client)["portals"]["roads"]
    assert counts["createRequestCount"] == 2
    assert counts["ticketCount"] == 1
    assert duplicate.json()["deduplicated"] is True


@pytest.mark.parametrize("change", ["digest", "values"])
def test_reference_reuse_with_changed_payload_is_conflict(client, change):
    create(client)
    changed = submission()
    if change == "digest":
        changed["payloadDigest"] = "f" * 64
    else:
        changed["values"]["description"] = "Different facts with the same claimed digest"
    result = client.post("/v1/portals/roads/tickets", json=changed)
    assert result.status_code == 409
    counts = evidence(client)["portals"]["roads"]
    assert (counts["createRequestCount"], counts["ticketCount"]) == (2, 1)


def test_exact_receipt_lookup_and_html_evidence(client):
    receipt = create(client)
    result = client.get("/v1/portals/roads/lookup", params=lookup_query(submission()))
    assert result.status_code == 200
    assert result.json()["receiptSignature"] == receipt["receiptSignature"]
    html = client.get(receipt["receiptUrl"])
    assert html.status_code == 200
    match = re.search(r'<script id="ontara-receipt" type="application/json">(.*?)</script>', html.text)
    assert match
    assert json.loads(match[1])["receiptId"] == receipt["receiptId"]
    assert receipt["payloadDigest"] in html.text
    wrong = client.get("/v1/portals/roads/lookup", params={**lookup_query(submission()), "payloadDigest": "0" * 64})
    assert wrong.status_code == 409
    absent = client.get("/v1/portals/roads/lookup", params=lookup_query(submission(reference="unknown-reference")))
    assert absent.status_code == 404
    assert client.get("/v1/portals/graffiti/lookup", params=lookup_query(submission())).status_code == 404


def test_browser_form_creates_real_receipt(client):
    data = submission(reference="browser-create-operation")
    form = client.get("/portals/roads/new", params=lookup_query(data))
    assert 'name="location" required' in form.text
    assert 'name="payloadDigest"' in form.text
    result = client.post("/portals/roads/tickets", data={**lookup_query(data), "formVersion": "1", **data["values"]})
    assert result.status_code == 201
    assert "ontara-receipt" in result.text
    assert evidence(client)["portals"]["roads"]["createRequestCount"] == 1


def test_update_same_ticket_has_own_stable_receipt_and_counters(client):
    first = create(client)
    update = submission(reference="operation-update-001", accessToken=access_token(first), values={"location": "Approved original synthetic location", "additionalDetails": "Approved follow-up"})
    path = f'/v1/portals/roads/tickets/{first["ticketId"]}/update'
    result = client.post(path, json=update)
    assert result.status_code == 201, result.text
    second = result.json()
    assert second["ticketId"] == first["ticketId"]
    assert second["receiptId"] != first["receiptId"]
    assert second["action"] == "update"
    assert client.post(path, json=update).status_code == 200
    lookup = client.get("/v1/portals/roads/lookup", params=lookup_query(update))
    assert lookup.json()["receiptId"] == second["receiptId"]
    counts = evidence(client)["portals"]["roads"]
    assert (counts["createRequestCount"], counts["ticketCount"], counts["updateRequestCount"], counts["acceptedUpdateCount"]) == (1, 1, 2, 1)


def test_update_requires_ticket_capability_and_matching_scope(client):
    first = create(client)
    path = f'/v1/portals/roads/tickets/{first["ticketId"]}/update'
    update = submission(reference="operation-update-unauthorized", values={"location": "Synthetic location"})
    assert client.post(path, json=update).status_code == 404
    assert client.get(first["ticketUrl"].replace(access_token(first), "invalid-token")).status_code == 404
    assert client.post(path, json={**update, "runId": "other-run-001", "accessToken": access_token(first)}).status_code == 404


def test_presenter_auth_and_version_mutation_are_scoped(client):
    first = create(client)
    create(client, data=submission(run="another-run-002"))
    path = "/internal/v1/runs/test-run-0001/portals/roads/form-version"
    assert client.post(path, json={"version": 2, "expectedVersion": 1}).status_code == 401
    assert client.post(path, headers={"Authorization": "Bearer incorrect"}, json={"version": 2, "expectedVersion": 1}).status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert client.post(path, headers=auth, json={"version": 2, "expectedVersion": 1}).status_code == 200
    assert client.post(path, headers=auth, json={"version": 2, "expectedVersion": 1}).status_code == 409
    assert client.post("/internal/v1/runs/missing-run-123/portals/roads/form-version", headers=auth, json={"version": 2, "expectedVersion": 1}).status_code == 404
    assert evidence(client, "another-run-002")["portals"]["roads"]["formVersion"] == 1
    assert client.get("/v1/portals/roads/form", params={"runId": "test-run-0001"}).json()["formVersion"] == 1
    html = client.get(first["updateUrl"])
    assert 'name="nearestLandmark" required' in html.text
    assert 'name="roadIntersection" required' in html.text
    assert 'name="location"' not in html.text
    # An old unfinished update is rejected; no hidden old-form adapter applies.
    update = submission(reference="stale-update-operation", accessToken=access_token(first), values={"location": "Old combined location"})
    update_path = f'/v1/portals/roads/tickets/{first["ticketId"]}/update'
    assert client.post(update_path, json=update).status_code == 409
    update.update(formVersion=2, values={"roadIntersection": "Synthetic Regional Road 25 / Example Drive", "travelDirection": "Northbound", "roadPosition": "At curb"})
    assert client.post(update_path, json=update).status_code == 422
    update["values"]["nearestLandmark"] = "Approved demonstration community sign"
    result = client.post(update_path, json=update)
    assert result.status_code == 201, result.text
    assert result.json()["ticketId"] == first["ticketId"]
    assert evidence(client)["portals"]["roads"]["ticketCount"] == 1


def test_receiver_restart_preserves_receipts_and_form_versions(receiver):
    settings, store = receiver
    with TestClient(create_app(settings, store)) as first_process:
        receipt = create(first_process)
        first_process.post("/internal/v1/runs/test-run-0001/portals/roads/form-version", headers={"Authorization": f"Bearer {TOKEN}"}, json={"version": 2, "expectedVersion": 1})
    with TestClient(create_app(settings, store)) as fresh_process:
        found = fresh_process.get(receipt["receiptUrl"])
        assert found.status_code == 200
        assert receipt["receiptId"] in found.text
        assert 'name="nearestLandmark" required' in fresh_process.get(receipt["updateUrl"]).text
        assert evidence(fresh_process)["portals"]["roads"]["createRequestCount"] == 1


def test_graffiti_uses_separate_synthetic_profile(client):
    data = submission(reference="graffiti-create-operation", values={"location": "Synthetic Milton public wall at Example Park", "description": "Synthetic graffiti for the second category", "surfaceType": "Public wall", "offensiveContent": "Not sure"})
    receipt = create(client, "graffiti", data)
    assert receipt["authorityId"] == "milton-town"
    assert receipt["routeId"] == "milton-graffiti-demo"
    assert receipt["ticketId"].startswith("GRA-")
    assert evidence(client)["portals"]["roads"]["ticketCount"] == 0
    assert evidence(client)["portals"]["graffiti"]["ticketCount"] == 1


def test_evidence_and_validation_do_not_expose_capabilities(client):
    receipt = create(client)
    assert access_token(receipt) not in json.dumps(evidence(client))
    assert client.get("/internal/v1/runs/test-run-0001/evidence").status_code == 401
    invalid = client.post("/v1/portals/roads/tickets", json={**submission(), "accessToken": "private-token" * 30})
    assert invalid.status_code == 422
    assert "private-token" not in invalid.text
    assert client.get(receipt["receiptUrl"]).headers["referrer-policy"] == "no-referrer"


def test_form_snapshot_persisted_and_no_secrets(receiver, client):
    _, store = receiver
    changed = store.snapshots.find_one({"portalId": "roads", "action": "update", "formVersion": 2})
    assert changed["snapshotDigest"]
    assert "nearestLandmark" in changed["html"]
    assert "accessToken" in changed["html"]  # Empty placeholder only.
    assert TOKEN not in changed["html"]
