import { notFound } from 'next/navigation';
import { CataloguePage } from '@/components/CataloguePage';
import { resolvePath } from '@/lib/catalogue';

export default async function ReportPage({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  let segments = path;
  let step: string | undefined;
  const possibleStep = path.at(-1);
  if (possibleStep && ['location', 'details', 'review'].includes(possibleStep)) {
    segments = path.slice(0, -1);
    step = possibleStep;
  }
  const trail = resolvePath(segments);
  if (!trail) notFound();
  return <CataloguePage trail={trail} step={step} />;
}
