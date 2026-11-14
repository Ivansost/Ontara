// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's form template: one content line and one final action.
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Layout, LayoutContent, LayoutHeader, LayoutFooter } from '@astryxdesign/core/Layout';
import { VStack, HStack, StackItem } from '@astryxdesign/core/Stack';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { Banner } from '@astryxdesign/core/Banner';
import { FormLayout } from '@astryxdesign/core/FormLayout';
import { TextInput } from '@astryxdesign/core/TextInput';
import { Selector, SelectorOption } from '@astryxdesign/core/Selector';
import { CheckboxInput } from '@astryxdesign/core/CheckboxInput';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { Divider } from '@astryxdesign/core/Divider';
import { Link } from '@astryxdesign/core/Link';
import { Icon } from '@astryxdesign/core/Icon';
import { useAnnounce } from '@astryxdesign/core/hooks';
import { catalogue, questionnaires, visibleQuestions, type CatalogueNode, type Answers, type DemoLocation } from '@/lib/catalogue';
import { api, ApiError } from '@/lib/api';
import type { CaseView } from '@/lib/contracts';
import { municipalityById, municipalitySelectorOptions } from '@/lib/municipalities';
import { useReporting, emptyDraft, type Draft, type IncidentLocation } from './ReportingContext';
import { usePreparedReport, reportErrors } from './usePreparedReport';
import { CatalogueBreadcrumbs } from './CatalogueBreadcrumbs';
import { QuestionField } from './QuestionField';
import { PageState } from './PageState';

const renderMunicipality = (option: { value: string }) => <SelectorOption label={municipalityById.get(option.value)?.label || 'Enter a municipality manually'} />;

