// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's form-wizard template: one aligned content line,
// horizontal progress, one panel per step and freely available backward moves.
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
import { Selector } from '@astryxdesign/core/Selector';
import { CheckboxInput } from '@astryxdesign/core/CheckboxInput';
import { Stepper, Step } from '@astryxdesign/core/Stepper';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Divider } from '@astryxdesign/core/Divider';
import { Spinner } from '@astryxdesign/core/Spinner';
import { Link } from '@astryxdesign/core/Link';
import { Icon } from '@astryxdesign/core/Icon';
import { useAnnounce } from '@astryxdesign/core/hooks';
import { catalogue, questionnaires, visibleQuestions, validateQuestions, type CatalogueNode, type Answers, type DemoLocation } from '@/lib/catalogue';
import { api, establishSession } from '@/lib/api';
import { draftFingerprint, type CaseView, type RouteDecision } from '@/lib/contracts';
import { useReporting, emptyDraft, type Draft, type IncidentLocation } from './ReportingContext';
import { CatalogueBreadcrumbs } from './CatalogueBreadcrumbs';
import { QuestionField } from './QuestionField';
import { PageState } from './PageState';
import { VoiceIntake } from './voice/VoiceIntake';
import { linkVoiceHistory } from './voice/linkVoiceHistory';

const STEPS = [{ id: 'location', label: 'Location' }, { id: 'details', label: 'Details' }, { id: 'review', label: 'Review' }];
const errorText = (error: unknown) => error instanceof Error ? error.message : 'We could not complete that step. Please try again.';

