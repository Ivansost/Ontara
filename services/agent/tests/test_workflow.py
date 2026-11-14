from copy import deepcopy
import pytest
from ontara_agent.workflow import ExecutionWorkflow


class Ledger:
    def __init__(self, state="prepared", action="create"):
        self.operation = {"id": "op-test", "runId": "run-test", "clientReference": "op-test", "payloadDigest": "a" * 64, "state": state, "action": action, "portalId": "roads", "caseId": "case-test", "recipientId": "halton", "payload": {"issueId": "roads-pothole", "location": {"incidentAddress": "Synthetic road"}, "answers": {"description": "Synthetic damage for tests"}}, "route": {}}
        self.events = []
        self.receipts = []
        self.transitions = []

    async def lease(self, worker_id, job_id, case_id):
        return {"job": {"id": "job-test", "workerId": worker_id, "leaseToken": "private-test-guard", "attempt": 1}, "case": {"id": "case-test", "issueId": "roads-pothole"}, "operation": deepcopy(self.operation)}

    async def heartbeat(self, job):
        return {}

    async def event(self, *args, **kwargs):
        self.events.append((args, kwargs))

    async def transition(self, job, op, state, **kwargs):
        self.transitions.append(state)
        op["state"] = state
        self.operation["state"] = state

    async def receipt(self, job, op, receipt, attempt_id):
        self.receipts.append(receipt)

    async def lessons(self, query):
        return {"status": "assistance_required", "candidates": [], "evidence": {"nativeQuery": True}}


class Tools:
    def __init__(self, *, timeout=False, found=True):
        self.calls = []
        self.timeout = timeout
        self.found = found

    async def call(self, action, body):
        self.calls.append(action)
        if action == "inspect":
            return {"status": "observed", "observation": {"formVersion": "1", "fingerprint": "b" * 64, "fields": [{"name": "location", "label": "Location", "type": "text", "required": True}, {"name": "description", "label": "Description", "type": "textarea", "required": True}]}}
        if action == "submit" and self.timeout:
            raise TimeoutError("deliberately ambiguous test result")
        if action == "reconcile" and not self.found:
            return {"status": "not_found", "accepted": False}
        return {"status": "accepted", "accepted": True, "receipt": {"receiptId": "receipt-test"}}


@pytest.mark.parametrize("state", ["dispatch_started", "outcome_unknown", "reconciling"])
async def test_unresolved_operation_reconciles_without_creating_again(state):
    ledger, tools = Ledger(state), Tools()
    result = await ExecutionWorkflow(ledger, tools, None).run({"job_id": "job-test"})
    assert tools.calls == ["reconcile"]
    assert result["status"] == "receipt_verified"
    assert len(ledger.receipts) == 1


async def test_missing_lookup_is_not_permission_to_recreate():
    ledger, tools = Ledger("dispatch_started"), Tools(found=False)
    result = await ExecutionWorkflow(ledger, tools, None).run({"job_id": "job-test"})
    assert tools.calls == ["reconcile"]
    assert result["status"] == "needs_assistance"
    assert not ledger.receipts


async def test_ambiguous_submit_marks_unknown_and_does_not_retry():
    ledger, tools = Ledger(), Tools(timeout=True)
    with pytest.raises(TimeoutError):
        await ExecutionWorkflow(ledger, tools, None).run({"job_id": "job-test"})
    assert tools.calls == ["inspect", "submit"]
    assert ledger.transitions == ["dispatch_started", "outcome_unknown"]
    assert not ledger.receipts


async def test_withheld_lesson_stops_before_model_or_external_update():
    ledger, tools = Ledger(action="update"), Tools()
    class ForbiddenMapper:
        async def propose(self, *args):
            raise AssertionError("Model must not run without eligible retrieved memory")
    result = await ExecutionWorkflow(ledger, tools, ForbiddenMapper()).run({"job_id": "job-test"})
    assert result["status"] == "needs_assistance"
    assert tools.calls == ["inspect"]
    assert "dispatch_started" not in ledger.transitions


async def test_mail_inspection_requests_missing_fact_without_write_authorization():
    from ontara_agent.mapping import MappingProposal
    ledger, tools = Ledger("receipt_verified"), Tools()
    ledger.operation["receipt"] = {"ticketId": "existing-ticket", "updateUrl": "https://demo.invalid/portals/roads/tickets/existing-ticket/update?accessToken=private"}
    original_lease = ledger.lease
    results, questions = [], []
    async def inspection_lease(*args):
        value = await original_lease(*args)
        value["job"].update(kind="follow_up_inspection", readOnly=True, sourceEventId="received-mail-1")
        return value
    async def lessons(query):
        return {"status": "ready", "candidates": [{"id": "verified-1", "verified": True, "knowledgeKind": "verified_rehearsal"}], "evidence": {"nativeQuery": True}}
    async def result(job, status, **kwargs):
        results.append((status, kwargs))
    async def follow_up(*args, **kwargs):
        questions.append((args, kwargs))
    class InspectTools:
        async def call(self, action, body):
            assert action == "inspect" and body["action"] == "update" and body["ticketId"] == "existing-ticket"
            tools.calls.append(action)
            return {"status": "observed", "observation": {"formVersion": "2", "fingerprint": "b" * 64, "fields": [{"name": "roadIntersection", "label": "Road or intersection", "type": "text", "required": True}, {"name": "nearestLandmark", "label": "Nearest landmark", "type": "text", "required": True}]}}
    class Mapper:
        async def propose(self, observation, facts, records):
            return MappingProposal(formFingerprint=observation["fingerprint"], lessonIds=["verified-1"], mappings=[{"fieldName": "roadIntersection", "factId": "location"}], missingFacts=[{"fieldName": "nearestLandmark", "questionId": "nearestLandmark"}], explanation="Current form requires the absent landmark."), {"model": "synthetic-test-model"}
    ledger.lease, ledger.lessons, ledger.inspection_result, ledger.follow_up = inspection_lease, lessons, result, follow_up
    value = await ExecutionWorkflow(ledger, InspectTools(), Mapper()).run({"job_id": "inspection-job"})
    assert value["status"] == "needs_input"
    assert tools.calls == ["inspect"]
    assert not ledger.transitions and not ledger.receipts
    assert ledger.operation["state"] == "receipt_verified"
    assert questions[0][1]["source_event_id"] == "received-mail-1"
    assert results[0][0] == "needs_input"
