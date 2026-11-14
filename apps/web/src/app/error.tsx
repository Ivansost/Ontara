'use client';
import { PageState } from '@/components/PageState';
export default function ErrorPage({ reset }: { reset: () => void }) { return <PageState title="We couldn’t load this page" message="Your report has not been resubmitted. Try loading the page again." retry={reset} />; }
