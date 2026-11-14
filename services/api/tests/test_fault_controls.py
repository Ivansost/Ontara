import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import ApprovalRequest, CaseCreate, LeaseRequest
from app.service import DomainError


def graffiti_report():
    return CaseCreate(issueId="graffiti-wall", location={"municipalityId": "milton-town", "upperTierId": "halton-region",
        "fixtureId": "milton-public-wall", "incidentAddress": "Synthetic municipal public wall, Milton", "confirmed": True},
        answers={"immediateDanger": "No", "surfaceType": "Public wall", "offensiveContent": "Not sure", "description": "Synthetic public wall graffiti."})


def test_approval_transfers_one_shot_before_durable_job_is_runnable(cases, store):
    case = cases.create_case("resident", graffiti_report())
    cases.arm_next_create_fault(case["id"], True)
    assert "pendingCreateFault" not in cases.get_case(case["id"], "resident")
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    operation = cases.get_operation_internal(approved["currentOperationId"])
    assert operation["faultPlan"]["armed"] is True and operation["faultPlan"]["scope"] == "case_next_create"
    persisted = store.db.cases.find_one({"id": case["id"]})["pendingCreateFault"]
    assert persisted["armed"] is False and persisted["consumedAt"] and persisted["operationId"] == operation["id"]
    cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    assert store.db.operations.count_documents({"caseId": case["id"]}) == 1
    assert store.db.jobs.count_documents({"caseId": case["id"]}) == 1
    first = cases.lease_job(LeaseRequest(workerId="first-worker", caseId=case["id"]))
    assert first["job"]["faultAfterAcceptance"] is True
    cases.abandon(first["job"]["id"], "first-worker", first["job"]["leaseToken"], {"reason": "test_process_exit"})
    second = cases.lease_job(LeaseRequest(workerId="fresh-worker", caseId=case["id"]))
    assert second["job"]["faultAfterAcceptance"] is False
    with pytest.raises(DomainError):
        cases.arm_next_create_fault(case["id"], True)
    with pytest.raises(DomainError):
        cases.arm_fault(operation["id"], True)


def test_case_fault_rejects_non_demo_and_used_case(cases, store):
    case = cases.create_case("resident", graffiti_report())
    store.db.cases.update_one({"id": case["id"]}, {"$set": {"route.demo": False}})
    with pytest.raises(DomainError):
        cases.arm_next_create_fault(case["id"], True)
    store.db.cases.update_one({"id": case["id"]}, {"$set": {"route.demo": True}})
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    with pytest.raises(DomainError):
        cases.arm_next_create_fault(case["id"], True)
    store.db.operations.update_one({"id": approved["currentOperationId"]}, {"$set": {"action": "update"}})
    with pytest.raises(DomainError):
        cases.arm_fault(approved["currentOperationId"], True)


def test_fault_controls_require_internal_bearer_and_cannot_enter_public_body(store, settings):
    with TestClient(create_app(settings, store)) as client:
        body = graffiti_report().model_dump(by_alias=True)
        assert client.post("/v1/cases", json={**body, "pendingCreateFault": {"armed": True}}).status_code == 422
        created = client.post("/v1/cases", json=body).json()
        endpoint = f"/internal/v1/cases/{created['id']}/fault-next-create"
        assert client.post(endpoint, json={"armed": True}).status_code == 401
        armed = client.post(endpoint, json={"kind": "kill_after_acceptance", "armed": True},
                            headers={"Authorization": f"Bearer {settings.internal_token}"})
        assert armed.status_code == 200 and armed.json()["appliesTo"] == "next_create"
        approved = client.post(f"/v1/cases/{created['id']}/approve", json={"version": 1})
        assert approved.status_code == 200
        op = store.db.operations.find_one({"id": approved.json()["currentOperationId"]})
        assert op["faultPlan"]["armed"] is True
