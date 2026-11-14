import { expect, test } from '@playwright/test';
import catalogue from '../src/generated/catalogue.json';

type Node = { label: string; slug: string; available: boolean; kind: string; children: Node[] };
function leaves(nodes: Node[], parents: string[] = []): { path: string; node: Node }[] {
  return nodes.flatMap(node => node.children.length ? leaves(node.children, [...parents, node.slug]) : [{ path: '/report/' + [...parents, node.slug].join('/'), node }]);
}

test('nine categories remain readable at desktop and mobile widths', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('What needs attention?');
  await expect(page.locator('.astryx-clickable-card')).toHaveCount(9);
  const removedCopy = /Browse only|Municipal reporting demo|Reporting at demo locations|available to browse/i;
  await expect(page.getByText(removedCopy)).toHaveCount(0);
  for (const category of catalogue.categories) {
    await page.locator('.astryx-clickable-card').filter({ has: page.getByRole('heading', { name: category.label, exact: true }) }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(category.label);
    await expect(page.getByText(removedCopy)).toHaveCount(0);
    await page.getByRole('link', { name: 'Back', exact: true }).click();
  }
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('all seven inactive trees show disabled form previews without collection or API requests', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/backend/')) apiRequests.push(request.url()); });
  const inactiveLeaves = leaves(catalogue.categories).filter(({ node }) => !node.available);
  expect(inactiveLeaves.length).toBeGreaterThan(20);
  for (const { path, node } of inactiveLeaves) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(node.label);
    await expect(page.getByRole('heading', { level: 2, name: 'Report details', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit report', exact: true })).toBeDisabled();
    await expect(page.getByRole('textbox')).toHaveCount(3);
    for (const field of await page.getByRole('textbox').all()) {
      await expect(field).toBeDisabled();
      await expect(field).not.toBeEditable();
      await expect(field).toHaveValue('');
    }
    await expect(page.getByLabel('Email', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('Name', { exact: true })).toHaveCount(0);
  }
  for (const step of ['location', 'details', 'review']) {
    await page.goto(inactiveLeaves[0].path + '/' + step);
    await expect(page.getByRole('heading', { level: 2, name: 'Report details', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit report', exact: true })).toBeDisabled();
    for (const field of await page.getByRole('textbox').all()) {
      await expect(field).toBeDisabled();
      await expect(field).not.toBeEditable();
      await expect(field).toHaveValue('');
    }
  }
  expect(apiRequests).toEqual([]);
});

test('nested choices use dedicated routes and preserve browser back', async ({ page }) => {
  await page.goto('/report/roads');
  await page.locator('.astryx-clickable-card').filter({ has: page.getByRole('heading', { name: 'Road surface', exact: true }) }).click();
  await expect(page).toHaveURL(/\/report\/roads\/road-surface$/);
  await page.getByRole('link', { name: 'Pothole', exact: true }).press('Enter');
  await expect(page).toHaveURL(/\/report\/roads\/road-surface\/pothole$/);
  await expect(page.getByRole('heading', { level: 2, name: 'Where is the problem?' })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Road surface');
  await page.getByRole('link', { name: 'Back', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Roads, Sidewalks & Traffic');
});
