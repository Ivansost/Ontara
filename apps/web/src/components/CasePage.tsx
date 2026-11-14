// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's detail-page template, with a private chronological case.
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Layout, LayoutContent, LayoutHeader, LayoutPanel } from '@astryxdesign/core/Layout';
import { VStack, HStack } from '@astryxdesign/core/Stack';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { Banner } from '@astryxdesign/core/Banner';
import { FormLayout } from '@astryxdesign/core/FormLayout';
import { CheckboxInput } from '@astryxdesign/core/CheckboxInput';
import { List, ListItem } from '@astryxdesign/core/List';
import { Timestamp } from '@astryxdesign/core/Timestamp';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { CodeBlock } from '@astryxdesign/core/CodeBlock';
import { Divider } from '@astryxdesign/core/Divider';
import { Link } from '@astryxdesign/core/Link';
import { Icon } from '@astryxdesign/core/Icon';
import { useMediaQuery, useAnnounce } from '@astryxdesign/core/hooks';
import { api, ApiError } from '@/lib/api';
import { issuePath, questionnaires, followUpQuestions, validateQuestions, type Answers } from '@/lib/catalogue';
import { draftFingerprint, type CaseView, type TimelineView, type TimelineEvent } from '@/lib/contracts';
import { PageState } from './PageState';
import { QuestionField } from './QuestionField';
import { useReporting } from './ReportingContext';

type EvidenceView = { events?: TimelineEvent[]; [key: string]: unknown };
const STATUS: Record<string, { label: string; description: string }> = {
  draft: { label: 'Review needed', description: 'Your report is saved. Approval is needed before it can be sent.' },
  preparing_report: { label: 'Preparing report', description: 'Ontara is preparing the approved report for the controlled demo portal.' },
  checking_submission: { label: 'Checking submission', description: 'Ontara is checking the receiving portal for evidence of acceptance.' },
  report_acknowledged: { label: 'Report acknowledged', description: 'A receipt has been verified. The responsible organization decides what happens next.' },
  more_information_needed: { label: 'More information needed', description: 'A reporting step needs a fact only you can provide. Review the question below.' },
  needs_assistance: { label: 'Assistance needed', description: 'The reporting process has paused. Ontara will not invent a fact or repeat an uncertain action.' },
  cancelled: { label: 'Future actions stopped', description: 'Ontara will stop future actions after cancellation is observed. An accepted report cannot be retracted here.' },
};
const text = (value: unknown): string => typeof value === 'string' ? value : typeof value === 'number' ? String(value) : '';
const errorText = (problem: unknown) => problem instanceof Error ? problem.message : 'We could not complete that action.';

function publicEvidence(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(publicEvidence);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !/password|secret|authorization|cookie|access.?token|api.?key|chain.?of.?thought|hidden.?reasoning/i.test(key)).map(([key, item]) => [key, publicEvidence(item)]));
}

