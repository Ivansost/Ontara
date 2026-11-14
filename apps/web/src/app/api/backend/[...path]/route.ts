import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const configured = process.env.ONTARA_API_URL;
  if (!configured) {
    return Response.json({ detail: 'The reporting service is being connected. Please try again shortly.' }, { status: 503 });
  }
  const { path } = await context.params;
  // Paths are encoded independently; the destination always remains the configured API.
  const destination = new URL(path.map(encodeURIComponent).join('/') + request.nextUrl.search, configured.replace(/\/?$/, '/'));
  const headers = new Headers({ accept: 'application/json' });
  // Keep browser origin metadata intact so the API can enforce its write allowlist.
  for (const name of ['content-type', 'cookie', 'x-csrf-token', 'origin', 'sec-fetch-site']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set('x-forwarded-host', request.headers.get('host') || request.nextUrl.host);
  headers.set('x-forwarded-proto', request.nextUrl.protocol.replace(':', ''));
  try {
    const upstream = await fetch(destination, {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(55_000),
    });
    const responseHeaders = new Headers({ 'content-type': upstream.headers.get('content-type') || 'application/json', 'cache-control': 'no-store' });
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append('set-cookie', cookie);
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return Response.json({ detail: 'The reporting service is taking longer than expected. Your report has not been resubmitted. Please try again.' }, { status: 503 });
  }
}
export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
