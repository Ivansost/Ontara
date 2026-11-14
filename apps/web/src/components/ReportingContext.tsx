'use client';
import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import type { Answers } from '@/lib/catalogue';

import type { components } from '@/generated/api';
export type IncidentLocation = components['schemas']['IncidentLocation'] & { confirmed: boolean };
export type Reporter = components['schemas']['Reporter'] & { contactConsent: boolean };
export type Draft = {
  issueId: string;
  location: IncidentLocation;
  answers: Answers;
  reporter: Reporter;
  caseId?: string;
  caseVersion?: number;
  savedFingerprint?: string;
};
export const emptyDraft = (issueId: string): Draft => ({ issueId, location: { municipalityId: '', incidentAddress: '', confirmed: false }, answers: {}, reporter: { name: '', email: '', contactConsent: false } });
const Context = createContext<{ draft: Draft | null; setDraft: Dispatch<SetStateAction<Draft | null>> } | null>(null);

export function ReportingProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  return <Context.Provider value={{ draft, setDraft }}>{children}</Context.Provider>;
}
export function useReporting() {
  const context = useContext(Context);
  if (!context) throw new Error('ReportingProvider is required');
  return context;
}
