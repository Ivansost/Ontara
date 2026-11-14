'use client';

import { useEffect, useRef, useState } from 'react';
import type { Conversation } from '@elevenlabs/react';
import { VStack, HStack } from '@astryxdesign/core/Stack';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { CheckboxInput } from '@astryxdesign/core/CheckboxInput';
import { Banner } from '@astryxdesign/core/Banner';
import { Divider } from '@astryxdesign/core/Divider';
import type { Answers, Question } from '@/lib/catalogue';
import { api, establishSession } from '@/lib/api';
import type { IncidentLocation } from '../ReportingContext';

type Snapshot = {
  id: string;
  revision: number;
  status: 'collecting' | 'ready_for_review' | 'urgent_handoff';
  answers: Answers;
  nextQuestion: Question | null;
  spokenQuestion: string;
  recipientName: string;
  message: string;
  reviewText: string | null;
  transcriptStatus: 'pending' | 'saved';
};
type IssuedSession = { session: Snapshot; signedUrl: string; conversationId: string; mode: 'voice'; connectionType: 'websocket' };
export type VoiceIntakeProps = {
  issueId: string;
  location: IncidentLocation;
  answers: Answers;
  onAnswersChange: (answers: Answers) => void;
  onSessionStarted: (sessionId: string) => void;
  onActiveChange: (active: boolean) => void;
};