export default function ReportJourney({ issue, trail }: { issue: CatalogueNode; trail: CatalogueNode[]; step?: string }) {
  const router = useRouter();
  const announce = useAnnounce();
  const { draft: stored, setDraft } = useReporting();
  const draft = stored?.issueId === issue.id ? stored : null;
  const questionnaire = questionnaires[issue.id];
  const prepared = usePreparedReport(draft, questionnaire?.questions || [], setDraft);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationMessage, setLocationMessage] = useState('');
  const [approvalUnknown, setApprovalUnknown] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const requestGuard = useRef(false);

  useEffect(() => { if (!draft) setDraft(emptyDraft(issue.id)); }, [draft, issue.id, setDraft]);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); }, []);

  function update(patch: Partial<Draft>) {
    if (requestGuard.current || approvalUnknown) return;
    setError('');
    setDraft(current => ({ ...(current?.issueId === issue.id ? current : emptyDraft(issue.id)), ...patch }));
  }
  function updateLocation(patch: Partial<IncidentLocation>) {
    if (draft) update({ location: { ...draft.location, ...patch } });
  }
  function updateAnswer(id: string, value: string) {
    if (!draft) return;
    const answers: Answers = { ...draft.answers, [id]: value };
    for (const question of questionnaire.questions) {
      if (question.visibleWhen && answers[question.visibleWhen.questionId] !== question.visibleWhen.equals) delete answers[question.id];
    }
    update({ answers });
  }

  const locate = useCallback(() => {
    if (!navigator.geolocation) { setLocationMessage('Location is unavailable. Enter the incident location manually.'); return; }
    setLocating(true); setLocationMessage('');
    navigator.geolocation.getCurrentPosition(position => {
      if (!requestGuard.current) setDraft(current => current?.issueId === issue.id ? { ...current, location: { ...current.location, latitude: position.coords.latitude, longitude: position.coords.longitude, confirmed: false, fixtureId: null } } : current);
      setLocationMessage(`Device location detected at ${position.coords.latitude.toFixed(4)}, ${position.coords.longitude.toFixed(4)}. Confirm the incident municipality and address below.`);
      setLocating(false);
      announce('Location detected. Confirm the incident municipality and address.');
    }, () => { setLocationMessage('We could not get your location. Enter it manually.'); setLocating(false); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 });
  }, [announce, issue.id, setDraft]);

  function chooseFixture(fixture: DemoLocation) {
    updateLocation({ municipalityId: fixture.municipalityId, upperTierId: fixture.upperTierId, incidentAddress: fixture.incidentAddress, fixtureId: fixture.fixtureId, confirmed: true, latitude: null, longitude: null });
    setLocationMessage('Synthetic location selected. You can edit it above.');
  }

  async function send() {
    const saved = prepared.savedCase;
    if (!draft || !saved || !prepared.isCurrent || requestGuard.current || approvalUnknown) return;
    if (Object.keys(reportErrors(draft, questionnaire.questions)).length) return;
    requestGuard.current = true; setBusy(true); setError('');
    try {
      await api<CaseView>(`/v1/cases/${encodeURIComponent(saved.id)}/approve`, { method: 'POST', body: { version: saved.version } });
      announce('Report approved. Opening its status.');
      router.push(`/cases/${encodeURIComponent(saved.id)}`);
    } catch (problem) {
      if (!(problem instanceof ApiError) || problem.status >= 500) {
        setApprovalUnknown(true);
        router.push(`/cases/${encodeURIComponent(saved.id)}`);
      } else setError(problem.message);
    } finally { requestGuard.current = false; setBusy(false); }
  }

  if (!questionnaire) return <PageState title="This report is unavailable" message="This issue does not yet have a supported reporting procedure." />;
  if (!draft) return <PageState title={issue.label} loading />;
  const questions = visibleQuestions(questionnaire.questions, draft.answers);
  const urgentIndex = questions.findIndex(question => question.options?.some(option => option.urgentHandoff && option.value === draft.answers[question.id]));
  const urgent = urgentIndex >= 0;
  const displayQuestions = urgent ? questions.slice(0, urgentIndex + 1) : questions;
  const showEmail = !urgent && questions.filter(question => question.options?.some(option => option.urgentHandoff)).every(question => Boolean(draft.answers[question.id]));
  const fixtures = catalogue.demoLocations.filter(location => location.categoryId === trail[0].id);
  const listedMunicipality = municipalityById.has(draft.location.municipalityId);
  const municipalityValue = listedMunicipality ? draft.location.municipalityId : draft.location.municipalityId ? 'other' : '';
  const saved = prepared.isCurrent ? prepared.savedCase : null;
  const recipient = saved?.route.recipient?.name || '';
  const routeBlocked = prepared.decision && !prepared.decision.supported;
  const knowledgePending = saved?.route.portalId === 'roads' && saved.route.knowledgeStatus && saved.route.knowledgeStatus !== 'ready';
  const editable = !busy && !approvalUnknown;
  const canSend = Boolean(saved && saved.stage === 'draft' && !urgent && !knowledgePending && !routeBlocked && editable);
  const emailError = draft.notifications?.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.notifications.email) ? 'Enter a valid email address.' : undefined;

  return <Layout height="auto" contentWidth={720} padding={5} defaultHasDividers
    header={<LayoutHeader hasDivider={false}><VStack gap={3}>
      <CatalogueBreadcrumbs trail={trail} />
      <Heading level={1} ref={headingRef}>{issue.label}</Heading>
      <Text color="secondary">Tell us where it is and what you noticed.</Text>
    </VStack></LayoutHeader>}
    content={<LayoutContent><VStack gap={6}>
      {error || prepared.error ? <Banner status="error" title="Your report has not been sent" description={error || prepared.error} endContent={prepared.error ? <Button label="Try saving again" onClick={prepared.retry} size="sm" /> : undefined} /> : null}

      <VStack gap={4}>
        <Heading level={2}>Where is the problem?</Heading>
        <FormLayout defaultOptionality="optional">
          <Selector label="Municipality or region" placeholder="Choose the incident municipality" options={municipalitySelectorOptions} value={municipalityValue} onChange={value => updateLocation({ municipalityId: value === 'other' ? 'Other' : value, upperTierId: municipalityById.get(value)?.upperTierId || null, fixtureId: null, confirmed: false, latitude: null, longitude: null })} renderOption={renderMunicipality} renderValue={renderMunicipality} isRequired isDisabled={!editable} hasSearch searchPlaceholder="Search Ontario municipalities or regions" />
          {municipalityValue === 'other' ? <TextInput label="Incident municipality" value={draft.location.municipalityId === 'Other' ? '' : draft.location.municipalityId} onChange={value => updateLocation({ municipalityId: value || 'Other', fixtureId: null, confirmed: false, latitude: null, longitude: null })} isRequired isDisabled={!editable} /> : null}
        </FormLayout>
        <Text justify="center" color="secondary">or</Text>
        <HStack hAlign="center"><Button label="Use my location" onClick={locate} isLoading={locating} isDisabled={!editable} icon={<Icon icon="search" />} /></HStack>
        <FormLayout defaultOptionality="optional">
          <TextInput label="Incident address or intersection" value={draft.location.incidentAddress} onChange={value => updateLocation({ incidentAddress: value, fixtureId: null, confirmed: false, latitude: null, longitude: null })} placeholder="Street address or nearest intersection" autoComplete="off" isRequired isDisabled={!editable} description="Use the problem’s location, even if you live somewhere else." />
          {fixtures.map(fixture => <VStack key={fixture.id} gap={2}><HStack><Button label="Use synthetic demo location" onClick={() => chooseFixture(fixture)} variant="secondary" size="sm" isDisabled={!editable} /></HStack><Text type="supporting" color="secondary">{fixture.incidentAddress}</Text></VStack>)}
          {!draft.location.fixtureId ? <CheckboxInput label="I confirm this is the incident location" value={draft.location.confirmed} onChange={value => updateLocation({ confirmed: value })} isRequired isDisabled={!editable} /> : null}
        </FormLayout>
        {locationMessage ? <Text type="supporting" color="secondary">{locationMessage}</Text> : null}
      </VStack>

      {routeBlocked && !urgent ? <Banner status="info" title="This location needs a different route" description={prepared.decision!.reason} /> : null}
      <Divider />
      <VStack gap={4}>
        <Heading level={2}>Tell us what you noticed</Heading>
        <FormLayout defaultOptionality="optional">{displayQuestions.map(question => <QuestionField key={question.id} question={question} value={draft.answers[question.id]} onChange={value => updateAnswer(question.id, value)} isDisabled={!editable} />)}</FormLayout>
        {urgent ? <Banner status="warning" title="This may need urgent assistance" description="Stay clear of the hazard and use the appropriate emergency or urgent service. Ordinary reporting cannot provide immediate assistance." /> : null}
      </VStack>

      {showEmail && !routeBlocked ? <VStack gap={4}>
        <Divider />
        <FormLayout defaultOptionality="optional"><TextInput label="Email for updates" type="email" value={draft.notifications?.email || ''} onChange={value => update({ notifications: value ? { email: value.trim(), consent: true } : null })} autoComplete="email" isOptional isReadOnly={draft.notificationSettingsLocked} isDisabled={!editable} status={emailError ? { type: 'error', message: emailError } : undefined} description={draft.notificationSettingsLocked ? 'The update address is fixed after the report is sent.' : 'Get a filing confirmation and requests for details. This address is not included in the report.'} /></FormLayout>
      </VStack> : null}

      {!urgent ? <VStack gap={4}>
        <Divider />
        <Heading level={2}>Review and send</Heading>
        {saved ? <>
          <Text type="label">To: {recipient}</Text>
          <Text type="supporting" color="secondary">This is a team-controlled demo portal. No live municipal report is made.</Text>
          <MetadataList orientation="vertical">
            <MetadataListItem label="Problem">{issue.label}</MetadataListItem>
            <MetadataListItem label="Incident location">{saved.location.incidentAddress}</MetadataListItem>
            {visibleQuestions(questionnaire.questions, saved.answers).filter(question => saved.answers[question.id]).map(question => <MetadataListItem key={question.id} label={question.label}>{saved.answers[question.id]}</MetadataListItem>)}
            {saved.reporter?.name ? <MetadataListItem label="Report contact name">{saved.reporter.name}</MetadataListItem> : null}
            {saved.reporter?.email ? <MetadataListItem label="Report contact email">{saved.reporter.email}</MetadataListItem> : null}
            <MetadataListItem label="Email updates">{saved.notifications?.email || 'Not requested'}</MetadataListItem>
          </MetadataList>
          {saved.reporter?.name || saved.reporter?.email ? <HStack><Button label="Remove report contact" size="sm" onClick={() => update({ reporter: emptyDraft(issue.id).reporter })} isDisabled={!editable} /></HStack> : null}
          <Collapsible trigger={<Text type="label">Why this recipient?</Text>} defaultIsOpen={false}><VStack gap={3}><Text>{saved.route.reason}</Text>{saved.route.sources?.map(source => <Link key={source.url} href={source.url} isExternalLink>{source.title}</Link>)}</VStack></Collapsible>
          {knowledgePending ? <Text color="secondary">The reporting procedure is still being checked. Your draft is saved.</Text> : null}
          {saved.stage !== 'draft' ? <Link href={`/cases/${encodeURIComponent(saved.id)}`}>Open this report’s status</Link> : <Text type="supporting">By selecting Send report, you confirm this location and approve the details above being sent to {recipient}{saved.notifications ? `, with reporting updates emailed to ${saved.notifications.email}` : ''}. New facts or a different recipient need your approval.</Text>}
        </> : <Text color="secondary">{prepared.state === 'saving' || prepared.state === 'checking' ? 'Preparing your draft…' : 'Complete the required fields to see the report and its recipient.'}</Text>}
      </VStack> : null}
    </VStack></LayoutContent>}
    footer={<LayoutFooter><HStack gap={3} vAlign="center" wrap="wrap">
      <StackItem size="fill"><Button label="Back" variant="secondary" href={'/report/' + trail.slice(0, -1).map(node => node.slug).join('/')} icon={<Icon icon="chevronLeft" />} isDisabled={busy} /></StackItem>
      <Button label="Send report" variant="primary" onClick={send} isLoading={busy} isDisabled={!canSend} />
    </HStack></LayoutFooter>}
  />;
}
