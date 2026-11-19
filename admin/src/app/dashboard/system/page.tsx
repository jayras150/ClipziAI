import PageContainer from '@/components/layout/page-container';
import { StatCard } from '@/features/admin/table-shell';
import BackupPanel from '@/features/system/backup-panel';
import { NeonSystem } from '@/features/system/neon-system';
import { AdminErrorCard } from '@/components/admin-error-card';
import { adminFetchSafe } from '@/lib/clipzi';
import type { HostSnapshot } from './actions';

export const metadata = { title: 'Admin: System' };

type Health = { status: string; database: string; version: string };

const PRUNE_CMD = `docker builder prune -af && docker image prune -af`;

export default async function SystemPage() {
  const healthResult = await adminFetchSafe<Health>('/api/admin/system/health');
  const hostResult = await adminFetchSafe<HostSnapshot>('/api/admin/system/host');
  const health = healthResult.data;
  const host = hostResult.data;
  const healthError = healthResult.error;
  const hostError = hostResult.error;

  return (
    <PageContainer pageTitle='System' pageDescription='Status layanan, metrik VPS realtime & operasional'>
      <div className='space-y-6'>
        {healthError ? (
          <AdminErrorCard title='API tidak tersedia' message={healthError} />
        ) : (
          <div className='grid gap-4 sm:grid-cols-3'>
            <StatCard label='API' value={health?.status ?? '-'} />
            <StatCard label='Database' value={health?.database ?? '-'} />
            <StatCard label='Versi' value={health?.version ?? '-'} />
          </div>
        )}

        <section className='space-y-3'>
          <div>
            <h3 className='text-sm font-medium'>VPS realtime</h3>
            <p className='text-muted-foreground text-xs'>
              CPU, RAM, disk, uptime, Caddy, dan antrean task — data agent host (5 detik).
              Tombol Clear Cache &amp; Restart Caddy dieksekusi agent host, bukan container API.
            </p>
          </div>
          {hostError ? (
            <AdminErrorCard title='Data host tidak tersedia' message={hostError} />
          ) : (
            <NeonSystem initial={host ?? null} />
          )}
        </section>

        <section className='space-y-3'>
          <BackupPanel />
          <div className='rounded-lg border p-4 text-sm'>
            <p className='font-medium'>Bersihkan disk (manual, di VPS)</p>
            <pre className='bg-muted overflow-x-auto rounded p-2 text-xs'>{PRUNE_CMD}</pre>
          </div>
        </section>
      </div>
    </PageContainer>
  );
}
