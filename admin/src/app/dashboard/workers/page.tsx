import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { Button } from '@/components/ui/button';
import { adminFetch } from '@/lib/clipzi';
import WorkerLogsButton from '@/features/settings/components/worker-logs-button';
import { WorkerLogAudit } from '@/features/settings/components/worker-log-audit';
import type { StoredWorkerLog } from './actions';
import { destroyInstance } from './actions';

export const metadata = { title: 'Admin: Workers' };
export const dynamic = 'force-dynamic';

type LiveRow = {
  instance_id: number;
  machine_id: number | null;
  gpu_name: string | null;
  price_per_hour: number | null;
  disk_space: number | null;
  disk_util: number | null;
  gpu_util: number | null;
  state: string | null;
  status_msg: string | null;
  label: string | null;
  start_date: string | null;
};

type LocalRow = {
  instance_id: number;
  task_id: string;
  state: string;
  gpu_name: string | null;
  price_per_hour: number | null;
  attempt: number;
  created_at: string | null;
  log_tail: string | null;
  outcome?: string;
  has_log?: boolean;
};

type Paged<T> = { items: T[]; count: number };

const OUTCOME_LABEL: Record<string, string> = {
  success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  failed: 'bg-red-500/15 text-red-300 border-red-500/40',
  cancelled: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  running: 'bg-sky-500/15 text-sky-300 border-sky-500/40'
};

function outcomeOf(row: Record<string, unknown>): string {
  const explicit = String(row.outcome || '').toLowerCase();
  if (explicit) return explicit;
  const state = String(row.state || '').toLowerCase();
  if (['failed', 'error', 'timeout'].includes(state)) return 'failed';
  if (['exited', 'cancelled'].includes(state)) return 'cancelled';
  return 'running';
}

const columns: Column[] = [
  { key: 'instance_id', label: 'Instance' },
  {
    key: 'outcome',
    label: 'Hasil',
    render: (row) => {
      const outcome = outcomeOf(row);
      return (
        <span
          className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${
            OUTCOME_LABEL[outcome] || OUTCOME_LABEL.running
          }`}
        >
          {outcome}
        </span>
      );
    }
  },
  { key: 'state', label: 'State' },
  { key: 'gpu_name', label: 'GPU' },
  {
    key: 'disk',
    label: 'Disk (GB)',
    render: (row) =>
      `${Number(row.disk_util ?? 0).toFixed(1)} / ${Number(row.disk_space ?? 0).toFixed(0)}`
  },
  {
    key: 'price_per_hour',
    label: '$/jam',
    render: (row) => (row.price_per_hour ? '$' + Number(row.price_per_hour).toFixed(3) : '-')
  },
  { key: 'task_id', label: 'Task', render: (row) => String(row.task_id ?? '').slice(0, 8) || '-' },
  { key: 'started', label: 'Mulai', render: (row) => formatDate(String(row.started ?? '')) },
  {
    key: 'actions',
    label: 'Aksi',
    render: (row) => (
      <div className='flex flex-wrap justify-end gap-1'>
        <WorkerLogsButton
          instanceId={Number(row.instance_id)}
          label={String(row.gpu_name || row.label || '')}
        />
        {row.is_live ? (
          <form action={destroyInstance}>
            <input type='hidden' name='instance_id' value={String(row.instance_id)} />
            <Button size='sm' variant='destructive' type='submit'>
              Destroy
            </Button>
          </form>
        ) : null}
      </div>
    )
  }
];

export default async function WorkersPage() {
  const [liveResult, localResult, logsResult] = await Promise.allSettled([
    adminFetch<Paged<LiveRow>>('/api/admin/workers/live'),
    adminFetch<Paged<LocalRow>>('/api/admin/workers/instances?limit=50'),
    adminFetch<{ items: StoredWorkerLog[] }>('/api/admin/workers/logs?outcome=all&limit=50')
  ]);
  const storedLogs = logsResult.status === 'fulfilled' ? logsResult.value.items : [];
  const live = liveResult.status === 'fulfilled' ? liveResult.value.items : [];
  const local = localResult.status === 'fulfilled' ? localResult.value.items : [];
  const localByInstance = new Map(local.map((row) => [Number(row.instance_id), row]));
  const liveError =
    liveResult.status === 'rejected'
      ? String((liveResult.reason as Error)?.message || '').replace(/^\d{3}\s+/, '')
      : '';

  const rows: Record<string, unknown>[] = live.length
    ? live.map((row) => {
        const match = localByInstance.get(Number(row.instance_id));
        return {
          ...row,
          task_id: match?.task_id ?? row.label ?? '',
          started: row.start_date || match?.created_at || '',
          is_live: true
        };
      })
    : local.map((row) => ({
        ...row,
        disk_util: null,
        disk_space: null,
        started: row.created_at,
        is_live: false
      }));

  return (
    <PageContainer
      pageTitle='Workers (Vast.ai)'
      pageDescription={`${live.length} instance live · ${local.length} riwayat lokal (maks 50)`}
    >
      <div className='space-y-3'>
        {liveError ? (
          <p className='text-xs text-amber-600'>Live Vast gagal dimuat: {liveError}</p>
        ) : null}
        {live.length === 0 ? (
          <p className='text-muted-foreground text-xs'>
            Tidak ada instance live. Tabel di bawah menampilkan riwayat lokal.
          </p>
        ) : null}
        <TableShell columns={columns} rows={rows} empty='Tidak ada instance.' />
        <WorkerLogAudit logs={storedLogs} />
      </div>
    </PageContainer>
  );
}

