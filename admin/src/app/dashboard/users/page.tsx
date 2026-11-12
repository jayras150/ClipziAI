import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { adminFetch, type Paged } from '@/lib/clipzi';
import { SubmitButton } from '@/components/ui/submit-button';
import { banUser, unbanUser } from './actions';

export const metadata = { title: 'Admin: Users' };
export const dynamic = 'force-dynamic';

type UserRow = {
  id: string;
  email: string | null;
  name: string | null;
  provider: string;
  is_active: boolean;
  is_banned: boolean;
  ban_reason: string | null;
  email_verified: boolean;
  plan: string;
  credits_balance: number;
  last_login_at: string | null;
  created_at: string | null;
};

type SearchParams = {
  q?: string;
  status?: string;
  plan?: string;
  page?: string;
};

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

const STATUS_OPTIONS = [
  { value: '', label: 'Semua status' },
  { value: 'active', label: 'Aktif' },
  { value: 'banned', label: 'Diblokir' },
  { value: 'inactive', label: 'Nonaktif' }
];

const PLAN_OPTIONS = [
  { value: '', label: 'Semua plan' },
  { value: 'free', label: 'Free' },
  { value: 'standar', label: 'Standar' },
  { value: 'pro', label: 'Pro' },
  { value: 'team', label: 'Team' }
];

export default async function UsersPage({
  searchParams
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.status) query.set('status', params.status);
  if (params.plan) query.set('plan', params.plan);
  query.set('page', params.page || '1');
  query.set('page_size', '25');

  const data = await adminFetch<Paged<UserRow>>(`/api/admin/users/?${query.toString()}`);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <PageContainer
      pageTitle='Users'
      pageDescription={`${data.total} akun terdaftar — klik nama untuk detail, plan, kredit, dan log aktivitas`}
    >
      <div className='space-y-4'>
        <Card>
          <CardContent className='pt-6'>
            <form className='flex flex-wrap items-end gap-2' action='/dashboard/users'>
              <div className='min-w-[220px] flex-1'>
                <label className='text-muted-foreground mb-1 block text-xs'>Cari</label>
                <Input
                  name='q'
                  defaultValue={params.q || ''}
                  placeholder='email atau nama'
                  className='h-9'
                />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Status</label>
                <select
                  name='status'
                  defaultValue={params.status || ''}
                  className='border-input bg-background h-9 rounded-md border px-3 text-sm'
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Plan</label>
                <select
                  name='plan'
                  defaultValue={params.plan || ''}
                  className='border-input bg-background h-9 rounded-md border px-3 text-sm'
                >
                  {PLAN_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <Button type='submit' size='sm'>
                Terapkan
              </Button>
              <Button variant='ghost' size='sm' render={<Link href='/dashboard/users' />}>
                Reset
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className='pt-6'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Kredit</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Login terakhir</TableHead>
                  <TableHead>Dibuat</TableHead>
                  <TableHead className='text-right'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.length ? (
                  data.items.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell>
                        <Link
                          href={`/dashboard/users/${user.id}`}
                          className='font-medium hover:underline'
                        >
                          {user.name || user.email || user.id.slice(0, 8)}
                        </Link>
                        <div className='text-muted-foreground text-xs'>{user.email}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant='outline'>{user.plan}</Badge>
                      </TableCell>
                      <TableCell className='tabular-nums'>{user.credits_balance}</TableCell>
                      <TableCell>
                        {user.is_banned ? (
                          <Badge variant='destructive'>banned</Badge>
                        ) : user.is_active ? (
                          <Badge variant='secondary'>aktif</Badge>
                        ) : (
                          <Badge variant='outline'>nonaktif</Badge>
                        )}
                        {user.ban_reason ? (
                          <div className='text-muted-foreground max-w-[160px] truncate text-xs'>
                            {user.ban_reason}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(user.last_login_at)}
                      </TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(user.created_at)}
                      </TableCell>
                      <TableCell className='text-right'>
                        <div className='flex justify-end gap-1'>
                          <form action={user.is_banned ? unbanUser : banUser}>
                            <input type='hidden' name='uid' value={user.id} />
                            <SubmitButton
                              size='sm'
                              pendingLabel='Proses…'
                              variant={user.is_banned ? 'outline' : 'destructive'}
                            >
                              {user.is_banned ? 'Buka blokir' : 'Blokir'}
                            </SubmitButton>
                          </form>
                          <Button
                            size='sm'
                            variant='secondary'
                            render={<Link href={`/dashboard/users/${user.id}`} />}
                          >
                            Detail
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7} className='text-muted-foreground text-center'>
                      Tidak ada user yang cocok dengan filter.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className='mt-3 flex items-center justify-between text-sm'>
              <span className='text-muted-foreground'>
                Halaman {data.page} dari {totalPages} · {data.total} akun
              </span>
              <div className='flex gap-2'>
                <Button size='sm' variant='outline' disabled={data.page <= 1}>
                  <Link
                    href={{
                      pathname: '/dashboard/users',
                      query: { ...params, page: String(Math.max(1, data.page - 1)) }
                    }}
                  >
                    Sebelumnya
                  </Link>
                </Button>
                <Button size='sm' variant='outline' disabled={data.page >= totalPages}>
                  <Link
                    href={{
                      pathname: '/dashboard/users',
                      query: { ...params, page: String(Math.min(totalPages, data.page + 1)) }
                    }}
                  >
                    Berikutnya
                  </Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

