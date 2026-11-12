import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { adminFetch, type Paged } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Transactions' };
export const dynamic = 'force-dynamic';

type TxRow = {
  id: string;
  user_id: string;
  user_email: string | null;
  duitku_transaction_id: string;
  amount: number;
  status: string;
  payment_method: string | null;
  created_at: string | null;
};

type Summary = { paid_count: number; paid_amount: number };

function fmtIdr(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0
  }).format(value || 0);
}

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

export default async function TransactionsPage({
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

  const [data, summary] = await Promise.all([
    adminFetch<Paged<TxRow>>(`/api/admin/transactions/?${query.toString()}`),
    adminFetch<Summary>('/api/admin/transactions/summary')
  ]);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <PageContainer pageTitle='Transactions' pageDescription={`${data.total} transaksi`}>
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardDescription>Total pembayaran sukses</CardDescription>
            <CardTitle className='text-2xl'>
              {fmtIdr(summary.paid_amount)} · {summary.paid_count} transaksi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className='flex flex-wrap items-end gap-2' action='/dashboard/transactions'>
              <div className='min-w-[200px] flex-1'>
                <Input name='q' defaultValue={params.q || ''} placeholder='ID / email' className='h-9' />
              </div>
              <select
                name='status'
                defaultValue={params.status || ''}
                className='border-input bg-background h-9 rounded-md border px-3 text-sm'
              >
                {['', 'pending', 'success', 'failed', 'expired'].map((status) => (
                  <option key={status} value={status}>
                    {status || 'semua status'}
                  </option>
                ))}
              </select>
              <Button size='sm' type='submit'>
                Filter
              </Button>
              <Button variant='ghost' size='sm' render={<Link href='/dashboard/transactions' />}>
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
                  <TableHead>ID</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Jumlah</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Metode</TableHead>
                  <TableHead>Waktu</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.length ? (
                  data.items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className='max-w-[140px] truncate text-xs'>
                        {row.duitku_transaction_id}
                      </TableCell>
                      <TableCell className='max-w-[200px] truncate text-xs'>
                        <Link className='hover:underline' href={`/dashboard/users/${row.user_id}`}>
                          {row.user_email || row.user_id.slice(0, 8)}
                        </Link>
                      </TableCell>
                      <TableCell className='tabular-nums'>{fmtIdr(row.amount)}</TableCell>
                      <TableCell>
                        <Badge variant={row.status === 'success' ? 'secondary' : 'outline'}>
                          {row.status}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-xs'>{row.payment_method || '-'}</TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(row.created_at)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className='text-muted-foreground text-center'>
                      Belum ada transaksi pada filter ini.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className='text-muted-foreground mt-3 flex justify-between text-xs'>
              <span>
                Halaman {data.page}/{totalPages}
              </span>
              <span className='flex gap-2'>
                <Link
                  href={{
                    pathname: '/dashboard/transactions',
                    query: { ...params, page: String(Math.max(1, data.page - 1)) }
                  }}
                >
                  ‹ sebelumnya
                </Link>
                <Link
                  href={{
                    pathname: '/dashboard/transactions',
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
