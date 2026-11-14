import assert from 'node:assert/strict';

const escaped = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const named = value => new RegExp('^' + escaped(value));

/** Read only the resident API through the browser's ordinary cookie session. */
export async function readResidentJson(page, path) {
  assert.match(path, /^\/v1\//, 'Only resident API paths belong in the browser.');
  const result = await page.evaluate(async path => {
    const response = await fetch('/api/backend' + path, { credentials: 'same-origin', cache: 'no-store' });
    return { status: response.status, body: await response.json().catch(() => null) };
  }, path);
  assert.equal(result.status, 200, `Resident API read failed (${result.status}).`);
  return result.body;
}

export function catalogueTrail(nodes, issueId, parents = []) {
  for (const node of nodes) {
    const trail = [...parents, node];
    if (node.id === issueId) return trail;
    const child = catalogueTrail(node.children || [], issueId, trail);
    if (child) return child;
  }
  return null;
}

export async function fillAuthoredQuestions(page, questionnaire, answers) {
  for (const question of questionnaire.questions) {
    if (question.visibleWhen && answers[question.visibleWhen.questionId] !== question.visibleWhen.equals) continue;
    const value = answers[question.id];
    if (value === undefined || value === '') {
      assert.equal(question.required, false, `A required synthetic test fact is missing: ${question.id}.`);
      continue;
    }
    if (question.type === 'select') {
      const option = question.options.find(option => option.value === value);
      assert.ok(option, `The supplied fact is not an authored option: ${question.id}.`);
      assert.ok(!option.urgentHandoff, 'An urgent answer must not enter ordinary submission QA.');
      await page.getByRole('radiogroup', { name: named(question.label) }).getByRole('radio', { name: option.label, exact: true }).check();
    } else if (question.type === 'text' || question.type === 'textarea') {
      await page.getByRole('textbox', { name: named(question.label) }).fill(String(value));
    } else if (question.type === 'date') {
      await page.getByLabel(named(question.label)).fill(String(value));
      await page.getByLabel(named(question.label)).press('Tab');
    } else {
      throw new Error(`The QA driver does not support authored control type ${question.type}.`);
    }
  }
}

/** Create a fresh draft through category cards and form buttons; never approve. */
export async function prepareDraftThroughUi(page, webOrigin, issueId, answers) {
  await page.goto(webOrigin + '/report');
  const catalogue = await readResidentJson(page, '/v1/catalogue');
  const trail = catalogueTrail(catalogue.categories, issueId);
  assert.ok(trail?.at(-1)?.available, 'The selected issue has no active catalogue intake.');
  for (const node of trail) {
    // Clicking the visible card heading uses Astryx's normal clickable surface.
    await page.getByRole('heading', { level: 2, name: node.label, exact: true }).click();
  }
  await page.getByRole('heading', { name: 'Where is the problem?', exact: true }).waitFor();
  const fixture = page.getByRole('button', { name: 'Use synthetic demo location', exact: true });
  assert.equal(await fixture.count(), 1, 'The configured demo fixture is ambiguous.');
  await fixture.click();
  await page.getByRole('checkbox', { name: /^I confirm this is the incident location/ }).check();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.waitForURL(/\/details$/);
  const questionnaire = await readResidentJson(page, '/v1/questions/' + encodeURIComponent(issueId));
  await fillAuthoredQuestions(page, questionnaire, answers);
  const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/backend/v1/cases' && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Review report', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 201, 'Creating a real draft must return HTTP 201.');
  const saved = await response.json();
  await page.waitForURL(/\/review$/);
  await page.getByRole('heading', { name: 'Review and approve', exact: true }).waitFor();
  const approval = page.getByRole('checkbox', { name: /^I approve this report/ });
  assert.equal(await approval.isChecked(), false, 'The resident has not approved the draft.');
  const current = await readResidentJson(page, '/v1/cases/' + encodeURIComponent(saved.id));
  assert.equal(current.stage, 'draft');
  assert.equal(current.approvedVersion, null);
  assert.equal(current.currentOperationId, null);
  assert.ok(current.route.demo && current.route.recipient.name.includes('DEMO'));
  return { caseData: current, catalogueVersion: catalogue.version, questionnaireVersion: questionnaire.version };
}

