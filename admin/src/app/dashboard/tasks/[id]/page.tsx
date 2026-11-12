import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SubmitButton } from '@/components/ui/submit-button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { adminFetch } from '@/lib/clipzi';
import { cancelTask, retryTask } from '../actions';

export const dynamic = 'force-dynamic';

type TaskDetail = {
  id: string;
  user_id: string;
  user_email: string | null;
  source_url: string;
  source_type: string;
  status: string;
  progress: number;
  credits_spent: number;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
  original_duration: number | null;
  plan_at_time: string | null;
  youtube_video_url: string | null;
  editing_options: Record<string, unknown> | null;
  clips: {
    id: string;
    clip_index: number;
    title: string;
    duration: number;
    download_url: string | null;
  }[];
};

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

export default async function TaskDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const task = await adminFetch<TaskDetail>(`/api/admin/tasks/${id}`);

  return (
    <PageContainer pageTitle='Detail task' pageDescription={task.source_url}>
      <div className='space-y-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <Badge variant={task.status === 'error' ? 'destructive' : 'outline'}>{task.status}</Badge>
          <Badge variant='secondary'>progress {task.progress}%</Badge>
          {task.plan_at_time ? <Badge variant='outline'>plan {task.plan_at_time}</Badge> : null}
          <Button variant='ghost' size='sm' render={<Link href='/dashboard/tasks' />}>
            ← Kembali
          </Button>
          {['error', 'cancelled'].includes(task.status) ? (
            <form action={retryTask}>
              <input type='hidden' name='tid' value={task.id} />
              <SubmitButton size='sm' variant='secondary'>
                Ulangi task
              </SubmitButton>
            </form>
          ) : (
            <form action={cancelTask}>
              <input type='hidden' name='tid' value={task.id} />
              <SubmitButton size='sm' variant='destructive'>
                Batalkan task
              </SubmitButton>
            </form>
          )}
        </div>

        <div className='grid gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle>Ringkasan</CardTitle>
              <CardDescription className='break-all'>{task.source_url}</CardDescription>
            </CardHeader>
            <CardContent className='space-y-1 text-sm'>
              <div>User: {task.user_email || task.user_id}</div>
              <div>Tipe: {task.source_type}</div>
              <div>
                Durasi asli:{' '}
                {task.original_duration ? `${Math.round(task.original_duration)}s` : '-'}
              </div>
              <div>Kredit terpakai: {task.credits_spent}</div>
              <div>Dibuat: {fmt(task.created_at)}</div>
              <div>Selesai: {fmt(task.completed_at)}</div>
              {task.youtube_video_url ? (
                <div>
                  YouTube:{' '}
                  <a
                    className='underline'
                    href={task.youtube_video_url}
                    target='_blank'
                    rel='noreferrer'
                  >
                    buka video
                  </a>
                </div>
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Error / opsi editing</CardTitle>
              <CardDescription>Pesan error dan opsi yang dipakai pipeline</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className='bg-muted max-h-40 overflow-auto rounded p-2 text-xs whitespace-pre-wrap'>
                {task.error_message || 'Tidak ada error.'}
              </pre>
              <pre className='bg-muted mt-2 max-h-40 overflow-auto rounded p-2 text-xs whitespace-pre-wrap'>
                {JSON.stringify(task.editing_options || {}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Klip ({task.clips.length})</CardTitle>
            <CardDescription>Hasil klip untuk task ini</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Judul</TableHead>
                  <TableHead>Durasi</TableHead>
                  <TableHead>Link</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {task.clips.length ? (
                  task.clips.map((clip) => (
                    <TableRow key={clip.id}>
                      <TableCell>{clip.clip_index}</TableCell>
                      <TableCell className='max-w-[320px] truncate'>{clip.title || '-'}</TableCell>
                      <TableCell>{Math.round(clip.duration)}s</TableCell>
                      <TableCell className='text-xs'>
                        {clip.download_url ? (
                          <a
                            className='underline'
                            href={clip.download_url}
                            target='_blank'
                            rel='noreferrer'
                          >
                            unduh
                          </a>
                        ) : (
                          '-'
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={4} className='text-muted-foreground text-center'>
                      Belum ada klip.
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
