import PageContainer from '@/components/layout/page-container';
import TableShell, { StatCard, formatDate, type Column } from '@/features/admin/table-shell';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Overview' };

type Stats = {
  total_users: number;
  banned_users: number;
  total_tasks: number;
  completed_tasks: number;
  total_clips: number;
  credits_spent: number;
  tasks_by_status: Record<string, number>;
  tasks_per_day: { date: string; count: number }[];
  recent_tasks: Record<string, unknown>[];
};

const columns: Column[] = [
  { key: 'id', label: 'Task' },
  { key: 'status', label: 'Status' },
  { key: 'progress', label: 'Progress', render: (row) => String(row.progress ?? 0) + '%' },
  { key: 'source_url', label: 'Sumber' },
  { key: 'created_at', label: 'Dibuat', render: (row) => formatDate(row.created_at) }
];

export default async function OverviewPage() {
  const stats = await adminFetch<Stats>('/api/admin/system/stats');
  const statusEntries = Object.entries(stats.tasks_by_status || {});

  return (
    <PageContainer pageTitle='Overview' pageDescription='Ringkasan platform ClipzyAI'>
      <div className='space-y-6'>
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
          <StatCard label='User' value={stats.total_users} hint={stats.banned_users + ' banned'} />
          <StatCard label='Task' value={stats.total_tasks} hint={stats.completed_tasks + ' selesai'} />
          <StatCard label='Klip' value={stats.total_clips} />
          <StatCard label='Kredit terpakai' value={stats.credits_spent} />
        </div>

        <div className='grid gap-4 md:grid-cols-2'>
          <div className='rounded-lg border p-4'>
            <p className='mb-3 text-sm font-medium'>Task per status</p>
            <div className='space-y-1 text-sm'>
              {statusEntries.length ? (
                statusEntries.map(([status, count]) => (
                  <div key={status} className='flex justify-between'>
                    <span className='text-muted-foreground'>{status}</span>
                    <span className='font-medium'>{count}</span>
                  </div>
                ))
              ) : (
                <p className='text-muted-foreground'>Belum ada data.</p>
              )}
            </div>
          </div>
          <div className='rounded-lg border p-4'>
            <p className='mb-3 text-sm font-medium'>Task per hari</p>
            <div className='space-y-1 text-sm'>
              {(stats.tasks_per_day || []).slice(-7).map((row) => (
                <div key={row.date} className='flex justify-between'>
                  <span className='text-muted-foreground'>{row.date}</span>
                  <span className='font-medium'>{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className='space-y-3'>
          <p className='text-sm font-medium'>Task terbaru</p>
          <TableShell columns={columns} rows={stats.recent_tasks || []} />
        </div>
      </div>
    </PageContainer>
  );
}
