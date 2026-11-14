from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage
from .clients import BackendClient, BrowserClient
from .mapping import MappingError, StructuredMapper, approved_facts, initial_mapping, validate_proposal


class ExecutionState(TypedDict, total=False):
    job_id: str | None
    case_id: str | None
    status: str
    operation_id: str
    attempt_id: str
    process_id: int
    messages: list


class ExecutionWorkflow:
    def __init__(self, backend: BackendClient, browser, mapper: StructuredMapper | None):
        self.backend = backend
        self.browser = browser
        self.mapper = mapper
        self.process_birth_id = uuid.uuid4().hex
        self.worker_id = f"executor-{socket.gethostname()}-{os.getpid()}-{self.process_birth_id[:12]}"

    async def _heartbeat(self, job):
        while True:
            await asyncio.sleep(max(3, int(os.environ.get("ONTARA_LEASE_SECONDS", "15")) // 3))
            await self.backend.heartbeat(job)

    async def _browser_call(self, action, body):
        if callable(self.browser):
            return await self.browser(action, body)
        return await self.browser.call(action, body)

    async def _assistance(self, job, op, attempt_id, reason):
        if op["state"] not in {"needs_assistance", "receipt_verified", "stopped"}:
            await self.backend.transition(job, op, "needs_assistance", attempt_id=attempt_id, evidence={"reason": reason})
        return {"status": "needs_assistance", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}

    async def run(self, state: ExecutionState) -> ExecutionState:
        envelope = await self.backend.lease(self.worker_id, state.get("job_id"), state.get("case_id"))
        job = envelope.get("job")
        if not job:
            return {"status": "no_runnable_job", "process_id": os.getpid()}
        op = envelope["operation"]
        case = envelope["case"]
        attempt_id = f"attempt-{uuid.uuid4().hex}"
        control_fd = os.environ.get("ONTARA_SUPERVISOR_CONTROL_FD")
        if control_fd:
            # Private parent/child pipe, never stdout/presenter evidence. It lets
            # the surviving supervisor release this exact dead child's lease.
            os.write(int(control_fd), (json.dumps({"jobId": job["id"], "caseId": case["id"], "operationId": op["id"], "workerId": job["workerId"], "leaseToken": job["leaseToken"], "processId": os.getpid(), "attemptId": attempt_id}) + "\n").encode())
            os.close(int(control_fd))
        await self.backend.event(case["id"], "execution_process_started", "Execution process acquired the approved operation.", op=op, attempt_id=attempt_id, data={"processId": os.getpid(), "processBirthId": self.process_birth_id, "workerId": self.worker_id, "jobAttempt": job.get("attempt"), "runtimeMode": os.environ.get("ONTARA_RUNTIME_MODE", "engine"), "fence": job.get("fence")})
        heartbeat = asyncio.create_task(self._heartbeat(job))
        work = asyncio.create_task(self._run_leased(job, op, case, envelope.get("approvedVersion") or {}, attempt_id))
        try:
            done, _ = await asyncio.wait({heartbeat, work}, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                # Losing a lease prevents this process from taking further steps.
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work
                await heartbeat
                raise RuntimeError("Lease heartbeat stopped unexpectedly")
            return await work
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _run_leased(self, job, op, case, approved, attempt_id):
        context = {"operationId": op["id"], "caseId": case["id"], "runId": op["runId"], "attemptId": attempt_id, "portalId": op["portalId"], "clientReference": op["clientReference"], "payloadDigest": op["payloadDigest"], "action": op["action"], "ticketId": op.get("externalTicketId"), "updateUrl": op.get("updateUrl") or (op.get("route") or {}).get("updateUrl")}
        if case.get("cancelledAt") or case.get("stage") in {"cancelled", "stopped"}:
            return await self._assistance(job, op, attempt_id, "case_cancelled")
        if job.get("kind") in {"follow_up_inspection", "followup_inspection"}:
            return await self._inspect_follow_up(job, op, case, approved, attempt_id, context)
        if job.get("readOnly"):
            raise ValueError("Unknown read-only job kind")
        if op["state"] == "receipt_verified":
            return {"status": "receipt_verified", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}
        if op["state"] != "prepared":
            # The application ledger wins over graph replay/checkpoint position.
            if op["state"] != "reconciling":
                await self.backend.transition(job, op, "reconciling", attempt_id=attempt_id, evidence={"reason": "unresolved_operation_on_fresh_attempt"})
            result = await self._browser_call("reconcile", context)
            await self.backend.event(case["id"], "receiving_lookup", "Checked the receiving portal using the original operation reference.", op=op, attempt_id=attempt_id, data=result.get("evidence", {}) | {"status": result["status"]})
            if result.get("accepted") and result.get("receipt"):
                await self.backend.receipt(job, op, result["receipt"], attempt_id)
                return {"status": "receipt_verified", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}
            return await self._assistance(job, op, attempt_id, "receiving_outcome_could_not_be_established_no_retry")
        try:
            inspection = await self._browser_call("inspect", context)
            observation = inspection.get("observation")
            if inspection["status"] != "observed" or not observation:
                return await self._assistance(job, op, attempt_id, "receiving_form_unavailable")
            await self.backend.event(case["id"], "form_observed", "Inspected the current receiving form before execution.", op=op, attempt_id=attempt_id, data={"observation": observation})
            payload = op.get("payload") or approved.get("payload") or approved
            facts = approved_facts(payload)
            if op["action"] == "create":
                values = initial_mapping(observation, facts)
                mapping_evidence = {"kind": "authored_v1", "factIds": sorted(values), "formFingerprint": observation["fingerprint"]}
            else:
                values, missing, mapping_evidence = await self._map_changed_form(job, op, case, payload, attempt_id, observation, facts)
                if missing:
                    await self.backend.follow_up(case["id"], op, missing, "The receiving form requires an approved nearest landmark before this update can be sent.", observation["fingerprint"])
                    return await self._assistance(job, op, attempt_id, "awaiting_authored_answer_and_new_approval")
            if job.get("faultAfterAcceptance") and os.environ.get("ONTARA_ENABLE_DEMO_FAULTS") != "1":
                return await self._assistance(job, op, attempt_id, "demo_process_fault_not_enabled")
            # Refresh the live lease immediately before the external side effect.
            await self.backend.heartbeat(job)
            await self.backend.transition(job, op, "dispatch_started", attempt_id=attempt_id, evidence={"processId": os.getpid(), "processBirthId": self.process_birth_id, "formFingerprint": observation["fingerprint"], "mappedFieldNames": sorted(values), "mapping": mapping_evidence, "faultIntentConsumed": bool(job.get("faultAfterAcceptance"))})
            result = await self._browser_call("submit", context | {"formFingerprint": observation["fingerprint"], "values": values, "returnReceipt": not bool(job.get("faultAfterAcceptance"))})
            if result.get("accepted") and job.get("faultAfterAcceptance"):
                # Actual OS process death. No receipt is parsed or recorded in the
                # fault path. HTTP cancellation/tab closure is never used as proof.
                os.kill(os.getpid(), signal.SIGKILL)
                raise RuntimeError("SIGKILL unexpectedly returned")
            if result.get("accepted") and result.get("receipt"):
                await self.backend.receipt(job, op, result["receipt"], attempt_id)
                return {"status": "receipt_verified", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}
            await self.backend.transition(job, op, "outcome_unknown", attempt_id=attempt_id, evidence={"reason": "external_result_unverified", "toolStatus": result.get("status")})
            return {"status": "outcome_unknown", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}
        except (MappingError, ValueError) as error:
            return await self._assistance(job, op, attempt_id, str(error))
        except Exception as error:
            # The exception type is safe evidence; never emit private requests,
            # headers, provider errors or payloads through stdout/traces.
            if op["state"] == "dispatch_started":
                with contextlib.suppress(Exception):
                    await self.backend.transition(job, op, "outcome_unknown", attempt_id=attempt_id, evidence={"errorType": type(error).__name__, "reason": "ambiguous_tool_outcome"})
            raise

    async def _map_changed_form(self, job, op, case, payload, attempt_id, observation, facts):
        route = op.get("route") or {}
        observed_requirements = "; ".join(f"{f['label']} ({f['type']}, {'required' if f.get('required') else 'optional'})" for f in observation["fields"] if f["type"] != "hidden")
        query = {"query": "Adapt a changed municipal follow-up form while updating the existing ticket using only approved facts. The previous report stored a combined incident location. Current observed controls: " + observed_requirements, "authorityId": route.get("authorityId") or op.get("recipientId"), "issueId": payload.get("issueId") or case.get("issueId"), "portalId": op["portalId"], "workflowKind": "ticket_update", "formFamily": "roads-follow-up" if op["portalId"] == "roads" else "graffiti-follow-up", "formVersion": observation["formVersion"]}
        if job.get("withholdLessonIds"):
            # Only an authenticated presenter-created diagnostic inspection job
            # can supply this policy; resident inputs do not enter this field.
            query["withholdLessonIds"] = job["withholdLessonIds"]
        retrieval = await self.backend.lessons(query)
        lessons = retrieval.get("candidates", [])
        await self.backend.event(case["id"], "procedural_memory_retrieved", "Retrieved scoped procedural experience for the changed form.", op=op, attempt_id=attempt_id, data={"retrieval": retrieval.get("evidence", {}), "candidateIds": [l["id"] for l in lessons], "status": retrieval.get("status")})
        if retrieval.get("status") != "ready" or not lessons:
            raise MappingError("applicable_verified_lesson_unavailable")
        if not self.mapper:
            raise MappingError("generation_provider_unavailable")
        proposal, model_evidence = await self.mapper.propose(observation, facts, lessons)
        values, missing = validate_proposal(proposal, observation, facts, lessons)
        mapping_evidence = model_evidence | {"kind": "model_mapping", "formFingerprint": observation["fingerprint"], "selectedLessonIds": proposal.lessonIds, "mappedFactIds": [m.factId for m in proposal.mappings], "missingQuestionIds": missing}
        await self.backend.event(case["id"], "changed_form_mapping_validated", "Validated the proposed field mapping against approved facts and the current form.", op=op, attempt_id=attempt_id, data=mapping_evidence)
        return values, missing, mapping_evidence

    async def _inspect_follow_up(self, job, op, case, approved, attempt_id, context):
        receipt = op.get("receipt") or {}
        context = context | {"action": "update", "ticketId": receipt.get("ticketId"), "updateUrl": receipt.get("updateUrl")}
        evidence = {"readOnly": True, "sourceEventId": job.get("sourceEventId"), "processId": os.getpid(), "attemptId": attempt_id}
        try:
            if op["state"] != "receipt_verified" or not context["ticketId"] or not context["updateUrl"]:
                raise MappingError("Original verified ticket is required for follow-up inspection")
            inspection = await self._browser_call("inspect", context)
            observation = inspection.get("observation")
            if inspection.get("status") != "observed" or not observation:
                raise MappingError("receiving_form_unavailable")
            await self.backend.event(case["id"], "follow_up_form_observed", "Inspected the changed receiving form after a verified authority message.", op=op, attempt_id=attempt_id, data={"observation": observation, "readOnly": True, "sourceEventId": job.get("sourceEventId")})
            payload = op.get("payload") or approved.get("payload") or approved
            values, missing, mapping_evidence = await self._map_changed_form(job, op, case, payload, attempt_id, observation, approved_facts(payload))
            evidence.update(mapping=mapping_evidence, formFingerprint=observation["fingerprint"])
            status = "needs_input" if missing else "ready"
            reason = "The current receiving form needs an approved nearest landmark." if missing else "The current form can be mapped using approved facts. An approved update operation is still required before any write."
            if missing:
                await self.backend.follow_up(case["id"], op, missing, reason, observation["fingerprint"], source_event_id=job.get("sourceEventId"), ticket_id=context["ticketId"])
            await self.backend.inspection_result(job, status, question_ids=missing, reason=reason, evidence=evidence)
            return {"status": status, "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}
        except (MappingError, ValueError) as error:
            await self.backend.inspection_result(job, "needs_assistance", reason=str(error), evidence=evidence)
            return {"status": "needs_assistance", "operation_id": op["id"], "attempt_id": attempt_id, "process_id": os.getpid()}


def build_graph(workflow: ExecutionWorkflow, checkpointer=None, finish=None):
    graph = StateGraph(ExecutionState)
    async def execute(state):
        result = await workflow.run(state)
        if finish:
            finish()
        return result | {"messages": [AIMessage(content=json.dumps({k: result[k] for k in ("status", "operation_id", "attempt_id", "process_id") if k in result}))]}
    graph.add_node("execute_approved_operation", execute)
    graph.add_edge(START, "execute_approved_operation")
    graph.add_edge("execute_approved_operation", END)
    return graph.compile(checkpointer=checkpointer)
