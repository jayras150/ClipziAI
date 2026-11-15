'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

type HistoryPoint = {
  time: string;
  cpu: number;
  memory: number;
  disk: number;
  rx_rate: number;
  tx_rate: number;
};

type ContainerRow = {
  name: string;
  state: string;
  status: string;
  image?: string | null;
  health?: string | null;
  started_at?: string | null;
  uptime_seconds?: number | null;
  restarts?: number;
  cpu_percent: number | null;
  mem_usage: string | null;
  mem_percent: number | null;
};

type ServiceRow = {
  key: string;
  label: string;
  container: string;
  found: boolean;
  state: string;
  status: string | null;
  health: string | null;
  image: string | null;
  started_at: string | null;
  uptime_seconds: number | null;
  restarts: number;
  cpu_percent: number | null;
  mem_usage: string | null;
  mem_percent: number | null;
  healthy: boolean;
};

type HostPayload = {
  available: boolean;
  stale?: boolean;
  age_seconds?: number | null;
  latest?: {
    hostname: string | null;
    cpu: { percent: number; cores: number };
    memory: { total: number; used: number; percent: number; swap_used?: number; swap_percent?: number };
    disk: { total: number; used: number; free: number; percent: number };
    load: { '1': number; '5': number; '15': number };
    uptime_seconds: number | null;
    network: { rx_rate: number | null; tx_rate: number | null };
    containers: ContainerRow[];
    docker?: { total: number; running: number; disk_usage?: string[] };
  } | null;
  history?: HistoryPoint[];
  services?: ServiceRow[];
  api_uptime_seconds?: number;
  api_version?: string;
  queue?: { queued: number; processing: number };
  workers_active?: number;
  error?: string;
};

const chartConfig = {
  cpu: { label: 'CPU', color: 'var(--chart-1)' },
  memory: { label: 'RAM', color: 'var(--chart-2)' }
} satisfies ChartConfig;

