import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SubmitButton } from '@/components/ui/submit-button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { adminFetch, type PlatformConfig } from '@/lib/clipzi';
import { applyDomain, cancelDomain, savePlatform } from '../platform-actions';

export const metadata = { title: 'Admin: Platform' };
export const dynamic = 'force-dynamic';

type DomainStatus = {
  status: string;
  pending_domain: string | null;
  pending_admin_domain: string | null;
  applied_domain: string | null;
  requested_at: string | null;
  applied_at: string | null;
  last_error: string | null;
  effective_site_url: string;
};

const STATUS_VARIANT: Record<string, 'secondary' | 'outline' | 'destructive'> = {
  applied: 'secondary',
  pending: 'outline',
  failed: 'destructive',
  idle: 'outline'
};

export default async function PlatformSettingsPage() {
  const [config, status] = await Promise.all([
    adminFetch<PlatformConfig>('/api/admin/settings/platform'),
    adminFetch<DomainStatus>('/api/admin/settings/platform/domain-status')
  ]);

  return (
    <PageContainer
      pageTitle='Platform'
      pageDescription='Domain publik/admin dan setelan yang berlaku untuk seluruh ekosistem'
    >
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardTitle>Identitas platform</CardTitle>
            <CardDescription>
              Dipakai backend (link email, redirect OAuth, CORS) dan frontend (runtime-env)
              tanpa perlu rebuild image.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form action={savePlatform} className='grid gap-4 md:grid-cols-2'>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Site URL (publik)</label>
                <Input name='site_url' defaultValue={config.site_url} placeholder='https://domain.com' />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Admin URL</label>
                <Input
                  name='admin_url'
                  defaultValue={config.admin_url}
                  placeholder='https://admin.domain.com'
                />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Email dukungan</label>
                <Input
                  name='support_email'
                  defaultValue={config.support_email}
                  placeholder='support@domain.com'
                />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Zona waktu</label>
                <Input name='timezone' defaultValue={config.timezone} placeholder='Asia/Jakarta' />
              </div>
              <div className='md:col-span-2'>
                <label className='text-muted-foreground mb-1 block text-xs'>
                  Google OAuth Client ID (publik)
                </label>
                <Input
                  name='google_client_id'
                  defaultValue={config.google_client_id}
                  placeholder='xxxx.apps.googleusercontent.com'
                />
              </div>
              <div className='flex flex-wrap items-center gap-4 md:col-span-2'>
                <label className='flex items-center gap-2 text-sm'>
                  <input
                    type='checkbox'
                    name='signup_enabled'
                    defaultChecked={config.signup_enabled}
                  />
                  Pendaftaran dibuka
                </label>
                <label className='flex items-center gap-2 text-sm'>
                  <input
                    type='checkbox'
                    name='maintenance_mode'
                    defaultChecked={config.maintenance_mode}
                  />
                  Mode maintenance
                </label>
                <SubmitButton size='sm'>
                  Simpan setelan
                </SubmitButton>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='flex flex-row items-center justify-between'>
            <div>
              <CardTitle>Ganti domain (1 klik)</CardTitle>
              <CardDescription>
                Backend menyimpan permintaan; agent VPS menerapkan ke .env + Caddy (dan DNS
                Cloudflare bila token tersedia) dalam ~30 detik, lalu melapor balik.
              </CardDescription>
            </div>
            <Badge variant={STATUS_VARIANT[status.status] || 'outline'}>{status.status}</Badge>
          </CardHeader>
          <CardContent className='space-y-4'>
            <form action={applyDomain} className='flex flex-wrap items-end gap-2'>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Domain baru</label>
                <Input name='domain' placeholder='clipzy.id' className='h-9 w-52' />
              </div>
              <div>
                <label className='text-muted-foreground mb-1 block text-xs'>Subdomain admin</label>
                <Input name='admin_domain' placeholder='admin.clipzy.id' className='h-9 w-52' />
              </div>
              <SubmitButton size='sm'>
                Terapkan domain
              </SubmitButton>
            </form>

            <div className='grid gap-2 text-sm md:grid-cols-2'>
              <div>
                Domain aktif: <strong>{status.applied_domain || config.site_url || '-'}</strong>
              </div>
              <div>
                Efektif: <strong>{status.effective_site_url}</strong>
              </div>
              <div>Pending: {status.pending_domain || '-'}</div>
              <div>Admin pending: {status.pending_admin_domain || '-'}</div>
              <div>Diminta: {status.requested_at || '-'}</div>
              <div>Diterapkan: {status.applied_at || '-'}</div>
            </div>

            {status.last_error ? (
              <pre className='bg-muted rounded p-2 text-xs whitespace-pre-wrap'>
                {status.last_error}
              </pre>
            ) : null}

            {status.status === 'pending' ? (
              <form action={cancelDomain}>
                <SubmitButton size='sm' variant='outline'>
                  Batalkan permintaan
                </SubmitButton>
              </form>
            ) : null}

            <div className='text-muted-foreground space-y-1 border-t pt-3 text-xs'>
              <p>Checklist sebelum/sesudah menekan tombol:</p>
              <ol className='list-decimal space-y-1 pl-4'>
                <li>A record domain &amp; subdomain admin di Cloudflare → IP VPS (proxied).</li>
                <li>Cloudflare Access: policy email admin untuk subdomain admin.</li>
                <li>
                  Agent VPS: <code>deploy/clipzi-domain-sync.sh</code> +{' '}
                  <code>clipzi-domain-sync.timer</code> (30 detik).
                </li>
                <li>Perbarui redirect URI OAuth Google/YouTube di Google Cloud Console.</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

