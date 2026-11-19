import PageContainer from '@/components/layout/page-container';
import { AdminErrorCard } from '@/components/admin-error-card';
import RunnerManager, { type RunnerRow } from '@/features/settings/components/runner-manager';
import RunnerProvision from '@/features/settings/components/runner-provision';
import { adminFetchSafe } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Download Runner' };
export const dynamic = 'force-dynamic';

export default async function RunnersPage() {
  const dataResult = await adminFetchSafe<{ items: RunnerRow[] }>(
    '/api/admin/settings/runners/'
  );
  const statsResult = await adminFetchSafe<{
    downloads: Record<string, number>;
    runners: { total: number; active: number; disabled: number };
    attempts: number;
  }>('/api/admin/settings/runners/stats');
  const data = dataResult.data;
  const stats = statsResult.data;
  const loadError = dataResult.error || statsResult.error;

  if (!data || !stats || loadError) {
    return (
      <PageContainer pageTitle='Download Runner'>
        <AdminErrorCard title='Gagal memuat runner' message={loadError ?? 'Data tidak tersedia.'} />
      </PageContainer>
    );
  }
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
      <div className='space-y-4'>
        <RunnerProvision />
        <RunnerManager runners={data.items} />
      </div>
    </PageContainer>
  );
}
