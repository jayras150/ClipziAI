'use client';

import Link from 'next/link';
import { useEffect, useState, useTransition } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  autoVastConnection,
  loadVastConnections,
  resetVastConfig,
  saveVastConfig,
  testVastConnection,
  testVastOffers,
} from '@/app/dashboard/settings/vast/actions';
import VastEnvPanel from '@/features/settings/components/vast-env-panel';
import VastBillingPanel from '@/features/settings/components/vast-billing-panel';

export type VastConfigData = {
  api_key_set: boolean;
  api_key_masked: string;
  api_key_source: string;
  dispatch_mode: string;
  dispatch_mode_effective: string;
  endpoint_url: string;
  endpoint_name: string;
  worker_image: string;
  template_hash: string;
  worker_disk: number;
  gpu_filter: string;
  gpu_allowlist: string[];
  max_price_per_hour: number;
  max_price_multiplier: number;
  min_workers: number;
  max_workers: number;
  target_util: number;
  inactivity_timeout: number;
  boot_timeout: number;
  worker_start_timeout: number;
  oneshot_timeout: number;
  oneshot_boot_timeout: number;
  max_attempts: number;
  retry_backoff: number;
  request_timeout: number;
  supervisor_interval: number;
  restore_enabled: boolean;
  restore_connection: string;
  restore_src: string;
  restore_dst: string;
  restore_model_path: string;
  restore_timeout: number;
  sources: Record<string, string>;
  ready: boolean;
};

const TABS = ['Konfigurasi', 'Environment', 'Billing'] as const;
type Tab = (typeof TABS)[number];

