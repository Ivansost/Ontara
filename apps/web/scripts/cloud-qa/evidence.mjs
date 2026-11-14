import assert from 'node:assert/strict';

export function receiptSummary(receipt) {
  assert.ok(receipt && typeof receipt === 'object', 'A saved receiving-system receipt is required.');
  const keys = ['ticketId', 'receiptId', 'portalId', 'action', 'acceptedAt', 'formVersion'];
  return Object.fromEntries(keys.filter(key => receipt[key] !== undefined).map(key => [key, receipt[key]]));
}

export function assertCreateRecovery(evidence, residentCase) {
  const operations = evidence.operations.filter(operation => operation.action === 'create');
  assert.equal(operations.length, 1, 'Crash recovery must preserve one logical create operation.');
  const operation = operations[0];
  assert.equal(operation.state, 'receipt_verified');
  assert.equal(operation.receipt.ticketId, residentCase.receipt.ticketId);
  assert.equal(operation.clientReference, operation.receipt.clientReference);
  assert.equal(operation.payloadDigest, operation.receipt.payloadDigest);
  const events = evidence.events.filter(event => event.operationId === operation.id);
  const starts = events.filter(event => event.kind === 'execution_process_started');
  const killed = events.find(event => event.kind === 'worker_process_exited' && event.data?.exitCode === -9);
  assert.ok(killed?.data?.attemptId, 'An actual SIGKILL exit with an attempt ID is required.');
  const killedStart = starts.find(event => event.data?.attemptId === killed.data.attemptId);
  assert.ok(killedStart?.data?.processBirthId, 'The killed process start must be recorded.');
  const lookup = events.find(event => event.kind === 'receiving_lookup' && event.data?.attemptId !== killed.data.attemptId && starts.some(start => start.data?.attemptId === event.data?.attemptId));
  assert.ok(lookup?.data?.attemptId, 'A new attempt must perform receiving-system reconciliation.');
  const recoveredStart = starts.find(event => event.data?.attemptId === lookup.data.attemptId);
  assert.ok(recoveredStart?.data?.processBirthId);
  assert.ok(Number.isInteger(killedStart.data.processId) && killedStart.data.processId > 0);
  assert.ok(Number.isInteger(recoveredStart.data.processId) && recoveredStart.data.processId > 0);
  assert.notEqual(recoveredStart.data.processBirthId, killedStart.data.processBirthId, 'Recovery must use a fresh process; a read-only inspection is insufficient.');
  return {
    operationId: operation.id,
    clientReferenceMatched: true,
    payloadDigestMatched: true,
    receipt: receiptSummary(operation.receipt),
    killed: { eventId: killed.id, startEventId: killedStart.id, attemptId: killed.data.attemptId, processId: killedStart.data.processId, processBirthId: killedStart.data.processBirthId, exitCode: -9 },
    recovered: { lookupEventId: lookup.id, startEventId: recoveredStart.id, attemptId: recoveredStart.data.attemptId, processId: recoveredStart.data.processId, processBirthId: recoveredStart.data.processBirthId },
  };
}

export function assertChangedFormEvidence(evidence) {
  const retrievalEvents = evidence.events.filter(event => event.kind === 'procedural_memory_retrieved' && event.data?.retrieval?.nativeQuery === true && event.data?.retrieval?.queryExecuted === true && event.data?.retrieval?.model === 'voyage-4-large');
  assert.ok(retrievalEvents.length, 'Actual native Voyage text-query retrieval must be recorded.');
  const candidateIds = new Set(retrievalEvents.flatMap(event => event.data.candidateIds || []));
  const mappings = evidence.events.filter(event => event.kind === 'changed_form_mapping_validated');
  const missing = mappings.find(event => event.data?.missingQuestionIds?.includes('nearestLandmark'));
  const complete = mappings.find(event => event.data?.missingQuestionIds?.length === 0 && event.data?.mappedFactIds?.includes('nearestLandmark'));
  assert.ok(missing, 'The changed form must record the missing authored landmark question.');
  assert.ok(complete, 'The approved landmark must be mapped without inventing another fact.');
  for (const event of [missing, complete]) {
    assert.ok(event.data.selectedLessonIds?.length, 'A validated mapping must use a selected procedural lesson.');
    assert.ok(event.data.selectedLessonIds.every(id => candidateIds.has(id)), 'Selected lessons must come from recorded native retrieval.');
    assert.ok(event.data.provider && event.data.model && event.data.usage?.total_tokens > 0, 'Actual generation-provider usage must be recorded.');
  }
  const summarize = event => ({ eventId: event.id, provider: event.data.provider, model: event.data.model, usage: event.data.usage, selectedLessonIds: event.data.selectedLessonIds, mappedFactIds: event.data.mappedFactIds, missingQuestionIds: event.data.missingQuestionIds, formFingerprint: event.data.formFingerprint });
  return {
    retrieval: retrievalEvents.map(event => ({ eventId: event.id, candidateIds: event.data.candidateIds, nativeQuery: true, queryExecuted: true, model: event.data.retrieval.model, indexName: event.data.retrieval.indexName })),
    missingFact: summarize(missing),
    approvedMapping: summarize(complete),
  };
}

