import Link from 'next/link';

import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { adminFetch, type Paged } from '@/lib/clipzi';

export const metadata = { title: 'Admin: Audit Log' };
export const dynamic = 'force-dynamic';

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

export default async function AuditPage({
  searchParams
}: {
  searchParams: Promise<{ q?: string; action?: string; actor_type?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.action) query.set('action', params.action);
  if (params.actor_type) query.set('actor_type', params.actor_type);
  query.set('page', params.page || '1');
  query.set('page_size', '50');

  const data = await adminFetch<Paged<LogRow>>(`/api/admin/audit/?${query.toString()}`);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <PageContainer pageTitle='Audit Log' pageDescription={`${data.total} kejadian tercatat`}>
      <div className='space-y-4'>
        <Card>
          <CardContent className='pt-6'>
            <form className='flex flex-wrap items-end gap-2' action='/dashboard/audit'>
              <div className='min-w-[200px] flex-1'>
                <Input
                  name='q'
                  defaultValue={params.q || ''}
                  placeholder='aksi / email / resource id'
                  className='h-9'
                />
              </div>
              <div>
                <Input
                  name='action'
                  defaultValue={params.action || ''}
                  placeholder='filter aksi'
                  className='h-9 w-40'
                />
              </div>
              <select
                name='actor_type'
                defaultValue={params.actor_type || ''}
                className='border-input bg-background h-9 rounded-md border px-3 text-sm'
              >
                {['', 'admin', 'user', 'system'].map((actor) => (
                  <option key={actor} value={actor}>
                    {actor || 'semua pelaku'}
                  </option>
                ))}
              </select>
              <Button size='sm' type='submit'>
                Filter
              </Button>
              <Button variant='ghost' size='sm' render={<Link href='/dashboard/audit' />}>
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
                  <TableHead>Aksi</TableHead>
                  <TableHead>Pelaku</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>IP</TableHead>
                  <TableHead>Waktu</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.length ? (
                  data.items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className='text-xs font-medium'>{row.action}</TableCell>
                      <TableCell className='text-xs'>
                        <Badge variant='outline'>{row.actor_type}</Badge>{' '}
                        {row.actor_email || '-'}
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
                      Tidak ada log pada filter ini.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className='text-muted-foreground mt-3 flex justify-between text-xs'>
              <span>
                Halaman {data.page}/{totalPages} · {data.total} log
              </span>
              <span className='flex gap-2'>
                <Link
                  href={{
                    pathname: '/dashboard/audit',
                    query: { ...params, page: String(Math.max(1, data.page - 1)) }
                  }}
                >
                  ‹ sebelumnya
                </Link>
                <Link
                  href={{
                    pathname: '/dashboard/audit',
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
