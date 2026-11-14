import { expect, test } from '@playwright/test';

// These opt-in checks exercise the real proxy and API. Keep traces off so an
// anonymous session cookie cannot end up in a captured request/response trace.
test.use({ trace: 'off' });
test.skip(process.env.ONTARA_LIVE_API_TESTS !== '1', 'Requires the live case API configured through ONTARA_API_URL.');

test('the real API rejects both untrusted Origin and cross-site writes through the proxy', async ({ request, baseURL }) => {
  const trustedOrigin = new URL(baseURL!).origin;
  const wrongOrigin = await request.post('/api/backend/v1/cases', {
    headers: { origin: 'https://untrusted.ontara.invalid', 'sec-fetch-site': 'same-origin' },
    data: {},
  });
  expect(wrongOrigin.status()).toBe(403);

  const crossSite = await request.post('/api/backend/v1/cases', {
    headers: { origin: trustedOrigin, 'sec-fetch-site': 'cross-site' },
    data: {},
  });
  expect(crossSite.status()).toBe(403);

  // A trusted request reaches payload validation. The intentionally incomplete
  // body creates no case, approval or external operation.
  const sameOrigin = await request.post('/api/backend/v1/cases', {
    headers: { origin: trustedOrigin, 'sec-fetch-site': 'same-origin' },
    data: {},
  });
  expect(sameOrigin.status()).toBe(422);
});

test('the session cookie survives the proxy with attributes matching the deployed scheme', async ({ request, baseURL }) => {
  const response = await request.get('/api/backend/v1/session');
  expect(response.status()).toBe(200);
  const cookie = response.headers()['set-cookie'] || '';
  // Assert booleans rather than cookie strings, so failure output reveals no value.
  expect(cookie.startsWith('ontara_session=')).toBe(true);
  expect(/;\s*HttpOnly(?:;|$)/i.test(cookie)).toBe(true);
  expect(/;\s*SameSite=Lax(?:;|$)/i.test(cookie)).toBe(true);
  expect(/;\s*Path=\/(?:;|$)/i.test(cookie)).toBe(true);
  expect(/;\s*Secure(?:;|$)/i.test(cookie)).toBe(new URL(baseURL!).protocol === 'https:');
  expect(/;\s*Domain=/i.test(cookie)).toBe(false);
});
