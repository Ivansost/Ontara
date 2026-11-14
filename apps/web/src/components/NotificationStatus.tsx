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
};
export function notificationState(item: NotificationProgress): string {
  if (item.state === 'SENT' && item.deliveryState === 'RECEIVED') return 'Email delivery verified';
  return { QUEUED: 'Email queued', SENDING: 'Sending email', SENT: 'Email sent — inbox delivery unverified', OUTCOME_UNKNOWN: 'Checking whether the email was sent', NEEDS_ASSISTANCE: 'Email needs assistance', CANCELLED: 'Email cancelled' }[item.state];
}
export function NotificationStatus({ notifications, progress }: { notifications?: NotificationSettings | null; progress: NotificationProgress[] }) {
  if (!notifications) return null;
  return <VStack gap={3}>
    <Heading level={2}>Email updates</Heading>
    <Text color="secondary">{notifications.email}</Text>
    {progress.length ? <MetadataList orientation="vertical">{progress.map(item => <MetadataListItem key={item.id} label={purposes[item.purpose]}>{notificationState(item)}</MetadataListItem>)}</MetadataList> : <Text type="supporting" color="secondary">An email is queued after a verified receipt or a request for more information.</Text>}
  </VStack>;
}
