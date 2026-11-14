// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's documentation template; canonical content is backend-owned.
'use client';

import * as stylex from '@stylexjs/stylex';
import { borderVars, spacingVars, typeScaleVars } from '@astryxdesign/core/theme/tokens.stylex';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { ClickableCard } from '@astryxdesign/core/ClickableCard';
import { HStack, VStack, StackItem } from '@astryxdesign/core/Stack';
import { Layout, LayoutContent } from '@astryxdesign/core/Layout';
import { Grid } from '@astryxdesign/core/Grid';
import { CatalogueBreadcrumbs } from './CatalogueBreadcrumbs';
import { Icon } from '@astryxdesign/core/Icon';
import {
  WrenchScrewdriverIcon, PaintBrushIcon, TrashIcon, GlobeAltIcon,
  BeakerIcon, BuildingLibraryIcon, CloudIcon, SpeakerWaveIcon, BugAntIcon,
} from '@heroicons/react/24/outline';
import { catalogue, type CatalogueNode } from '@/lib/catalogue';
import { PageState } from './PageState';
import ReportJourney from './ReportJourney';
import { InactiveReportPreview } from './InactiveReportPreview';

const categoryIcons = { roads: WrenchScrewdriverIcon, graffiti: PaintBrushIcon, waste: TrashIcon, trees: GlobeAltIcon, water: BeakerIcon, parks: BuildingLibraryIcon, snow: CloudIcon, bylaws: SpeakerWaveIcon, animals: BugAntIcon };
const styles = stylex.create({
  content: { paddingInline: { default: spacingVars['--spacing-8'], '@media (max-width: 640px)': spacingVars['--spacing-5'] } },
  homeContent: { marginInline: 'auto' },
  homeGrid: { gridTemplateColumns: { default: 'repeat(3, minmax(0, 1fr))', '@media (max-width: 960px)': 'repeat(2, minmax(0, 1fr))' } },
  choice: { minWidth: 0, height: '100%' },
  homeChoice: {
    aspectRatio: { default: 'auto', '@media (max-width: 960px)': '1 / 1' },
    height: {
      default: `calc(${spacingVars['--spacing-10']} * 5)`,
      '@media (min-width: 961px) and (max-height: 850px)': `calc(${spacingVars['--spacing-10']} * 4 + ${spacingVars['--spacing-5']})`,
      '@media (max-width: 960px)': 'auto',
    },
    paddingInline: { default: `calc(${spacingVars['--spacing-6']} - ${borderVars['--border-width']})`, '@media (max-width: 640px)': spacingVars['--spacing-3'] },
    paddingBlock: { default: `calc(${spacingVars['--spacing-6']} - ${borderVars['--border-width']})`, '@media (max-width: 640px)': spacingVars['--spacing-3'] },
  },
  homeChoiceContent: { rowGap: { default: spacingVars['--spacing-6'], '@media (max-width: 640px)': spacingVars['--spacing-2'] } },
  homeChoiceText: {
    minHeight: {
      default: `calc(${spacingVars['--spacing-10']} * 2)`,
      '@media (max-width: 640px)': `calc(${spacingVars['--spacing-12']} + ${spacingVars['--spacing-6']})`,
    },
  },
  homeChoiceTitle: {
    fontSize: { default: typeScaleVars['--text-heading-2-size'], '@media (max-width: 640px)': typeScaleVars['--text-heading-3-size'] },
    lineHeight: { default: typeScaleVars['--text-heading-2-leading'], '@media (max-width: 640px)': typeScaleVars['--text-heading-3-leading'] },
  },
  homeExamples: { display: { default: 'block', '@media (max-width: 640px)': 'none' } },
  intro: { maxWidth: '64ch' },
  bottom: { paddingBlockStart: spacingVars['--spacing-4'] },
});

