import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import WorkerLogViewer from '@/features/settings/components/worker-log-viewer';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Worker Logs' };
export const dynamic = 'force-dynamic';

type Row = {
  id: string;
  status: string | null;
  progress: number | null;
  download_status: string | null;
  error_message: string | null;
  created_at: string | null;
  log_count: number;
};

const BADGE: Record<string, string> = {
  running: 'bg-emerald-600 text-white',
  success: 'bg-blue-600 text-white',
  error: 'bg-red-600 text-white',
  queued: 'bg-amber-500 text-black'
};

function stateOf(row: Row): keyof typeof BADGE {
  const value = (row.status || '').toLowerCase();
  if (value === 'completed') return 'success';
  if (value === 'error' || value === 'cancelled') return 'error';
  if (value === 'queued' || value === 'pending') return 'queued';
  return 'running';
}

export default async function WorkersPage({
  searchParams
}: {
  searchParams?: { task?: string };
}) {
  let items: Row[] = [];
  let error = '';
  try {
    const data = await adminFetch<{ items: Row[]; error?: string | null }>(
      '/api/admin/workers/tasks?limit=30'
    );
    items = data.items || [];
    error = data.error || '';
  } catch (exc) {
    error = exc instanceof Error ? exc.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat daftar task.';
  }

  return (
    <PageContainer
      pageTitle='Worker Logs'
      pageDescription='Log pipeline asli dari dalam instance (bukan Vast logs). Pilih task di bawah untuk melihat log.'
    >
      {error ? <p className='text-destructive mb-3 text-sm'>{error}</p> : null}
      <div className='mb-4 overflow-x-auto rounded-lg border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/40 text-muted-foreground text-xs uppercase'>
            <tr>
              <th className='px-3 py-2 text-left'>Task</th>
              <th className='px-3 py-2 text-left'>Status</th>
              <th className='px-3 py-2 text-left'>Progress</th>
              <th className='px-3 py-2 text-left'>Logs</th>
              <th className='px-3 py-2 text-left'>Dibuat</th>
              <th className='px-3 py-2 text-left'>Error</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td className='text-muted-foreground px-3 py-4 text-xs' colSpan={6}>
                  Belum ada task.
                </td>
              </tr>
            ) : (
              items.map((row) => {
                const state = stateOf(row);
                return (
                  <tr key={row.id} className='border-t hover:bg-muted/30'>
                    <td className='px-3 py-2 font-mono text-xs'>
                      <Link className='underline' href={`/dashboard/workers?task=${row.id}`}>
                        {row.id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td className='px-3 py-2'>
                      <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${BADGE[state]}`}>
                        {state}
                      </span>
                    </td>
                    <td className='px-3 py-2'>{row.progress ?? 0}%</td>
                    <td className='px-3 py-2'>{row.log_count}</td>
                    <td className='px-3 py-2 text-xs'>
                      {row.created_at ? new Date(row.created_at).toLocaleString('id-ID') : '-'}
                    </td>
                    <td className='max-w-[240px] truncate px-3 py-2 text-xs'>{row.error_message || '-'}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {(() => {
        const selected = searchParams?.task || items[0]?.id || '';
        const row = items.find((item) => item.id === selected);
        return (
          <WorkerLogViewer
            key={selected}
            initialTaskId={selected}
            status={row?.status || ''}
          />
        );
      })()}
    </PageContainer>
  );
}
