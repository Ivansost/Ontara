import { test, expect, type Page } from '@playwright/test';
import { chmod, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import questionBank from '../src/generated/questions.json';
import { issuePath } from '../src/lib/catalogue';
import type { CaseView, RouteRecord } from '../src/lib/contracts';
import { fillAuthoredQuestions } from '../scripts/cloud-qa/ui.mjs';

// Intercepted browser-contract fixtures only. Nothing is written to a real API,
// case ledger, receiving portal, mailbox or provider.
test.use({ trace: 'off', viewport: { width: 1440, height: 1100 } });

async function assertWrittenForm(page: Page) {
  await expect(page.getByRole('region', { name: 'Voice input', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /voice|microphone/i })).toHaveCount(0);
  await expect(page.getByText(/ElevenLabs|voice transcript|Fill in these questions by voice|Use my microphone/i)).toHaveCount(0);
}

for (const scenario of [
  { issueId: 'roads-pothole', portalId: 'roads', recipient: 'Regional Roads Portal — DEMO', answers: { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic typed fixture: a pothole near the marked intersection.' } },
  { issueId: 'graffiti-wall', portalId: 'graffiti', recipient: 'Local Municipality Portal — DEMO', answers: { immediateDanger: 'No', surfaceType: 'Public wall', offensiveContent: 'No', description: 'Synthetic typed fixture: graffiti on the marked public wall.' } },
]) {
  test(`typed ${scenario.issueId} saves, resumes and explicitly approves without browser voice activity`, async ({ page }) => {
    const requests: { path: string; method: string }[] = [];
    const voiceRequests: string[] = [];
    const providerRequests: string[] = [];
    const providerSockets: string[] = [];
    let microphoneRequests = 0;
    let record: CaseView | undefined;
    let creates = 0;
    let patches = 0;
    let approvals = 0;
    const stamp = new Date().toISOString();
    const destination: RouteRecord = {
      id: 'typed-browser-fixture-route', authorityId: scenario.portalId === 'roads' ? 'halton-region' : 'milton-town', portalId: scenario.portalId,
      recipient: { id: 'typed-browser-fixture-recipient', name: scenario.recipient, portalId: scenario.portalId, portalUrl: 'https://fixture.invalid/' + scenario.portalId },
      reason: 'Explicit controlled browser-contract fixture.', sources: [{ title: 'Fixture source', url: 'https://fixture.invalid/procedure' }], demo: true,
    };
    await page.exposeFunction('typedMicAttempt', () => { microphoneRequests += 1; });
    await page.addInitScript(() => {
      const state = window as Window & { typedMicAttempt?: () => Promise<void> };
      Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { async getUserMedia() {
        await state.typedMicAttempt?.();
        throw new DOMException('Typed-only regression forbids microphone access', 'NotAllowedError');
      } } });
    });
    await page.route('**/*', intercepted => /elevenlabs|livekit/i.test(new URL(intercepted.request().url()).hostname) ? intercepted.abort() : intercepted.fallback());
    await page.routeWebSocket(/elevenlabs|livekit/i, socket => { providerSockets.push('blocked provider socket attempt'); socket.close(); });
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.includes('/v1/voice')) voiceRequests.push(url.pathname);
      if (/elevenlabs|livekit/i.test(url.hostname)) providerRequests.push(url.hostname);
    });
    page.on('websocket', socket => {
      const url = new URL(socket.url());
      if (!url.pathname.startsWith('/_next/')) providerSockets.push(url.hostname);
    });
    await page.route('**/api/backend/**', async intercepted => {
      const request = intercepted.request();
      const path = new URL(request.url()).pathname.replace('/api/backend', '');
      requests.push({ path, method: request.method() });
      const body = request.method() === 'GET' ? undefined : request.postDataJSON();
      if (path === '/v1/session') return intercepted.fulfill({ json: {} });
      if (path === '/v1/routes/preview') return intercepted.fulfill({ json: { supported: true, reason: destination.reason, route: destination, missingAnswers: [], urgentHandoff: false, demo: true } });
      if (path === '/v1/cases' && request.method() === 'POST') {
        creates += 1;
        record = { id: 'case_typed_' + scenario.issueId.replaceAll('-', '_'), version: 1, ...body, stage: 'draft', route: destination, pendingQuestions: [], approvedVersion: null, currentOperationId: null, receipt: null, createdAt: stamp, updatedAt: stamp, cancelledAt: null, runId: 'run_typed_fixture' };
        return intercepted.fulfill({ status: 201, json: record });
      }
      if (path.endsWith('/timeline')) return intercepted.fulfill({ json: { events: [] } });
      if (path.endsWith('/evidence')) return intercepted.fulfill({ json: { case: record, operations: [], events: [] } });
      if (record && path === `/v1/cases/${record.id}` && request.method() === 'PATCH') {
        expect(body.expectedVersion).toBe(record.version);
        const { expectedVersion: _expectedVersion, ...changes } = body;
        patches += 1;
        record = { ...record, ...changes, version: record.version + 1, approvedVersion: null };
        return intercepted.fulfill({ json: record });
      }
      if (record && path === `/v1/cases/${record.id}/approve`) {
        expect(body.version).toBe(record.version);
        approvals += 1;
        record = { ...record, stage: 'preparing_report', approvedVersion: record.version, currentOperationId: 'op_typed_fixture' };
        return intercepted.fulfill({ json: record });
      }
      if (record && path === `/v1/cases/${record.id}`) return intercepted.fulfill({ json: record });
      return intercepted.fulfill({ status: 500, json: { detail: 'Unexpected fixture request: ' + path } });
    });

    await page.goto('/report/waste/collection/missed-collection');
    await page.getByRole('heading', { name: 'Report details', exact: true }).waitFor();
    await assertWrittenForm(page);
    await expect(page.getByRole('button', { name: 'Submit report', exact: true })).toBeDisabled();
    expect(requests).toEqual([]);

    const path = issuePath(scenario.issueId);
    expect(path).not.toBeNull();
    await page.goto(path!);
    await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
    await page.getByRole('heading', { name: 'Tell us what you noticed', exact: true }).waitFor();
    await assertWrittenForm(page);
    const questionnaire = questionBank.issues[scenario.issueId as keyof typeof questionBank.issues];
    await fillAuthoredQuestions(page, questionnaire, scenario.answers);
    await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
    const screenshotDirectory = process.env.ONTARA_TYPED_DETAILS_SCREENSHOT_DIR;
    if (screenshotDirectory) {
      await mkdir(screenshotDirectory, { recursive: true, mode: 0o700 });
      const screenshot = join(screenshotDirectory, scenario.issueId + '-typed-details.png');
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: screenshot, fullPage: true, animations: 'disabled' });
      await chmod(screenshot, 0o600);
    }
    await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
    await page.getByRole('heading', { name: 'Review and send', exact: true }).waitFor();
    await assertWrittenForm(page);
    expect(creates).toBe(1);
    expect(approvals).toBe(0);
    await expect(page.getByRole('checkbox', { name: /^I approve this report/ })).toHaveCount(0);

    await page.goto('/cases/' + record!.id);
    await page.getByRole('button', { name: 'Review saved report', exact: true }).click();
    await page.getByRole('heading', { name: 'Review and send', exact: true }).waitFor();
    await assertWrittenForm(page);
    const description = questionnaire.questions.find(question => question.id === 'description')!;
    const label = description.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const field = page.getByRole('textbox', { name: new RegExp('^' + label) });
    await expect(field).toHaveValue(scenario.answers.description);
    await field.fill(scenario.answers.description + ' Updated typed detail for review.');
    await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
    await assertWrittenForm(page);
    expect(patches).toBeGreaterThanOrEqual(1);
    expect(record!.version).toBeGreaterThanOrEqual(2);
    const reviewedVersion = record!.version;
    expect(approvals).toBe(0);
    await page.getByRole('button', { name: 'Send report', exact: true }).click();
    await page.waitForURL(new RegExp('/cases/' + record!.id + '$'));
    expect(approvals).toBe(1);
    expect(record!.approvedVersion).toBe(reviewedVersion);
    expect(voiceRequests).toEqual([]);
    expect(providerRequests).toEqual([]);
    expect(providerSockets).toEqual([]);
    expect(microphoneRequests).toBe(0);
  });
}
