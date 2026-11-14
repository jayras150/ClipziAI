import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SubmitButton } from '@/components/ui/submit-button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ProxyManager } from '@/features/settings/components/proxy-manager';
import CookieImporter from '@/features/settings/components/cookie-importer';
import CookieBase64Actions from '@/features/settings/components/cookie-base64-actions';
import type { ProxyPoolView } from '../proxy-actions';
import { adminFetch } from '@/lib/clipzi';
import {
  deleteCookie,
  probeAllCookies,
  probeCookie,
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
  const [cookies, settings, proxyPool] = await Promise.all([
    adminFetch<CookieRow[]>('/api/admin/ytdlp-cookies'),
    adminFetch<Settings>('/api/admin/ytdlp-cookies/settings'),
    adminFetch<ProxyPoolView>('/api/admin/settings/proxies')
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
              Tempel cookies.txt (Netscape) atau base64. Tombol Encode membuat base64;
              centang “Simpan base64 untuk ENV worker” agar fallback ENV ikut diperbarui.
              Pemilihan cookies di pool dilakukan acak antar akun.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CookieImporter />
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
              <SubmitButton size='sm' variant='outline'>
                Uji semua
              </SubmitButton>
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
                          <CookieBase64Actions id={row.id} />
                          <form action={probeCookie}>
                            <input type='hidden' name='cid' value={row.id} />
                            <SubmitButton size='sm' variant='outline'>
                              Uji
                            </SubmitButton>
                          </form>
                          <form action={setCookieStatus}>
                            <input type='hidden' name='cid' value={row.id} />
                            <input
                              type='hidden'
                              name='action'
                              value={row.status === 'active' ? 'disable' : 'reactivate'}
                            />
                            <SubmitButton size='sm' variant='secondary'>
                              {row.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}
                            </SubmitButton>
                          </form>
                          <form action={deleteCookie}>
                            <input type='hidden' name='cid' value={row.id} />
                            <SubmitButton size='sm' variant='destructive'>
                              Hapus
                            </SubmitButton>
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
        <ProxyManager initial={proxyPool} />
      </div>
    </PageContainer>
  );
}

