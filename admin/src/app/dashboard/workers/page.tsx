import PageContainer from '@/components/layout/page-container';
import WorkerLogViewer from '@/features/settings/components/worker-log-viewer';

export const metadata = { title: 'Admin: Worker Logs' };
export const dynamic = 'force-dynamic';

// Tampilan Vast (instance, destroy, Vast logs) DIHAPUS.
// Isi halaman: log pipeline yang dikirim dari dalam instance worker.
export default async function WorkersPage({
  searchParams
}: {
  searchParams?: { task?: string };
}) {
  return (
    <PageContainer
      pageTitle='Worker Logs'
      pageDescription='Log pipeline asli dari dalam instance (stdout/stderr, stage, exit code, dmesg, nvidia-smi). Bukan log Vast.'
    >
      <WorkerLogViewer initialTaskId={searchParams?.task || ''} />
    </PageContainer>
  );
}