export function CataloguePage({ trail = [], step }: { trail?: CatalogueNode[]; step?: string }) {
  const current = trail.at(-1);
  const isHome = !current;
  const isPreview = current?.kind === 'issue' && !current.available;
  const base = '/report' + (trail.length ? '/' + trail.map(node => node.slug).join('/') : '');
  if (current?.kind === 'issue' && current.available) return <ReportJourney issue={current} trail={trail} step={step} />;
  if (step && !isPreview) return <PageState title="This report isn’t available" message="Return to the issue choices to continue." />;
  const nodes = current ? current.children : catalogue.categories;
  return (
    <Layout height="auto" contentWidth={1200} content={
      <LayoutContent padding={8} xstyle={styles.content}>
        <VStack gap={10} width={isHome ? '100%' : undefined} maxWidth={isHome ? 960 : undefined} xstyle={isHome ? styles.homeContent : undefined}>
          <VStack gap={5}>
            {current ? <CatalogueBreadcrumbs trail={trail} /> : null}
            <VStack gap={3} xstyle={styles.intro}>
              <Heading level={1}>{isHome ? 'What needs attention?' : current.label}</Heading>
              {!isPreview ? <Text type="large" color="secondary">
                {isHome ? 'Report a non-emergency local problem and follow the next steps.' : 'Choose the option that best describes the problem.'}
              </Text> : null}
            </VStack>
          </VStack>

          {nodes.length ? (
            <Grid columns={{ minWidth: 280, max: 3 }} gap={4} xstyle={isHome ? styles.homeGrid : undefined}>
              {nodes.map(node => {
                const Glyph = categoryIcons[node.id as keyof typeof categoryIcons];
                return (
                  <ClickableCard key={node.id} label={node.label} href={`${base}/${node.slug}`} padding={isHome ? 6 : 5} xstyle={[styles.choice, isHome && styles.homeChoice]}>
                    {isHome ? <VStack height="100%" gap={6} vAlign="between" xstyle={styles.homeChoiceContent}>
                      <HStack hAlign="between" vAlign="start">
                        {Glyph ? <Icon icon={Glyph} size="lg" color="primary" /> : null}
                        <Icon icon="chevronRight" color="secondary" size="sm" />
                      </HStack>
                      <VStack gap={3} xstyle={styles.homeChoiceText}>
                        <Heading level={2} textWrap="balance" xstyle={styles.homeChoiceTitle}>{node.label}</Heading>
                        <Text color="secondary" xstyle={styles.homeExamples}>{node.description || node.children.slice(0, 3).map(child => child.label).join(', ')}</Text>
                      </VStack>
                    </VStack> : <VStack gap={4}>
                      <HStack gap={3} vAlign="start">
                        {Glyph ? <Icon icon={Glyph} size="lg" color="secondary" /> : null}
                        <StackItem size="fill"><Heading level={2}>{node.label}</Heading></StackItem>
                        <Icon icon="chevronRight" color="secondary" size="sm" />
                      </HStack>
                      <Text color="secondary">{node.description || node.children.slice(0, 3).map(child => child.label).join(', ') || 'View this issue'}</Text>
                    </VStack>}
                  </ClickableCard>
                );
              })}
            </Grid>
          ) : (
            <VStack gap={5} xstyle={styles.intro}>
              <InactiveReportPreview />
            </VStack>
          )}

          {isHome ? <VStack as="section" aria-labelledby="how-ontara-works" gap={6}>
            <Heading level={2} id="how-ontara-works">How Ontara works</Heading>
            <Grid columns={{ minWidth: 240, max: 3 }} gap={6}>
              <VStack gap={2}>
                <Heading level={3}>Choose an issue and location</Heading>
                <Text color="secondary">Pick the category that fits, confirm where the problem is, and answer the questions.</Text>
              </VStack>
              <VStack gap={2}>
                <Heading level={3}>Review before sending</Heading>
                <Text color="secondary">Check the report and its named recipient. You decide when to approve and send it.</Text>
              </VStack>
              <VStack gap={2}>
                <Heading level={3}>Follow the same case</Heading>
                <Text color="secondary">View the receipt and requests for more information in one private case. Add requested details there and approve each update.</Text>
              </VStack>
            </Grid>
          </VStack> : null}

          <VStack gap={4} xstyle={styles.bottom}>
            {current ? <HStack><Button label="Back" href={trail.length > 1 ? '/report/' + trail.slice(0, -1).map(node => node.slug).join('/') : '/report'} variant="secondary" icon={<Icon icon="chevronLeft" />} /></HStack> : null}
            <Text type="supporting" color="secondary">For an immediate danger, use the appropriate emergency or urgent service. An ordinary report cannot provide immediate assistance.</Text>
          </VStack>
        </VStack>
      </LayoutContent>
    } />
  );
}
