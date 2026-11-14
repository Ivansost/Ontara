import { expect, test } from '@playwright/test';
import { mkdir, chmod } from 'node:fs/promises';
import { join } from 'node:path';
import questionBank from '../src/generated/questions.json';
import { fillAuthoredQuestions } from '../scripts/cloud-qa/ui.mjs';

test.use({ trace: 'off' });

test('Ontario search finds upper tiers, member municipalities and the configured Milton fixture', async ({ page }) => {
  const requests: string[] = [];
  const locations: Record<string, unknown>[] = [];
  const recipient = { id: 'halton-region', name: 'Regional Roads Portal — DEMO', portalId: 'roads', portalUrl: 'https://fixture.invalid' };
  const route = { id: 'route_fixture', authorityId: 'halton-region', portalId: 'roads', recipient, reason: 'Explicit fixture.', sources: [], demo: true };
  await page.route('**/api/backend/**', async intercepted => {
    const request = intercepted.request();
    const path = new URL(request.url()).pathname.replace('/api/backend', '');
    requests.push(path);
    const data = request.method() === 'GET' ? {} : request.postDataJSON();
    if (path === '/v1/routes/preview') {
      locations.push(data.location);
      const supported = data.location.municipalityId === 'milton-town' && data.location.upperTierId === 'halton-region' && data.location.fixtureId === 'halton-regional-road';
      return intercepted.fulfill({ json: { supported, route: supported ? route : null, reason: supported ? route.reason : 'This municipality has no tested submission integration.', urgentHandoff: false, missingAnswers: [], demo: true } });
    }
    if (path === '/v1/cases') return intercepted.fulfill({ status: 201, json: { id: 'case_directory_fixture', version: 1, ...data, route, stage: 'draft', pendingQuestions: [], approvedVersion: null, currentOperationId: null, receipt: null } });
    return intercepted.fulfill({ json: {} });
  });
  await page.goto('/report/roads/road-surface/pothole');
  const selector = page.getByRole('button', { name: /^Municipality or region/ });
  await expect(selector).toContainText('Choose the incident municipality');
  await selector.click();
  const search = page.getByPlaceholder('Search Ontario municipalities or regions');
  await search.fill('Peel');
  await expect(page.getByRole('option', { name: 'Peel Region', exact: true })).toBeVisible();
  await page.getByRole('option', { name: 'Peel Region', exact: true }).click();
  await page.getByRole('textbox', { name: /^Incident address or intersection/ }).fill('Synthetic unsupported incident intersection');
  await page.getByRole('checkbox', { name: /^I confirm this is the incident location/ }).check();
  await expect(page.getByText('This municipality has no tested submission integration.')).toBeVisible();
  expect(locations.at(-1)).toMatchObject({ municipalityId: 'peel-region', upperTierId: null, fixtureId: null, confirmed: true });
  expect(requests.filter(path => path === '/v1/cases')).toHaveLength(0);
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();

  await selector.click();
  await search.fill('Halton');
  await expect(page.getByRole('option', { name: 'Halton Region', exact: true })).toBeVisible();
  await expect(page.getByRole('option', { name: 'Milton, Halton Region', exact: true })).toBeVisible();
  const directory = process.env.ONTARA_SIMPLIFIED_SCREENSHOT_DIR;
  if (directory) {
    await page.waitForTimeout(300); // Capture the settled Astryx popup, after its entrance transition.
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const path = join(directory, 'ontario-selector.png');
    await page.screenshot({ path, animations: 'disabled' }); await chmod(path, 0o600);
  }
  await page.getByRole('option', { name: 'Milton, Halton Region', exact: true }).click();
  await expect(selector).toContainText('Milton, Halton Region');
  await expect(page.getByRole('checkbox', { name: /^I confirm this is the incident location/ })).not.toBeChecked();
  await page.getByRole('button', { name: 'Use synthetic demo location', exact: true }).click();
  await fillAuthoredQuestions(page, questionBank.issues['roads-pothole'], { immediateDanger: 'No', roadPosition: 'In travel lane', travelDirection: 'Northbound', description: 'Synthetic directory fixture at the configured intersection.' });
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
  expect(requests.filter(path => path === '/v1/cases')).toHaveLength(1);
  expect(locations.at(-1)).toMatchObject({ municipalityId: 'milton-town', upperTierId: 'halton-region', fixtureId: 'halton-regional-road', confirmed: true });
});

test('manual and empty search choices do not bypass route checks or save an unsupported report', async ({ page }) => {
  let creates = 0;
  await page.route('**/api/backend/**', async intercepted => {
    const path = new URL(intercepted.request().url()).pathname;
    if (path.endsWith('/v1/cases')) creates += 1;
    return intercepted.fulfill({ json: { supported: false, route: null, reason: 'No tested submission integration for this location.', urgentHandoff: false, missingAnswers: [], demo: true } });
  });
  await page.goto('/report/roads/road-surface/pothole');
  await page.getByRole('button', { name: /^Municipality or region/ }).click();
  const search = page.getByPlaceholder('Search Ontario municipalities or regions');
  await search.fill('A deliberately unlisted place');
  await expect(page.getByRole('listbox', { name: 'Municipality or region', exact: true }).getByText('No results found', { exact: true })).toBeVisible();
  await search.fill('');
  await page.getByRole('option', { name: 'Enter a municipality manually', exact: true }).click();
  await page.getByRole('textbox', { name: /^Incident municipality/ }).fill('Synthetic unlisted municipality');
  await page.getByRole('textbox', { name: /^Incident address or intersection/ }).fill('Synthetic unsupported location');
  await page.getByRole('checkbox', { name: /^I confirm this is the incident location/ }).check();
  await expect(page.getByText('No tested submission integration for this location.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeDisabled();
  expect(creates).toBe(0);
});