export default function ReportJourney({ issue, trail, step = 'location' }: { issue: CatalogueNode; trail: CatalogueNode[]; step?: string }) {
  const router = useRouter();
  const announce = useAnnounce();
  const { draft: stored, setDraft } = useReporting();
  const draft = stored?.issueId === issue.id ? stored : null;
  const questionnaire = questionnaires[issue.id];
  const activeStep = Math.max(0, STEPS.findIndex(item => item.id === step));
  const base = '/report/' + trail.map(node => node.slug).join('/');
  const categoryId = trail[0].id;
  const fixtures = catalogue.demoLocations.filter(location => location.categoryId === categoryId);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState<RouteDecision | null>(null);
  const [reviewCase, setReviewCase] = useState<CaseView | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [approved, setApproved] = useState(false);
  const [locating, setLocating] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [voiceHistoryPending, setVoiceHistoryPending] = useState(false);
  const [locationMessage, setLocationMessage] = useState('');
  const headingRef = useRef<HTMLHeadingElement>(null);
  const requestGuard = useRef(false);

  useEffect(() => { if (!draft) setDraft(emptyDraft(issue.id)); }, [draft, issue.id, setDraft]);
  useEffect(() => {
    setErrors({}); setError(''); setApproved(false); setDecision(null);
    headingRef.current?.focus({ preventScroll: true });
  }, [step, issue.id]);

  useEffect(() => {
    if (draft && step !== 'location' && (!draft.location.confirmed || !draft.location.incidentAddress || !draft.location.municipalityId)) router.replace(`${base}/location`);
  }, [draft?.location.confirmed, draft?.location.incidentAddress, draft?.location.municipalityId, step, base, router]);

  const fingerprint = draft ? draftFingerprint(draft) : '';
  useEffect(() => { setApproved(false); }, [fingerprint]);
  useEffect(() => {
    if (step !== 'review' || !draft?.caseId) return;
    const controller = new AbortController();
    setReviewLoading(true);
    api<CaseView>(`/v1/cases/${encodeURIComponent(draft.caseId)}`, { signal: controller.signal })
      .then(setReviewCase)
      .catch(problem => { if (!controller.signal.aborted) setError(errorText(problem)); })
      .finally(() => { if (!controller.signal.aborted) setReviewLoading(false); });
    return () => controller.abort();
  }, [step, draft?.caseId, draft?.caseVersion]);

  function update(patch: Partial<Draft>) {
    setDraft(current => ({ ...(current?.issueId === issue.id ? current : emptyDraft(issue.id)), ...patch }));
  }
  function updateLocation(patch: Partial<IncidentLocation>) {
    if (draft) update({ location: { ...draft.location, ...patch } });
  }
  function updateAnswer(id: string, value: string) {
    if (!draft) return;
    const answers: Answers = { ...draft.answers, [id]: value };
    // Remove answers that no longer belong to the authored branch.
    for (const question of questionnaire.questions) {
      if (question.visibleWhen && answers[question.visibleWhen.questionId] !== question.visibleWhen.equals) delete answers[question.id];
    }
    update({ answers });
    setDecision(null);
  }
  function goTo(index: number) { router.push(`${base}/${STEPS[index].id}`); }
  function focusError() {
    window.setTimeout(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(), 0);
  }

  const locate = useCallback(() => {
    if (!navigator.geolocation) { setLocationMessage('Location is unavailable in this browser. Enter the incident location manually.'); return; }
    setLocating(true); setLocationMessage('');
    navigator.geolocation.getCurrentPosition(position => {
      setDraft(current => current?.issueId === issue.id ? { ...current, location: { ...current.location, latitude: position.coords.latitude, longitude: position.coords.longitude, confirmed: false, fixtureId: null } } : current);
      setLocationMessage(`Device location detected at ${position.coords.latitude.toFixed(4)}, ${position.coords.longitude.toFixed(4)}. Choose and confirm the incident municipality and address below. Your device may be somewhere else.`);
      setLocating(false);
      announce('Location detected. Confirm the incident municipality and address.');
    }, () => {
      setLocationMessage('We could not get your location. You can enter the incident location manually.');
      setLocating(false);
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 });
  }, [announce, issue.id, setDraft]);

  function chooseFixture(fixture: DemoLocation) {
    updateLocation({ municipalityId: fixture.municipalityId, upperTierId: fixture.upperTierId, incidentAddress: fixture.incidentAddress, fixtureId: fixture.fixtureId, confirmed: false, latitude: null, longitude: null });
    setLocationMessage('Synthetic demo location selected. Confirm it is the location you want to use.');
  }

  function validateLocation(): Record<string, string> {
    if (!draft) return {};
    const found: Record<string, string> = {};
    if (!draft.location.municipalityId.trim()) found.municipality = 'Choose or enter the incident municipality.';
    if (draft.location.incidentAddress.trim().length < 3) found.address = 'Enter the address or nearest intersection.';
    if (!draft.location.confirmed) found.confirmed = 'Confirm where the problem is before continuing.';
    return found;
  }

  async function next() {
    if (!draft || requestGuard.current) return;
    if (voiceActive) { setError('Stop voice before continuing so you can check the entered answers.'); return; }
    setError(''); setDecision(null);
    if (step === 'location') {
      const found = validateLocation(); setErrors(found);
      if (Object.keys(found).length) { focusError(); return; }
      requestGuard.current = true; setBusy(true);
      try {
        const route = await api<RouteDecision>('/v1/routes/preview', { method: 'POST', body: { issueId: issue.id, location: draft.location, answers: {} } });
        setDecision(route);
        if (route.route && !route.urgentHandoff) goTo(1);
        else announce(route.reason);
      } catch (problem) { setError(errorText(problem)); }
      finally { requestGuard.current = false; setBusy(false); }
      return;
    }
    if (step === 'details') {
      const found = { ...validateLocation(), ...validateQuestions(questionnaire.questions, draft.answers) };
      if (draft.reporter.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.reporter.email)) found.email = 'Enter a valid email address.';
      if ((draft.reporter.email || draft.reporter.name) && !draft.reporter.contactConsent) found.contactConsent = 'Approve sharing your contact details, or remove them.';
      setErrors(found);
      if (Object.keys(found).length) { focusError(); return; }
      requestGuard.current = true; setBusy(true);
      try {
        const route = await api<RouteDecision>('/v1/routes/preview', { method: 'POST', body: { issueId: issue.id, location: draft.location, answers: draft.answers } });
        setDecision(route);
        if (!route.supported || route.urgentHandoff) { announce(route.reason); return; }
        await establishSession();
        const data = { location: draft.location, answers: draft.answers, reporter: draft.reporter };
        const saved = draft.caseId
          ? await api<CaseView>(`/v1/cases/${encodeURIComponent(draft.caseId)}`, { method: 'PATCH', body: { ...data, expectedVersion: draft.caseVersion } })
          : await api<CaseView>('/v1/cases', { method: 'POST', body: { ...data, issueId: issue.id } });
        update({ caseId: saved.id, caseVersion: saved.version, savedFingerprint: draftFingerprint(draft) });
        setReviewCase(saved);
        setVoiceHistoryPending(!await linkVoiceHistory(draft.voiceSessionIds, saved.id, saved.version));
        goTo(2);
      } catch (problem) { setError(errorText(problem)); }
      finally { requestGuard.current = false; setBusy(false); }
      return;
    }
    if (!approved) { setErrors({ approval: 'Approve this version before sending.' }); focusError(); return; }
    if (!reviewCase || draft.savedFingerprint !== fingerprint) { setError('Your report changed. Review the updated details before approving.'); return; }
    requestGuard.current = true; setBusy(true);
    try {
      await api<CaseView>(`/v1/cases/${encodeURIComponent(reviewCase.id)}/approve`, { method: 'POST', body: { version: reviewCase.version } });
      announce('Report approved. Opening your private case.');
      router.push(`/cases/${encodeURIComponent(reviewCase.id)}`);
    } catch (problem) { setError(errorText(problem)); }
    finally { requestGuard.current = false; setBusy(false); }
  }

  if (!questionnaire) return <PageState title="This report is unavailable" message="This issue does not yet have a supported reporting procedure." />;
  if (!draft) return <PageState title={issue.label} loading />;
  const questions = visibleQuestions(questionnaire.questions, draft.answers);
  const urgentIndex = questions.findIndex(question => question.options?.some(option => option.urgentHandoff && option.value === draft.answers[question.id]));
  const urgent = urgentIndex >= 0;
  const displayQuestions = urgent ? questions.slice(0, urgentIndex + 1) : questions;
  const showContact = !urgent && questions.filter(question => question.options?.some(option => option.urgentHandoff)).every(question => Boolean(draft.answers[question.id]));
  const isDirty = draft.savedFingerprint !== fingerprint;
  const municipalityOptions = Array.from(new Map(catalogue.demoLocations.map(location => [location.municipalityId, { value: location.municipalityId, label: `${location.municipalityName}, ${location.upperTierName}` }])).values());
  const listedMunicipality = municipalityOptions.some(option => option.value === draft.location.municipalityId);
  const municipalityValue = listedMunicipality ? draft.location.municipalityId : draft.location.municipalityId ? 'other' : '';

  return (
    <Layout height="auto" contentWidth={720} padding={5} defaultHasDividers
      header={<LayoutHeader hasDivider={false}><VStack gap={5}>
        <CatalogueBreadcrumbs trail={trail} suffix={STEPS[activeStep].label} />
        <Heading level={1} ref={headingRef}>{issue.label}</Heading>
        <Stepper activeStep={activeStep} orientation="horizontal" onStepClick={index => { if (index <= activeStep) goTo(index); }} label="Report progress" density="balanced" indicatorPosition="on-track">
          {STEPS.map((item, i) => <Step key={item.id} step={i} label={item.label} />)}
        </Stepper>
      </VStack></LayoutHeader>}
      content={<LayoutContent><VStack gap={5}>
        {error ? <Banner status="error" title="We couldn’t complete this step" description={error} /> : null}
        {decision && (!decision.supported || decision.urgentHandoff) ? <Banner status={decision.urgentHandoff ? 'warning' : 'info'} title={decision.urgentHandoff ? 'Use an urgent service' : 'This location needs a different route'} description={decision.reason} /> : null}
        {voiceHistoryPending ? <Banner status="info" title="Voice transcript is still being saved" description="Your report draft is saved. The private voice transcript is pending; you can check the written answers before approving." /> : null}

        {step === 'location' ? <VStack gap={5}>
          <VStack gap={1}><Heading level={2}>Where is the problem?</Heading><Text color="secondary">Use the incident location, even if you live somewhere else.</Text></VStack>
          <FormLayout defaultOptionality="optional">
            <Selector label="Municipality or region" placeholder="Choose the incident municipality" options={[...municipalityOptions, { value: 'other', label: 'Another municipality — enter manually' }]} value={municipalityValue} onChange={value => updateLocation({ municipalityId: value === 'other' ? 'Other' : value, upperTierId: value === 'milton-town' ? 'halton-region' : null, fixtureId: null, confirmed: false, latitude: null, longitude: null })} isRequired status={errors.municipality ? { type: 'error', message: errors.municipality } : undefined} hasSearch />
            {municipalityValue === 'other' ? <TextInput label="Incident municipality" value={draft.location.municipalityId === 'Other' ? '' : draft.location.municipalityId} onChange={value => updateLocation({ municipalityId: value || 'Other', fixtureId: null, confirmed: false, latitude: null, longitude: null })} isRequired description="Live municipal submission is not connected. We will check whether this location has a supported demo route." /> : null}
          </FormLayout>
          <Text justify="center" color="secondary">or</Text>
          <HStack hAlign="center"><Button label="Use my location" onClick={locate} isLoading={locating} icon={<Icon icon="search" />} /></HStack>
          {locationMessage ? <Text type="supporting">{locationMessage}</Text> : null}
          <Divider />
          <FormLayout defaultOptionality="optional">
            <TextInput label="Incident address or intersection" value={draft.location.incidentAddress} onChange={value => updateLocation({ incidentAddress: value, fixtureId: null, confirmed: false, latitude: null, longitude: null })} placeholder="Street address or nearest intersection" autoComplete="off" isRequired status={errors.address ? { type: 'error', message: errors.address } : undefined} />
            {fixtures.map(fixture => <VStack key={fixture.id} gap={2}><HStack><Button label="Use synthetic demo location" onClick={() => chooseFixture(fixture)} variant="secondary" size="sm" /></HStack><Text type="supporting" color="secondary">{fixture.incidentAddress}</Text></VStack>)}
            <CheckboxInput label="I confirm this is the incident location" description="Your device location and home municipality may be different." value={draft.location.confirmed} onChange={value => updateLocation({ confirmed: value })} isRequired status={errors.confirmed ? { type: 'error', message: errors.confirmed } : undefined} />
          </FormLayout>
          <Text type="supporting" color="secondary">Only configured synthetic locations submit to the two controlled demo portals. A location check does not establish asset ownership.</Text>
        </VStack> : null}

        {step === 'details' ? <VStack gap={5}>
          <VStack gap={1}><Heading level={2}>Tell us what you noticed</Heading><Text color="secondary">Only report what you know. Use “not sure” where it is available.</Text></VStack>
          <VoiceIntake issueId={issue.id} location={draft.location} answers={draft.answers}
            onAnswersChange={answers => { update({ answers }); setDecision(null); }}
            onSessionStarted={id => setDraft(current => current?.issueId === issue.id ? { ...current, voiceSessionIds: [...new Set([...(current.voiceSessionIds || []), id])] } : current)}
            onActiveChange={setVoiceActive} />
          <FormLayout defaultOptionality="optional">
            {displayQuestions.map(question => <QuestionField key={question.id} question={question} value={draft.answers[question.id]} onChange={value => updateAnswer(question.id, value)} error={errors[question.id]} />)}
          </FormLayout>
          {urgent ? <Banner status="warning" title="This may need urgent assistance" description="Stay clear of the hazard and use the appropriate emergency or urgent service. Ordinary reporting cannot provide immediate assistance. You can go back and correct your answer if needed." /> : null}
          {showContact ? <VStack gap={4}>
            <Divider />
            <Heading level={2}>Contact for the report</Heading>
            <FormLayout defaultOptionality="optional">
              <TextInput label="Name" value={draft.reporter.name || ''} onChange={value => update({ reporter: { ...draft.reporter, name: value, contactConsent: false } })} autoComplete="name" isOptional />
              <TextInput label="Email" type="email" value={draft.reporter.email || ''} onChange={value => update({ reporter: { ...draft.reporter, email: value, contactConsent: false } })} autoComplete="email" isOptional description="Include only the contact details you want shared with the demo recipient." status={errors.email ? { type: 'error', message: errors.email } : undefined} />
              {draft.reporter.email || draft.reporter.name ? <CheckboxInput label="Share these contact details with the named demo recipient" value={draft.reporter.contactConsent} onChange={value => update({ reporter: { ...draft.reporter, contactConsent: value } })} isRequired status={errors.contactConsent ? { type: 'error', message: errors.contactConsent } : undefined} /> : null}
            </FormLayout>
          </VStack> : null}
        </VStack> : null}

        {step === 'review' ? <VStack gap={5}>
          <VStack gap={1}><Heading level={2}>Review and approve</Heading><Text color="secondary">Check the report and destination before anything is sent.</Text></VStack>
          {reviewLoading ? <Spinner label="Loading your saved report" /> : !reviewCase || isDirty ? <Banner status="info" title="Review your details first" description="Finish or update the details step to prepare the current report version." endContent={<Button label="Review details" onClick={() => goTo(1)} />} /> : <>
            <Banner status="info" title={reviewCase.route.recipient?.name || 'Controlled demo recipient'} description="DEMO — this is a team-controlled receiving portal. No live municipal submission is made." />
            <MetadataList orientation="vertical">
              <MetadataListItem label="Problem">{issue.label}</MetadataListItem>
              <MetadataListItem label="Incident location">{reviewCase.location.incidentAddress}</MetadataListItem>
              {visibleQuestions(questionnaire.questions, reviewCase.answers).map(question => <MetadataListItem key={question.id} label={question.label}>{reviewCase.answers[question.id] || 'Not provided'}</MetadataListItem>)}
              {reviewCase.reporter?.name ? <MetadataListItem label="Name">{reviewCase.reporter.name}</MetadataListItem> : null}
              {reviewCase.reporter?.email ? <MetadataListItem label="Contact email">{reviewCase.reporter.email}</MetadataListItem> : null}
            </MetadataList>
            <HStack gap={3} wrap="wrap"><Button label="Edit location" onClick={() => goTo(0)} size="sm" /><Button label="Edit details or contact" onClick={() => goTo(1)} size="sm" /></HStack>
            <Divider />
            <VStack gap={3}><Heading level={3}>Why this destination?</Heading><Text>{reviewCase.route.reason}</Text>{reviewCase.route.sources?.map(source => <Link key={source.url} href={source.url} isExternalLink>{source.title}</Link>)}</VStack>
            <Divider />
            <CheckboxInput label={`I approve this report and its listed details being sent to ${reviewCase.route.recipient?.name || 'the named demo recipient'}`} description="Ontara may check the receipt and handle routine follow-up on this case. New information or a changed recipient requires your approval. An acknowledgement does not mean the problem is repaired." value={approved} onChange={setApproved} isRequired status={errors.approval ? { type: 'error', message: errors.approval } : undefined} />
          </>}
        </VStack> : null}
      </VStack></LayoutContent>}
      footer={<LayoutFooter><HStack gap={3} vAlign="center" wrap="wrap">
        <StackItem size="fill"><Button label="Back" variant="secondary" onClick={() => activeStep > 0 ? goTo(activeStep - 1) : router.push('/report/' + trail.slice(0, -1).map(node => node.slug).join('/'))} icon={<Icon icon="chevronLeft" />} /></StackItem>
        <Text type="supporting">{activeStep + 1} of {STEPS.length}</Text>
        <Button label={step === 'review' ? 'Approve and send report' : step === 'details' ? 'Review report' : 'Continue'} variant="primary" onClick={next} isLoading={busy} isDisabled={voiceActive || (step === 'details' && Boolean(urgent)) || (step === 'review' && (!reviewCase || isDirty || reviewLoading))} />
      </HStack></LayoutFooter>}
    />
  );
}
