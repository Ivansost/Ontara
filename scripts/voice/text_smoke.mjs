/** Bounded, real ElevenLabs text-only test. No microphone, audio or submission.
 * The existing Atlas-backed API validates every actual model tool call. The only
 * created case is a synthetic unapproved draft; its actual transcript is linked.
 * Session cookies and signed URLs stay in memory and are never printed.
 */
import assert from 'node:assert/strict';
import { writeFile, chmod } from 'node:fs/promises';

const base = process.env.ONTARA_VOICE_TEST_API || 'http://127.0.0.1:8027';
const origin = new URL(base);
assert(['127.0.0.1', 'localhost', 'ontara-api-35iy.onrender.com'].includes(origin.hostname), 'Choose an Ontara test API');
let cookie = '';
async function api(path, body, useCookie = true) {
  const response = await fetch(base + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { ...(useCookie && cookie ? { cookie } : {}), ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20_000),
  });
  if (useCookie) for (const value of response.headers.getSetCookie()) cookie = value.split(';')[0];
  const result = await response.json();
  if (!response.ok) throw new Error(`Ontara API returned HTTP ${response.status}: ${typeof result.detail === 'string' ? result.detail : 'request rejected'}`);
  return result;
}

await api('/v1/session');
const catalogue = await api('/v1/catalogue');
const fixture = catalogue.demoLocations.find(item => item.fixtureId === 'halton-regional-road');
assert(fixture, 'Configured synthetic Roads fixture required');
const location = { municipalityId: fixture.municipalityId, upperTierId: fixture.upperTierId,
  incidentAddress: fixture.incidentAddress, fixtureId: fixture.fixtureId, confirmed: true };
const issued = await api('/v1/voice/sessions', { requestId: `voice_smoke_${Date.now()}`, issueId: 'roads-pothole',
  location, answers: {}, voiceConsent: true, consentVersion: '2026-11-14.1', mode: 'text' });
