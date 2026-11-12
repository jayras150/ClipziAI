import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import {
  SignupsBarChart,
  StatusPieChart,
  TasksAreaChart,
  type TimelinePoint
} from '@/features/overview/components/metrics-charts';
import { adminFetch } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Overview' };
export const dynamic = 'force-dynamic';

type Stats = {
  total_users: number;
  banned_users: number;
  total_tasks: number;
  total_clips: number;
  credits_spent: number;
  revenue_paid: number;
  tasks_by_status: Record<string, number>;
  recent_tasks: {
    id: string;
    status: string;
    progress: number;
    total_clips: number | null;
    credits_spent: number;
    user_email: string | null;
    created_at: string | null;
  }[];
  completed_tasks: number;
  failed_tasks: number;
  error_rate: number;
};

type Metrics = {
  days: number;
  timeline: TimelinePoint[];
  credits_spent_today: number;
  credits_spent_week: number;
  avg_task_duration_seconds: number;
  top_users: { email: string | null; name: string | null; tasks: number }[];
  active_workers: number;
  plans_total: number;
  ai: { configured: boolean; provider: string | null; model: string | null };
};

type Health = {
  status: string;
  database: string;
  database_latency_ms: number;
  version: string;
  environment: string;
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat('id-ID').format(value || 0);
}

function formatIdr(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0
  }).format(value || 0);
}

function formatDate(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

function KpiCard({
  label,
  value,
  hint,
  badge
}: {
  label: string;
  value: string;
  hint?: string;
  badge?: string;
}) {
  return (
    <Card className='@container/card'>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className='text-2xl font-semibold tabular-nums'>{value}</CardTitle>
      </CardHeader>
      <CardContent className='text-muted-foreground flex items-center gap-2 text-xs'>
        {badge ? <Badge variant='outline'>{badge}</Badge> : null}
        {hint}
      </CardContent>
    </Card>
  );
}

export default async function OverviewPage() {
  // Semua angka di halaman ini berasal dari database (tidak ada data contoh).
  const [stats, metrics, health] = await Promise.all([
    adminFetch<Stats>('/api/admin/system/stats'),
    adminFetch<Metrics>('/api/admin/system/metrics?days=30'),
    adminFetch<Health>('/api/admin/system/health')
  ]);

  const statusData = Object.entries(stats.tasks_by_status || {}).map(([status, count]) => ({
    status,
    count
  }));

  return (
    <PageContainer pageTitle='Overview' pageDescription='Ringkasan nyata platform ClipzyAI'>
      <div className='space-y-4'>
        <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
          <KpiCard
            label='Total user'
            value={formatNumber(stats.total_users)}
            hint={`${stats.banned_users} diblokir`}
          />
          <KpiCard
            label='Task'
            value={formatNumber(stats.total_tasks)}
            hint={`${stats.completed_tasks} selesai · ${stats.failed_tasks} gagal`}
            badge={`error ${stats.error_rate}%`}
          />
          <KpiCard label='Klip dihasilkan' value={formatNumber(stats.total_clips)} />
          <KpiCard
            label='Pendapatan (paid)'
            value={formatIdr(stats.revenue_paid)}
            hint={`Kredit terpakai ${formatNumber(stats.credits_spent)}`}
          />
        </div>

        <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
          <KpiCard
            label='Kredit terpakai hari ini'
            value={formatNumber(metrics.credits_spent_today)}
            hint={`7 hari: ${formatNumber(metrics.credits_spent_week)}`}
          />
          <KpiCard
            label='Rata-rata durasi task'
            value={`${Math.round((metrics.avg_task_duration_seconds || 0) / 60)} mnt`}
            hint='dari task selesai 30 hari terakhir'
          />
          <KpiCard
            label='Worker aktif'
            value={formatNumber(metrics.active_workers)}
            hint={`${metrics.plans_total} plan tersedia`}
          />
          <KpiCard
            label='AI'
            value={metrics.ai.configured ? 'Aktif' : 'Belum diset'}
            hint={`${metrics.ai.provider || '-'} · ${metrics.ai.model || '-'}`}
            badge={health.status}
          />
        </div>

        <div className='grid gap-4 lg:grid-cols-7'>
          <Card className='lg:col-span-4'>
            <CardHeader>
              <CardTitle>Task & klip per hari</CardTitle>
              <CardDescription>{metrics.days} hari terakhir</CardDescription>
            </CardHeader>
            <CardContent>
              <TasksAreaChart data={metrics.timeline} />
            </CardContent>
          </Card>
          <Card className='lg:col-span-3'>
            <CardHeader>
              <CardTitle>Status task</CardTitle>
              <CardDescription>Distribusi seluruh task</CardDescription>
            </CardHeader>
            <CardContent>
              {statusData.length ? (
                <StatusPieChart data={statusData} />
              ) : (
                <p className='text-muted-foreground text-sm'>Belum ada task.</p>
              )}
              <div className='mt-2 grid grid-cols-2 gap-1 text-xs'>
                {statusData.map((item) => (
                  <div key={item.status} className='flex justify-between'>
                    <span className='text-muted-foreground'>{item.status}</span>
                    <span className='font-medium'>{item.count}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card className='lg:col-span-4'>
            <CardHeader>
              <CardTitle>Pendaftar baru</CardTitle>
              <CardDescription>{metrics.days} hari terakhir</CardDescription>
            </CardHeader>
            <CardContent>
              <SignupsBarChart data={metrics.timeline} />
            </CardContent>
          </Card>
          <Card className='lg:col-span-3'>
            <CardHeader>
              <CardTitle>User paling aktif</CardTitle>
              <CardDescription>Berdasarkan jumlah task 30 hari</CardDescription>
            </CardHeader>
            <CardContent className='space-y-2 text-sm'>
              {metrics.top_users.length ? (
                metrics.top_users.map((user) => (
                  <div key={user.email} className='flex items-center justify-between gap-2'>
                    <span className='truncate'>{user.email || user.name || '-'}</span>
                    <Badge variant='secondary'>{user.tasks}</Badge>
                  </div>
                ))
              ) : (
                <p className='text-muted-foreground'>Belum ada aktivitas.</p>
              )}
              <div className='text-muted-foreground border-t pt-2 text-xs'>
                DB {health.database} · {health.database_latency_ms} ms · v{health.version} ·{' '}
                {health.environment}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className='flex flex-row items-center justify-between'>
            <div>
              <CardTitle>Task terbaru</CardTitle>
              <CardDescription>8 task terakhir dari semua user</CardDescription>
            </div>
            <Button variant='outline' size='sm' render={<Link href='/dashboard/tasks' />}>
              Lihat semua
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Klip</TableHead>
                  <TableHead>Kredit</TableHead>
                  <TableHead>Dibuat</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.recent_tasks.length ? (
                  stats.recent_tasks.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className='max-w-[220px] truncate'>
                        {task.user_email || '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={task.status === 'error' ? 'destructive' : 'outline'}>
                          {task.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{task.progress}%</TableCell>
                      <TableCell>{task.total_clips ?? '-'}</TableCell>
                      <TableCell>{task.credits_spent}</TableCell>
                      <TableCell className='text-muted-foreground'>
                        {formatDate(task.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className='text-muted-foreground text-center'>
                      Belum ada task.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

