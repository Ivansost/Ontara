import { expect, test, type Page } from '@playwright/test';
import { mkdir, chmod } from 'node:fs/promises';
import { join } from 'node:path';

test.use({ trace: 'off' });
const stamp = '2026-11-14T20:00:00Z';
const submitted = { id: 'scripted_submitted_fixture', purpose: 'RESIDENT_SCRIPTED_SUBMITTED', state: 'QUEUED', deliveryState: 'UNVERIFIED', updatedAt: stamp };
const resolved = { id: 'scripted_resolved_fixture', purpose: 'RESIDENT_SCRIPTED_RESOLVED', state: 'QUEUED', deliveryState: 'UNVERIFIED', updatedAt: stamp };
const base = {
  id: 'case_scripted_email_fixture', issueId: 'roads-pothole', version: 1, stage: 'preparing_report', approvedVersion: 1, currentOperationId: 'op_create_fixture',
  location: { municipalityId: 'milton-town', incidentAddress: 'Synthetic controlled intersection', fixtureId: 'halton-regional-road', confirmed: true },
  answers: {}, reporter: null, route: { id: 'route_fixture', demo: true, recipient: { id: 'halton-region', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'https://fixture.invalid' }, reason: 'Controlled fixture.', sources: [] },
  notifications: { email: 'scripted-fixture@example.invalid', consent: true }, scriptedEmailDemo: true, pendingQuestions: [], receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_scripted_fixture',
};
const cue = 'Demo emails simulate city updates: submitted, then resolved. They do not change the actual report status above.';

async function caseFixture(page: Page, initial: Record<string, unknown>, denied = false) {
  const state = { record: initial, writes: [] as string[] };
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    if (request.method() !== 'GET') state.writes.push(path);
    if (denied) return intercepted.fulfill({ status: 403, json: { detail: 'Private case access denied.' } });
    return intercepted.fulfill({ json: path.endsWith('/timeline') ? { events: [] } : state.record });
  });
  return state;
}

test('two scripted email states never supply a receipt or resolve the actual case', async ({ page }) => {
  const state = await caseFixture(page, { ...base, notificationProgress: [submitted] });
  await page.goto('/cases/' + base.id);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sending report');
  await expect(page.getByText(cue, { exact: true })).toBeVisible();
  await expect(page.getByText('Submitted email (simulated)', { exact: true })).toBeVisible();
  await expect(page.getByText('Resolved email (simulated)', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Email queued', { exact: true })).toBeVisible();
  state.record = { ...state.record, notificationProgress: [{ ...submitted, state: 'SENT' }, resolved] };
  await expect(page.getByText('Resolved email (simulated)', { exact: true })).toBeVisible();
  await expect(page.getByText('Email sent — inbox delivery unverified', { exact: true })).toHaveCount(1);
  await expect(page.getByText('Email queued', { exact: true })).toHaveCount(1);
  state.record = { ...state.record, notificationProgress: [{ ...submitted, state: 'SENT' }, { ...resolved, state: 'SENT' }] };
  await expect(page.getByText('Email sent — inbox delivery unverified', { exact: true })).toHaveCount(2);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sending report');
  await expect(page.getByText('Receipt verified', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /resolved|fixed/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Stop future actions', exact: true })).toBeVisible();
  const directory = process.env.ONTARA_SCRIPTED_EMAIL_SCREENSHOT_DIR;
  if (directory) {
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const path = join(directory, 'scripted-email-case.png');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path, fullPage: true, animations: 'disabled' }); await chmod(path, 0o600);
  }
  expect(state.writes).toEqual([]);
});

test('a real filing receipt remains separate from simulated resolved-email delivery', async ({ page }) => {
  const state = await caseFixture(page, { ...base, stage: 'report_acknowledged', receipt: { ticketId: 'DEMO-SCRIPTED-001', receiptId: 'receipt_fixture' }, notificationProgress: [{ ...submitted, state: 'SENT', deliveryState: 'RECEIVED' }, { ...resolved, state: 'SENT', deliveryState: 'RECEIVED' }] });
  await page.goto('/cases/' + base.id);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Report filed');
  await expect(page.getByText('Receipt verified', { exact: true })).toBeVisible();
  await expect(page.getByText('Email delivery verified', { exact: true })).toHaveCount(2);
  await expect(page.getByText(cue, { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: /resolved|fixed/i })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test('scripted admission without mail records invents no queued or sent state', async ({ page }) => {
  await caseFixture(page, { ...base, notificationProgress: [] });
  await page.goto('/cases/' + base.id);
  await expect(page.getByText(cue, { exact: true })).toBeVisible();
  await expect(page.getByText('Email steps will appear here as the demo runs.', { exact: true })).toBeVisible();
  await expect(page.getByText('Email queued', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Submitted email (simulated)', { exact: true })).toHaveCount(0);
});

test('older ordinary notification cases keep their existing presentation', async ({ page }) => {
  await caseFixture(page, { ...base, scriptedEmailDemo: false, notificationProgress: [{ ...submitted, purpose: 'RESIDENT_REPORT_FILED', state: 'SENT' }] });
  await page.goto('/cases/' + base.id);
  await expect(page.getByText('Filing confirmation', { exact: true })).toBeVisible();
  await expect(page.getByText(cue, { exact: true })).toHaveCount(0);
  await expect(page.getByText('Email sent — inbox delivery unverified', { exact: true })).toBeVisible();
});

test('scripted progress remains private to the owning case session', async ({ page }) => {
  const state = await caseFixture(page, { ...base, notificationProgress: [submitted, resolved] }, true);
  await page.goto('/cases/' + base.id);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This private case is unavailable');
  await expect(page.getByText('scripted-fixture@example.invalid', { exact: true })).toHaveCount(0);
  await expect(page.getByText(cue, { exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});