/** Restore a saved draft using the real private case and edit/review buttons. */
export async function reopenDraftReview(page, webOrigin, caseId) {
  await page.goto(webOrigin + '/cases/' + encodeURIComponent(caseId));
  const current = await readResidentJson(page, '/v1/cases/' + encodeURIComponent(caseId));
  assert.equal(current.stage, 'draft', 'Only an unapproved draft can enter initial approval.');
  assert.equal(current.approvedVersion, null);
  assert.equal(current.currentOperationId, null);
  assert.equal(current.receipt, null);
  await page.getByRole('button', { name: 'Review saved report', exact: true }).click();
  await page.waitForURL(/\/details$/);
  await page.getByRole('button', { name: 'Review report', exact: true }).click();
  await page.waitForURL(/\/review$/);
  await page.getByRole('heading', { name: 'Review and approve', exact: true }).waitFor();
  return readResidentJson(page, '/v1/cases/' + encodeURIComponent(caseId));
}

export async function approveReviewedReportThroughUi(page, caseId) {
  const checkbox = page.getByRole('checkbox', { name: /^I approve this report/ });
  assert.equal(await checkbox.isChecked(), false, 'Fresh review approval must start unchecked.');
  await checkbox.check();
  const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === `/api/backend/v1/cases/${caseId}/approve` && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Approve and send report', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 200, `The reviewed report was not approved (HTTP ${response.status()}).`);
  await page.waitForURL(new RegExp('/cases/' + escaped(caseId) + '$'));
  return response.json();
}

export async function answerAndApproveLandmarkThroughUi(page, caseId, pendingQuestion, landmark) {
  assert.equal(pendingQuestion.id, 'nearestLandmark');
  await page.getByRole('textbox', { name: named(pendingQuestion.label) }).fill(landmark);
  const savePromise = page.waitForResponse(response => new URL(response.url()).pathname === `/api/backend/v1/cases/${caseId}/follow-up` && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Review update', exact: true }).click();
  const saved = await savePromise;
  assert.equal(saved.status(), 200, 'The resident follow-up answer was not saved.');
  await page.getByRole('heading', { name: 'Review this update', exact: true }).waitFor();
  const checkbox = page.getByRole('checkbox', { name: /^I approve sending this update/ });
  assert.equal(await checkbox.isChecked(), false, 'A new fact requires fresh update approval.');
  await checkbox.check();
  const approvePromise = page.waitForResponse(response => new URL(response.url()).pathname === `/api/backend/v1/cases/${caseId}/approve` && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Approve and send update', exact: true }).click();
  const approved = await approvePromise;
  assert.equal(approved.status(), 200, 'The reviewed update was not approved.');
  return approved.json();
}

/** Cancel a separate unused draft in the UI, then probe the rejected approval. */
export async function cancelUnusedDraftThroughUi(page, webOrigin, caseId) {
  await page.goto(webOrigin + '/cases/' + encodeURIComponent(caseId));
  const before = await readResidentJson(page, '/v1/cases/' + encodeURIComponent(caseId));
  assert.equal(before.stage, 'draft');
  assert.equal(before.approvedVersion, null);
  assert.equal(before.currentOperationId, null);
  assert.equal(before.receipt, null);
  await page.getByRole('button', { name: 'Stop future actions', exact: true }).click();
  await page.getByRole('button', { name: 'Stop future actions', exact: true }).last().click();
  await page.getByRole('heading', { level: 1, name: 'Future actions stopped', exact: true }).waitFor();
  const cancelled = await readResidentJson(page, '/v1/cases/' + encodeURIComponent(caseId));
  assert.equal(cancelled.stage, 'cancelled');
  assert.ok(cancelled.cancelledAt);
  assert.equal(await page.getByRole('button', { name: 'Review saved report', exact: true }).count(), 0);
  const rejection = await page.evaluate(async ({ caseId, version }) => {
    const response = await fetch(`/api/backend/v1/cases/${encodeURIComponent(caseId)}/approve`, { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ version }) });
    return response.status;
  }, { caseId, version: cancelled.version });
  assert.equal(rejection, 409, 'Cancellation must be enforced by the API after the UI hides approval.');
  return { caseData: cancelled, subsequentApprovalStatus: rejection };
}
