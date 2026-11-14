import { expect, test, type Page } from '@playwright/test';
import questionBank from '../src/generated/questions.json';
import type { CaseView, RouteRecord } from '../src/lib/contracts';
import { fillAuthoredQuestions } from '../scripts/cloud-qa/ui.mjs';

test.use({ trace: 'off' });
const facts = { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic one-page fixture near the marked intersection.' };
const route: RouteRecord = { id: 'route_fixture', authorityId: 'halton-region', portalId: 'roads', recipient: { id: 'recipient_fixture', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'https://fixture.invalid' }, reason: 'Controlled browser fixture.', sources: [], demo: true };

async function fixture(page: Page, options: { holdCreate?: Promise<void>; loseApprovalResponse?: boolean; changeFollowUpRecipient?: boolean; existing?: Partial<CaseView> } = {}) {
  const state = { creates: 0, patches: 0, approvals: 0, record: undefined as CaseView | undefined };
  const stamp = new Date().toISOString();
  if (options.existing) state.record = { id: 'case_one_page', issueId: 'roads-pothole', version: 1, questionnaireVersion: 'fixture', location: { municipalityId: 'milton-town', upperTierId: 'halton-region', incidentAddress: 'Regional Road 25 at Louis St. Laurent Avenue, Milton', fixtureId: 'halton-regional-road', confirmed: true }, answers: facts, reporter: { name: '', email: '', contactConsent: false }, route, pendingQuestions: [], stage: 'draft', approvedVersion: null, currentOperationId: null, receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_fixture', ...options.existing };
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    const data = request.method() === 'GET' ? undefined : request.postDataJSON();
    if (path === '/v1/session') return intercepted.fulfill({ json: {} });
    if (path === '/v1/routes/preview') return intercepted.fulfill({ json: { route, supported: true, reason: route.reason, urgentHandoff: false, missingAnswers: [], demo: true } });
    if (path === '/v1/cases' && request.method() === 'POST') {
      state.creates += 1;
      await options.holdCreate;
      state.record = { id: 'case_one_page', version: 1, ...data, route, pendingQuestions: [], stage: 'draft', approvedVersion: null, currentOperationId: null, receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_fixture' };
      return intercepted.fulfill({ status: 201, json: state.record });
    }
    if (path.endsWith('/timeline')) return intercepted.fulfill({ json: { events: [] } });
    if (path.endsWith('/follow-up')) {
      expect(data.expectedVersion).toBe(state.record!.version);
      state.record = { ...state.record!, answers: { ...state.record!.answers, ...data.answers }, version: state.record!.version + 1, stage: 'draft', approvedVersion: null, ...(options.changeFollowUpRecipient ? { route: { ...route, recipient: { ...route.recipient, id: 'changed_recipient', name: 'Changed receiving portal — DEMO' } } } : {}) };
      return intercepted.fulfill({ json: state.record });
    }
    if (path.endsWith('/approve')) {
      expect(data.version).toBe(state.record!.version);
      state.approvals += 1;
      state.record = { ...state.record!, approvedVersion: state.record!.version, currentOperationId: 'op_fixture', stage: 'preparing_report', pendingQuestions: [] };
      return options.loseApprovalResponse ? intercepted.abort('failed') : intercepted.fulfill({ json: state.record });
    }
    if (request.method() === 'PATCH') {
      state.patches += 1;
      expect(data.expectedVersion).toBe(state.record!.version);
      state.record = { ...state.record!, ...data, version: state.record!.version + 1, approvedVersion: null };
      return intercepted.fulfill({ json: state.record });
    }
    if (path.includes('/v1/cases/')) return intercepted.fulfill({ json: state.record });
    return intercepted.fulfill({ status: 500, json: { detail: 'Unexpected fixture request.' } });
  });
  return state;
}

async function fillReport(page: Page) {
  await page.goto('/report/roads/road-surface/pothole');
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await fillAuthoredQuestions(page, questionBank.issues['roads-pothole'], facts);
}

test('edits during a background create serialize into the same draft before Send', async ({ page }) => {
  let release!: () => void;
  const state = await fixture(page, { holdCreate: new Promise<void>(resolve => { release = resolve; }) });
  await fillReport(page);
  await expect.poll(() => state.creates).toBe(1);
  await page.getByRole('textbox', { name: /^What did you notice/ }).fill('The latest synthetic observation while the first save is in flight.');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();
  await page.waitForTimeout(750);
  expect(state.patches).toBe(0);
  release();
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  expect(state.creates).toBe(1);
  expect(state.patches).toBe(1);
  expect(state.approvals).toBe(0);
  expect(state.record!.answers.description).toContain('latest synthetic observation');
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/case_one_page$/);
  expect(state.approvals).toBe(1);
  expect(state.record!.approvedVersion).toBe(2);
});

test('an uncertain approval response opens the same case instead of creating another report', async ({ page }) => {
  const state = await fixture(page, { loseApprovalResponse: true });
  await fillReport(page);
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/case_one_page$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sending report');
  expect(state.creates).toBe(1);
  expect(state.approvals).toBe(1);
  await expect(page.getByText('Receipt verified', { exact: true })).toHaveCount(0);
});

test('a changed follow-up recipient is shown before a fresh Send update approval', async ({ page }) => {
  const state = await fixture(page, { changeFollowUpRecipient: true, existing: { stage: 'more_information_needed', receipt: { ticketId: 'DEMO-FIXTURE', receiptId: 'receipt_fixture' }, pendingQuestions: [{ ...questionBank.followUp.nearestLandmark, options: [], visibleWhen: null } as CaseView['pendingQuestions'][number]] } });
  await page.goto('/cases/case_one_page');
  await page.getByRole('textbox', { name: /^What is the nearest landmark/ }).fill('Synthetic community centre sign');
  await page.getByRole('button', { name: 'Send update', exact: true }).click();
  await expect(page.getByText('The saved update changed. Check the details and recipient below before sending.')).toBeVisible();
  expect(state.approvals).toBe(0);
  await expect(page.getByText(/^By selecting Send update, you approve/)).toContainText('Changed receiving portal — DEMO');
  await page.getByRole('button', { name: 'Send update', exact: true }).click();
  await expect.poll(() => state.approvals).toBe(1);
});

test('a previously approved notification address remains read-only when editing', async ({ page }) => {
  await fixture(page, { existing: { notificationSettingsLocked: true, notifications: { email: 'locked-fixture@example.invalid', consent: true } } });
  await page.goto('/cases/case_one_page');
  await page.getByRole('button', { name: 'Review saved report', exact: true }).click();
  const email = page.getByRole('textbox', { name: /^Email for updates/ });
  await expect(email).toHaveValue('locked-fixture@example.invalid');
  await expect(email).toHaveAttribute('readonly', '');
});
