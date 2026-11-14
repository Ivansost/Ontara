import { test, expect, type Page } from '@playwright/test';
import catalogue from '../src/generated/catalogue.json';
import questions from '../src/generated/questions.json';
import type { CaseView, RouteRecord } from '../src/lib/contracts';
import { fillAuthoredQuestions } from '../scripts/cloud-qa/ui.mjs';
import { linkVoiceHistory } from '../src/components/voice/linkVoiceHistory';

// Browser-contract fixtures only. No microphone, voice provider, model, Atlas,
// mail, real case or receiving portal is used by these checks.
test.use({ trace: 'off' });

async function fixtureApi(page: Page) {
  const requests: { path: string; method: string }[] = [];
  let record: CaseView | undefined;
  let approvals = 0;
  const stamp = new Date().toISOString();
  const route: RouteRecord = {
    id: 'voice-browser-fixture-route', authorityId: 'halton-region', portalId: 'roads',
    recipient: { id: 'voice-browser-recipient', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'https://fixture.invalid/roads' },
    reason: 'Controlled browser fixture.', sources: [{ title: 'Fixture source', url: 'https://fixture.invalid/procedure' }], demo: true,
  };
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    requests.push({ path, method: request.method() });
    const body = request.method() === 'GET' ? undefined : request.postDataJSON();
    if (path === '/v1/voice/availability') return intercepted.fulfill({ json: { available: true } });
    if (path === '/v1/session') return intercepted.fulfill({ json: {} });
    if (path === '/v1/routes/preview') return intercepted.fulfill({ json: { supported: true, reason: route.reason, route, missingAnswers: [], urgentHandoff: false, demo: true } });
    if (path === '/v1/cases' && request.method() === 'POST') {
      record = { id: 'case_voice_browser_fixture', version: 1, ...body, stage: 'draft', route, pendingQuestions: [], approvedVersion: null, currentOperationId: null, receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_voice_browser_fixture' };
      return intercepted.fulfill({ status: 201, json: record });
    }
    if (path.endsWith('/timeline')) return intercepted.fulfill({ json: { events: [] } });
    if (path.endsWith('/evidence')) return intercepted.fulfill({ json: { operations: [], events: [] } });
    if (record && path === `/v1/cases/${record.id}/approve`) {
      expect(body.version).toBe(record.version);
      approvals += 1;
      record = { ...record, stage: 'preparing_report', approvedVersion: record.version };
      return intercepted.fulfill({ json: record });
    }
    if (record && path === `/v1/cases/${record.id}`) return intercepted.fulfill({ json: record });
    return intercepted.fulfill({ status: 500, json: { detail: 'Unexpected fixture request: ' + path } });
  });
  return { requests, approvals: () => approvals, case: () => record };
}

async function openDetails(page: Page) {
  await page.goto('/report/roads/road-surface/pothole');
  await expect(page.getByRole('region', { name: 'Voice input', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await page.getByRole('checkbox', { name: /^I confirm this is the incident location/ }).check();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page).toHaveURL(/\/details$/);
  await expect(page.getByRole('region', { name: 'Voice input', exact: true })).toBeVisible();
}

test('voice mounts only on active details and never contacts its API from inactive previews', async ({ page }) => {
  const api = await fixtureApi(page);
  await openDetails(page);
  await expect.poll(() => api.requests.filter(request => request.path.startsWith('/v1/voice/')).length).toBe(1);
  await expect(page.getByRole('button', { name: 'Start voice', exact: true })).toBeDisabled();
  const firstLeaf = (node: (typeof catalogue.categories)[number]): string[] => node.children.length ? [node.slug, ...firstLeaf(node.children[0] as typeof node)] : [node.slug];
  for (const category of catalogue.categories.filter(category => !category.available)) {
    await page.goto('/report/' + firstLeaf(category).join('/'));
    await expect(page.getByRole('heading', { name: 'Report details', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Voice input', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Submit report', exact: true })).toBeDisabled();
  }
  expect(api.requests.filter(request => request.path.startsWith('/v1/voice/'))).toEqual([{ path: '/v1/voice/availability', method: 'GET' }]);
  expect(api.requests.filter(request => request.path === '/v1/cases')).toEqual([]);
});

test('consent and Start are required for microphone access; denial preserves manual review and explicit approval', async ({ page }) => {
  const api = await fixtureApi(page);
  await page.addInitScript(() => {
    const state = window as Window & { qaMicrophoneRequests?: number };
    state.qaMicrophoneRequests = 0;
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia() { state.qaMicrophoneRequests = (state.qaMicrophoneRequests || 0) + 1; return Promise.reject(new DOMException('Synthetic permission denial', 'NotAllowedError')); } } });
  });
  await openDetails(page);
  await expect(page.getByRole('button', { name: 'Start voice', exact: true })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'Use my microphone for voice input', exact: true }).check();
  expect(await page.evaluate(() => (window as Window & { qaMicrophoneRequests?: number }).qaMicrophoneRequests)).toBe(0);
  await page.getByRole('button', { name: 'Start voice', exact: true }).click();
  await expect(page.getByText('Microphone permission was not granted. You can continue with the form.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { qaMicrophoneRequests?: number }).qaMicrophoneRequests)).toBe(1);
  expect(api.requests.filter(request => request.path === '/v1/voice/sessions')).toEqual([]);
  await expect(page.getByRole('button', { name: 'Review report', exact: true })).toBeEnabled();
  await fillAuthoredQuestions(page, questions.issues['roads-pothole'], { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic fixture observation near the marked intersection.' });
  await page.getByRole('button', { name: 'Review report', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Review and approve', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Voice input', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: /^I approve this report/ })).not.toBeChecked();
  await page.getByRole('button', { name: 'Approve and send report', exact: true }).click();
  expect(api.approvals()).toBe(0);
  await page.getByRole('checkbox', { name: /^I approve this report/ }).check();
  await page.getByRole('button', { name: 'Approve and send report', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/case_voice_browser_fixture$/);
  expect(api.approvals()).toBe(1);
  expect(api.case()?.answers.description).toContain('Synthetic fixture observation');
});

test('pending microphone permission blocks review until the resident cancels voice', async ({ page }) => {
  const api = await fixtureApi(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: () => new Promise<MediaStream>(() => {}) } });
  });
  await openDetails(page);
  await page.getByRole('checkbox', { name: 'Use my microphone for voice input', exact: true }).check();
  await page.getByRole('button', { name: 'Start voice', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Review report', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel voice', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Review report', exact: true })).toBeEnabled();
  expect(api.requests.filter(request => request.path === '/v1/voice/sessions' || request.path === '/v1/cases')).toEqual([]);
});

test('a stalled optional transcript cannot block the ordinary report review indefinitely', async () => {
  const original = globalThis.fetch;
  const signals: AbortSignal[] = [];
  globalThis.fetch = async (_input, options) => new Promise<Response>((_resolve, reject) => {
    const signal = options?.signal;
    if (!signal) return reject(new Error('Transcript work requires a deadline.'));
    signals.push(signal);
    if (signal.aborted) return reject(signal.reason);
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
  const started = Date.now();
  try {
    expect(await linkVoiceHistory(['voice_fixture_1', 'voice_fixture_2'], 'case_fixture', 1)).toBe(false);
    expect(Date.now() - started).toBeLessThan(8000);
    expect(signals.length).toBeGreaterThan(0);
    expect(signals.every(signal => signal === signals[0])).toBe(true);
  } finally { globalThis.fetch = original; }
});
