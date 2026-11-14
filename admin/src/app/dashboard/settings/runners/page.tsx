import PageContainer from '@/components/layout/page-container';
import RunnerManager, { type RunnerRow } from '@/features/settings/components/runner-manager';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Download Runner' };
export const dynamic = 'force-dynamic';

export default async function RunnersPage() {
  const data = await adminFetch<{ items: RunnerRow[] }>('/api/admin/settings/runners/');
  const stats = await adminFetch<{
    downloads: Record<string, number>;
    runners: { total: number; active: number; disabled: number };
    attempts: number;
  }>('/api/admin/settings/runners/stats');
  return (
    <PageContainer
      pageTitle='Download Runner'
      pageDescription='Fallback downloader via GitHub Actions saat download di Vast gagal. Token disimpan terenkripsi dan tidak pernah ditampilkan kembali.'
    >
      <div className='mb-4 grid gap-3 md:grid-cols-4'>
        {[
          ['Runner aktif', `${stats.runners.active}/${stats.runners.total}`],
          ['Download aktif', String(stats.downloads.downloading || 0)],
          ['Download sukses', String(stats.downloads.downloaded || 0)],
          ['Download gagal', String((stats.downloads.download_failed || 0) + (stats.downloads.failed || 0))]
        ].map(([label, value]) => (
          <div key={label} className='rounded-lg border p-3'>
            <div className='text-muted-foreground text-xs'>{label}</div>
            <div className='text-2xl font-semibold'>{value}</div>
          </div>
        ))}
      </div>
      <RunnerManager runners={data.items} />
    </PageContainer>
  );
}
