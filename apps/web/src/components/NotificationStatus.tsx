import { VStack } from '@astryxdesign/core/Stack';
import { Heading } from '@astryxdesign/core/Heading';
import { Text } from '@astryxdesign/core/Text';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import type { NotificationProgress, NotificationSettings } from '@/lib/contracts';

const purposes: Record<NotificationProgress['purpose'], string> = {
  RESIDENT_REPORT_FILED: 'Filing confirmation',
  RESIDENT_INFORMATION_NEEDED: 'Request for a detail',
  RESIDENT_NOTIFICATION: 'Report update',
  RESIDENT_NEEDS_ASSISTANCE: 'Paused report',
  RESIDENT_SCRIPTED_SUBMITTED: 'Submitted email (simulated)',
  RESIDENT_SCRIPTED_RESOLVED: 'Resolved email (simulated)',
};
export function notificationState(item: NotificationProgress): string {
  if (item.state === 'SENT' && item.deliveryState === 'RECEIVED') return 'Email delivery verified';
  return { QUEUED: 'Email queued', SENDING: 'Sending email', SENT: 'Email sent — inbox delivery unverified', OUTCOME_UNKNOWN: 'Checking whether the email was sent', NEEDS_ASSISTANCE: 'Email needs assistance', CANCELLED: 'Email cancelled' }[item.state];
}
export function NotificationStatus({ notifications, progress, scriptedEmailDemo = false }: { notifications?: NotificationSettings | null; progress: NotificationProgress[]; scriptedEmailDemo?: boolean }) {
  if (!notifications) return null;
  const scripted = scriptedEmailDemo || progress.some(item => item.purpose === 'RESIDENT_SCRIPTED_SUBMITTED' || item.purpose === 'RESIDENT_SCRIPTED_RESOLVED');
  return <VStack gap={3}>
    <Heading level={2}>Email updates</Heading>
    <Text color="secondary">{notifications.email}</Text>
    {scripted ? <Text type="supporting">Demo emails simulate city updates: submitted, then resolved. They do not change the actual report status above.</Text> : null}
    {progress.length ? <MetadataList orientation="vertical">{progress.map(item => <MetadataListItem key={item.id} label={purposes[item.purpose]}>{notificationState(item)}</MetadataListItem>)}</MetadataList> : <Text type="supporting" color="secondary">{scripted ? 'Email steps will appear here as the demo runs.' : 'An email is queued after a verified receipt or a request for more information.'}</Text>}
  </VStack>;
}