/** Mounted only inside the supported active report's details step. */
export function VoiceIntake(props: VoiceIntakeProps) {
  const [availability, setAvailability] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<'idle' | 'starting' | 'connected' | 'stopping'>('idle');
  const [muted, setMuted] = useState(false);
  const [caption, setCaption] = useState('');
  const [captionRole, setCaptionRole] = useState<'user' | 'agent'>('agent');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const conversation = useRef<Conversation | null>(null);
  const session = useRef<Snapshot | null>(null);
  const latest = useRef(props);
  const mounted = useRef(true);
  const active = useRef(false);
  const generation = useRef(0);
  const finishing = useRef(false);
  const expectedAnswers = useRef(JSON.stringify(props.answers));
  const finishCurrent = useRef<() => Promise<void>>(async () => {});
  latest.current = props;

  useEffect(() => {
    const controller = new AbortController();
    api<{ available: boolean }>('/v1/voice/availability', { signal: controller.signal })
      .then(result => setAvailability(result.available ? 'ready' : 'unavailable'))
      .catch(() => { if (!controller.signal.aborted) setAvailability('unavailable'); });
    return () => controller.abort();
  }, []);

  async function finish() {
    if (finishing.current) return;
    finishing.current = true;
    active.current = false;
    generation.current += 1;
    if (mounted.current) setState('stopping');
    const current = conversation.current;
    conversation.current = null;
    try {
      current?.setMicMuted(true);
      if (current) await Promise.race([
        current.endSession(),
        new Promise<void>(resolve => window.setTimeout(resolve, 2500)),
      ]);
    } catch {
      // A disconnected socket still needs its server-side transcript reconciled.
    }
    // Releasing the microphone and stopping the socket are the input boundary.
    // Provider transcript finalization must not hold the ordinary form hostage.
    latest.current.onActiveChange(false);
    const transcriptDeadline = AbortSignal.timeout(4500);
    if (session.current) {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const result = await api<{ transcriptStatus: string; message: string }>(`/v1/voice/sessions/${encodeURIComponent(session.current.id)}/finish`, { method: 'POST', signal: transcriptDeadline });
          if (mounted.current) setNotice(result.message);
          if (result.transcriptStatus === 'saved') break;
        } catch {
          if (mounted.current) setNotice('Voice stopped. Your entered answers remain. The private transcript will be checked when the report is saved.');
        }
        if (transcriptDeadline.aborted) break;
        if (attempt < 2) await new Promise(resolve => window.setTimeout(resolve, 750));
      }
    }
    finishing.current = false;
    if (mounted.current) { setState('idle'); setMuted(false); }
  }
  finishCurrent.current = finish;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      void finishCurrent.current();
    };
  }, []);

  const answersKey = JSON.stringify(props.answers);
  useEffect(() => {
    if (active.current && answersKey !== expectedAnswers.current) {
      setNotice('Voice paused so you can edit the form. Start again to use your updated answers.');
      void finishCurrent.current();
    }
  }, [answersKey]);

  async function toolState(attempt: number) {
    if (attempt !== generation.current || !active.current || !session.current) return JSON.stringify({ error: 'Voice input has stopped. Continue with the form.' });
    try {
      const result = await api<Snapshot>(`/v1/voice/sessions/${encodeURIComponent(session.current.id)}`);
      if (attempt !== generation.current || !active.current) return JSON.stringify({ error: 'This voice input has stopped.' });
      session.current = result;
      return JSON.stringify(result);
    } catch {
      return JSON.stringify({ error: 'The current question is unavailable. Ask the resident to use the written form.' });
    }
  }

  async function toolAnswer(parameters: Record<string, unknown>, skip: boolean, attempt: number) {
    if (attempt !== generation.current || !active.current || !session.current) return JSON.stringify({ error: 'Voice input has stopped. Continue with the form.' });
    if (typeof parameters.questionId !== 'string' || (!skip && typeof parameters.value !== 'string')) {
      return JSON.stringify({ error: 'Use the exact current question ID and an allowed answer.' });
    }
    const baseline = JSON.stringify(latest.current.answers);
    if (baseline !== expectedAnswers.current) return JSON.stringify({ error: 'The resident edited the form. Voice is paused.' });
    try {
      const result = await api<Snapshot>(`/v1/voice/sessions/${encodeURIComponent(session.current.id)}/answers`, {
        method: 'POST', body: { expectedRevision: session.current.revision, questionId: parameters.questionId, value: skip ? null : parameters.value },
      });
      // A late model/tool response must not overwrite a concurrent resident edit.
      if (attempt !== generation.current || !active.current || JSON.stringify(latest.current.answers) !== baseline) {
        return JSON.stringify({ error: 'The resident changed the form. No voice answer was applied to it.' });
      }
      session.current = result;
      expectedAnswers.current = JSON.stringify(result.answers);
      latest.current.onAnswersChange(result.answers);
      if (result.status === 'ready_for_review') setNotice('Questions complete. Stop voice, check the written answers, then review your report.');
      if (result.status === 'urgent_handoff') setNotice(result.message);
      return JSON.stringify(result);
    } catch (problem) {
      return JSON.stringify({ error: problem instanceof Error ? problem.message : 'Check the answer and try again, or use the written form.' });
    }
  }

  async function start() {
    if (active.current || finishing.current || !consent || availability !== 'ready') return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('Microphone input requires a supported browser on a secure connection. You can use the form.');
      return;
    }
    active.current = true;
    const attempt = ++generation.current;
    session.current = null;
    latest.current.onActiveChange(true);
    expectedAnswers.current = JSON.stringify(latest.current.answers);
    setState('starting'); setError(''); setNotice(''); setCaption('');
    let permissionStream: MediaStream | null = null;
    try {
      // This is reached only from the explicit Start voice action and consent.
      // The SDK owns its live stream; this short check is always released.
      permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach(track => track.stop());
      permissionStream = null;
      if (attempt !== generation.current || !active.current || !mounted.current) return;
      await establishSession();
      const [{ Conversation: ElevenConversation }, issued] = await Promise.all([
        import('@elevenlabs/react'),
        api<IssuedSession>('/v1/voice/sessions', { method: 'POST', body: {
          requestId: crypto.randomUUID(), issueId: latest.current.issueId, location: latest.current.location,
          answers: latest.current.answers, voiceConsent: true, consentVersion: '2026-11-14.1', mode: 'voice',
        } }),
      ]);
      latest.current.onSessionStarted(issued.session.id);
      if (attempt !== generation.current || !active.current || !mounted.current) {
        void api(`/v1/voice/sessions/${encodeURIComponent(issued.session.id)}/finish`, { method: 'POST', signal: AbortSignal.timeout(4500) }).catch(() => {});
        return;
      }
      session.current = issued.session;
      const connected = await ElevenConversation.startSession({
        signedUrl: issued.signedUrl,
        connectionType: 'websocket',
        dynamicVariables: { first_question: issued.session.spokenQuestion },
        clientTools: {
          get_intake_state: () => toolState(attempt),
          record_answer: parameters => toolAnswer(parameters, false, attempt),
          skip_question: parameters => toolAnswer(parameters, true, attempt),
        },
        onMessage: event => { if (mounted.current && attempt === generation.current) { setCaption(event.message); setCaptionRole(event.role); } },
        onDisconnect: () => { if (attempt === generation.current) void finishCurrent.current(); },
        onError: () => {
          if (attempt !== generation.current) return;
          if (mounted.current) setError('The voice connection was interrupted. Your entered answers remain on the form.');
          void finishCurrent.current();
        },
      });
      if (connected.getId() !== issued.conversationId) {
        await connected.endSession();
        throw new Error('The private voice session could not be matched.');
      }
      if (attempt !== generation.current || !active.current || !mounted.current) {
        connected.setMicMuted(true);
        await connected.endSession();
        return;
      }
      conversation.current = connected;
      setState('connected');
    } catch (problem) {
      if (attempt !== generation.current) return;
      if (mounted.current) {
        const denied = problem instanceof DOMException && ['NotAllowedError', 'PermissionDeniedError'].includes(problem.name);
        setError(denied ? 'Microphone permission was not granted. You can continue with the form.' : 'Voice could not start. You can continue with the form and try again later.');
      }
      await finish();
    } finally {
      permissionStream?.getTracks().forEach(track => track.stop());
    }
  }

  function toggleMute() {
    const next = !muted;
    conversation.current?.setMicMuted(next);
    setMuted(next);
  }

  const running = state === 'connected';
  const busy = state === 'starting' || state === 'stopping';
  return <section aria-label="Voice input"><VStack gap={3}>
    <Divider />
    <Heading level={3}>Fill in these questions by voice</Heading>
    <Text color="secondary">Ontara asks the same questions and enters your answers below. Check them before you review.</Text>
    <CheckboxInput label="Use my microphone for voice input" value={consent} onChange={setConsent}
      isDisabled={running || busy}
      description="ElevenLabs processes your speech. The transcript is saved privately with your report. Audio recording is off. You can stop at any time." />
    <HStack gap={2} wrap="wrap">
      {running ? <>
        <Button label="Stop voice" onClick={() => { void finish(); }} />
        <Button label={muted ? 'Unmute microphone' : 'Mute microphone'} onClick={toggleMute} variant="ghost" />
      </> : <Button label={state === 'stopping' ? 'Stopping voice' : 'Start voice'} onClick={() => { void start(); }}
        isLoading={busy} isDisabled={!consent || availability !== 'ready'} />}
      {state === 'starting' ? <Button label="Cancel voice" variant="ghost" onClick={() => { void finish(); }} /> : null}
      {running ? <Text type="supporting">{muted ? 'Microphone muted' : 'Microphone on'} · three-minute limit</Text> : null}
    </HStack>
    {availability === 'unavailable' ? <Text type="supporting" color="secondary">Voice is not enabled here. You can fill in the form below.</Text> : null}
    {caption ? <VStack gap={1}><Text type="supporting" color="secondary">{captionRole === 'user' ? 'You said' : 'Ontara'}</Text><Text>{caption}</Text></VStack> : null}
    {notice ? <Text type="supporting">{notice}</Text> : null}
    {error ? <Banner status="warning" title="Use the form to continue" description={error} /> : null}
    <Divider />
  </VStack></section>;
}
