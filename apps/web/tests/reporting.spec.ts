import { expect, test } from '@playwright/test';
import catalogue from '../src/generated/catalogue.json';
import questionBank from '../src/generated/questions.json';
import { validateQuestions, type Question } from '../src/lib/catalogue';
import type { CaseView, RouteRecord, TimelineEvent } from '../src/lib/contracts';

// These are explicit browser-contract fixtures. They exercise UI state and
// approvals; they do not claim a live API, mailbox or portal integration.
test('report edits require fresh approval and follow-up stays on the same case', async ({ page }) => {
  const fixture = catalogue.demoLocations[0];
  const route: RouteRecord = {
    id: 'browser-fixture-route', authorityId: 'halton-region', portalId: 'roads',
    recipient: { id: 'browser-fixture-recipient', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'http://demo.invalid/roads' },
    reason: 'Synthetic fixture has an explicit controlled-demo owner profile.',
    sources: [{ title: 'Controlled fixture source', url: 'https://example.invalid/fixture' }], demo: true,
  };
  let record: CaseView;
  const events: TimelineEvent[] = [];
  let approvals = 0;
  const stamp = new Date().toISOString();
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    const data = request.method() === 'GET' ? undefined : request.postDataJSON();
    let body: unknown = {};
    if (path === '/v1/routes/preview') body = { supported: true, reason: route.reason, route, missingAnswers: [], urgentHandoff: false, demo: true };
    else if (path === '/v1/cases' && request.method() === 'POST') {
      record = { id: 'case_browser_fixture', version: 1, ...data, stage: 'draft', route, pendingQuestions: [], approvedVersion: null, currentOperationId: null, receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_browser_fixture' };
      body = record;
    } else if (path.endsWith('/timeline')) body = { events };
    else if (path.endsWith('/evidence')) body = { case: { version: record.version }, operations: [] };
    else if (path.endsWith('/follow-up')) { record = { ...record, answers: { ...record.answers, ...data.answers }, version: record.version + 1, approvedVersion: null, stage: 'draft' }; body = record; }
    else if (path.endsWith('/approve')) {
      if (data.version !== record.version) return intercepted.fulfill({ status: 409, json: { detail: 'The report changed.' } });
      approvals += 1;
      record = { ...record, approvedVersion: record.version, stage: 'preparing_report', pendingQuestions: [] };
      events.push({ id: `event_${approvals}`, caseId: record.id, kind: 'report_approved', message: 'You approved this report version and its named recipient.', createdAt: stamp, visibility: 'resident', data: {} });
      body = record;
    } else if (request.method() === 'PATCH') { record = { ...record, ...data, version: record.version + 1, approvedVersion: null }; body = record; }
    else if (path.includes('/v1/cases/')) body = record;
    await intercepted.fulfill({ status: 200, json: body });
  });

  await page.goto('/report/roads/road-surface/pothole');
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await expect(page.getByRole('textbox', { name: /^Incident address or intersection/ })).toHaveValue(fixture.incidentAddress);
  await expect(page).toHaveURL(/\/pothole$/);
  await expect(page.getByRole('radio', { name: 'In travel lane', exact: true })).toHaveCount(0);
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await page.getByRole('radio', { name: 'In travel lane', exact: true }).check();
  await page.getByRole('radio', { name: 'Northbound', exact: true }).check();
  await page.getByRole('textbox', { name: /^What did you notice/ }).fill('A pothole in the northbound lane near the intersection.');
  await page.getByRole('textbox', { name: /^Email for updates/ }).fill('resident-fixture@example.invalid');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  await expect(page.getByRole('heading', { name: 'Review and send', exact: true })).toBeVisible();
  expect(approvals).toBe(0);
  await page.getByRole('textbox', { name: /^What did you notice/ }).fill('An updated observation of the pothole near the intersection.');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  expect(approvals).toBe(0);
  expect(record!.notifications?.email).toBe('resident-fixture@example.invalid');
  expect(record!.reporter?.email).toBe('');
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/case_browser_fixture$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sending report');
  await expect(page.getByText('Receipt verified', { exact: true })).toHaveCount(0);
  expect(approvals).toBe(1);

  record = { ...record!, stage: 'more_information_needed', receipt: { ticketId: 'DEMO-BROWSER-001', receiptId: 'receipt_fixture' }, notificationProgress: [{ id: 'filing_email', purpose: 'RESIDENT_REPORT_FILED', state: 'SENT', deliveryState: 'UNVERIFIED', updatedAt: stamp }], pendingQuestions: [{ ...questionBank.followUp.nearestLandmark, options: [], visibleWhen: null } as CaseView['pendingQuestions'][number]] };
  await expect(page.getByRole('textbox', { name: /^What is the nearest landmark/ })).toBeVisible();
  await page.getByRole('textbox', { name: /^What is the nearest landmark/ }).fill('The community centre sign');
  await expect(page.getByText('Email sent — inbox delivery unverified', { exact: true })).toBeVisible();
  await expect(page.getByText(/^By selecting Send update, you approve/)).toContainText(route.recipient.name);
  expect(approvals).toBe(1);
  await page.getByRole('button', { name: 'Send update', exact: true }).click();
  await expect.poll(() => approvals).toBe(2);
  expect(approvals).toBe(2);
  expect(record!.id).toBe('case_browser_fixture');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sending report');
});

