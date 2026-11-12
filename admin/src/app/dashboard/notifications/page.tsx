import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Alerts' };

type TaskRow = {
  id: string;
  status: string;
  source_url: string;
  created_at: string;
};

type WorkerRow = { instance_id: number; state: string; status_msg: string | null; task_id: string };

const taskColumns: Column[] = [
  { key: 'id', label: 'Task', render: (row) => String(row.id).slice(0, 8) },
  { key: 'status', label: 'Status' },
  { key: 'source_url', label: 'Sumber' },
  { key: 'created_at', label: 'Waktu', render: (row) => formatDate(row.created_at) }
];

const workerColumns: Column[] = [
  { key: 'instance_id', label: 'Instance' },
  { key: 'state', label: 'State' },
  { key: 'task_id', label: 'Task', render: (row) => String(row.task_id ?? '').slice(0, 8) },
  { key: 'status_msg', label: 'Pesan', render: (row) => String(row.status_msg ?? '-').slice(0, 120) }
];

export default async function AlertsPage() {
  const [tasks, workers] = await Promise.all([
    adminFetch<{ items: TaskRow[] }>('/api/admin/tasks/?status=error&page_size=20'),
    adminFetch<{ items: WorkerRow[] }>('/api/admin/workers/instances?limit=50')
  ]);
  const failedTasks = (tasks.items || []).slice(0, 20);
  const failedWorkers = (workers.items || []).filter((row) => row.state === 'failed');

  return (
    <PageContainer pageTitle='Alerts' pageDescription='Task gagal & instance bermasalah'>
      <div className='space-y-8'>
        <section className='space-y-3'>
          <p className='text-sm font-medium'>Task gagal ({failedTasks.length})</p>
          <TableShell
            columns={taskColumns}
            rows={failedTasks as unknown as Record<string, unknown>[]}
            empty='Tidak ada task gagal.'
          />
        </section>
        <section className='space-y-3'>
          <p className='text-sm font-medium'>Instance gagal ({failedWorkers.length})</p>
          <TableShell
            columns={workerColumns}
            rows={failedWorkers as unknown as Record<string, unknown>[]}
            empty='Tidak ada instance gagal.'
          />
        </section>
      </div>
    </PageContainer>
  );
}
