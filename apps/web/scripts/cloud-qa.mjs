#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile, writeFile, rename, mkdir, chmod, realpath, stat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, resolve, relative, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { chromium } from '@playwright/test';
import { prepareDraftThroughUi, reopenDraftReview, approveReviewedReportThroughUi, answerAndApproveLandmarkThroughUi, cancelUnusedDraftThroughUi, readResidentJson } from './cloud-qa/ui.mjs';
import { receiptSummary, assertCreateRecovery, assertChangedFormEvidence, receivedMail, duplicateMailSnapshot } from './cloud-qa/evidence.mjs';

const sourceRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const roadsFacts = { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic cloud QA: a pothole in the northbound travel lane near the marked intersection.' };
const graffitiFacts = { immediateDanger: 'No', surfaceType: 'Public wall', offensiveContent: 'No', description: 'Synthetic cloud QA: graffiti on the marked controlled public wall surface.' };
const out = (event, details = {}) => process.stdout.write(JSON.stringify({ event, ...details }) + '\n');

function options(argv) {
  const action = argv.shift() || 'help';
  const flags = new Map();
  const booleans = new Set(['headed', 'record', 'allow-local', 'recovery-ready', 'recovery-reviewed']);
  for (let i = 0; i < argv.length; i++) {
    assert.ok(argv[i].startsWith('--'), 'Use named CLI options.');
    const key = argv[i].slice(2);
    if (booleans.has(key)) flags.set(key, true);
    else { assert.ok(argv[i + 1] && !argv[i + 1].startsWith('--'), `Option --${key} needs a value.`); flags.set(key, argv[++i]); }
  }
  return { action, flags };
}

function origin(value, allowLocal) {
  assert.ok(value, 'An explicit verified web/API origin is required.');
  const url = new URL(value);
  assert.ok(!url.username && !url.password && !url.search && !url.hash && url.pathname === '/', 'Service configuration must be an origin without credentials or paths.');
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  assert.ok(url.protocol === 'https:' || (allowLocal && local && url.protocol === 'http:'), 'Cloud QA requires HTTPS; local mode must be explicit.');
  return url.origin;
}

async function writePrivateJson(path, value) {
  const temporary = path + '.' + randomUUID() + '.tmp';
  await writeFile(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  await rename(temporary, path);
  await chmod(path, 0o600);
}

async function runDirectory(flags, create) {
  const runId = flags.get('run') || (create ? 'qa_' + new Date().toISOString().replace(/[^0-9TZ]/g, '') + '_' + randomUUID().slice(0, 8) : null);
  assert.ok(runId && /^[a-zA-Z0-9_-]{1,100}$/.test(runId), 'Supply the exact prepared --run ID.');
  const base = resolve(flags.get('state-dir') || join(homedir(), '.config/ontara/cloud-ui-qa'));
  const baseRelative = relative(sourceRoot, base);
  assert.ok(baseRelative.startsWith('..') || isAbsolute(baseRelative), 'QA state must stay outside the repository.');
  await mkdir(base, { recursive: true, mode: 0o700 });
  assert.equal((await stat(base)).mode & 0o077, 0, 'The QA state directory must be owner-only.');
  const directory = resolve(base, runId);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  assert.equal((await stat(directory)).mode & 0o077, 0, 'The QA run directory must be owner-only.');
  const actual = await realpath(directory);
  const inside = relative(sourceRoot, actual);
  assert.ok(inside.startsWith('..') || isAbsolute(inside), 'Browser session state must stay outside the repository.');
  return { runId, directory, manifestPath: join(directory, 'manifest.json'), storagePath: join(directory, 'browser-session.json') };
}

async function readManifest(run) {
  const manifest = JSON.parse(await readFile(run.manifestPath, 'utf8'));
  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.runId, run.runId);
  return manifest;
}

async function internalToken(flags) {
  if (!flags.has('private-env') && process.env.ONTARA_INTERNAL_TOKEN) return process.env.ONTARA_INTERNAL_TOKEN;
  const path = resolve(flags.get('private-env') || join(homedir(), '.config/ontara/cloud.env'));
  const info = await stat(path);
  assert.equal(info.mode & 0o077, 0, 'The private control environment must have owner-only permissions.');
  const input = await readFile(path, 'utf8');
  const match = input.match(/^\s*(?:export\s+)?ONTARA_INTERNAL_TOKEN\s*=\s*(.*?)\s*$/m);
  assert.ok(match, 'The private control environment does not define ONTARA_INTERNAL_TOKEN.');
  let value = match[1];
  if (value.startsWith('"')) {
    try { value = JSON.parse(value); } catch { throw new Error('The private control token could not be parsed.'); }
  } else if (value.startsWith("'")) {
    assert.ok(value.endsWith("'"), 'The private control token could not be parsed.'); value = value.slice(1, -1);
  } else value = value.replace(/\s+#.*$/, '').trim();
  assert.ok(typeof value === 'string' && value.length >= 16, 'The private control token is missing or incomplete.');
  return value;
}

export function controlClient(apiOrigin, token, send = fetch) {
  return async (path, method = 'GET', body) => {
    assert.match(path, /^\/internal\/v1\//, 'Control requests must use internal API paths.');
    const response = await send(apiOrigin + path, {
      method, headers: { accept: 'application/json', authorization: 'Bearer ' + token, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(60_000), redirect: 'error',
    });
    assert.ok(response.ok, `Internal control request failed (${response.status}).`);
    return response.json();
  };
}

async function readiness(webOrigin, apiOrigin) {
  for (const endpoint of [webOrigin + '/api/health', apiOrigin + '/readyz']) {
    const response = await fetch(endpoint, { signal: AbortSignal.timeout(60_000), redirect: 'error' });
    assert.equal(response.status, 200, 'A verified hosted web/API health check is not ready.');
  }
}

async function until(label, milliseconds, read) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    const result = await read();
    if (result) return result;
    await sleep(3000);
  }
  throw new Error('Timed out waiting for ' + label + '. No approval or external action is retried automatically.');
}

async function browserSession(run, flags, restore) {
  // Chrome receives only ordinary OS settings, never the driver's ambient API keys.
  const browserEnvironment = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'USER', 'LOGNAME', 'TZ', '__CF_USER_TEXT_ENCODING', 'DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'SYSTEMROOT', 'WINDIR', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'].filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]]));
  const browser = await chromium.launch({ channel: 'chrome', headless: !flags.has('headed'), env: browserEnvironment });
  const videoDirectory = join(run.directory, 'page-video');
  if (flags.has('record')) { await mkdir(videoDirectory, { recursive: true, mode: 0o700 }); await chmod(videoDirectory, 0o700); }
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, ...(restore ? { storageState: run.storagePath } : {}), ...(flags.has('record') ? { recordVideo: { dir: videoDirectory, size: { width: 1440, height: 1000 } } } : {}) });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  let browserAuthorization = false;
  page.on('request', request => { if (request.headers().authorization) browserAuthorization = true; });
  return {
    browser, context, page,
    async save() { assert.equal(browserAuthorization, false, 'Internal authorization must never enter the resident browser.'); await writePrivateJson(run.storagePath, await context.storageState()); },
    async screenshot(name) { const path = join(run.directory, name + '.png'); await page.screenshot({ path, fullPage: true }); await chmod(path, 0o600); },
    async close() {
      const video = page.video();
      await context.close();
      if (video) { const path = await video.path(); await chmod(path, 0o600); out('page_video_saved', { run: run.runId, path }); }
      await browser.close();
    },
  };
}