function bytes(value?: number | null): string {
  if (!value && value !== 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function rate(value?: number | null): string {
  if (!value && value !== 0) return '-';
  return `${bytes(value)}/s`;
}

function uptime(seconds?: number | null): string {
  if (!seconds) return '-';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}h ${hours}j`;
  if (hours) return `${hours}j ${minutes}m`;
  return `${minutes}m`;
}

function tone(percent: number): 'ok' | 'warn' | 'bad' {
  if (percent >= 90) return 'bad';
  if (percent >= 75) return 'warn';
  return 'ok';
}

const TONE_CLASS: Record<'ok' | 'warn' | 'bad', string> = {
  ok: 'text-emerald-500',
  warn: 'text-amber-500',
  bad: 'text-destructive'
};

const TONE_BAR: Record<'ok' | 'warn' | 'bad', string> = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-500',
  bad: 'bg-destructive'
};

const TONE_DOT: Record<'ok' | 'warn' | 'bad', string> = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-500',
  bad: 'bg-destructive'
};

/** Nama image pendek: `sujinwo555/clipzi-backend:api` -> `clipzi-backend:api`. */
function shortImage(image?: string | null): string {
  if (!image) return '-';
  const parts = image.split('/');
  return parts[parts.length - 1];
}

function serviceTone(row: ServiceRow): 'ok' | 'warn' | 'bad' {
  if (!row.found) return 'bad';
  if (row.healthy) return 'ok';
  if (row.state === 'running') return 'warn';
  return 'bad';
}

function MetricCard({
  label,
  value,
  hint,
  percent,
  extra
}: {
  label: string;
  value: string;
  hint?: string;
  percent?: number;
  extra?: string;
}) {
  const level = tone(percent ?? 0);
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={`text-2xl tabular-nums ${percent !== undefined ? TONE_CLASS[level] : ''}`}>
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-2'>
        {percent !== undefined ? (
          <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
            <div
              className={`h-full rounded-full transition-all duration-500 ${TONE_BAR[level]}`}
              style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
            />
          </div>
        ) : null}
        <p className='text-muted-foreground text-xs'>
          {hint}
          {extra ? ` · ${extra}` : ''}
        </p>
      </CardContent>
    </Card>
  );
}

export function HostLive() {
  const [data, setData] = useState<HostPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/system/host', { cache: 'no-store' });
      const payload = (await response.json()) as HostPayload;
      setData(payload);
      setError(payload.error || '');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // Polling 3 detik; berhenti saat tab tidak aktif agar hemat resource.
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 3000);
    return () => clearInterval(timer);
  }, [load]);

  const latest = data?.latest;
  const history = useMemo(() => (data?.history || []).slice(-60), [data?.history]);

  if (loading && !data) {
    return (
      <Card>
        <CardContent className='flex min-h-[200px] items-center justify-center gap-3'>
          <ClipzySpinner size='lg' />
          <span className='text-muted-foreground text-sm'>Mengambil metrik VPS…</span>
        </CardContent>
      </Card>
    );
  }

  if (!data?.available || !latest) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Metrik VPS belum tersedia</CardTitle>
          <CardDescription>
            Agent host belum mengirim data. Pasang di VPS:{' '}
            <code>systemctl enable --now clipzi-host-metrics</code> lalu tunggu ±10 detik.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          {error ? <p className='text-destructive text-sm'>{error}</p> : null}
          <Button size='sm' variant='outline' onClick={() => void load()}>
            Coba lagi
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant={data.stale ? 'destructive' : 'secondary'} className='gap-1'>
          {data.stale ? 'agent stale' : 'live'}
        </Badge>
        <span className='text-muted-foreground text-xs'>
          {latest.hostname} · update {data.age_seconds}s lalu · {latest.cpu.cores} core · host up{' '}
          {uptime(latest.uptime_seconds)}
          {data.api_uptime_seconds ? ` · API up ${uptime(data.api_uptime_seconds)}` : ''}
          {data.api_version ? ` (v${data.api_version})` : ''}
        </span>
        <Button size='sm' variant='ghost' className='ml-auto gap-2' onClick={() => void load()}>
          {loading ? <ClipzySpinner size='xs' variant='ring' /> : null}
          Refresh
        </Button>
      </div>

      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-4'>
        <MetricCard
          label='CPU'
          value={`${latest.cpu.percent}%`}
          percent={latest.cpu.percent}
          hint={`load ${latest.load['1']} / ${latest.load['5']} / ${latest.load['15']}`}
        />
        <MetricCard
          label='RAM'
          value={`${latest.memory.percent}%`}
          percent={latest.memory.percent}
          hint={`${bytes(latest.memory.used)} dari ${bytes(latest.memory.total)}`}
          extra={latest.memory.swap_percent ? `swap ${latest.memory.swap_percent}%` : undefined}
        />
        <MetricCard
          label='Disk /'
          value={`${latest.disk.percent}%`}
          percent={latest.disk.percent}
          hint={`${bytes(latest.disk.used)} dari ${bytes(latest.disk.total)}`}
          extra={`sisa ${bytes(latest.disk.free)}`}
        />
        <MetricCard
          label='Jaringan'
          value={rate(latest.network.rx_rate)}
          hint={`keluar ${rate(latest.network.tx_rate)}`}
          extra={
            data.queue ? `antrean ${data.queue.queued} · proses ${data.queue.processing}` : undefined
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Status layanan</CardTitle>
          <CardDescription>
            Backend, frontend, admin, dan Caddy — diperbarui tiap 3 detik dari agent host
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className='grid gap-2 sm:grid-cols-2 xl:grid-cols-4'>
            {(data.services || []).map((row) => {
              const level = serviceTone(row);
              return (
                <div key={row.key} className='rounded-lg border p-3'>
                  <div className='flex items-center gap-2'>
                    <span
                      className={`size-2 shrink-0 rounded-full ${TONE_DOT[level]}`}
                      aria-hidden
                    />
                    <span className='truncate text-sm font-medium'>{row.label}</span>
                    <Badge variant='outline' className='ml-auto text-[10px]'>
                      {row.found ? row.state : 'tidak ada'}
                    </Badge>
                  </div>
                  <p className='text-muted-foreground mt-1 text-xs'>
                    {row.found ? `up ${uptime(row.uptime_seconds)}` : 'container tidak ditemukan'}
                    {' · '}
                    <span className='font-mono text-[11px]'>{shortImage(row.image)}</span>
                  </p>
                  <div className='text-muted-foreground mt-1 flex flex-wrap gap-x-2 text-[11px]'>
                    {row.health ? <span>health {row.health}</span> : null}
                    {row.cpu_percent !== null && row.cpu_percent !== undefined ? (
                      <span>cpu {row.cpu_percent}%</span>
                    ) : null}
                    {row.mem_usage ? <span>ram {row.mem_usage}</span> : null}
                    {row.restarts ? <span>restart {row.restarts}×</span> : null}
                  </div>
                </div>
              );
            })}
            {!(data.services || []).length ? (
              <p className='text-muted-foreground text-xs'>
                Belum ada data container dari agent host.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className='grid gap-4 lg:grid-cols-7'>
        <Card className='lg:col-span-4'>
          <CardHeader>
            <CardTitle>CPU & RAM (10 menit)</CardTitle>
            <CardDescription>Diperbarui tiap 3 detik dari agent host</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className='aspect-auto h-[220px] w-full'>
              <AreaChart data={history} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray='3 3' />
                <XAxis dataKey='time' hide />
                <YAxis domain={[0, 100]} width={28} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area
                  dataKey='cpu'
                  type='monotone'
                  stroke='var(--color-cpu)'
                  fill='var(--color-cpu)'
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
                <Area
                  dataKey='memory'
                  type='monotone'
                  stroke='var(--color-memory)'
                  fill='var(--color-memory)'
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card className='lg:col-span-3'>
          <CardHeader>
            <CardTitle>Container</CardTitle>
            <CardDescription>
              {latest.docker?.running ?? 0}/{latest.docker?.total ?? 0} berjalan ·{' '}
              {data.workers_active ?? 0} worker Vast aktif
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nama</TableHead>
                  <TableHead>Uptime</TableHead>
                  <TableHead>CPU</TableHead>
                  <TableHead>RAM</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {latest.containers.length ? (
                  latest.containers.map((row) => (
                    <TableRow key={row.name}>
                      <TableCell className='text-xs font-medium'>
                        {row.name}
                        <div className='text-muted-foreground font-mono text-[10px]'>
                          {shortImage(row.image)}
                        </div>
                      </TableCell>
                      <TableCell className='text-xs whitespace-nowrap tabular-nums'>
                        {row.uptime_seconds ? uptime(row.uptime_seconds) : '-'}
                      </TableCell>
                      <TableCell className='text-xs tabular-nums'>
                        {row.cpu_percent === null ? '-' : `${row.cpu_percent}%`}
                      </TableCell>
                      <TableCell className='text-xs'>{row.mem_usage || '-'}</TableCell>
                      <TableCell>
                        <Badge variant={row.state === 'running' ? 'secondary' : 'outline'}>
                          {row.state}
                          {row.health ? ` · ${row.health}` : ''}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className='text-muted-foreground text-center'>
                      Tidak ada container.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
