// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's documentation template; canonical content is backend-owned.
'use client';

import * as stylex from '@stylexjs/stylex';
import { spacingVars } from '@astryxdesign/core/theme/tokens.stylex';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { ClickableCard } from '@astryxdesign/core/ClickableCard';
import { HStack, VStack, StackItem } from '@astryxdesign/core/Stack';
import { Layout, LayoutContent } from '@astryxdesign/core/Layout';
import { Grid } from '@astryxdesign/core/Grid';
import { CatalogueBreadcrumbs } from './CatalogueBreadcrumbs';
import { Icon } from '@astryxdesign/core/Icon';
import { Banner } from '@astryxdesign/core/Banner';
import {
  WrenchScrewdriverIcon, PaintBrushIcon, TrashIcon, GlobeAltIcon,
  BeakerIcon, BuildingLibraryIcon, CloudIcon, SpeakerWaveIcon, BugAntIcon,
} from '@heroicons/react/24/outline';
import { catalogue, type CatalogueNode } from '@/lib/catalogue';
import { PageState } from './PageState';
import ReportJourney from './ReportJourney';

const categoryIcons = { roads: WrenchScrewdriverIcon, graffiti: PaintBrushIcon, waste: TrashIcon, trees: GlobeAltIcon, water: BeakerIcon, parks: BuildingLibraryIcon, snow: CloudIcon, bylaws: SpeakerWaveIcon, animals: BugAntIcon };
const styles = stylex.create({
  content: { paddingInline: { default: spacingVars['--spacing-8'], '@media (max-width: 640px)': spacingVars['--spacing-5'] } },
  choice: { minWidth: 0, height: '100%' },
  intro: { maxWidth: '64ch' },
  bottom: { paddingBlockStart: spacingVars['--spacing-4'] },
});

export function CataloguePage({ trail = [], step }: { trail?: CatalogueNode[]; step?: string }) {
  const current = trail.at(-1);
  const isHome = !current;
  const base = '/report' + (trail.length ? '/' + trail.map(node => node.slug).join('/') : '');
  if (current?.kind === 'issue' && current.available) return <ReportJourney issue={current} trail={trail} step={step} />;
  if (step) return <PageState title="This report isn’t available" message="Return to the issue choices to continue." />;
  const nodes = current ? current.children : catalogue.categories;
  return (
    <Layout height="auto" contentWidth={1200} content={
      <LayoutContent padding={8} xstyle={styles.content}>
        <VStack gap={10}>
          <VStack gap={5}>
            {current ? <CatalogueBreadcrumbs trail={trail} /> : null}
            <VStack gap={3} xstyle={styles.intro}>
              <Heading level={1}>{isHome ? 'What needs attention?' : current.label}</Heading>
              <Text type="large" color="secondary">
                {isHome ? 'Report a non-emergency local problem and follow the next steps.' : current.kind === 'issue' ? 'This issue is not available for reporting in the demo.' : 'Choose the option that best describes the problem.'}
              </Text>
            </VStack>
            {isHome ? <Banner status="info" title="Municipal reporting demo" description="Roads and Graffiti use controlled demo locations and portals. The other seven categories are available to browse." /> : null}
          </VStack>

          {nodes.length ? (
            <Grid columns={{ minWidth: 280, max: 3 }} gap={4}>
              {nodes.map(node => {
                const Glyph = categoryIcons[node.id as keyof typeof categoryIcons];
                return (
                  <ClickableCard key={node.id} label={node.label} href={`${base}/${node.slug}`} padding={5} xstyle={styles.choice}>
                    <VStack gap={4}>
                      <HStack gap={3} vAlign="start">
                        {Glyph ? <Icon icon={Glyph} size="lg" color="secondary" /> : null}
                        <StackItem size="fill"><Heading level={2}>{node.label}</Heading></StackItem>
                        <Icon icon="chevronRight" color="secondary" size="sm" />
                      </HStack>
                      <Text color="secondary">{node.description || node.children.slice(0, 3).map(child => child.label).join(', ') || 'View this issue'}</Text>
                      {isHome ? <Text type="supporting">{node.available ? 'Reporting at demo locations' : 'Browse only'}</Text> : null}
                    </VStack>
                  </ClickableCard>
                );
              })}
            </Grid>
          ) : (
            <VStack gap={5}>
              <Banner status="info" title="Not available in this demo" description={current?.disabledReason || 'You can browse this category, but reporting has not been connected. No report or personal information is collected here.'} />
              <HStack><Button label="Not available in this demo" variant="primary" isDisabled /></HStack>
            </VStack>
          )}

          <VStack gap={4} xstyle={styles.bottom}>
            {current ? <HStack><Button label="Back" href={trail.length > 1 ? '/report/' + trail.slice(0, -1).map(node => node.slug).join('/') : '/report'} variant="secondary" icon={<Icon icon="chevronLeft" />} /></HStack> : null}
            <Text type="supporting" color="secondary">For an immediate danger, use the appropriate emergency or urgent service. An ordinary report cannot provide immediate assistance.</Text>
            {isHome ? <Text type="supporting" color="secondary">Ontara helps complete the reporting process. The responsible organization decides what action or repair follows.</Text> : null}
          </VStack>
        </VStack>
      </LayoutContent>
    } />
  );
}