test('device location is requested only by pressing its button', async ({ page }) => {
  await page.addInitScript(() => {
    const state = window as Window & { locationRequests?: number };
    state.locationRequests = 0;
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition(success: PositionCallback) { state.locationRequests! += 1; success({ coords: { latitude: 43.5, longitude: -79.8, accuracy: 25 } } as GeolocationPosition); } } });
  });
  await page.goto('/report/roads/road-surface/pothole');
  expect(await page.evaluate(() => (window as Window & { locationRequests?: number }).locationRequests)).toBe(0);
  await page.getByRole('button', { name: 'Use my location', exact: true }).click();
  expect(await page.evaluate(() => (window as Window & { locationRequests?: number }).locationRequests)).toBe(1);
  await expect(page.getByText(/Device location detected at 43.5000, -79.8000/)).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /^I confirm this is the incident location/ })).not.toBeChecked();
});

test('authored critical-control choices stop ordinary intake immediately', async ({ page }) => {
  await page.route('**/api/backend/v1/routes/preview', route => route.fulfill({ json: { supported: true, route: { id: 'fixture' }, reason: 'Controlled fixture', missingAnswers: [], urgentHandoff: false, demo: true } }));
  await page.goto('/report/roads/signs-safety/sign');
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await page.getByRole('radio', { name: 'Stop sign', exact: true }).check();
  await expect(page.getByText('This may need urgent assistance', { exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: /^What did you notice/ })).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: /^Email/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();
});


test('API-serialized empty options do not turn text, textarea or date answers into enums', () => {
  const common = { description: '', required: true, options: [], visibleWhen: null };
  const questions: Question[] = [
    { ...common, id: 'landmark', type: 'text', label: 'Landmark', minLength: 2, maxLength: 300 },
    { ...common, id: 'observation', type: 'textarea', label: 'Observation', minLength: 10 },
    { ...common, id: 'noticed', type: 'date', label: 'Noticed', required: false },
    { ...common, id: 'position', type: 'select', label: 'Position', options: [{ value: 'In travel lane', label: 'In travel lane', urgentHandoff: false }] },
  ];
  const answers = { landmark: 'Known synthetic sign', observation: 'A known synthetic observation.', noticed: '2026-11-14', position: 'In travel lane' };
  expect(validateQuestions(questions, answers)).toEqual({});
  expect(validateQuestions(questions, { ...answers, position: 'Not an authored option' })).toHaveProperty('position');
});
