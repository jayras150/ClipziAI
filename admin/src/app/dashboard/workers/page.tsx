import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { Button } from '@/components/ui/button';
import { adminFetch } from '@/lib/clipzi';
import { destroyInstance } from './actions';

export const metadata = { title: 'Admin: Workers' };

type WorkerRow = {
  instance_id: number;
  task_id: string;
  state: string;
  gpu_name: string | null;
  price_per_hour: number | null;
  attempt: number;
  created_at: string | null;
  log_tail: string | null;
};

type Response = { items: WorkerRow[]; count: number };

const columns: Column[] = [
  { key: 'instance_id', label: 'Instance' },
  { key: 'state', label: 'State' },
  { key: 'gpu_name', label: 'GPU' },
  {
    key: 'price_per_hour',
    label: '$/jam',
    render: (row) => (row.price_per_hour ? '$' + Number(row.price_per_hour).toFixed(3) : '-')
  },
  { key: 'attempt', label: 'Percobaan' },
  { key: 'task_id', label: 'Task', render: (row) => String(row.task_id ?? '').slice(0, 8) },
  { key: 'created_at', label: 'Mulai', render: (row) => formatDate(row.created_at) },
  {
    key: 'actions',
    label: 'Aksi',
    render: (row) => (
      <form action={destroyInstance}>
        <input type='hidden' name='instance_id' value={String(row.instance_id)} />
        <Button size='sm' variant='destructive' type='submit'>
          Destroy
        </Button>
      </form>
    )
  }
];

export default async function WorkersPage() {
  const data = await adminFetch<Response>('/api/admin/workers/instances?limit=50');
  return (
    <PageContainer
      pageTitle='Workers (Vast.ai)'
      pageDescription={data.count + ' instance aktif/riwayat (maks 50)'}
    >
      <TableShell columns={columns} rows={data.items as unknown as Record<string, unknown>[]} empty='Tidak ada instance.' />
    </PageContainer>
  );
}
