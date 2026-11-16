'use client';

import { useCallback, useEffect, useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  fetchHostSnapshot,
  runSystemAction,
  type CommandJob,
  type HostSnapshot
} from '@/app/dashboard/system/actions';

const POLL_MS = 5000;

function gb(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return '0 GB';
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function uptime(seconds?: number | null): string {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  if (!total) return '-';
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}d ${hours}h ${minutes}m`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/** Dashboard System bergaya neon glass (data nyata + aksi host). */
export function NeonSystem({ initial }: { initial: HostSnapshot | null }) {
  const [data, setData] = useState<HostSnapshot | null>(initial);
  const [busy, setBusy] = useState<string>('');
  const [result, setResult] = useState<CommandJob | null>(null);
  const [, startTransition] = useTransition();

  const load = useCallback(async () => {
    const next = await fetchHostSnapshot();
    if (next) setData(next);
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const run = (action: string) => {
    setBusy(action);
    startTransition(async () => {
      try {
        const job = await runSystemAction(action);
        setResult(job);
        if (job.status === 'done' && job.ok) {
          toast.success(job.output || 'Perintah selesai.');
        } else if (job.status === 'pending' || job.status === 'running') {
          toast.info('Perintah dikirim ke agent host. Cek hasil beberapa saat lagi.');
        } else {
          toast.error(job.output || 'Perintah gagal dijalankan agent host.');
        }
        void load();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Gagal menjalankan aksi.');
      } finally {
        setBusy('');
      }
    });
  };

  const latest = data?.latest || null;
  const cpu = Number(latest?.cpu?.percent || 0);
  const ramPercent = Number(latest?.memory?.percent || 0);
  const diskPercent = Number(latest?.disk?.percent || 0);
  const services = data?.services || [];
  const api = services.find((item) => item.key === 'api');
  const caddy = services.find((item) => item.key === 'caddy');
  const online = Boolean(api?.healthy);
  const staleNote = data?.stale ? `data ${data?.age_seconds ?? '?'} detik lalu` : 'realtime';

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-3'>
        <section className='ns-card ns-cpu'>
          <header className='ns-head'>
            <h3>CPU Usage</h3>
            <span className='ns-dot' />
          </header>
          <p className='ns-value'>{cpu.toFixed(1)}%</p>
          <p className='ns-sub'>
            {latest?.cpu?.cores || '-'} cores · load {latest?.load?.['1'] ?? '-'}
          </p>
          <div className='ns-bar'>
            <span style={{ width: `${Math.min(100, cpu)}%`, background: '#00f3ff' }} />
          </div>
        </section>

        <section className='ns-card ns-ram'>
          <header className='ns-head'>
            <h3>Memory (RAM)</h3>
            <span className='ns-dot' />
          </header>
          <p className='ns-value'>
            {gb(latest?.memory?.used)} <span className='ns-muted'>/ {gb(latest?.memory?.total)}</span>
          </p>
          <p className='ns-sub'>Usage: {ramPercent.toFixed(1)}%</p>
          <div className='ns-bar'>
            <span style={{ width: `${Math.min(100, ramPercent)}%`, background: '#bc13fe' }} />
          </div>
        </section>

        <section className='ns-card ns-storage'>
          <header className='ns-head'>
            <h3>Storage (Disk)</h3>
            <span className='ns-dot' />
          </header>
          <p className='ns-value'>
            {gb(latest?.disk?.used)} <span className='ns-muted'>/ {gb(latest?.disk?.total)}</span>
          </p>
          <p className='ns-sub'>Usage: {diskPercent.toFixed(1)}%</p>
          <div className='ns-bar'>
            <span style={{ width: `${Math.min(100, diskPercent)}%`, background: '#ff0080' }} />
          </div>
        </section>
        <section className='ns-card ns-server'>
          <header className='ns-head'>
            <h3>Server Status</h3>
            <span className='ns-dot' />
          </header>
          <div className={`ns-badge ${online ? 'is-online' : 'is-offline'}`}>
            <span className='ns-badge-dot' />
            {online ? 'ONLINE (UP)' : api?.state ? api.state.toUpperCase() : 'TIDAK ADA DATA'}
          </div>
          <p className='ns-sub'>Uptime host: {uptime(latest?.uptime_seconds)}</p>
          <p className='ns-sub'>
            Queue: {data?.queue?.queued ?? 0} antre · {data?.queue?.processing ?? 0} proses · workers{' '}
            {data?.workers_active ?? 0}
          </p>
        </section>

        <section className='ns-card ns-cache'>
          <header className='ns-head'>
            <h3>Clear Cache VPS</h3>
            <span className='ns-dot' />
          </header>
          <p className='ns-sub'>Buang page cache/buffer RAM (aman, data tidak dihapus).</p>
          <Button
            className='ns-btn mt-3 w-full'
            disabled={busy === 'clear_cache'}
            onClick={() => run('clear_cache')}
          >
            {busy === 'clear_cache' ? 'Menjalankan…' : 'Clear Cache Now'}
          </Button>
        </section>

        <section className='ns-card ns-caddy'>
          <header className='ns-head'>
            <h3>Caddy Reverse Proxy</h3>
            <span className='ns-dot' />
          </header>
          <p className={`ns-badge ${caddy?.healthy ? 'is-online' : 'is-offline'}`}>
            <span className='ns-badge-dot' />
            {caddy?.healthy
              ? `Running${caddy.image ? ` (${caddy.image})` : ''}`
              : caddy?.state || 'missing'}
          </p>
          <Button
            className='ns-btn mt-3 w-full'
            disabled={busy === 'restart_caddy'}
            onClick={() => run('restart_caddy')}
          >
            {busy === 'restart_caddy' ? 'Merestart…' : 'Restart Caddy'}
          </Button>
        </section>

        <div className='text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs sm:col-span-2 xl:col-span-3'>
          <span>
            Metrik {staleNote} · versi API {data?.api_version || '-'} · uptime API{' '}
            {uptime(data?.api_uptime_seconds)}
          </span>
          <Button
            size='sm'
            variant='outline'
            disabled={busy === 'prune_docker'}
            onClick={() => run('prune_docker')}
          >
            {busy === 'prune_docker' ? 'Membersihkan…' : 'Prune Docker build cache'}
          </Button>
        </div>

        {result ? (
          <div className='rounded-md border p-3 text-xs sm:col-span-2 xl:col-span-3'>
            <p className='font-medium'>
              {result.label || result.action}: {result.status}
              {result.ok === false ? ' (gagal)' : ''}
            </p>
            <pre className='bg-muted mt-2 max-h-40 overflow-auto rounded p-2 whitespace-pre-wrap'>
              {result.output || 'Tidak ada output.'}
            </pre>
          </div>
        ) : null}
      </div>
    </div>
  );
}