export function receivedMail(status, purpose, operationId) {
  const item = status.outbox?.find(item => item.purpose === purpose && item.operationId === operationId && item.state === 'SENT' && item.deliveryState === 'RECEIVED' && item.receivingEvidence?.evidence === 'message_read_from_controlled_receiving_inbox');
  if (!item) return null;
  assert.ok(item.receivingEvidence.inboxId && item.receivingEvidence.providerMessageId && item.receivingEvidence.providerThreadId, 'Delivery proof needs exact provider inbox/message/thread IDs.');
  return {
    id: item.id, caseId: item.caseId, operationId: item.operationId, purpose: item.purpose, state: item.state, deliveryState: item.deliveryState,
    providerMessageId: item.providerMessageId, providerThreadId: item.providerThreadId,
    receivingEvidence: { inboxId: item.receivingEvidence.inboxId, providerMessageId: item.receivingEvidence.providerMessageId, providerThreadId: item.receivingEvidence.providerThreadId, evidence: item.receivingEvidence.evidence },
  };
}

export function sentMail(status, purpose, operationId) {
  const item = status.outbox?.find(item => item.purpose === purpose && item.operationId === operationId && item.state === 'SENT');
  if (!item) return null;
  return { id: item.id, caseId: item.caseId, operationId: item.operationId, purpose: item.purpose, state: item.state, deliveryState: item.deliveryState || 'UNVERIFIED' };
}

export function duplicateMailSnapshot(evidence, status) {
  assert.equal(evidence.case.stage, 'report_acknowledged');
  assert.equal(evidence.case.approvedVersion, evidence.case.version);
  assert.equal(evidence.operations.filter(item => item.action === 'create').length, 1);
  assert.equal(evidence.operations.filter(item => item.action === 'update').length, 1);
  assert.ok(evidence.operations.every(item => item.state === 'receipt_verified'));
  const optedIn = Boolean(evidence.case.notifications?.consent);
  const required = ['AUTHORITY_QUESTION', 'AUTHORITY_RESPONSE', 'RESIDENT_NOTIFICATION', ...(optedIn ? ['RESIDENT_REPORT_FILED', 'RESIDENT_INFORMATION_NEEDED'] : [])];
  const allowed = new Set([...required, 'RESIDENT_NEEDS_ASSISTANCE']);
  assert.ok(status.outbox.every(item => allowed.has(item.purpose)), 'Only expected case-mail purposes belong to this proof.');
  if (!optedIn) {
    assert.equal(status.messagesStored, 6, 'Historical blank-email runs retain exactly six stored sender/receiver copies.');
    assert.equal(status.outbox.length, 3);
  }
  assert.ok(required.every(purpose => status.outbox.some(item => item.purpose === purpose)), 'The completed run must retain every applicable mail purpose.');
  const outbox = status.outbox.map(item => {
    assert.equal(item.attemptCount, 1, 'Repeating existing mail work must not attempt another send.');
    assert.ok(optedIn && item.purpose.startsWith('RESIDENT_') ? sentMail(status, item.purpose, item.operationId) : receivedMail(status, item.purpose, item.operationId));
    return { id: item.id, purpose: item.purpose, operationId: item.operationId, providerMessageId: item.providerMessageId, receivingEvidence: item.receivingEvidence, attemptCount: item.attemptCount };
  }).sort((a, b) => a.purpose.localeCompare(b.purpose));
  if (!optedIn) assert.deepEqual(outbox.map(item => item.purpose), required);
  const inspections = evidence.events.filter(item => item.kind === 'form_inspected' && item.data?.sourceEventId?.startsWith('received:'));
  assert.equal(inspections.length, 1, 'Duplicate provider processing must retain one genuine authority-mail inspection.');
  return { version: evidence.case.version, approvedVersion: evidence.case.approvedVersion, receipt: receiptSummary(evidence.case.receipt), operationIds: evidence.operations.map(item => item.id).sort(), outbox, inspectionIds: inspections.map(item => item.id), messagesStored: status.messagesStored };
}
