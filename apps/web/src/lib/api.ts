export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorMessage(body: unknown): string {
  if (!body || typeof body !== 'object') return 'We could not complete that step. Please try again.';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || 'Check your answers.').join(' ');
  return 'We could not complete that step. Please try again.';
}

export async function api<T>(path: string, options?: { method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'; body?: unknown; signal?: AbortSignal }): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    method: options?.method || 'GET',
    credentials: 'same-origin',
    headers: options?.body === undefined ? undefined : { 'content-type': 'application/json' },
    body: options?.body === undefined ? undefined : JSON.stringify(options.body),
    cache: 'no-store',
    signal: options?.signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(body), body);
  return body as T;
}

let sessionPromise: Promise<unknown> | null = null;
export function establishSession(): Promise<unknown> {
  if (!sessionPromise) sessionPromise = api('/v1/session').catch(error => { sessionPromise = null; throw error; });
  return sessionPromise;
}
