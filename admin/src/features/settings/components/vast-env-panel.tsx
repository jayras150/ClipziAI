'use client';

import { useState, useTransition } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { exportVastEnv, refreshVastEnv, syncVastEnv } from '@/app/dashboard/settings/vast/actions';

export type WorkerEnvItem = {
  name: string;
  required: boolean;
  runtime: boolean;
  set: boolean;
  secret: boolean;
  preview: string;
};

export default function VastEnvPanel({ items }: { items: Array<Record<string, unknown>> }) {
  const [rows, setRows] = useState<WorkerEnvItem[]>(items as unknown as WorkerEnvItem[]);
  const configurable = rows.filter((row) => !row.runtime).map((row) => row.name);
  const [selected, setSelected] = useState<string[]>(configurable);
  const [text, setText] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [confirmReveal, setConfirmReveal] = useState(false);
  const [pending, startTransition] = useTransition();

  /**
   * Samakan tampilan dengan isi database tanpa restart container.
   * Backend menghidrasi cookies/HF token/storage dari DB lalu mengembalikan
   * daftar env terbaru, jadi panel tidak lagi menampilkan nilai usang.
   */
  const refresh = () => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const result = await refreshVastEnv();
      if (!result.ok) {
        setError(result.error);
        return;
      }
      const next = (result.data.items || []) as unknown as WorkerEnvItem[];
      setRows(next);
      setSelected(next.filter((row) => !row.runtime).map((row) => row.name));
      setMessage('Env disegarkan dari database.');
    });
  };

  const toggle = (name: string) => {
    setSelected((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name]
    );
  };

  const exportEnv = (reveal: boolean) => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const result = await exportVastEnv(reveal);
      setConfirmReveal(false);
      if ('error' in result && result.error) {
        setError(String(result.error));
        return;
      }
      if (!('text' in result)) {
        setError('Export gagal: respons tidak berisi teks.');
        return;
      }
      setText(result.text || '');
      setMessage(
        reveal ? 'Nilai asli ditampilkan (diaudit).' : 'Export dengan nilai secret disamarkan.'
      );
    });
  };

  const copy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setMessage('Isi .env disalin ke clipboard.');
    } catch {
      setError('Browser memblokir clipboard.');
    }
  };

  const download = () => {
    if (!text) return;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'clipzi-worker.env';
    link.click();
    URL.revokeObjectURL(url);
  };

  const sync = (dryRun: boolean) => {
    setError('');
    setMessage('');
    startTransition(async () => {
      const result = await syncVastEnv(selected, dryRun);
      if ('error' in result && result.error) {
        setError(String(result.error));
        return;
      }
      setText(JSON.stringify(result, null, 2));
      setMessage(
        dryRun
          ? 'Simulasi selesai — belum ada yang diubah di Vast.'
          : 'Sinkronisasi env ke Vast selesai.'
      );
    });
  };

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Environment worker (otomatis dari env backend)</CardTitle>
          <CardDescription>
            Sumber sama dengan dispatch instance. Sync membuat/memperbarui environment variable
            akun Vast; nilai secret tidak pernah ditampilkan.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex flex-wrap gap-2'>
            <button
              type='button'
              disabled={pending}
              onClick={() => exportEnv(false)}
              className='hover:bg-muted rounded-md border px-3 py-1 text-xs disabled:opacity-50'
            >
              Export .env (masked)
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => setConfirmReveal(true)}
              className='hover:bg-muted rounded-md border px-3 py-1 text-xs disabled:opacity-50'
            >
              Export .env (nilai asli)
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => sync(true)}
              className='hover:bg-muted rounded-md border px-3 py-1 text-xs disabled:opacity-50'
            >
              Simulasi sync
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={() => sync(false)}
              className='bg-primary text-primary-foreground rounded-md px-3 py-1 text-xs disabled:opacity-50'
            >
              {pending ? 'Memproses…' : 'Sync ke Vast'}
            </button>
            <button
              type='button'
              disabled={pending}
              onClick={refresh}
              className='hover:bg-muted rounded-md border px-3 py-1 text-xs disabled:opacity-50'
              title='Muat ulang cookies/HF token/storage dari database tanpa restart container'
            >
              Sinkron dari DB
            </button>
            {text ? (
              <>
                <button
                  type='button'
                  onClick={copy}
                  className='hover:bg-muted rounded-md border px-3 py-1 text-xs'
                >
                  Copy
                </button>
                <button
                  type='button'
                  onClick={download}
                  className='hover:bg-muted rounded-md border px-3 py-1 text-xs'
                >
                  Download
                </button>
              </>
            ) : null}
          </div>
          <div className='overflow-auto rounded-md border'>
            <table className='w-full text-xs'>
              <thead className='bg-muted/50 text-left'>
                <tr>
                  <th className='p-2'>Pilih</th>
                  <th className='p-2'>Nama</th>
                  <th className='p-2'>Wajib</th>
                  <th className='p-2'>Status</th>
                  <th className='p-2'>Preview</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.name} className='border-t'>
                    <td className='p-2'>
                      <input
                        type='checkbox'
                        disabled={row.runtime}
                        checked={row.runtime || selected.includes(row.name)}
                        onChange={() => toggle(row.name)}
                      />
                    </td>
                    <td className='p-2 font-mono'>{row.name}</td>
                    <td className='p-2'>{row.required ? 'ya' : '-'}</td>
                    <td className='p-2'>
                      <Badge variant={row.set ? 'secondary' : 'destructive'}>
                        {row.runtime ? 'runtime' : row.set ? 'ada' : 'kosong'}
                      </Badge>
                    </td>
                    <td className='text-muted-foreground p-2 font-mono'>{row.preview || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {message ? <p className='text-xs text-emerald-600'>{message}</p> : null}
          {error ? <p className='text-destructive text-xs'>{error}</p> : null}
          {text ? (
            <textarea
              readOnly
              rows={8}
              value={text}
              className='border-input bg-muted/40 w-full rounded-md border p-2 font-mono text-[11px]'
            />
          ) : null}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmReveal}
        onOpenChange={(next) => {
          if (!next && !pending) setConfirmReveal(false);
        }}
        loading={pending}
        tone='warning'
        title='Tampilkan nilai asli (secret)?'
        description='Semua nilai .env akan terlihat di layar, termasuk API key dan token. Aksi ini dicatat di audit log.'
        details='Gunakan hanya di perangkat tepercaya, lalu hapus salinan setelah selesai.'
        confirmLabel='Tampilkan nilai asli'
        cancelLabel='Batal'
        onConfirm={() => exportEnv(true)}
      />
    </div>
  );
}
