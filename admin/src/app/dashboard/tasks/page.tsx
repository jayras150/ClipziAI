import PageContainer from '@/components/layout/page-container';
import TableShell, { formatDate, type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Tasks' };

type TaskRow = {
  id: string;
  user_id: string;
  source_url: string;
  status: string;
  progress: number;
  created_at: string;
};

const columns: Column[] = [
  { key: 'id', label: 'Task', render: (row) => String(row.id).slice(0, 8) },
  { key: 'status', label: 'Status' },
  { key: 'progress', label: 'Progress', render: (row) => String(row.progress ?? 0) + '%' },
  { key: 'user_id', label: 'User', render: (row) => String(row.user_id ?? '').slice(0, 8) },
  {
    key: 'source_url',
    label: 'Sumber',
    render: (row) => (
      <span className='block max-w-[320px] truncate' title={String(row.source_url)}>
        {String(row.source_url)}
      </span>
    )
  },
  { key: 'created_at', label: 'Dibuat', render: (row) => formatDate(row.created_at) }
];

export default async function TasksPage() {
  const tasks = await adminFetch<TaskRow[]>('/api/admin/tasks/');
  return (
    <PageContainer pageTitle='Tasks' pageDescription={tasks.length + ' task terakhir'}>
      <TableShell columns={columns} rows={tasks as unknown as Record<string, unknown>[]} />
    </PageContainer>
  );
}
