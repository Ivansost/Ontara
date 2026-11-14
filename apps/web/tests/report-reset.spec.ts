import { expect, test, type Page } from '@playwright/test';
import questionBank from '../src/generated/questions.json';
import { fillAuthoredQuestions } from '../scripts/cloud-qa/ui.mjs';
import type { CaseView, RouteRecord } from '../src/lib/contracts';

test.use({ trace: 'off' });
const facts = { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic report before starting another report.' };
const destination: RouteRecord = { id: 'route_reset_fixture', authorityId: 'halton-region', portalId: 'roads', recipient: { id: 'recipient_reset_fixture', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'https://fixture.invalid' }, reason: 'Controlled fixture.', sources: [], demo: true };
const topReport = (page: Page) => page.getByRole('navigation', { name: 'Ontara navigation' }).getByRole('link', { name: 'Report a problem', exact: true });

async function fixtures(page: Page, holdFirst?: Promise<void>) {
  const records = new Map<string, CaseView>();
  const requests: { path: string; method: string }[] = [];
  const creates: string[] = [];
  const approvals: string[] = [];
  let heldResponseFinished = false;
  const stamp = new Date().toISOString();
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    requests.push({ path, method: request.method() });
    const data = request.method() === 'GET' ? undefined : request.postDataJSON();
    if (path === '/v1/session') return intercepted.fulfill({ json: {} });
    if (path === '/v1/routes/preview') return intercepted.fulfill({ json: { supported: true, route: destination, reason: destination.reason, missingAnswers: [], urgentHandoff: false, demo: true } });
    if (path === '/v1/cases' && request.method() === 'POST') {
      const id = 'case_reset_' + (creates.length + 1);
      creates.push(id);
      const record: CaseView = { id, version: 1, ...data, route: destination, stage: 'draft', pendingQuestions: [], receipt: null, approvedVersion: null, currentOperationId: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_' + id };
      records.set(id, record);
      if (creates.length === 1 && holdFirst) { await holdFirst; heldResponseFinished = true; }
      return intercepted.fulfill({ status: 201, json: record });
    }
    if (path.endsWith('/timeline')) return intercepted.fulfill({ json: { events: [] } });
    const id = path.split('/')[3];
    const record = records.get(id);
    if (!record) return intercepted.fulfill({ status: 404, json: { detail: 'Fixture case not found.' } });
    if (path.endsWith('/approve')) {
      expect(data.version).toBe(record.version);
      approvals.push(id);
      const approved = { ...record, stage: 'preparing_report', approvedVersion: record.version, currentOperationId: 'op_' + id };
      records.set(id, approved);
      return intercepted.fulfill({ json: approved });
    }
    if (request.method() === 'PATCH') {
      expect(data.expectedVersion).toBe(record.version);
      const patched = { ...record, ...data, version: record.version + 1, approvedVersion: null };
      records.set(id, patched);
      return intercepted.fulfill({ json: patched });
    }
    return intercepted.fulfill({ json: record });
  });
  return { records, requests, creates, approvals, get heldResponseFinished() { return heldResponseFinished; } };
}

async function openPothole(page: Page) {
  await page.getByRole('heading', { level: 2, name: 'Roads, Sidewalks & Traffic', exact: true }).click();
  await page.getByRole('heading', { level: 2, name: 'Road surface', exact: true }).click();
  await page.getByRole('heading', { level: 2, name: 'Pothole', exact: true }).click();
}
async function fillReport(page: Page, description = facts.description, email = 'previous-fixture@example.invalid') {
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await fillAuthoredQuestions(page, questionBank.issues['roads-pothole'], { ...facts, description });
  await page.getByRole('textbox', { name: /^Email for updates/ }).fill(email);
}
async function expectEmpty(page: Page) {
  await expect(page.getByRole('textbox', { name: /^Incident address or intersection/ })).toHaveValue('');
  await expect(page.getByRole('button', { name: /^Municipality or region/ })).toContainText('Choose the incident municipality');
  await expect(page.getByRole('checkbox', { name: /^I confirm this is the incident location/ })).not.toBeChecked();
  await expect(page.getByRole('radio', { name: 'No', exact: true })).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();
}

