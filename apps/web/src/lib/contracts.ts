import type { IncidentLocation, Reporter } from '@/components/ReportingContext';
import type { Answers } from './catalogue';

import type { components } from '@/generated/api';

export type Recipient = { id: string; name: string; portalId: string; portalUrl: string };
export type RouteRecord = {
  id: string;
  authorityId: string;
  portalId: string;
  recipient: Recipient;
  reason: string;
  sources: { title: string; url: string }[];
  demo: boolean;
  procedureId?: string;
  knowledgeStatus?: string;
  publishedProcedure?: Record<string, unknown>;
};
export type RouteDecision = Omit<Required<components['schemas']['RouteDecision']>, 'route'> & { route: RouteRecord | null };
export type NotificationSettings = components['schemas']['ResidentNotifications'];
export type NotificationProgress = Required<components['schemas']['NotificationProgress']>;
export type CaseView = Omit<Required<components['schemas']['CaseView']>, 'location' | 'answers' | 'reporter' | 'route' | 'notifications' | 'notificationProgress' | 'notificationSettingsLocked'> & {
  location: IncidentLocation;
  answers: Answers;
  reporter: Reporter | null;
  route: RouteRecord;
  // Optional while reading cases created before notification preferences existed.
  notifications?: NotificationSettings | null;
  notificationProgress?: NotificationProgress[];
  notificationSettingsLocked?: boolean;
};
export type TimelineEvent = { id: string; caseId: string; kind: string; message: string; createdAt: string; visibility: 'resident' | 'presenter'; data: Record<string, unknown>; operationId?: string | null };
export type TimelineView = { events: TimelineEvent[] };
export function draftFingerprint(draft: { issueId: string; location: IncidentLocation; answers: Answers; reporter: Reporter; notifications?: NotificationSettings | null }) {
  return JSON.stringify({ issueId: draft.issueId, location: draft.location, answers: draft.answers, reporter: draft.reporter, notifications: draft.notifications || null });
}