let snapshot = issued.session;
const toolCalls = [];
const eventCounts = {};
const answered = new Set();
let reviewSpoken = false;
let receivedConversationId = '';
let receivedAudio = false;
let socket;
try {
  await new Promise((resolve, reject) => {
    let queue = Promise.resolve();
    let settled = false;
    const finish = error => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      socket?.close();
      if (error) reject(error); else resolve();
    };
    const deadline = setTimeout(() => finish(new Error(`Provider text smoke exceeded 90 seconds (events ${JSON.stringify(eventCounts)}; next ${snapshot.nextQuestion?.id || 'none'})`)), 90_000);
    socket = new WebSocket(issued.signedUrl);
    socket.addEventListener('open', () => socket.send(JSON.stringify({
      type: 'conversation_initiation_client_data',
      conversation_config_override: { conversation: { text_only: true } },
      dynamic_variables: { first_question: snapshot.spokenQuestion },
    })));
    socket.addEventListener('error', () => finish(new Error('Provider WebSocket connection failed')));
    socket.addEventListener('close', event => {
      if (!settled) finish(snapshot.status === 'ready_for_review' && reviewSpoken ? undefined : new Error(`Provider disconnected before authored intake and review completed (code ${event.code}; events ${JSON.stringify(eventCounts)}; next ${snapshot.nextQuestion?.id || 'none'})`));
    });
    socket.addEventListener('message', event => {
      queue = queue.then(async () => {
        const data = JSON.parse(String(event.data));
        eventCounts[data.type] = (eventCounts[data.type] || 0) + 1;
        if (data.type === 'audio') { receivedAudio = true; throw new Error('Text-only test unexpectedly received audio'); }
        if (data.type === 'ping') socket.send(JSON.stringify({ type: 'pong', event_id: data.ping_event.event_id }));
        if (data.type === 'conversation_initiation_metadata') {
          receivedConversationId = data.conversation_initiation_metadata_event.conversation_id;
          assert.equal(receivedConversationId, issued.conversationId, 'Provider must use the server-reserved conversation ID');
        }
        if (data.type === 'client_tool_call') {
          const call = data.client_tool_call;
          assert(['get_intake_state', 'record_answer', 'skip_question'].includes(call.tool_name), 'No approval or arbitrary action tools');
          toolCalls.push(call.tool_name);
          let result;
          try {
            if (call.tool_name === 'get_intake_state') result = await api(`/v1/voice/sessions/${snapshot.id}`);
            else result = await api(`/v1/voice/sessions/${snapshot.id}/answers`, { expectedRevision: snapshot.revision,
              questionId: call.parameters.questionId, value: call.tool_name === 'skip_question' ? null : call.parameters.value });
            snapshot = result;
            socket.send(JSON.stringify({ type: 'client_tool_result', tool_call_id: call.tool_call_id, result: JSON.stringify(result), is_error: false }));
          } catch (error) {
            socket.send(JSON.stringify({ type: 'client_tool_result', tool_call_id: call.tool_call_id, result: JSON.stringify({ error: error.message }), is_error: true }));
            throw error;
          }
        }
        if (data.type === 'agent_response') {
          if (snapshot.status === 'ready_for_review') {
            const text = data.agent_response_event.agent_response;
            reviewSpoken = text.includes(snapshot.recipientName) && /review|check/i.test(text);
            if (reviewSpoken) setTimeout(() => finish(), 300);
          } else if (snapshot.nextQuestion && !answered.has(snapshot.nextQuestion.id)) {
            const question = snapshot.nextQuestion;
            const text = data.agent_response_event.agent_response;
            // Require the real agent to ask the authored question before replying.
            if (!text.toLowerCase().includes(question.label.toLowerCase())) return;
            answered.add(question.id);
            let value = question.type === 'select'
              ? (question.id === 'immediateDanger' ? 'No' : question.options.find(option => option.value === 'Not sure')?.value || question.options[0].value)
              : question.type === 'date' ? 'I do not know the date. Please skip this optional question.'
              : 'A synthetic pothole is visible on the controlled demo road beside the test marker.';
            setTimeout(() => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'user_message', text: value })); }, 300);
          }
        }
        if (data.type === 'error' || data.type === 'client_error') throw new Error('Provider returned a conversation error');
      }).catch(finish);
    });
  });
} finally {
  socket?.close();
  // Even an interrupted probe leaves a truthful, recoverable transcript state.
  await api(`/v1/voice/sessions/${snapshot.id}/finish`, {}).catch(() => {});
}
assert.equal(snapshot.status, 'ready_for_review');
assert.equal(receivedAudio, false);
assert(reviewSpoken && receivedConversationId, 'Actual provider conversation and review required');
let finishResult;
for (let attempt = 0; attempt < 5; attempt += 1) {
  finishResult = await api(`/v1/voice/sessions/${snapshot.id}/finish`, {});
  if (finishResult.transcriptStatus === 'saved') break;
  await new Promise(resolve => setTimeout(resolve, 1000));
}
const created = await api('/v1/cases', { issueId: 'roads-pothole', location, answers: snapshot.answers });
assert.equal(created.stage, 'draft');
assert.equal(created.approvedVersion, null);
assert.equal(created.currentOperationId, null);
const linked = await api(`/v1/voice/sessions/${snapshot.id}/bind`, { caseId: created.id, caseVersion: created.version });
assert(linked.linked);
await api(`/v1/voice/sessions/${snapshot.id}/finish`, {});
const history = await api(`/v1/voice/cases/${created.id}/history`);
assert.equal(history.conversations.length, 1);
const record = history.conversations[0];
assert.equal(record.providerConversationId, receivedConversationId);
assert.equal(record.mode, 'text');
assert.equal(record.transcriptStatus, 'saved');
assert(record.transcript.some(turn => turn.role === 'user') && record.transcript.some(turn => turn.role === 'agent'));
assert.equal(record.recording.enabled, false);
assert.equal(record.recording.reference, null);
const after = await api(`/v1/cases/${created.id}`);
assert.equal(after.stage, 'draft');
assert.equal(after.approvedVersion, null);
assert.equal(after.currentOperationId, null);
const denied = await fetch(`${base}/v1/voice/cases/${created.id}/history`, { signal: AbortSignal.timeout(20_000) });
assert.equal(denied.status, 404, 'A fresh browser cannot access the private transcript');
const summary = { checkedAt: new Date().toISOString(), status: 'passed', testMode: 'provider_text_only',
  microphoneUsed: false, audioProduced: receivedAudio, audioRecording: false,
  managedModel: 'gemini-3.5-flash-lite', authoredAnswerIds: Object.keys(snapshot.answers),
  providerToolCalls: toolCalls, providerEventCounts: eventCounts, reviewSpoken,
  atlasTranscriptSaved: true, transcriptTurns: record.transcript.length,
  sameCaseLink: true, crossSessionHistoryDenied: true, approvedVersion: after.approvedVersion,
  operationCreated: Boolean(after.currentOperationId), actualSubmission: false };
console.log(JSON.stringify(summary, null, 2));
if (process.env.ONTARA_VOICE_PROOF_FILE) {
  await writeFile(process.env.ONTARA_VOICE_PROOF_FILE, JSON.stringify({ ...summary, caseId: created.id,
    voiceSessionId: snapshot.id, conversationId: receivedConversationId }, null, 2) + '\n');
  await chmod(process.env.ONTARA_VOICE_PROOF_FILE, 0o600);
}