test('top report link clears a saved draft while normal report Back preserves it', async ({ page }) => {
  const state = await fixtures(page);
  await page.goto('/report/roads/road-surface/pothole');
  await fillReport(page);
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  await page.getByRole('link', { name: 'Back', exact: true }).click();
  await page.getByRole('heading', { level: 2, name: 'Pothole', exact: true }).click();
  await expect(page.getByRole('textbox', { name: /^What did you notice/ })).toHaveValue(facts.description);
  await expect(page.getByRole('textbox', { name: /^Email for updates/ })).toHaveValue('previous-fixture@example.invalid');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  expect(state.creates).toHaveLength(1);

  await topReport(page).click();
  await expect(page).toHaveURL(/\/report$/);
  await openPothole(page);
  await expectEmpty(page);
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await expect(page.getByRole('textbox', { name: /^What did you notice/ })).toHaveValue('');
  await expect(page.getByRole('textbox', { name: /^Email for updates/ })).toHaveValue('');
  expect(state.creates).toHaveLength(1);
  expect(state.approvals).toEqual([]);
});

test('top report link resets even when the current route is already /report', async ({ page }) => {
  await fixtures(page);
  await page.goto('/report/roads/road-surface/pothole');
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await page.getByRole('textbox', { name: /^Email for updates/ }).fill('same-route-fixture@example.invalid');
  await page.getByRole('navigation', { name: 'Report path' }).getByRole('link', { name: 'Report a problem', exact: true }).click();
  await expect(page).toHaveURL(/\/report$/);
  await topReport(page).click();
  await openPothole(page);
  await expectEmpty(page);
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await expect(page.getByRole('textbox', { name: /^Email for updates/ })).toHaveValue('');
});

test('a held old save cannot restore fields or case association after reset', async ({ page }) => {
  let release!: () => void;
  const state = await fixtures(page, new Promise<void>(resolve => { release = resolve; }));
  await page.goto('/report/roads/road-surface/pothole');
  await fillReport(page);
  await expect.poll(() => state.creates.length).toBe(1);
  await topReport(page).click();
  await expect(page).toHaveURL(/\/report$/);
  await openPothole(page);
  await expectEmpty(page);
  await fillReport(page, 'Synthetic fresh report after the reset.', 'fresh-fixture@example.invalid');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  expect(state.creates).toEqual(['case_reset_1', 'case_reset_2']);
  release();
  await expect.poll(() => state.heldResponseFinished).toBe(true);
  await page.getByRole('textbox', { name: /^What did you notice/ }).fill('Synthetic fresh report after the older save has returned.');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  await expect(page.getByRole('textbox', { name: /^Email for updates/ })).toHaveValue('fresh-fixture@example.invalid');
  expect(state.requests.filter(request => request.method === 'PATCH').every(request => request.path === '/v1/cases/case_reset_2')).toBe(true);
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/case_reset_2$/);
  expect(state.approvals).toEqual(['case_reset_2']);
  expect(state.records.get('case_reset_1')?.approvedVersion).toBe(null);
});

test('fresh start preserves the owning cookie and existing receipt case', async ({ page, context, baseURL }) => {
  const state = await fixtures(page);
  await context.addCookies([{ name: 'ontara_session', value: 'reset-session-fixture', url: baseURL!, httpOnly: true, sameSite: 'Lax' }]);
  const stamp = new Date().toISOString();
  state.records.set('case_existing', { id: 'case_existing', issueId: 'roads-pothole', version: 1, questionnaireVersion: 'fixture', stage: 'report_acknowledged', location: { municipalityId: 'milton-town', incidentAddress: 'Existing synthetic incident', confirmed: true }, answers: facts, reporter: null, route: destination, pendingQuestions: [], receipt: { ticketId: 'DEMO-EXISTING-001', receiptId: 'receipt_existing' }, approvedVersion: 1, currentOperationId: 'op_existing', createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_existing' });
  await page.goto('/cases/case_existing');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Report filed');
  await topReport(page).click();
  await expect(page).toHaveURL(/\/report$/);
  expect((await context.cookies(baseURL!)).find(cookie => cookie.name === 'ontara_session')?.value).toBe('reset-session-fixture');
  await page.goto('/cases/case_existing');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Report filed');
  await expect(page.getByText('Receipt verified', { exact: true })).toBeVisible();
  expect(state.requests.filter(request => request.method !== 'GET')).toEqual([]);
});
