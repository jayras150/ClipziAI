import PageContainer from '@/components/layout/page-container';
import { StatCard } from '@/features/admin/table-shell';
import { NeonSystem } from '@/features/system/neon-system';
import { adminFetch } from '@/lib/clipzi';
import type { HostSnapshot } from './actions';

export const metadata = { title: 'Admin: System' };

type Health = { status: string; database: string; version: string };

const BACKUP_CMD = `cd /opt/clipzi/app && bash scripts/backup-all.sh
# hasil: /opt/clipzi/app/backups/clipzi-YYYYmmdd-HHMMSS.tar.gz
# dari Windows: .\scripts\backup-all.ps1`;

const RESTORE_CMD = `bash scripts/restore-all.sh <arsip.tar.gz>
# opsi: --db-only | --config-only`;

const PRUNE_CMD = `docker builder prune -af && docker image prune -af`;

export default async function SystemPage() {
  const health = await adminFetch<Health>('/api/admin/system/health');
  const host = await adminFetch<HostSnapshot>('/api/admin/system/host').catch(() => null);
  return (
    <PageContainer pageTitle='System' pageDescription='Status layanan, metrik VPS realtime & operasional'>
      <div className='space-y-6'>
        <div className='grid gap-4 sm:grid-cols-3'>
          <StatCard label='API' value={health.status} />
          <StatCard label='Database' value={health.database} />
          <StatCard label='Versi' value={health.version} />
        </div>

        <section className='space-y-3'>
          <div>
            <h3 className='text-sm font-medium'>VPS realtime</h3>
            <p className='text-muted-foreground text-xs'>
              CPU, RAM, disk, uptime, Caddy, dan antrean task — data agent host (5 detik).
              Tombol Clear Cache &amp; Restart Caddy dieksekusi agent host, bukan container API.
            </p>
          </div>
          <NeonSystem initial={host} />
        </section>

        <section className='space-y-3 rounded-lg border p-4 text-sm'>
          <p className='font-medium'>Backup sekarang (jalankan di VPS)</p>
          <pre className='bg-muted overflow-x-auto rounded p-2 text-xs'>{BACKUP_CMD}</pre>
          <p className='font-medium'>Restore</p>
          <pre className='bg-muted overflow-x-auto rounded p-2 text-xs'>{RESTORE_CMD}</pre>
          <p className='font-medium'>Bersihkan disk</p>
          <pre className='bg-muted overflow-x-auto rounded p-2 text-xs'>{PRUNE_CMD}</pre>
        </section>
      </div>
    </PageContainer>
  );
}