function caseSummary(caseData) {
  return { id: caseData.id, runId: caseData.runId, issueId: caseData.issueId, version: caseData.version, stage: caseData.stage, approvedVersion: caseData.approvedVersion, operationId: caseData.currentOperationId, ...(caseData.receipt ? { receipt: receiptSummary(caseData.receipt) } : {}) };
}

async function prepareRoads(run, flags, webOrigin, apiOrigin) {
  try { await stat(run.manifestPath); throw new Error('This run already exists; use its exact continuation stage instead of creating another draft.'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await readiness(webOrigin, apiOrigin);
  const session = await browserSession(run, flags, false);
  try {
    const prepared = await prepareDraftThroughUi(session.page, webOrigin, 'roads-pothole', roadsFacts);
    const manifest = { schemaVersion: 1, runId: run.runId, webOrigin, apiOrigin, phase: 'roads_draft_prepared', preparedAt: new Date().toISOString(), catalogueVersion: prepared.catalogueVersion, questionnaireVersion: prepared.questionnaireVersion, roads: caseSummary(prepared.caseData) };
    await session.screenshot('roads-unapproved-review'); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('roads_draft_prepared', { run: run.runId, ...manifest.roads, approvalSent: false });
    out('coordination_required', { next: 'Parent/Sol2 arm the next-create fault and the deterministic mail hold; Sol4 confirms cloud executor readiness before approve-roads.' });
  } finally { await session.close(); }
}

async function approveRoads(run, flags, manifest, control, timeout) {
  assert.ok(flags.has('recovery-ready'), 'Wait for Sol4 readiness and use --recovery-ready only after its go.');
  assert.equal(manifest.phase, 'roads_draft_prepared');
  const session = await browserSession(run, flags, true);
  try {
    const reviewed = await reopenDraftReview(session.page, manifest.webOrigin, manifest.roads.id);
    const before = await control(`/internal/v1/cases/${reviewed.id}/evidence`);
    assert.equal(before.operations.length, 0, 'No create operation may exist before resident approval.');
    const fault = before.events.filter(event => ['presenter_fault_armed', 'presenter_fault_disarmed'].includes(event.kind)).sort((a, b) => a.createdAt.localeCompare(b.createdAt)).at(-1);
    assert.ok(fault?.data?.armed === true && fault.data.kind === 'kill_after_acceptance', 'Parent/Sol2 must arm the unused draft fault before approval.');
    await assertMailHold(control, reviewed.id);
    await session.screenshot('roads-current-reviewed-version');
    const approved = await approveReviewedReportThroughUi(session.page, reviewed.id);
    manifest.roads = caseSummary(approved); manifest.phase = 'roads_approved'; await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('roads_approved', { run: run.runId, ...manifest.roads });
    await collectInitialReceipt(run, flags, manifest, control, timeout, session);
  } finally { await session.close(); }
}

async function collectInitialReceipt(run, flags, manifest, control, timeout, existingSession) {
  assert.ok(['roads_draft_prepared', 'roads_approved'].includes(manifest.phase), 'Only the existing initial create may be collected.');
  const session = existingSession || await browserSession(run, flags, true);
  try {
    if (!existingSession) await session.page.goto(manifest.webOrigin + '/cases/' + manifest.roads.id);
    const live = await readResidentJson(session.page, `/v1/cases/${manifest.roads.id}`);
    assert.ok(live.approvedVersion !== null && live.currentOperationId, 'No initial approval is recorded; collection never creates approval.');
    manifest.roads = caseSummary(live); manifest.phase = 'roads_approved'; await writePrivateJson(run.manifestPath, manifest);
    const acknowledged = await until('the reconciled initial receipt', timeout, async () => {
      const current = await readResidentJson(session.page, `/v1/cases/${manifest.roads.id}`);
      assert.equal(current.cancelledAt, null, 'The QA case was cancelled.');
      return current.receipt?.action === 'create' ? current : null;
    });
    await session.page.getByText('Receipt verified', { exact: true }).first().waitFor();
    assert.equal(String(acknowledged.receipt.formVersion).replace(/^v/, ''), '1', 'The initial accepted form must still be v1.');
    const held = await until('the durable unsent authority-question hold', timeout, async () => {
      const status = await control(`/internal/v1/cases/${manifest.roads.id}/follow-up-hold`);
      assert.equal(status.held, true, 'Authority mail must remain held until the post-reconcile v2 switch.');
      if (!status.authorityOutbox) return null;
      assert.equal(status.authorityOutbox.state, 'HELD');
      assert.equal(status.authorityOutbox.attemptCount, 0, 'No authority email may be attempted before the v2 release.');
      return status;
    });
    manifest.mailHold = { held: true, authorityOutbox: { id: held.authorityOutbox.id, state: 'HELD', attemptCount: 0 } };
    const evidence = await control(`/internal/v1/cases/${manifest.roads.id}/evidence`);
    manifest.roads = caseSummary(acknowledged); manifest.createRecovery = assertCreateRecovery(evidence, acknowledged); manifest.phase = 'roads_initial_receipt_verified';
    await session.screenshot('roads-reconciled-receipt'); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('roads_initial_receipt_verified', { run: run.runId, ...manifest.roads, recovery: manifest.createRecovery });
    out('coordination_required', { next: 'Stop here. Sol4 verifies receiver counters and fresh process proof, then changes this run from v1 to v2. Release the held genuine authority question only after that change is confirmed.' });
  } finally { if (!existingSession) await session.close(); }
}

async function followUpRoads(run, flags, manifest, control, timeout) {
  assert.ok(flags.has('recovery-reviewed'), 'Sol4 must confirm recovery/counters and the post-reconcile v2 switch first.');
  assert.equal(manifest.phase, 'roads_initial_receipt_verified');
  const landmark = flags.get('landmark');
  assert.ok(typeof landmark === 'string' && landmark.trim().length >= 2, 'Supply the known synthetic resident fact with --landmark. The driver will not invent it.');
  const session = await browserSession(run, flags, true);
  try {
    await session.page.goto(manifest.webOrigin + '/cases/' + manifest.roads.id);
    const held = await control(`/internal/v1/cases/${manifest.roads.id}/follow-up-hold`);
    const release = held.held ? await control(`/internal/v1/cases/${manifest.roads.id}/follow-up-hold`, 'POST', { held: false }) : held;
    assert.equal(release.held, false, 'The API must confirm the same-run v2 release before genuine mail delivery.');
    assert.ok(release.releasedAt && release.portalConfirmation, 'An already released case must retain its actual same-run portal confirmation.');
    manifest.followUpReleasedAt = release.releasedAt;
    manifest.followUpControl = { caseId: release.caseId, held: release.held, releasedAt: release.releasedAt };
    manifest.pendingResidentFact = { questionId: 'nearestLandmark', value: landmark, source: 'known synthetic scenario supplied by coordinator' };
    await writePrivateJson(run.manifestPath, manifest);
    const createOperationId = manifest.createRecovery.operationId;
    const question = await until('genuine authority mail received in the controlled inbox', timeout, async () => {
      const received = receivedMail(await control(`/internal/v1/mail/status?case_id=${encodeURIComponent(manifest.roads.id)}`), 'AUTHORITY_QUESTION', createOperationId);
      if (received) return received;
      await control('/internal/v1/mail/poll', 'POST');
      return null;
    });
    manifest.authorityQuestion = question; await writePrivateJson(run.manifestPath, manifest);
    const waiting = await until('the authored nearest-landmark question', timeout, async () => {
      const current = await readResidentJson(session.page, `/v1/cases/${manifest.roads.id}`);
      if (!current.pendingQuestions?.some(question => question.id === 'nearestLandmark')) return null;
      const evidence = await control(`/internal/v1/cases/${manifest.roads.id}/evidence`);
      const grounded = evidence.events.some(event => event.kind === 'changed_form_mapping_validated' && event.data?.missingQuestionIds?.includes('nearestLandmark') && event.data?.selectedLessonIds?.length > 0 && event.data?.usage?.total_tokens > 0);
      return grounded ? current : null;
    });
    await session.screenshot('roads-authored-landmark-question');
    const pending = waiting.pendingQuestions.find(question => question.id === 'nearestLandmark');
    const approved = await answerAndApproveLandmarkThroughUi(session.page, waiting.id, pending, landmark);
    manifest.roads = caseSummary(approved); manifest.phase = 'roads_update_approved'; await session.save(); await writePrivateJson(run.manifestPath, manifest);
    await collectUpdatedReceipt(run, flags, manifest, control, timeout, session);
  } finally { await session.close(); }
}

async function collectUpdatedReceipt(run, flags, manifest, control, timeout, existingSession) {
  assert.ok(['roads_initial_receipt_verified', 'roads_update_approved'].includes(manifest.phase), 'Collect only this existing Roads update.');
  const session = existingSession || await browserSession(run, flags, true);
  try {
    if (!existingSession) await session.page.goto(manifest.webOrigin + '/cases/' + manifest.roads.id);
    const live = await readResidentJson(session.page, `/v1/cases/${manifest.roads.id}`);
    assert.ok(live.approvedVersion === live.version && live.currentOperationId && live.currentOperationId !== manifest.createRecovery.operationId, 'No new approved update is recorded; collection never creates approval.');
    manifest.roads = caseSummary(live); manifest.phase = 'roads_update_approved'; await writePrivateJson(run.manifestPath, manifest);
    const updated = await until('a verified update to the same ticket', timeout, async () => {
      const current = await readResidentJson(session.page, `/v1/cases/${manifest.roads.id}`);
      if (current.receipt?.action !== 'update') return null;
      assert.equal(current.receipt.ticketId, manifest.createRecovery.receipt.ticketId, 'Follow-up must update the original ticket.');
      assert.notEqual(current.receipt.receiptId, manifest.createRecovery.receipt.receiptId);
      assert.equal(String(current.receipt.formVersion).replace(/^v/, ''), '2', 'The approved follow-up must use the actual changed v2 form.');
      return current;
    });
    const evidence = await control(`/internal/v1/cases/${manifest.roads.id}/evidence`);
    const updateOperations = evidence.operations.filter(operation => operation.action === 'update');
    assert.equal(updateOperations.length, 1, 'One approved follow-up must create one logical update operation.');
    assert.equal(updateOperations[0].state, 'receipt_verified');
    manifest.changedForm = assertChangedFormEvidence(evidence);
    manifest.updateOperationId = updateOperations[0].id;
    const finalMail = await until('genuine update response and resident notification delivery', timeout, async () => {
      const status = await control(`/internal/v1/mail/status?case_id=${encodeURIComponent(manifest.roads.id)}`);
      const authority = receivedMail(status, 'AUTHORITY_RESPONSE', manifest.updateOperationId);
      const resident = receivedMail(status, 'RESIDENT_NOTIFICATION', manifest.updateOperationId);
      if (authority && resident) return { authority, resident };
      await control('/internal/v1/mail/poll', 'POST');
      return null;
    });
    manifest.finalMail = finalMail; manifest.roads = caseSummary(updated); manifest.phase = 'roads_complete'; manifest.completedAt = new Date().toISOString();
    await session.screenshot('roads-same-ticket-updated'); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('roads_complete', { run: run.runId, ...manifest.roads, createOperationId: manifest.createRecovery.operationId, updateOperationId: manifest.updateOperationId, authorityQuestion: manifest.authorityQuestion, finalMail });
  } finally { if (!existingSession) await session.close(); }
}

async function submitGraffiti(run, flags, manifest, control, timeout) {
  assert.equal(manifest.phase, 'roads_complete', 'Roads recovery/follow-up must finish before Graffiti execution.');
  const session = await browserSession(run, flags, true);
  try {
    let draft;
    if (manifest.graffiti) {
      await session.page.goto(manifest.webOrigin + '/cases/' + manifest.graffiti.id);
      const existing = await readResidentJson(session.page, `/v1/cases/${manifest.graffiti.id}`);
      if (existing.approvedVersion !== null) return collectGraffitiReceipt(run, flags, manifest, control, timeout, session);
      draft = await reopenDraftReview(session.page, manifest.webOrigin, manifest.graffiti.id);
    } else {
      const prepared = await prepareDraftThroughUi(session.page, manifest.webOrigin, 'graffiti-wall', graffitiFacts);
      draft = prepared.caseData;
      manifest.graffiti = caseSummary(draft); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    }
    await session.screenshot('graffiti-reviewed');
    const approved = await approveReviewedReportThroughUi(session.page, draft.id);
    manifest.graffiti = caseSummary(approved); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    await collectGraffitiReceipt(run, flags, manifest, control, timeout, session);
  } finally { await session.close(); }
}

async function collectGraffitiReceipt(run, flags, manifest, control, timeout, existingSession) {
  assert.ok(manifest.graffiti?.id, 'A Graffiti case must already exist; do not submit another one.');
  const session = existingSession || await browserSession(run, flags, true);
  try {
    if (!existingSession) await session.page.goto(manifest.webOrigin + '/cases/' + manifest.graffiti.id);
    const acknowledged = await until('the separate Graffiti receipt', timeout, async () => {
      const current = await readResidentJson(session.page, `/v1/cases/${manifest.graffiti.id}`);
      return current.receipt?.action === 'create' ? current : null;
    });
    assert.equal(acknowledged.receipt.portalId, 'graffiti');
    const evidence = await control(`/internal/v1/cases/${manifest.graffiti.id}/evidence`);
    assert.equal(evidence.operations.filter(operation => operation.action === 'create').length, 1);
    await session.page.getByRole('heading', { level: 1, name: 'Report acknowledged', exact: true }).waitFor();
    manifest.graffiti = caseSummary(acknowledged); await session.screenshot('graffiti-receipt'); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('graffiti_complete', { run: run.runId, ...manifest.graffiti });
  } finally { if (!existingSession) await session.close(); }
}

async function cancelUnusedDraft(run, flags, manifest, control) {
  assert.equal(manifest.phase, 'roads_complete');
  assert.ok(manifest.graffiti?.receipt, 'Keep both successful demo cases intact before the separate cancellation check.');
  assert.ok(!manifest.cancelledDraft, 'This run already has its bounded cancellation check.');
  const session = await browserSession(run, flags, true);
  try {
    const prepared = await prepareDraftThroughUi(session.page, manifest.webOrigin, 'roads-pothole', { ...roadsFacts, description: 'Synthetic cancellation-only QA draft. It must never submit to a receiving portal.' });
    manifest.cancelledDraft = caseSummary(prepared.caseData); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    const result = await cancelUnusedDraftThroughUi(session.page, manifest.webOrigin, prepared.caseData.id);
    const evidence = await control(`/internal/v1/cases/${prepared.caseData.id}/evidence`);
    assert.equal(evidence.operations.length, 0, 'A cancelled unused draft must not queue an operation.');
    manifest.cancelledDraft = { ...caseSummary(result.caseData), subsequentApprovalStatus: result.subsequentApprovalStatus, operationCount: 0 };
    await session.screenshot('cancelled-unused-draft'); await session.save(); await writePrivateJson(run.manifestPath, manifest);
    out('unused_draft_cancellation_passed', { run: run.runId, ...manifest.cancelledDraft });
  } finally { await session.close(); }
}

async function checkDuplicateMail(run, manifest, control) {
  assert.equal(manifest.phase, 'roads_complete', 'Only repeat existing work on this completed Roads case.');
  const path = `/internal/v1/cases/${manifest.roads.id}`;
  const statusPath = `/internal/v1/mail/status?case_id=${encodeURIComponent(manifest.roads.id)}`;
  const before = duplicateMailSnapshot(await control(path + '/evidence'), await control(statusPath));
  const released = await control(path + '/follow-up-hold', 'POST', { held: false });
  assert.equal(released.held, false);
  const result = await control('/internal/v1/mail/poll', 'POST');
  const after = duplicateMailSnapshot(await control(path + '/evidence'), await control(statusPath));
  assert.deepEqual(after, before, 'Repeating release and existing-mail catch-up must preserve all completed work.');
  const numbers = value => Object.fromEntries(Object.entries(value || {}).filter(([, item]) => typeof item === 'number'));
  manifest.duplicateMail = { releaseHeld: false, unchanged: true, version: after.version, attemptsPerPurpose: Object.fromEntries(after.outbox.map(item => [item.purpose, item.attemptCount])), messagesStored: after.messagesStored, genuineInspections: after.inspectionIds.length, updateOperations: 1, receiptReplay: numbers(result.receiptReplay), outbox: numbers(result.outbox), poll: numbers(result.poll), checkedAt: new Date().toISOString() };
  await writePrivateJson(run.manifestPath, manifest);
  out('duplicate_mail_passed', manifest.duplicateMail);
}

async function smoke(run, flags, manifest) {
  const session = await browserSession(run, flags, true);
  try {
    await session.page.goto(manifest.webOrigin + '/report');
    assert.equal(await session.page.getByRole('heading', { level: 2 }).count(), 9);
    const widths = [];
    for (const width of [390, 320]) {
      await session.page.setViewportSize({ width, height: 844 });
      assert.equal(await session.page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'The mobile homepage must not overflow.');
      widths.push(width);
      await session.screenshot('homepage-mobile-' + width);
    }
    const cookie = (await session.context.cookies(manifest.webOrigin)).find(cookie => cookie.name === 'ontara_session');
    assert.ok(cookie?.httpOnly && cookie.sameSite === 'Lax' && cookie.path === '/');
    assert.equal(cookie.secure, new URL(manifest.webOrigin).protocol === 'https:');
    const fresh = await session.browser.newContext();
    const other = await fresh.newPage();
    await other.goto(manifest.webOrigin + '/cases/' + manifest.roads.id);
    await other.getByRole('heading', { level: 1, name: 'This private case is unavailable', exact: true }).waitFor();
    await fresh.close();
    const responseStatuses = [];
    for (const headers of [
      { origin: 'https://untrusted.ontara.invalid', 'sec-fetch-site': 'same-origin' },
      { origin: manifest.webOrigin, 'sec-fetch-site': 'cross-site' },
      { origin: manifest.webOrigin, 'sec-fetch-site': 'same-origin' },
    ]) {
      const response = await fetch(manifest.webOrigin + '/api/backend/v1/cases', { method: 'POST', headers: { ...headers, 'content-type': 'application/json' }, body: '{}', redirect: 'error', signal: AbortSignal.timeout(60_000) });
      responseStatuses.push(response.status);
    }
    assert.deepEqual(responseStatuses, [403, 403, 422]);
    manifest.smoke = { mobileWidths: widths, crossSessionDenied: true, writeOriginStatuses: responseStatuses, session: { httpOnly: true, sameSite: 'Lax', secure: cookie.secure, path: '/' } };
    await writePrivateJson(run.manifestPath, manifest); out('smoke_passed', { run: run.runId, ...manifest.smoke });
  } finally { await session.close(); }
}

async function assertMailHold(control, caseId) {
  const status = await control(`/internal/v1/cases/${caseId}/follow-up-hold`);
  assert.equal(status.held, true, 'Parent/Sol2 must persist the authority-question hold before initial approval.');
  assert.equal(status.nextCreateFaultArmed, true, 'The same unused draft must have its next-create crash armed.');
}

export async function main(argv = process.argv.slice(2)) {
  const { action, flags } = options(argv);
  if (action === 'help') {
    process.stdout.write('Ontara staged cloud UI QA\n\nprepare-roads --web HTTPS_ORIGIN --api HTTPS_ORIGIN [--run ID]\napprove-roads --run ID --recovery-ready\ncollect-roads --run ID\nfollow-up-roads --run ID --recovery-reviewed --landmark KNOWN_SYNTHETIC_FACT\ncollect-update --run ID\nsubmit-graffiti --run ID\ncollect-graffiti --run ID\ncancel-draft --run ID\nduplicate-mail --run ID\nsmoke --run ID\ninspect --run ID\n\nPrivate state stays outside the repository. Internal credentials are read process-side from --private-env or ~/.config/ontara/cloud.env; no secrets enter the browser or traces. Read scripts/cloud-qa/RUNBOOK.md before an execution stage.\n');
    return;
  }
  const preparing = action === 'prepare-roads';
  const run = await runDirectory(flags, preparing);
  if (preparing) return prepareRoads(run, flags, origin(flags.get('web'), flags.has('allow-local')), origin(flags.get('api'), flags.has('allow-local')));
  const manifest = await readManifest(run);
  manifest.webOrigin = origin(manifest.webOrigin, flags.has('allow-local')); manifest.apiOrigin = origin(manifest.apiOrigin, flags.has('allow-local'));
  await readiness(manifest.webOrigin, manifest.apiOrigin);
  if (action === 'smoke') return smoke(run, flags, manifest);
  const control = controlClient(manifest.apiOrigin, await internalToken(flags));
  const requestedTimeout = Number(flags.get('timeout-seconds') || 300);
  assert.ok(Number.isFinite(requestedTimeout) && requestedTimeout > 0, 'The timeout must be a positive number of seconds.');
  const timeout = Math.min(900, Math.max(30, requestedTimeout)) * 1000;
  if (action === 'approve-roads') return approveRoads(run, flags, manifest, control, timeout);
  if (action === 'collect-roads') return collectInitialReceipt(run, flags, manifest, control, timeout);
  if (action === 'collect-update') return collectUpdatedReceipt(run, flags, manifest, control, timeout);
  if (action === 'follow-up-roads') return followUpRoads(run, flags, manifest, control, timeout);
  if (action === 'collect-graffiti') return collectGraffitiReceipt(run, flags, manifest, control, timeout);
  if (action === 'cancel-draft') return cancelUnusedDraft(run, flags, manifest, control);
  if (action === 'duplicate-mail') return checkDuplicateMail(run, manifest, control);
  if (action === 'submit-graffiti') return submitGraffiti(run, flags, manifest, control, timeout);
  if (action === 'inspect') {
    const evidence = await control(`/internal/v1/cases/${manifest.roads.id}/evidence`);
    out('recorded_case_state', { run: run.runId, phase: manifest.phase, case: caseSummary(evidence.case), operations: evidence.operations.map(operation => ({ id: operation.id, action: operation.action, state: operation.state, ...(operation.receipt ? { receipt: receiptSummary(operation.receipt) } : {}) })), eventKinds: [...new Set(evidence.events.map(event => event.kind))] });
    return;
  }
  throw new Error('Unknown QA stage. Run the help command.');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { process.stderr.write('Cloud UI QA stopped: ' + String(error.message || 'Unknown failure').split('\n')[0].slice(0, 400) + '\n'); process.exitCode = 1; });
}
