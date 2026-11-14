import test from 'node:test';
import assert from 'node:assert/strict';
import { controlClient, privateNotificationEmail } from '../scripts/cloud-qa.mjs';
import { assertCreateRecovery, assertChangedFormEvidence, receiptSummary, receivedMail, sentMail, duplicateMailSnapshot } from '../scripts/cloud-qa/evidence.mjs';

function recoveryFixture() {
  const receipt = { ticketId: 'ticket_fixture', receiptId: 'receipt_fixture', clientReference: 'op_create_fixture', payloadDigest: 'digest_fixture', action: 'create', receiptSignature: 'private-capability-fixture', updateUrl: 'private-update-capability-fixture' };
  return {
    caseData: { receipt },
    evidence: {
      operations: [{ id: 'op_create_fixture', action: 'create', state: 'receipt_verified', clientReference: 'op_create_fixture', payloadDigest: 'digest_fixture', receipt }],
      events: [
        { id: 'start_killed', operationId: 'op_create_fixture', kind: 'execution_process_started', data: { attemptId: 'attempt_1', processId: 100, processBirthId: 'birth_1' } },
        { id: 'kill', operationId: 'op_create_fixture', kind: 'worker_process_exited', data: { attemptId: 'attempt_1', exitCode: -9 } },
        { id: 'start_inspection', operationId: 'op_create_fixture', kind: 'execution_process_started', data: { attemptId: 'inspection_1', processId: 101, processBirthId: 'birth_inspection' } },
        { id: 'start_recovered', operationId: 'op_create_fixture', kind: 'execution_process_started', data: { attemptId: 'attempt_2', processId: 102, processBirthId: 'birth_2' } },
        { id: 'lookup', operationId: 'op_create_fixture', kind: 'receiving_lookup', data: { attemptId: 'attempt_2' } },
      ],
    },
  };
}

test('recovery proof joins the actual killed and receiving-lookup attempts', () => {
  const { evidence, caseData } = recoveryFixture();
  const summary = assertCreateRecovery(evidence, caseData);
  assert.equal(summary.killed.attemptId, 'attempt_1');
  assert.equal(summary.recovered.attemptId, 'attempt_2');
  assert.equal(summary.recovered.processBirthId, 'birth_2');
  assert.equal(summary.clientReferenceMatched, true);
  assert.equal(summary.payloadDigestMatched, true);
  assert.ok(!JSON.stringify(summary).includes('digest_fixture'));
  assert.ok(!JSON.stringify(summary).includes('private-capability-fixture'));
  assert.ok(!JSON.stringify(summary).includes('private-update-capability-fixture'));
});

test('a read-only inspection start cannot replace a fresh recovery process', () => {
  const { evidence, caseData } = recoveryFixture();
  evidence.events = evidence.events.filter(event => !['start_recovered', 'lookup'].includes(event.id));
  assert.throws(() => assertCreateRecovery(evidence, caseData), /new attempt must perform receiving-system reconciliation/);
});

test('a same-process attempt cannot pass the crash recovery proof', () => {
  const { evidence, caseData } = recoveryFixture();
  evidence.events.find(event => event.id === 'start_recovered').data.processBirthId = 'birth_1';
  assert.throws(() => assertCreateRecovery(evidence, caseData), /fresh process/);
});

test('changed-form proof requires actual native retrieval and grounded approved landmark mapping', () => {
  const mapping = { provider: 'fixture-provider', model: 'fixture-model', usage: { total_tokens: 7 }, selectedLessonIds: ['lesson_fixture'], mappedFactIds: ['incidentAddress'], missingQuestionIds: ['nearestLandmark'], formFingerprint: 'fingerprint_fixture', proposal: { explanation: 'not included in exported evidence' } };
  const evidence = { events: [
    { id: 'retrieval', kind: 'procedural_memory_retrieved', data: { candidateIds: ['lesson_fixture'], retrieval: { nativeQuery: true, queryExecuted: true, model: 'voyage-4-large', indexName: 'procedural_lessons_autoembed_v1' } } },
    { id: 'missing', kind: 'changed_form_mapping_validated', data: mapping },
    { id: 'complete', kind: 'changed_form_mapping_validated', data: { ...mapping, mappedFactIds: ['incidentAddress', 'nearestLandmark'], missingQuestionIds: [] } },
  ] };
  const summary = assertChangedFormEvidence(evidence);
  assert.equal(summary.missingFact.missingQuestionIds[0], 'nearestLandmark');
  assert.ok(!JSON.stringify(summary).includes('not included in exported evidence'));
  evidence.events[0].data.retrieval.nativeQuery = false;
  assert.throws(() => assertChangedFormEvidence(evidence), /native Voyage/);
});

