import CasePage from '@/components/CasePage';
export default async function PrivateCase({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  return <CasePage caseId={caseId} />;
}
