import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { adminFetch } from '@/lib/clipzi';
import {
  deleteCookie,
  probeAllCookies,
  probeCookie,
  saveYoutubeCookies,
  setCookieStatus
} from '../youtube-actions';

export const metadata = { title: 'Admin: YouTube Cookies' };
export const dynamic = 'force-dynamic';

type CookieRow = {
  id: string;
  label: string;
  status: string;
  fail_count: number;
  success_count: number;
  refreshed_by_ytdlp: boolean;
  last_used_at: string | null;
  last_checked_at: string | null;
  last_error: string | null;
};

type Settings = {
  mode: string;
  label: string | null;
  updated_at: string | null;
  base64_set: boolean;
  summary: {
    cookie_count?: number;
    domains?: string[];
    earliest_expiry?: string | null;
  } | null;
};

function fmt(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

export default async function YoutubeCookiesPage() {
  const [cookies, settings] = await Promise.all([
    adminFetch<CookieRow[]>('/api/admin/ytdlp-cookies'),
    adminFetch<Settings>('/api/admin/ytdlp-cookies/settings')
  ]);

  return (
    <PageContainer
      pageTitle='YouTube Cookies'
      pageDescription='Cookies yt-dlp (Netscape atau base64) untuk download yang butuh login'
    >
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardTitle>Tambah / perbarui cookies</CardTitle>
            <CardDescription>
              Tempel isi cookies.txt (Netscape) atau hasil base64-nya. Disimpan terenkripsi
              AES-256-GCM dan dipakai rotasi otomatis.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form action={saveYoutubeCookies} className='space-y-3'>
              <div className='flex flex-wrap items-end gap-2'>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>Label akun</label>
                  <Input name='label' placeholder='akun-1' className='h-9 w-40' />
                </div>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>Mode</label>
                  <select
                    name='mode'
                    defaultValue={settings.mode || 'db'}
                    className='border-input bg-background h-9 rounded-md border px-3 text-sm'
                  >
                    <option value='db'>Rotasi DB (disarankan)</option>
                    <option value='base64'>Base64 env (worker)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Base64 cookies.txt</label>
                <textarea
                  name='cookies_base64'
                  rows={4}
                  placeholder='Tempel base64 di sini (boleh dengan prefix data:text/plain;base64,)'
                  className='border-input bg-background w-full rounded-md border p-2 font-mono text-xs'
                />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>
                  atau isi cookies.txt (Netscape)
                </label>
                <textarea
                  name='cookies'
                  rows={4}
                  placeholder='# Netscape HTTP Cookie File ...'
                  className='border-input bg-background w-full rounded-md border p-2 font-mono text-xs'
                />
              </div>
              <Button type='submit' size='sm'>
                Simpan cookies
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='flex flex-row items-center justify-between'>
            <div>
              <CardTitle>Cookies tersimpan ({cookies.length})</CardTitle>
              <CardDescription>
                Mode aktif: {settings.mode} · base64 env: {settings.base64_set ? 'ada' : 'belum'} ·
                diperbarui {fmt(settings.updated_at)}
              </CardDescription>
            </div>
            <form action={probeAllCookies}>
              <Button type='submit' size='sm' variant='outline'>
                Uji semua
              </Button>
            </form>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Sukses/Gagal</TableHead>
                  <TableHead>Dipakai</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead className='text-right'>Aksi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cookies.length ? (
                  cookies.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className='text-xs font-medium'>{row.label}</TableCell>
                      <TableCell>
                        <Badge variant={row.status === 'active' ? 'secondary' : 'outline'}>
                          {row.status}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-xs'>
                        {row.success_count}/{row.fail_count}
                      </TableCell>
                      <TableCell className='text-muted-foreground text-xs'>
                        {fmt(row.last_used_at)}
                      </TableCell>
                      <TableCell className='text-muted-foreground max-w-[200px] truncate text-xs'>
                        {row.last_error || '-'}
                      </TableCell>
                      <TableCell className='text-right'>
                        <div className='flex flex-wrap justify-end gap-1'>
                          <form action={probeCookie}>
                            <input type='hidden' name='cid' value={row.id} />
                            <Button size='sm' variant='outline' type='submit'>
                              Uji
                            </Button>
                          </form>
                          <form action={setCookieStatus}>
                            <input type='hidden' name='cid' value={row.id} />
                            <input
                              type='hidden'
                              name='action'
                              value={row.status === 'active' ? 'disable' : 'reactivate'}
                            />
                            <Button size='sm' variant='secondary' type='submit'>
                              {row.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}
                            </Button>
                          </form>
                          <form action={deleteCookie}>
                            <input type='hidden' name='cid' value={row.id} />
                            <Button size='sm' variant='destructive' type='submit'>
                              Hapus
                            </Button>
                          </form>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className='text-muted-foreground text-center'>
                      Belum ada cookies. Tambahkan di form di atas.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className='text-muted-foreground mt-3 space-y-1 border-t pt-3 text-xs'>
              <p>
                Ringkasan setelan: {settings.summary?.cookie_count ?? 0} cookie · domain{' '}
                {(settings.summary?.domains || []).join(', ') || '-'} · kedaluwarsa tercepat{' '}
                {settings.summary?.earliest_expiry || '-'}
              </p>
              <p>
                Ekspor base64 untuk env worker:{' '}
                <code>GET /api/admin/ytdlp-cookies/&lt;id&gt;/base64</code>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

