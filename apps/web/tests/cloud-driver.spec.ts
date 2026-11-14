import { test, expect } from '@playwright/test';
import catalogue from '../src/generated/catalogue.json';
import questionBank from '../src/generated/questions.json';
import { prepareDraftThroughUi, cancelUnusedDraftThroughUi } from '../scripts/cloud-qa/ui.mjs';

test.use({ trace: 'off' });
for (const example of [
  { issueId: 'roads-pothole', answers: { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic driver fixture: pothole near the marked intersection.' } },
  { issueId: 'graffiti-wall', answers: { immediateDanger: 'No', surfaceType: 'Public wall', offensiveContent: 'No', description: 'Synthetic driver fixture: graffiti on the marked public wall.' } },
]) {
  test(`cloud driver prepares ${example.issueId} through real UI and stops before approval`, async ({ page, baseURL }) => {
    let caseRecord: Record<string, unknown>;
    let approvals = 0;
    let creates = 0;
    const stamp = new Date().toISOString();
    const recipient = example.issueId.startsWith('roads-') ? 'Regional Roads Portal — DEMO' : 'Local Municipality Portal — DEMO';
    await page.route('**/api/backend/**', async intercepted => {
      const request = intercepted.request();
      const path = new URL(request.url()).pathname.replace('/api/backend', '');
      const data = request.method() === 'GET' ? undefined : request.postDataJSON();
      let body: unknown = {};
      let status = 200;
      if (path === '/v1/catalogue') body = catalogue;
      else if (path.startsWith('/v1/questions/')) body = questionBank.issues[example.issueId as keyof typeof questionBank.issues];
      else if (path === '/v1/routes/preview') body = { supported: true, route: { id: 'route_fixture' }, reason: 'Controlled demo', missingAnswers: [], urgentHandoff: false, demo: true };
      else if (path === '/v1/cases' && request.method() === 'POST') {
        creates += 1; status = 201;
        caseRecord = { id: 'case_driver_fixture', runId: 'run_driver_fixture', ...data, version: 1, stage: 'draft', approvedVersion: null, currentOperationId: null, receipt: null, pendingQuestions: [], createdAt: stamp, updatedAt: stamp, cancelledAt: null, route: { id: 'route_fixture', demo: true, recipient: { id: 'recipient_fixture', name: recipient, portalId: 'roads', portalUrl: 'https://portal.invalid' }, reason: 'Synthetic route', sources: [] } };
        body = caseRecord;
      } else if (path.endsWith('/approve')) { approvals += 1; status = 500; }
      else if (path.includes('/v1/cases/')) body = caseRecord!;
      await intercepted.fulfill({ status, json: body });
    });
    const prepared = await prepareDraftThroughUi(page, baseURL!, example.issueId, example.answers);
    expect(creates).toBe(1);
    expect(approvals).toBe(0);
    expect(prepared.caseData.stage).toBe('draft');
    expect(prepared.caseData.approvedVersion).toBe(null);
    expect(prepared.caseData.currentOperationId).toBe(null);
    await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
    await expect(page.getByRole('checkbox', { name: /^I approve this report/ })).toHaveCount(0);
  });
}


test('cancellation driver stops an unused draft and verifies rejected approval without an operation', async ({ page, baseURL }) => {
  const stamp = new Date().toISOString();
  let caseRecord: Record<string, unknown>;
  let approvalProbes = 0;
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    const data = request.method() === 'GET' ? undefined : request.postDataJSON();
    let body: unknown = {};
    let status = 200;
    if (path === '/v1/catalogue') body = catalogue;
    else if (path.startsWith('/v1/questions/')) body = questionBank.issues['roads-pothole'];
    else if (path === '/v1/routes/preview') body = { supported: true, route: { id: 'fixture' }, reason: 'Demo', missingAnswers: [], urgentHandoff: false, demo: true };
    else if (path === '/v1/cases' && request.method() === 'POST') {
      status = 201;
      caseRecord = { id: 'case_cancel_fixture', runId: 'run_cancel_fixture', ...data, version: 1, stage: 'draft', approvedVersion: null, currentOperationId: null, receipt: null, pendingQuestions: [], createdAt: stamp, updatedAt: stamp, cancelledAt: null, route: { demo: true, recipient: { name: 'Regional Roads Portal — DEMO' }, reason: 'Synthetic route', sources: [] } };
      body = caseRecord;
    } else if (path.endsWith('/timeline')) body = { events: [] };
    else if (path.endsWith('/cancel')) { caseRecord = { ...caseRecord!, stage: 'cancelled', cancelledAt: stamp }; body = caseRecord; }
    else if (path.endsWith('/approve')) { approvalProbes += 1; status = 409; body = { detail: 'This case has been cancelled' }; }
    else if (path.includes('/v1/cases/')) body = caseRecord!;
    await intercepted.fulfill({ status, json: body });
  });
  const prepared = await prepareDraftThroughUi(page, baseURL!, 'roads-pothole', { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic unused draft for cancellation.' });
  const cancelled = await cancelUnusedDraftThroughUi(page, baseURL!, prepared.caseData.id);
  expect(cancelled.caseData.stage).toBe('cancelled');
  expect(cancelled.caseData.currentOperationId).toBe(null);
  expect(cancelled.subsequentApprovalStatus).toBe(409);
  expect(approvalProbes).toBe(1);
});