test('mail requires exact operation correlation and receiving-inbox evidence', () => {
  const item = { id: 'outbox_fixture', caseId: 'case_fixture', operationId: 'op_update_fixture', purpose: 'RESIDENT_NOTIFICATION', state: 'SENT', deliveryState: 'RECEIVED', receivingEvidence: { inboxId: 'inbox_fixture', providerMessageId: 'message_fixture', providerThreadId: 'thread_fixture', evidence: 'message_read_from_controlled_receiving_inbox' } };
  assert.ok(receivedMail({ outbox: [item] }, 'RESIDENT_NOTIFICATION', 'op_update_fixture'));
  assert.equal(receivedMail({ outbox: [item] }, 'RESIDENT_NOTIFICATION', 'op_create_fixture'), null);
  item.deliveryState = 'PENDING';
  assert.equal(receivedMail({ outbox: [item] }, 'RESIDENT_NOTIFICATION', 'op_update_fixture'), null);
  assert.equal(sentMail({ outbox: [item] }, 'RESIDENT_NOTIFICATION', 'op_update_fixture').state, 'SENT');
  assert.ok(!('receiptSignature' in receiptSummary({ ticketId: 'ticket', receiptSignature: 'capability' })));
});

test('notification recipient is optional and read privately without a CLI address argument', async () => {
  assert.equal(await privateNotificationEmail(new Map(), {}), undefined);
  assert.ok(await privateNotificationEmail(new Map(), { ONTARA_QA_NOTIFICATION_EMAIL: 'controlled-fixture@example.invalid' }));
  await assert.rejects(() => privateNotificationEmail(new Map(), { ONTARA_QA_NOTIFICATION_EMAIL: 'bad\nrecipient' }), /valid email/);
});


test('internal process-side client reads native fetch status without exposing authorization', async () => {
  let requested;
  const control = controlClient('https://api.invalid', 'non-secret-test-fixture', async (url, options) => {
    requested = { url, options };
    return new Response(JSON.stringify({ held: true }), { status: 200 });
  });
  assert.deepEqual(await control('/internal/v1/cases/case_fixture/follow-up-hold'), { held: true });
  assert.equal(requested.url, 'https://api.invalid/internal/v1/cases/case_fixture/follow-up-hold');
  assert.equal(requested.options.headers.authorization, 'Bearer non-secret-test-fixture');
  const failed = controlClient('https://api.invalid', 'non-secret-test-fixture', async () => new Response('{}', { status: 503 }));
  await assert.rejects(() => failed('/internal/v1/cases/case_fixture/evidence'), /Internal control request failed \(503\)/);
});

test('duplicate check requires one genuine inspection and exactly one send per purpose', () => {
  const evidence = {
    case: { stage: 'report_acknowledged', version: 2, approvedVersion: 2, receipt: { ticketId: 'ticket_fixture', action: 'update' } },
    operations: [{ id: 'create_fixture', action: 'create', state: 'receipt_verified' }, { id: 'update_fixture', action: 'update', state: 'receipt_verified' }],
    events: [{ id: 'diagnostic_fixture', kind: 'form_inspected', data: { sourceEventId: 'presenter_fixture' } }, { id: 'inspection_fixture', kind: 'form_inspected', data: { sourceEventId: 'received:fixture' } }],
  };
  const status = { messagesStored: 6, outbox: ['AUTHORITY_QUESTION', 'AUTHORITY_RESPONSE', 'RESIDENT_NOTIFICATION'].map((purpose, index) => ({ id: 'mail_fixture_' + index, purpose, operationId: index ? 'update_fixture' : 'create_fixture', attemptCount: 1, state: 'SENT', deliveryState: 'RECEIVED', receivingEvidence: { inboxId: 'inbox_fixture', providerMessageId: 'message_fixture_' + index, providerThreadId: 'thread_fixture', evidence: 'message_read_from_controlled_receiving_inbox' } })) };
  assert.equal(duplicateMailSnapshot(evidence, status).inspectionIds.length, 1);
  const optedInEvidence = { ...evidence, case: { ...evidence.case, notifications: { email: 'private-fixture@example.invalid', consent: true } } };
  const optedInStatus = { messagesStored: 8, outbox: [...status.outbox, ...['RESIDENT_REPORT_FILED', 'RESIDENT_INFORMATION_NEEDED'].map((purpose, index) => ({ id: 'opted_mail_' + index, purpose, operationId: 'create_fixture', attemptCount: 1, state: 'SENT', deliveryState: 'UNVERIFIED' }))] };
  assert.equal(duplicateMailSnapshot(optedInEvidence, optedInStatus).outbox.length, 5);
  status.outbox[0].attemptCount = 2;
  assert.throws(() => duplicateMailSnapshot(evidence, status), /another send/);
  status.outbox[0].attemptCount = 1;
  evidence.events.push({ id: 'duplicate_inspection', kind: 'form_inspected', data: { sourceEventId: 'received:second' } });
  assert.throws(() => duplicateMailSnapshot(evidence, status), /one genuine authority-mail inspection/);
});
