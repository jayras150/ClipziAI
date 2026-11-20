'use client';

import { useCallback, useEffect, useState, useTransition } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

type Candidate = { files: number; bytes: number };

type CleanupInfo = {
  enabled?: boolean;
  schedule_hour?: number;
  temp_ttl_hours?: number;
  log_max_mb?: number;
  docker_enabled?: boolean;
  docker_available?: boolean;
  candidates?: Record<string, Candidate>;
};

type CleanupResult = {
  dry_run?: boolean;
  freed_mb?: number;
  summary?: Record<string, number>;
  results?: Array<Record<string, unknown>>;
  error?: string;
};

function mb(bytes: number | undefined): string {
  return `${Math.round(((bytes || 0) / (1024 * 1024)) * 10) / 10} MB`;
}

/** Kartu pembersihan sampah server (temp/log/cache/docker) di tab System. */
export default function ServerCleanupCard() {
  const [info, setInfo] = useState<CleanupInfo | null>(null);
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const load = useCallback(() => {
    startTransition(async () => {
      try {
        const response = await fetch('/api/system/cleanup', { cache: 'no-store' });
        const data = (await response.json()) as CleanupInfo & { error?: string };
        if (!response.ok || data.error) {
          setError(data.error || `HTTP ${response.status}`);
          return;
        }
        setInfo(data);
        setError('');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Gagal memuat status.');
      }
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = (dryRun: boolean) => {
    startTransition(async () => {
      try {
        const response = await fetch('/api/system/cleanup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dry_run: dryRun })
        });
        const data = (await response.json()) as CleanupResult;
        if (!response.ok || data.error) {
          setError(data.error || `HTTP ${response.status}`);
          return;
        }
        setError('');
        setResult(data);
        load();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Pembersihan gagal.');
      }
    });
  };

  const candidates = info?.candidates || {};
  const totalBytes = Object.values(candidates).reduce(
    (sum, item) => sum + (item?.bytes || 0),
    0
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bersih-bersih sampah server</CardTitle>
        <CardDescription>
          Menghapus file sementara aplikasi, memotong log yang membesar, dan membuang cache cookies
          yang tidak dipakai. Klip hasil, model, database, dan file pengguna tidak pernah disentuh.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-center gap-2 text-xs'>
          <Badge variant={info?.enabled ? 'secondary' : 'outline'}>
            {info?.enabled
              ? `otomatis tiap hari ${String(info?.schedule_hour ?? 3).padStart(2, '0')}:00`
              : 'otomatis mati'}
          </Badge>
          <Badge variant='outline'>temp &gt; {info?.temp_ttl_hours ?? 24} jam</Badge>
          <Badge variant='outline'>log &gt; {info?.log_max_mb ?? 50} MB</Badge>
          <Badge variant={info?.docker_enabled ? 'secondary' : 'outline'}>
            docker {info?.docker_enabled ? (info?.docker_available ? 'aktif' : 'tanpa socket') : 'mati'}
          </Badge>
          <span className='text-muted-foreground'>kandidat total ≈ {mb(totalBytes)}</span>
        </div>

        <div className='grid gap-2 text-xs sm:grid-cols-3'>
          {(['temp', 'logs', 'cache'] as const).map((key) => (
            <div key={key} className='rounded-md border p-2'>
              <p className='font-medium capitalize'>{key}</p>
              <p className='text-muted-foreground'>
                {candidates[key]?.files ?? 0} file · {mb(candidates[key]?.bytes)}
              </p>
            </div>
          ))}
        </div>

        <div className='flex flex-wrap gap-2'>
          <Button variant='outline' onClick={() => run(true)} disabled={pending}>
            Pindai (dry-run)
          </Button>
          <Button onClick={() => run(false)} disabled={pending}>
            {pending ? 'Memproses…' : 'Bersihkan sekarang'}
          </Button>
          <Button variant='ghost' onClick={load} disabled={pending}>
            Muat ulang
          </Button>
        </div>

        {error ? <p className='text-xs text-red-600'>{error}</p> : null}

        {result ? (
          <div className='rounded-md border border-dashed p-3 text-xs'>
            <p className='font-medium'>
              {result.dry_run ? 'Hasil pindai (belum ada yang dihapus)' : 'Pembersihan dijalankan'}
              {typeof result.freed_mb === 'number' ? ` · ${result.freed_mb} MB` : ''}
            </p>
            <ul className='mt-1 space-y-1'>
              {(result.results || []).map((item, index) => (
                <li key={index} className='text-muted-foreground'>
                  {String(item.target)} — kandidat {String(item.candidates ?? 0)}, dihapus{' '}
                  {String(item.removed ?? item.truncated ?? 0)}
                  {item.skipped ? ` (dilewati: ${String(item.skipped)})` : ''}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