export default function CasePage({ caseId }: { caseId: string }) {
  const router = useRouter();
  const announce = useAnnounce();
  const isNarrow = useMediaQuery('(max-width: 1024px)');
  const { setDraft } = useReporting();
  const [caseData, setCaseData] = useState<CaseView | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState('');
  const [fatal, setFatal] = useState(false);
  const [pollError, setPollError] = useState('');
  const [busy, setBusy] = useState(false);
  const [followUpAnswers, setFollowUpAnswers] = useState<Answers>({});
  const [followUpErrors, setFollowUpErrors] = useState<Record<string, string>>({});
  const [updateApproved, setUpdateApproved] = useState(false);
  const [savedUpdate, setSavedUpdate] = useState<CaseView | null>(null);
  const [stopOpen, setStopOpen] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceView | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState('');
  const requestGuard = useRef(false);
  const stageRef = useRef('');
  const initialLoaded = useRef(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    const results = await Promise.allSettled([
      api<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}`, { signal }),
      api<TimelineView>(`/v1/cases/${encodeURIComponent(caseId)}/timeline`, { signal }),
    ]);
    if (signal?.aborted) return;
    if (results[0].status === 'fulfilled') {
      const next = results[0].value;
      setCaseData(next); setFatal(false); setPollError('');
      if (!initialLoaded.current) {
        const existing = Object.fromEntries(next.pendingQuestions.filter(question => typeof next.answers[question.id] === 'string').map(question => [question.id, next.answers[question.id]]));
        setFollowUpAnswers(existing);
        if (next.stage === 'draft' && next.pendingQuestions.length > 0 && Object.keys(validateQuestions(next.pendingQuestions, existing)).length === 0) setSavedUpdate(next);
        initialLoaded.current = true;
      }
      if (stageRef.current && stageRef.current !== next.stage) announce(STATUS[next.stage]?.label || 'Your case has an update.');
      stageRef.current = next.stage;
    } else {
      const problem = results[0].reason;
      setPollError(errorText(problem));
      if (problem instanceof ApiError && [401, 403, 404].includes(problem.status)) setFatal(true);
    }
    if (results[1].status === 'fulfilled') setEvents(results[1].value.events.filter(event => event.visibility !== 'presenter').sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
  }, [announce, caseId]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!document.hidden) await load(controller.signal);
      if (!controller.signal.aborted) timer = setTimeout(poll, 4000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [load]);

  useEffect(() => { setUpdateApproved(false); }, [JSON.stringify(followUpAnswers), caseData?.version]);

  async function saveFollowUp() {
    if (!caseData || requestGuard.current) return;
    const found = validateQuestions(caseData.pendingQuestions, followUpAnswers);
    setFollowUpErrors(found);
    if (Object.keys(found).length) {
      window.setTimeout(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
      return;
    }
    requestGuard.current = true; setBusy(true); setError('');
    try {
      const saved = await api<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}/follow-up`, { method: 'POST', body: { expectedVersion: caseData.version, answers: followUpAnswers } });
      setSavedUpdate(saved); setCaseData(saved); setUpdateApproved(false);
      announce('Update saved. Review and approve it before sending.');
    } catch (problem) { setError(errorText(problem)); }
    finally { requestGuard.current = false; setBusy(false); }
  }

  async function approveUpdate() {
    if (!savedUpdate || !updateApproved || requestGuard.current) return;
    requestGuard.current = true; setBusy(true); setError('');
    try {
      const approvedCase = await api<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}/approve`, { method: 'POST', body: { version: savedUpdate.version } });
      setCaseData(approvedCase); setSavedUpdate(null); setFollowUpAnswers({}); setUpdateApproved(false);
      announce('Update approved. Ontara is checking the reporting process.');
      await load();
    } catch (problem) { setError(errorText(problem)); }
    finally { requestGuard.current = false; setBusy(false); }
  }

  async function stop() {
    if (requestGuard.current) return;
    requestGuard.current = true; setBusy(true); setError('');
    try {
      const next = await api<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}/cancel`, { method: 'POST', body: { reason: 'Resident stopped future actions from the private case page.' } });
      setCaseData(next); setStopOpen(false); setSavedUpdate(null);
      announce('Future actions stopped.');
      await load();
    } catch (problem) { setError(errorText(problem)); }
    finally { requestGuard.current = false; setBusy(false); }
  }

  function edit() {
    if (!caseData) return;
    const path = issuePath(caseData.issueId);
    if (!path) return;
    const draft = { issueId: caseData.issueId, location: caseData.location, answers: caseData.answers, reporter: caseData.reporter || { name: '', email: '', contactConsent: false }, caseId: caseData.id, caseVersion: caseData.version };
    setDraft({ ...draft, savedFingerprint: draftFingerprint(draft) });
    router.push(`${path}/details`);
  }

  async function loadEvidence(open: boolean) {
    if (!open) return;
    setEvidenceLoading(true); setEvidenceError('');
    try { setEvidence(await api<EvidenceView>(`/v1/cases/${encodeURIComponent(caseId)}/evidence`)); }
    catch (problem) { setEvidenceError(errorText(problem)); }
    finally { setEvidenceLoading(false); }
  }

  if (fatal) return <PageState title="This private case is unavailable" message="Open the case in the browser session that created it. A case reference alone does not grant access." retry={() => { setFatal(false); void load(); }} />;
  if (!caseData) return <PageState title="Your private case" loading={!error && !pollError} message={error || pollError || undefined} retry={error || pollError ? () => void load() : undefined} />;
  const status = STATUS[caseData.stage] || { label: 'Reporting in progress', description: 'Ontara is checking the next reporting step.' };
  const questionnaire = questionnaires[caseData.issueId];
  const issueLabel = questionnaire ? caseData.issueId.startsWith('roads-') ? 'Roads report' : 'Graffiti report' : 'Local problem report';
  const receipt = caseData.receipt;
  const ticketId = text(receipt?.ticketId || receipt?.ticket_id || receipt?.reference);
  const receiptUrl = text(receipt?.receiptUrl || receipt?.receipt_url);
  const ticketUrl = text(receipt?.ticketUrl || receipt?.ticket_url);
  const cancelled = caseData.stage === 'cancelled' || Boolean(caseData.cancelledAt);
  const recipientName = caseData.route.recipient?.name || 'Controlled demo recipient';

  const caseSummary = <VStack gap={4}>
    <Heading level={2}>Report details</Heading>
    <MetadataList orientation="vertical">
      <MetadataListItem label="Location">{caseData.location.incidentAddress}</MetadataListItem>
      <MetadataListItem label="Recipient">{recipientName}</MetadataListItem>
      {ticketId ? <MetadataListItem label="Verified reference">{ticketId}</MetadataListItem> : null}
      <MetadataListItem label="Created"><Timestamp value={caseData.createdAt} format="date_time" timezoneID="America/Toronto" /></MetadataListItem>
    </MetadataList>
    {ticketUrl ? <Link href={ticketUrl} isExternalLink>View demo portal ticket</Link> : null}
    {receiptUrl ? <Link href={receiptUrl} isExternalLink>View verified demo receipt</Link> : null}
    {caseData.stage === 'draft' && !savedUpdate ? <HStack><Button label="Review saved report" onClick={edit} /></HStack> : null}
    <Text type="supporting" color="secondary">This case is private to this browser session. The two receiving portals are controlled demonstrations.</Text>
  </VStack>;

  return <Layout height="auto" contentWidth={1000} defaultHasDividers
    header={<LayoutHeader hasDivider padding={4}><VStack gap={4}>
      <Link href="/report" color="secondary"><HStack gap={1} vAlign="center"><Icon icon="chevronLeft" size="sm" />Report another problem</HStack></Link>
      <Heading level={1}>{status.label}</Heading>
      <Text color="secondary">{status.description}</Text>
      <Text type="supporting">{issueLabel}{ticketId ? ` · ${ticketId}` : ''}</Text>
    </VStack></LayoutHeader>}
    content={<LayoutContent padding={4}><VStack gap={6}>
      {error || pollError ? <Banner status="error" title="This step needs attention" description={error || pollError} endContent={<Button label="Check again" onClick={() => void load()} size="sm" />} /> : null}
      {receipt ? <Banner status="success" title="Receipt verified" description="The demo portal acknowledged the report. This confirms acceptance of the reporting step; it does not confirm an inspection or repair." /> : null}

      {!cancelled && caseData.pendingQuestions.length > 0 && !savedUpdate ? <VStack gap={5}>
        <Heading level={2}>A little more information</Heading>
        <Text>The receiving process needs the following detail. Your earlier answers stay with the same case.</Text>
        <FormLayout defaultOptionality="optional">
          {caseData.pendingQuestions.map(question => <QuestionField key={question.id} question={question} value={followUpAnswers[question.id]} onChange={value => setFollowUpAnswers(current => ({ ...current, [question.id]: value }))} error={followUpErrors[question.id]} />)}
        </FormLayout>
        <HStack><Button label="Review update" variant="primary" onClick={saveFollowUp} isLoading={busy} /></HStack>
        <Divider />
      </VStack> : null}

      {!cancelled && savedUpdate ? <VStack gap={5}>
        <Heading level={2}>Review this update</Heading>
        <Text>This information will update the existing report at {recipientName}.</Text>
        <MetadataList orientation="vertical">{Object.entries(followUpAnswers).map(([id, value]) => <MetadataListItem key={id} label={caseData.pendingQuestions.find(question => question.id === id)?.label || followUpQuestions[id]?.label || id}>{value}</MetadataListItem>)}</MetadataList>
        <CheckboxInput label={`I approve sending this update to ${recipientName}`} value={updateApproved} onChange={setUpdateApproved} isRequired />
        <HStack gap={3} wrap="wrap"><Button label="Back to answer" onClick={() => setSavedUpdate(null)} /><Button label="Approve and send update" variant="primary" onClick={approveUpdate} isLoading={busy} isDisabled={!updateApproved} /></HStack>
        <Divider />
      </VStack> : null}

      <VStack gap={4}>
        <Heading level={2}>Case timeline</Heading>
        {events.length ? <List edge="flush" hasDividers density="spacious" header={<Text type="supporting">Verified steps and requests for this report</Text>}>
          {events.map(event => <ListItem key={event.id} label={<Text>{event.message}</Text>} description={<Timestamp value={event.createdAt} format="date_time" timezoneID="America/Toronto" />} startContent={<Icon icon={/receipt|acknowledg|verified/.test(event.kind) ? 'check' : /question|follow|information/.test(event.kind) ? 'info' : 'clock'} color="secondary" size="sm" />} align="start" />)}
        </List> : <Text color="secondary">The first reporting step will appear here when it is recorded.</Text>}
      </VStack>

      {isNarrow ? <><Divider />{caseSummary}</> : null}
      <Divider />
      <Collapsible trigger={<Text type="label">Presenter evidence</Text>} defaultIsOpen={false} onOpenChange={loadEvidence}>
        <VStack gap={4}>
          <MetadataList orientation="vertical"><MetadataListItem label="Case version">{caseData.version}</MetadataListItem><MetadataListItem label="Approved version">{caseData.approvedVersion || 'Awaiting approval'}</MetadataListItem><MetadataListItem label="Run ID">{caseData.runId}</MetadataListItem><MetadataListItem label="Current operation">{caseData.currentOperationId || 'Not prepared'}</MetadataListItem><MetadataListItem label="Published procedure integration">{caseData.route.publishedProcedure?.integrationStatus === 'research_only' ? 'Research coverage only — live submission is not integrated' : text(caseData.route.publishedProcedure?.integrationStatus) || 'No published integration status recorded'}</MetadataListItem></MetadataList>
          {evidenceLoading ? <Text>Loading recorded evidence…</Text> : evidence ? <CodeBlock code={JSON.stringify(publicEvidence(evidence), null, 2)} language="json" title="Recorded execution and retrieval evidence" isWrapped width="100%" maxHeight={480} /> : null}
          {evidenceError ? <Text color="secondary">{evidenceError}</Text> : null}
          <Text type="supporting" color="secondary">Official publications provide reporting knowledge; they do not establish live municipal submission. Only recorded evidence appears here. A submitted action, a verified receipt and a repaired issue are separate outcomes.</Text>
        </VStack>
      </Collapsible>

      {!cancelled ? <VStack gap={3}>
        <HStack><Button label="Stop future actions" variant="ghost" onClick={() => setStopOpen(value => !value)} /></HStack>
        {stopOpen ? <Banner status="warning" title="Stop Ontara’s future actions?" description="This stops further automated steps after revocation is observed. It cannot undo an accepted report or a remote action already in progress." endContent={<HStack gap={2}><Button label="Keep following" onClick={() => setStopOpen(false)} size="sm" /><Button label="Stop future actions" variant="destructive" onClick={stop} isLoading={busy} size="sm" /></HStack>} /> : null}
      </VStack> : null}
    </VStack></LayoutContent>}
    end={!isNarrow ? <LayoutPanel width={320} padding={4} role="complementary" label="Report summary" hasDivider>{caseSummary}</LayoutPanel> : undefined}
  />;
}
