import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SubmitButton } from '@/components/ui/submit-button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { adminFetch } from '@/lib/clipzi';
import {
  activateUser,
  adjustCredits,
  banUser,
  forceLogoutUser,
  resetUserPassword,
  setUserPlan,
  suspendUser,
  unbanUser,
  updateUser
} from '../actions';

export const dynamic = 'force-dynamic';

type UserDetail = {
  id: string;
  email: string | null;
  name: string | null;
  provider: string;
  is_active: boolean;
  is_banned: boolean;
  ban_reason: string | null;
  email_verified: boolean;
  two_factor_enabled: boolean;
  last_login_at: string | null;
  last_login_ip: string | null;
  created_at: string | null;
  profile: {
    plan: string;
    credits_balance: number;
    credits_total_earned: number;
    credits_total_spent: number;
    credits_used_this_month: number;
    subscription_expires_at: string | null;
    max_concurrent_tasks: number;
    watermark_enabled: boolean;
    priority_queue: boolean;
    language: string;
    timezone: string;
  };
  stats: {
    tasks_total: number;
    tasks_completed: number;
    clips_total: number;
    credits_spent: number;
    revenue_paid: number;
  };
};

type TaskRow = {
  id: string;
  source_url: string;
  status: string;
  progress: number;
  total_clips: number | null;
  credits_spent: number;
  error_message: string | null;
  created_at: string | null;
};

type CreditRow = {
  id: string;
  amount: number;
  type: string;
  balance_after: number;
  description: Record<string, string> | null;
  created_at: string | null;
};

type TxRow = {
  id: string;
  duitku_transaction_id: string;
  amount: number;
  status: string;
  payment_method: string | null;
  created_at: string | null;
};

type LogRow = {
  id: string;
  actor_type: string;
  actor_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  created_at: string | null;
};

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

const PLANS = ['free', 'standar', 'pro', 'team'];

