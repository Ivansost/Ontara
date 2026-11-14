'use client';

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { api, establishSession } from '@/lib/api';
import { validateQuestions, type Question } from '@/lib/catalogue';
import { draftFingerprint, type CaseView, type RouteDecision } from '@/lib/contracts';
import { emptyDraft, type Draft } from './ReportingContext';

export function locationErrors(draft: Draft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.location.municipalityId.trim()) errors.municipality = 'Choose or enter the incident municipality.';
  if (draft.location.incidentAddress.trim().length < 3) errors.address = 'Enter the address or nearest intersection.';
  if (!draft.location.confirmed) errors.confirmed = 'Confirm where the problem is.';
  return errors;
}

export function reportErrors(draft: Draft, questions: Question[]): Record<string, string> {
  const errors = { ...locationErrors(draft), ...validateQuestions(questions, draft.answers) };
  for (const email of [draft.notifications?.email, draft.reporter.email]) {
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email address.';
  }
  if ((draft.reporter.name || draft.reporter.email) && !draft.reporter.contactConsent) errors.contactConsent = 'Approve sharing the included report contact, or remove it.';
  return errors;
}

/** Serialize draft mutations: an edit never races an older expectedVersion. */
export function usePreparedReport(draft: Draft | null, questions: Question[], setDraft: Dispatch<SetStateAction<Draft | null>>) {
  const [savedCase, setSavedCase] = useState<CaseView | null>(null);
  const [decision, setDecision] = useState<RouteDecision | null>(null);
  const [state, setState] = useState<'idle' | 'checking' | 'saving' | 'ready' | 'error'>('idle');
  const [error, setError] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const current = useRef(draft);
  current.current = draft;
  const saved = useRef<CaseView | null>(null);
  const savedFingerprint = useRef('');
  const pending = useRef<Draft | null>(null);
  const processing = useRef(false);
  const mounted = useRef(true);
  const fingerprint = draft ? draftFingerprint(draft) : '';

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; pending.current = null; };
  }, []);

  const prepare = useCallback(async () => {
    if (processing.current) return;
    processing.current = true;
    try {
      while (pending.current && mounted.current) {
        const snapshot = pending.current;
        pending.current = null;
        const requestedFingerprint = draftFingerprint(snapshot);
        const isCurrent = () => mounted.current && current.current?.issueId === snapshot.issueId && draftFingerprint(current.current) === requestedFingerprint;
        if (!isCurrent()) continue;
        setState('checking'); setError('');
        try {
          const route = await api<RouteDecision>('/v1/routes/preview', { method: 'POST', body: { issueId: snapshot.issueId, location: snapshot.location, answers: snapshot.answers } });
          if (!isCurrent()) continue;
          setDecision(route);
          if (!route.supported || route.urgentHandoff || Object.keys(reportErrors(snapshot, questions)).length) { setState('idle'); continue; }
          await establishSession();
          if (!isCurrent()) continue;
          setState('saving');
          const previous = saved.current?.issueId === snapshot.issueId ? saved.current : null;
          const caseId = previous?.id || snapshot.caseId;
          const data = { location: snapshot.location, answers: snapshot.answers, reporter: snapshot.reporter, notifications: snapshot.notifications || null };
          const result = caseId
            ? await api<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}`, { method: 'PATCH', body: { ...data, expectedVersion: previous?.version || snapshot.caseVersion } })
            : await api<CaseView>('/v1/cases', { method: 'POST', body: { ...data, issueId: snapshot.issueId } });
          // Always retain the actual ID/version, even if the person edited during the save.
          saved.current = result;
          const canonical: Draft = { ...snapshot, location: result.location, answers: result.answers, reporter: result.reporter || emptyDraft(snapshot.issueId).reporter, notifications: result.notifications || null, notificationSettingsLocked: result.notificationSettingsLocked, caseId: result.id, caseVersion: result.version };
          const canonicalFingerprint = draftFingerprint(canonical);
          savedFingerprint.current = canonicalFingerprint;
          setDraft(latest => {
            if (latest?.issueId !== snapshot.issueId) return latest;
            return draftFingerprint(latest) === requestedFingerprint
              ? { ...canonical, savedFingerprint: canonicalFingerprint }
              : { ...latest, caseId: result.id, caseVersion: result.version, savedFingerprint: canonicalFingerprint };
          });
          if (!mounted.current) continue;
          setSavedCase(result);
          setState(isCurrent() ? 'ready' : 'checking');
        } catch (problem) {
          if (isCurrent()) { setError(problem instanceof Error ? problem.message : 'Your draft could not be saved.'); setState('error'); }
        }
      }
    } finally { processing.current = false; }
  }, [questions, setDraft]);

  useEffect(() => {
    if (!draft || Object.keys(locationErrors(draft)).length) { setDecision(null); setState('idle'); return; }
    if (saved.current?.issueId === draft.issueId && savedFingerprint.current === fingerprint) { setState('ready'); return; }
    setState('checking');
    const timer = window.setTimeout(() => { pending.current = current.current; void prepare(); }, 650);
    return () => window.clearTimeout(timer);
  }, [fingerprint, retryKey, prepare]);

  return { savedCase, decision, state, error, retry: () => { savedFingerprint.current = ''; setRetryKey(value => value + 1); }, isCurrent: Boolean(savedCase && savedFingerprint.current === fingerprint && state === 'ready') };
}