export default function VastPanel({
  config,
  envItems
}: {
  config: VastConfigData;
  envItems: Array<Record<string, unknown>>;
}) {
  const [tab, setTab] = useState<Tab>('Konfigurasi');
  const [form, setForm] = useState({ ...config });
  const [allowlist, setAllowlist] = useState((config.gpu_allowlist || []).join(', '));
  const [apiKey, setApiKey] = useState('');
  const [clearKey, setClearKey] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();
  const [connections, setConnections] = useState<Array<{ id: string; name: string }>>([]);
  const [connectionsBusy, setConnectionsBusy] = useState(false);
  const [connectionsError, setConnectionsError] = useState('');
  const [connectionsLoaded, setConnectionsLoaded] = useState(false);
  const set = (key: keyof VastConfigData, value: unknown) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const refreshConnections = async () => {
    setConnectionsBusy(true);
    setConnectionsError('');
    try {
      const response = await loadVastConnections();
      if ('error' in response && response.error) {
        setConnectionsError(String(response.error));
        return;
      }
      const payload = response as {
        connections: Array<{ id: string; name: string }>;
      };
      setConnections(payload.connections || []);
      setConnectionsLoaded(true);
    } finally {
      setConnectionsBusy(false);
    }
  };

  const applyAutoConnection = async () => {
    setConnectionsBusy(true);
    setError('');
    setResult('');
    try {
      const response = await autoVastConnection();
      if ('error' in response && response.error) {
        setError(String(response.error));
        return;
      }
      const data = (response as { data?: Record<string, unknown> }).data || {};
      const selected = String(data.selected || '');
      if (selected) {
        setForm((current) => ({ ...current, restore_connection: selected }));
      }
      setResult(
        selected
          ? `Connection otomatis dipakai: ${selected}. Konfigurasi restore sudah disimpan.`
          : 'Tidak ada koneksi yang bisa dipilih otomatis.'
      );
      await refreshConnections();
    } finally {
      setConnectionsBusy(false);
    }
  };

  useEffect(() => {
    void refreshConnections();
    // Muat sekali saat panel dibuka; tombol Refresh tersedia untuk memuat ulang.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const run = (kind: 'save' | 'test' | 'offers' | 'reset') => {
    setError('');
    setResult('');
    startTransition(async () => {
      if (kind === 'save') {
        const payload: Record<string, unknown> = {
          dispatch_mode: form.dispatch_mode,
          endpoint_url: form.endpoint_url,
          endpoint_name: form.endpoint_name,
          worker_image: form.worker_image,
          template_hash: form.template_hash,
          worker_disk: Number(form.worker_disk),
          gpu_filter: form.gpu_filter,
          gpu_allowlist: allowlist
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          max_price_per_hour: Number(form.max_price_per_hour),
          max_price_multiplier: Number(form.max_price_multiplier),
          min_workers: Number(form.min_workers),
          max_workers: Number(form.max_workers),
          target_util: Number(form.target_util),
          inactivity_timeout: Number(form.inactivity_timeout),
          boot_timeout: Number(form.boot_timeout),
          worker_start_timeout: Number(form.worker_start_timeout),
          oneshot_timeout: Number(form.oneshot_timeout),
          oneshot_boot_timeout: Number(form.oneshot_boot_timeout),
          max_attempts: Number(form.max_attempts),
          retry_backoff: Number(form.retry_backoff),
          request_timeout: Number(form.request_timeout),
          supervisor_interval: Number(form.supervisor_interval),
          restore_enabled: Boolean(form.restore_enabled),
          restore_connection: form.restore_connection,
          restore_src: form.restore_src,
          restore_dst: form.restore_dst,
          restore_model_path: form.restore_model_path,
          restore_timeout: Number(form.restore_timeout)
        };
        if (apiKey.trim()) payload.api_key = apiKey.trim();
        if (clearKey) payload.clear_api_key = true;
        const response = await saveVastConfig(payload);
        if ('error' in response && response.error) {
          setError(String(response.error));
          return;
        }
        setApiKey('');
        setClearKey(false);
        setResult('Konfigurasi disimpan dan langsung diterapkan.');
        return;
      }
      if (kind === 'reset') {
        const response = await resetVastConfig();
        if ('error' in response && response.error) {
          setError(String(response.error));
          return;
        }
        setResult('Override DB dihapus. Nilai kembali mengikuti ENV/default.');
        return;
      }
      if (kind === 'test') {
        const response = await testVastConnection();
        setResult(JSON.stringify(response, null, 2));
        if ((response as { ok?: boolean }).ok === false) {
          setError(String((response as { error?: string }).error || 'Koneksi gagal.'));
        }
        return;
      }
      const response = await testVastOffers(5);
      setResult(JSON.stringify(response, null, 2));
      if ('error' in response && response.error) setError(String(response.error));
    });
  };

  const connectionKnown = connections.some(
    (item) => item.id === String(form.restore_connection || '')
  );

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-2'>
        {TABS.map((item) => (
          <button
            key={item}
            type='button'
            onClick={() => setTab(item)}
            className={`rounded-md border px-3 py-1.5 text-sm ${
              tab === item ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === 'Environment' ? <VastEnvPanel items={envItems} /> : null}
      {tab === 'Billing' ? <VastBillingPanel /> : null}

      {tab === 'Konfigurasi' ? (
        <div className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle>Koneksi & worker</CardTitle>
              <CardDescription>
                API key sumber: {config.api_key_source} ({config.api_key_masked || '-'}) · mode
                efektif {config.dispatch_mode_effective} · prioritas DB &gt; ENV &gt; default
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-3'>
              <div className='space-y-1 md:col-span-3'>
                <label className='text-muted-foreground text-xs'>API key Vast (kosongkan = tetap)</label>
                <Input
                  type='password'
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={config.api_key_set ? 'sudah diset — isi untuk mengganti' : 'isi API key Vast'}
                  autoComplete='new-password'
                />
                <label className='text-muted-foreground flex items-center gap-2 text-xs'>
                  <input
                    type='checkbox'
                    checked={clearKey}
                    onChange={(event) => setClearKey(event.target.checked)}
                  />
                  Hapus API key dari DB (kembali ke ENV)
                </label>
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Mode dispatch</label>
                <select
                  value={form.dispatch_mode}
                  onChange={(event) => set('dispatch_mode', event.target.value)}
                  className='border-input bg-background h-9 w-full rounded-md border px-3 text-sm'
                >
                  <option value=''>auto</option>
                  <option value='oneshot'>oneshot</option>
                  <option value='http'>http</option>
                  <option value='sdk'>sdk</option>
                </select>
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Endpoint URL (mode http)</label>
                <Input value={form.endpoint_url} onChange={(event) => set('endpoint_url', event.target.value)} placeholder='https://…' />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Endpoint name (mode sdk)</label>
                <Input value={form.endpoint_name} onChange={(event) => set('endpoint_name', event.target.value)} placeholder='clipzy-processing' />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Worker image / tag</label>
                <Input value={form.worker_image} onChange={(event) => set('worker_image', event.target.value)} placeholder='sujinwo555/clipzi-backend:worker' />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Template hash (opsional)</label>
                <Input value={form.template_hash} onChange={(event) => set('template_hash', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Storage instance (GB)</label>
                <Input type='number' min={10} max={500} value={String(form.worker_disk)} onChange={(event) => set('worker_disk', event.target.value)} />
              </div>
              <div className='space-y-1 md:col-span-2'>
                <label className='text-muted-foreground text-xs'>GPU diizinkan (pisah koma; kosong = semua)</label>
                <Input value={allowlist} onChange={(event) => setAllowlist(event.target.value)} placeholder='RTX 4090, A100' />
              </div>
              <div className='space-y-1 md:col-span-3'>
                <label className='text-muted-foreground text-xs'>Filter GPU (query Vast)</label>
                <Input value={form.gpu_filter} onChange={(event) => set('gpu_filter', event.target.value)} placeholder='gpu_ram>=16 disk_space>=40 inet_down>200' />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Batas biaya & scaling</CardTitle>
              <CardDescription>
                Harga maksimum per jam, jumlah worker, dan waktu idle sebelum instance dihapus.
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-3'>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Harga maksimum $/jam (0 = tanpa batas)</label>
                <Input type='number' step='0.001' min={0} value={String(form.max_price_per_hour)} onChange={(event) => set('max_price_per_hour', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Pengali harga maksimum</label>
                <Input type='number' step='0.1' min={1} max={10} value={String(form.max_price_multiplier)} onChange={(event) => set('max_price_multiplier', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Max concurrent workers</label>
                <Input type='number' min={1} max={100} value={String(form.max_workers)} onChange={(event) => set('max_workers', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Min workers</label>
                <Input type='number' min={0} max={50} value={String(form.min_workers)} onChange={(event) => set('min_workers', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Target utilisasi (0.1–1)</label>
                <Input type='number' step='0.05' min={0.1} max={1} value={String(form.target_util)} onChange={(event) => set('target_util', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Inactivity timeout (detik)</label>
                <Input type='number' min={30} value={String(form.inactivity_timeout)} onChange={(event) => set('inactivity_timeout', event.target.value)} />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Restore model dari Google Drive</CardTitle>
              <CardDescription>
                Setelah instance dibuat, backend menyalin folder model ke /workspace dan
                pipeline menunggu sampai file stabil. Jika gagal, worker mengunduh ulang.
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-3'>
              <Link
                href='/dashboard/settings/models'
                className='text-primary text-xs underline md:col-span-3'
              >
                Kelola / tambah model Whisper dari Google Drive →
              </Link>
              <label className='text-muted-foreground flex items-center gap-2 text-sm md:col-span-3'>
                <input
                  type='checkbox'
                  checked={Boolean(form.restore_enabled)}
                  onChange={(event) => set('restore_enabled', event.target.checked)}
                />
                Aktifkan restore workspace sebelum pipeline
              </label>
              <div className='space-y-1'>
                <div className='flex items-center justify-between gap-2'>
                  <label className='text-muted-foreground text-xs'>Connection ID Vast</label>
                  <div className='flex gap-1'>
                    <button
                      type='button'
                      className='rounded border px-2 py-1 text-[11px] hover:bg-muted'
                      onClick={() => void refreshConnections()}
                      disabled={connectionsBusy}
                    >
                      {connectionsBusy ? 'Memuat…' : 'Refresh'}
                    </button>
                    <button
                      type='button'
                      className='rounded border px-2 py-1 text-[11px] hover:bg-muted'
                      onClick={() => void applyAutoConnection()}
                      disabled={connectionsBusy}
                      title='Pilih koneksi yang valid dan simpan otomatis'
                    >
                      Deteksi otomatis
                    </button>
                  </div>
                </div>
                <select
                  className='border-input bg-background h-9 w-full rounded-md border px-3 text-sm'
                  value={String(form.restore_connection || '')}
                  onChange={(event) => set('restore_connection', event.target.value)}
                >
                  <option value=''>Auto-detect saat restore</option>
                  {connections.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id} — {item.name}
                    </option>
                  ))}
                  {connectionsLoaded &&
                  form.restore_connection &&
                  !connectionKnown ? (
                    <option value={String(form.restore_connection)}>
                      {String(form.restore_connection)} — tidak ditemukan
                    </option>
                  ) : null}
                </select>
                {connectionsError ? (
                  <p className='text-destructive text-[11px]'>{connectionsError}</p>
                ) : connectionsLoaded && !connectionKnown && form.restore_connection ? (
                  <p className='text-amber-600 text-[11px]'>
                    ID ini tidak ada di akun Vast. Klik “Deteksi otomatis”.
                  </p>
                ) : connections.length === 0 && connectionsLoaded ? (
                  <p className='text-amber-600 text-[11px]'>
                    Belum ada Cloud Sync di akun Vast.
                  </p>
                ) : null}
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Path model di instance</label>
                <Input value={form.restore_model_path} onChange={(event) => set('restore_model_path', event.target.value)} placeholder='/workspace/whisper_model' />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Timeout restore (detik)</label>
                <Input type='number' min={60} max={3600} value={String(form.restore_timeout)} onChange={(event) => set('restore_timeout', event.target.value)} />
              </div>
              <div className='space-y-1 md:col-span-2'>
                <label className='text-muted-foreground text-xs'>Source di Google Drive</label>
                <Input value={form.restore_src} onChange={(event) => set('restore_src', event.target.value)} placeholder='/vast-backup/Clipzy/whisper_model' />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Destination di instance</label>
                <Input value={form.restore_dst} onChange={(event) => set('restore_dst', event.target.value)} placeholder='/workspace/whisper_model' />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Timeout & retry</CardTitle>
              <CardDescription>Batas waktu boot/kerja dan jumlah percobaan ulang.</CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-4'>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Boot timeout</label>
                <Input type='number' value={String(form.boot_timeout)} onChange={(event) => set('boot_timeout', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Worker start timeout</label>
                <Input type='number' value={String(form.worker_start_timeout)} onChange={(event) => set('worker_start_timeout', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Oneshot timeout</label>
                <Input type='number' value={String(form.oneshot_timeout)} onChange={(event) => set('oneshot_timeout', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Oneshot boot timeout</label>
                <Input type='number' value={String(form.oneshot_boot_timeout)} onChange={(event) => set('oneshot_boot_timeout', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Max attempts</label>
                <Input type='number' value={String(form.max_attempts)} onChange={(event) => set('max_attempts', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Retry backoff (detik)</label>
                <Input type='number' value={String(form.retry_backoff)} onChange={(event) => set('retry_backoff', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Request timeout</label>
                <Input type='number' value={String(form.request_timeout)} onChange={(event) => set('request_timeout', event.target.value)} />
              </div>
              <div className='space-y-1'>
                <label className='text-muted-foreground text-xs'>Supervisor interval</label>
                <Input type='number' value={String(form.supervisor_interval)} onChange={(event) => set('supervisor_interval', event.target.value)} />
              </div>
            </CardContent>
          </Card>

          <div className='flex flex-wrap items-center gap-2'>
            <button
              type='button'
              disabled={pending}
              onClick={() => run('save')}
              className='bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm disabled:opacity-50'
            >
              {pending ? 'Menyimpan…' : 'Simpan'}
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => run('test')}
              className='hover:bg-muted rounded-md border px-3 py-2 text-sm disabled:opacity-50'
            >
              Tes koneksi
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => run('offers')}
              className='hover:bg-muted rounded-md border px-3 py-2 text-sm disabled:opacity-50'
            >
              Tes filter offer
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => run('reset')}
              className='hover:bg-muted rounded-md border px-3 py-2 text-sm disabled:opacity-50'
            >
              Hapus override DB
            </button>
          </div>

          {result ? (
            <pre className='bg-muted max-h-72 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap'>
              {result}
            </pre>
          ) : null}
          {error ? <p className='text-destructive text-sm'>{error}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
