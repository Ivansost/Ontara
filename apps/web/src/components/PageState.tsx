'use client';
import { Layout, LayoutContent } from '@astryxdesign/core/Layout';
import { VStack } from '@astryxdesign/core/VStack';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { Button } from '@astryxdesign/core/Button';
import { Spinner } from '@astryxdesign/core/Spinner';
import { Banner } from '@astryxdesign/core/Banner';

export function PageState({ title, message, loading, retry }: { title: string; message?: string; loading?: boolean; retry?: () => void }) {
  return (
    <Layout height="auto" contentWidth={720} padding={5} content={
      <LayoutContent>
        <VStack gap={5}>
          <Heading level={1}>{title}</Heading>
          {loading ? <Spinner label="Loading the next step" /> : null}
          {message ? <Banner status="error" title="This step is unavailable" description={message} /> : null}
          {retry ? <Button label="Try again" onClick={retry} /> : null}
          {!loading ? <Text><Button label="Back to categories" href="/report" variant="ghost" /></Text> : null}
        </VStack>
      </LayoutContent>
    } />
  );
}