export default async function UserDetailPage({
  params,
  searchParams
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ temp?: string }>;
}) {
  const { id } = await params;
  const { temp } = await searchParams;

  const [user, tasks, credits, transactions, logs] = await Promise.all([
    adminFetch<UserDetail>(`/api/admin/users/${id}`),
    adminFetch<TaskRow[]>(`/api/admin/users/${id}/tasks`),
    adminFetch<CreditRow[]>(`/api/admin/users/${id}/credit-transactions`),
    adminFetch<TxRow[]>(`/api/admin/users/${id}/transactions`),
    adminFetch<LogRow[]>(`/api/admin/users/${id}/timeline`)
  ]);

  return (
    <PageContainer
      pageTitle={user.name || user.email || 'User'}
      pageDescription={user.email || ''}
    >
      <div className='space-y-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <Badge variant='outline'>{user.profile.plan}</Badge>
          {user.is_banned ? <Badge variant='destructive'>banned</Badge> : null}
          {!user.is_active ? <Badge variant='outline'>nonaktif</Badge> : null}
          {user.email_verified ? <Badge variant='secondary'>email terverifikasi</Badge> : null}
          {user.two_factor_enabled ? <Badge variant='secondary'>2FA</Badge> : null}
          <Badge variant='outline'>{user.provider}</Badge>
          <Button variant='ghost' size='sm' render={<Link href='/dashboard/users' />}>
            ← Kembali ke daftar
          </Button>
        </div>

        {temp ? (
          <Card className='border-amber-500/60'>
            <CardHeader>
              <CardTitle>Password sementara</CardTitle>
              <CardDescription>
                Tampil sekali. Salin sekarang dan kirim ke user lewat kanal aman; minta
                segera menggantinya.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <code className='text-base font-semibold'>{temp}</code>
            </CardContent>
          </Card>
        ) : null}

        <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
          <Card>
            <CardHeader>
              <CardDescription>Kredit</CardDescription>
              <CardTitle className='text-2xl'>{user.profile.credits_balance}</CardTitle>
            </CardHeader>
            <CardContent className='text-muted-foreground text-xs'>
              masuk {user.profile.credits_total_earned} · keluar {user.profile.credits_total_spent}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Task</CardDescription>
              <CardTitle className='text-2xl'>{user.stats.tasks_total}</CardTitle>
            </CardHeader>
            <CardContent className='text-muted-foreground text-xs'>
              {user.stats.tasks_completed} selesai · {user.stats.clips_total} klip
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Belanja (paid)</CardDescription>
              <CardTitle className='text-2xl'>
                {new Intl.NumberFormat('id-ID', {
                  style: 'currency',
                  currency: 'IDR',
                  maximumFractionDigits: 0
                }).format(user.stats.revenue_paid)}
              </CardTitle>
            </CardHeader>
            <CardContent className='text-muted-foreground text-xs'>
              kredit terpakai {user.stats.credits_spent}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Login terakhir</CardDescription>
              <CardTitle className='text-base'>{fmt(user.last_login_at)}</CardTitle>
            </CardHeader>
            <CardContent className='text-muted-foreground text-xs'>
              IP {user.last_login_ip || '-'} · daftar {fmt(user.created_at)}
            </CardContent>
          </Card>
        </div>

        <div className='grid gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle>Akun</CardTitle>
              <CardDescription>Ubah nama atau email user.</CardDescription>
            </CardHeader>
            <CardContent>
              <form action={updateUser} className='flex flex-wrap items-end gap-2'>
                <input type='hidden' name='uid' value={user.id} />
                <div className='min-w-[160px] flex-1'>
                  <label className='text-muted-foreground mb-1 block text-xs'>Nama</label>
                  <Input name='name' defaultValue={user.name || ''} className='h-9' />
                </div>
                <div className='min-w-[200px] flex-1'>
                  <label className='text-muted-foreground mb-1 block text-xs'>Email</label>
                  <Input name='email' defaultValue={user.email || ''} className='h-9' />
                </div>
                <SubmitButton size='sm'>
                  Simpan
                </SubmitButton>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Plan & kredit</CardTitle>
              <CardDescription>
                Plan saat ini: {user.profile.plan}
                {user.profile.subscription_expires_at
                  ? ` · berakhir ${fmt(user.profile.subscription_expires_at)}`
                  : ''}
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <form action={setUserPlan} className='flex flex-wrap items-end gap-2'>
                <input type='hidden' name='uid' value={user.id} />
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>Plan</label>
                  <select
                    name='plan'
                    defaultValue={user.profile.plan}
                    className='border-input bg-background h-9 rounded-md border px-3 text-sm'
                  >
                    {PLANS.map((plan) => (
                      <option key={plan} value={plan}>
                        {plan}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>
                    Set kredit (opsional)
                  </label>
                  <Input
                    name='reset_credits'
                    type='number'
                    min={0}
                    placeholder='kosong'
                    className='h-9 w-28'
                  />
                </div>
                <SubmitButton size='sm' variant='secondary'>
                  Terapkan plan
                </SubmitButton>
              </form>

              <form action={adjustCredits} className='flex flex-wrap items-end gap-2 border-t pt-3'>
                <input type='hidden' name='uid' value={user.id} />
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>Jumlah</label>
                  <Input name='amount' type='number' defaultValue={0} className='h-9 w-24' />
                </div>
                <div className='min-w-[180px] flex-1'>
                  <label className='text-muted-foreground mb-1 block text-xs'>Keterangan</label>
                  <Input name='description' placeholder='alasan penyesuaian' className='h-9' />
                </div>
                <SubmitButton size='sm'>
                  Sesuaikan kredit
                </SubmitButton>
              </form>
            </CardContent>
          </Card>

          <Card className='lg:col-span-2'>
            <CardHeader>
              <CardTitle>Keamanan & status</CardTitle>
              <CardDescription>
                Blokir, tangguhkan, reset password, atau cabut semua sesi user.
              </CardDescription>
            </CardHeader>
            <CardContent className='flex flex-wrap items-end gap-2'>
              <form action={banUser} className='flex items-end gap-2'>
                <input type='hidden' name='uid' value={user.id} />
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>Alasan blokir</label>
                  <Input name='reason' placeholder='alasan' className='h-9 w-52' />
                </div>
                <SubmitButton size='sm' variant='destructive'>
                  Blokir
                </SubmitButton>
              </form>
              <form action={unbanUser}>
                <input type='hidden' name='uid' value={user.id} />
                <SubmitButton size='sm' variant='outline'>
                  Buka blokir
                </SubmitButton>
              </form>
              <form action={suspendUser}>
                <input type='hidden' name='uid' value={user.id} />
                <SubmitButton size='sm' variant='outline'>
                  Tangguhkan
                </SubmitButton>
              </form>
              <form action={activateUser}>
                <input type='hidden' name='uid' value={user.id} />
                <SubmitButton size='sm' variant='secondary'>
                  Aktifkan
                </SubmitButton>
              </form>
              <form action={forceLogoutUser}>
                <input type='hidden' name='uid' value={user.id} />
                <SubmitButton size='sm' variant='outline'>
                  Paksa logout
                </SubmitButton>
              </form>
              <form action={resetUserPassword}>
                <input type='hidden' name='uid' value={user.id} />
                <SubmitButton size='sm' variant='outline'>
                  Reset password
                </SubmitButton>
              </form>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Task user</CardTitle>
            <CardDescription>{tasks.length} task terakhir</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sumber</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Klip</TableHead>
                  <TableHead>Kredit</TableHead>
                  <TableHead>Dibuat</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.length ? (
                  tasks.slice(0, 20).map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className='max-w-[260px] truncate text-xs'>
                        {task.source_url}
                      </TableCell>
                      <TableCell>
                        <Badge variant={task.status === 'error' ? 'destructive' : 'outline'}>
                          {task.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{task.progress}%</TableCell>
                      <TableCell>{task.total_clips ?? '-'}</TableCell>
                      <TableCell>{task.credits_spent}</TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(task.created_at)}
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

        <div className='grid gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle>Riwayat kredit</CardTitle>
              <CardDescription>{credits.length} transaksi kredit terakhir</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipe</TableHead>
                    <TableHead>Jumlah</TableHead>
                    <TableHead>Saldo</TableHead>
                    <TableHead>Waktu</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {credits.length ? (
                    credits.slice(0, 15).map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className='text-xs'>{row.type}</TableCell>
                        <TableCell
                          className={row.amount < 0 ? 'text-destructive' : 'text-emerald-600'}
                        >
                          {row.amount > 0 ? `+${row.amount}` : row.amount}
                        </TableCell>
                        <TableCell className='tabular-nums'>{row.balance_after}</TableCell>
                        <TableCell className='text-muted-foreground text-xs'>
                          {fmt(row.created_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={4} className='text-muted-foreground text-center'>
                        Belum ada transaksi kredit.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transaksi pembayaran</CardTitle>
              <CardDescription>{transactions.length} transaksi terakhir</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Jumlah</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Waktu</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transactions.length ? (
                    transactions.slice(0, 15).map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className='max-w-[120px] truncate text-xs'>
                          {row.duitku_transaction_id}
                        </TableCell>
                        <TableCell className='tabular-nums'>{row.amount}</TableCell>
                        <TableCell>
                          <Badge variant='outline'>{row.status}</Badge>
                        </TableCell>
                        <TableCell className='text-muted-foreground text-xs'>
                          {fmt(row.created_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={4} className='text-muted-foreground text-center'>
                        Belum ada transaksi.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Log aktivitas</CardTitle>
            <CardDescription>
              Aksi user dan aksi admin terhadap akun ini (dari audit log)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Aksi</TableHead>
                  <TableHead>Pelaku</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>IP</TableHead>
                  <TableHead>Waktu</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.length ? (
                  logs.slice(0, 30).map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className='text-xs font-medium'>{row.action}</TableCell>
                      <TableCell className='text-xs'>
                        {row.actor_type} · {row.actor_email || '-'}
                      </TableCell>
                      <TableCell className='text-xs'>
                        {row.resource_type || '-'}
                        {row.resource_id ? ` · ${row.resource_id.slice(0, 8)}` : ''}
                      </TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {row.ip_address || '-'}
                      </TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(row.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className='text-muted-foreground text-center'>
                      Belum ada log.
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

