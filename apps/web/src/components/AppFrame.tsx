// Copyright (c) Meta Platforms, Inc. and affiliates.
// Adapted from Astryx's shell-top-nav template.
'use client';

import { useState, type ReactNode } from 'react';
import NextLink from 'next/link';
import { usePathname } from 'next/navigation';
import { AppShell } from '@astryxdesign/core/AppShell';
import { TopNav, TopNavHeading, TopNavItem } from '@astryxdesign/core/TopNav';
import { Theme } from '@astryxdesign/core/theme';
import { LinkProvider } from '@astryxdesign/core/Link';
import { themes, defaultThemeSlug } from '../astryx-themes';
import { RouteFocus } from './RouteFocus';
import { ReportingProvider } from './ReportingContext';

export function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [reportSession, setReportSession] = useState(0);
  return (
    <Theme theme={themes[defaultThemeSlug]} mode="light">
      <LinkProvider component={NextLink}>
        <AppShell
          height="auto"
          variant="section"
          mobileNav={{ breakpoint: 'none' }}
          topNav={
            <TopNav
              label="Ontara navigation"
              heading={<TopNavHeading heading="Ontara" headingHref="/" />}
              endContent={
                <TopNavItem
                  label="Report a problem"
                  href="/report"
                  isSelected={pathname === '/' || pathname.startsWith('/report')}
                  onClick={event => {
                    if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && !event.defaultPrevented) setReportSession(current => current + 1);
                  }}
                />
              }
            />
          }
        >
          <ReportingProvider key={reportSession}><RouteFocus />{children}</ReportingProvider>
        </AppShell>
      </LinkProvider>
    </Theme>
  );
}
