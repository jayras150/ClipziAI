import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { SubmitButton } from '@/components/ui/submit-button';
import { adminFetch, type Paged } from '@/lib/clipzi';
import { cancelTask, retryTask } from './actions';

export const metadata = { title: 'Admin: Tasks' };
export const dynamic = 'force-dynamic';

type TaskRow = {
  id: string;
  user_id: string;
  user_email: string | null;
  source_url: string;
  status: string;
  progress: number;
  total_clips: number | null;
  credits_spent: number;
  error_message: string | null;
  created_at: string | null;
};

const STATUSES = ['', 'queued', 'processing', 'completed', 'error', 'cancelled'];

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

function FilterBar({ params }: { params: { q?: string; status?: string } }) {
  return (
    <Card>
      <CardContent className='pt-6'>
        <form className='flex flex-wrap items-end gap-2' action='/dashboard/tasks'>
          <div className='min-w-[200px] flex-1'>
            <Input name='q' defaultValue={params.q || ''} placeholder='URL / email' className='h-9' />
          </div>
          <select
            name='status'
            defaultValue={params.status || ''}
            className='border-input bg-background h-9 rounded-md border px-3 text-sm'
          >
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {status || 'semua status'}
              </option>
            ))}
          </select>
          <SubmitButton size='sm'>
            Filter
          </SubmitButton>
          <Button variant='ghost' size='sm' render={<Link href='/dashboard/tasks' />}>
            Reset
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default async function TasksPage({
  searchParams
}: {
  searchParams: Promise<{ q?: string; status?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.status) query.set('status', params.status);
  query.set('page', params.page || '1');
  query.set('page_size', '25');

  const data = await adminFetch<Paged<TaskRow>>(`/api/admin/tasks/?${query.toString()}`);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <PageContainer pageTitle='Tasks' pageDescription={`${data.total} task tercatat`}>
      <div className='space-y-4'>
        <FilterBar params={params} />
        <Card>
          <CardContent className='pt-6'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sumber / user</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Klip</TableHead>
                  <TableHead>Kredit</TableHead>
                  <TableHead>Dibuat</TableHead>
                  <TableHead className='text-right'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.length ? (
                  data.items.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className='max-w-[240px]'>
                        <div className='truncate text-xs'>{task.source_url}</div>
                        <div className='text-muted-foreground truncate text-xs'>
                          {task.user_email || task.user_id.slice(0, 8)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={task.status === 'error' ? 'destructive' : 'outline'}>
                          {task.status}
                        </Badge>
                        {task.error_message ? (
                          <div className='text-muted-foreground max-w-[160px] truncate text-xs'>
                            {task.error_message}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell>{task.progress}%</TableCell>
                      <TableCell>{task.total_clips ?? '-'}</TableCell>
                      <TableCell>{task.credits_spent}</TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(task.created_at)}
                      </TableCell>
                      <TableCell className='text-right'>
                        <div className='flex justify-end gap-1'>
                          <Button
                            size='sm'
                            variant='outline'
                            render={<Link href={`/dashboard/tasks/${task.id}`} />}
                          >
                            Detail
                          </Button>
                          {['error', 'cancelled'].includes(task.status) ? (
                            <form action={retryTask}>
                              <input type='hidden' name='tid' value={task.id} />
                              <SubmitButton size='sm' variant='secondary'>
                                Ulangi
                              </SubmitButton>
                            </form>
                          ) : (
                            <form action={cancelTask}>
                              <input type='hidden' name='tid' value={task.id} />
                              <SubmitButton size='sm' variant='destructive'>
                                Batalkan
                              </SubmitButton>
                            </form>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7} className='text-muted-foreground text-center'>
                      Tidak ada task pada filter ini.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className='text-muted-foreground mt-3 flex justify-between text-xs'>
              <span>
                Halaman {data.page}/{totalPages} · {data.total} task
              </span>
              <span className='flex gap-2'>
                <Link
                  href={{
                    pathname: '/dashboard/tasks',
                    query: { ...params, page: String(Math.max(1, data.page - 1)) }
                  }}
                >
                  ‹ sebelumnya
                </Link>
                <Link
                  href={{
                    pathname: '/dashboard/tasks',
                    query: { ...params, page: String(Math.min(totalPages, data.page + 1)) }
                  }}
                >
                  berikutnya ›
                </Link>
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
