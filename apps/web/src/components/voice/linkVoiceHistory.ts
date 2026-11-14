import { api } from '@/lib/api';

/** Link actual private conversation history; never alters or approves the case. */
export async function linkVoiceHistory(sessionIds: string[] | undefined, caseId: string, caseVersion: number): Promise<boolean> {
  let complete = true;
  const deadline = AbortSignal.timeout(5000);
  for (const sessionId of sessionIds || []) {
    if (deadline.aborted) return false;
    try {
      await api(`/v1/voice/sessions/${encodeURIComponent(sessionId)}/bind`, { method: 'POST', body: { caseId, caseVersion }, signal: deadline });
      // Provider finalization can lag the socket close. Reconcile the transcript
      // again after linking, without blocking the ordinary report on an outage.
      const result = await api<{ transcriptStatus: string }>(`/v1/voice/sessions/${encodeURIComponent(sessionId)}/finish`, { method: 'POST', signal: deadline });
      if (result.transcriptStatus !== 'saved') complete = false;
    } catch {
      complete = false;
    }
  }
  return complete;
}
