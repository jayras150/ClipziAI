'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { fetchWorkerLines, fetchWorkerTasks, type WorkerTaskRow } from '@/app/dashboard/workers/actions';

/** Interval auto-refresh log (permintaan produk: 2 detik). */
const LOG_REFRESH_MS = 2000;
/** Interval auto-refresh daftar task supaya status running/error ikut hidup. */
const TABLE_REFRESH_MS = 5000;

type Line = Awaited<ReturnType<typeof fetchWorkerLines>>['items'][number];

const STATE_CLASS: Record<string, string> = {
  running: 'bg-emerald-600 text-white',
  success: 'bg-blue-600 text-white',
  error: 'bg-red-600 text-white',
  queued: 'bg-amber-500 text-black'
};

function stateOf(status: string | null): string {
  const value = (status || '').toLowerCase();
  if (value === 'completed') return 'success';
  if (value === 'error' || value === 'cancelled') return 'error';
  if (value === 'queued' || value === 'pending') return 'queued';
  return 'running';
}

export default function WorkersTable() {
  const [rows, setRows] = useState<WorkerTaskRow[]>([]);
  const [selected, setSelected] = useState<WorkerTaskRow | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  // Seq terakhir disimpan di ref: membaca state `lines` di dalam interval akan
  // memakai nilai basi (closure lama) sehingga log baru tidak pernah terambil.
  const lastSeqRef = useRef(0);

  // Daftar task ikut auto-refresh agar status running/error selalu terbaru.
  useEffect(() => {
    let active = true;
    const load = async () => {
      const result = await fetchWorkerTasks();
      if (!active) return;
      setRows(result.items);
      setError(result.error || '');
    };
    void load();
    const timer = window.setInterval(load, TABLE_REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    setLines([]);
    lastSeqRef.current = 0;
    const tick = async () => {
      const after = lastSeqRef.current;
      const result = await fetchWorkerLines(selected.id, after);
      if (!active) return;
      if (result.items.length) {
        lastSeqRef.current = result.items[result.items.length - 1].seq;
      }
      setLines((prev) => {
        const merged = after ? [...prev, ...result.items] : result.items;
        return merged.slice(-3000);
      });
      setUpdatedAt(new Date().toLocaleTimeString('id-ID'));
      setError(result.error || '');
    };
    void tick();
    const timer = window.setInterval(tick, LOG_REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selected]);

  // Ikuti baris terbaru selama admin belum scroll ke atas.
  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [lines.length, autoScroll]);

  const text = useMemo(
    () =>
      lines
        .map(
          (line) =>
            `[${line.created_at || ''}] ${line.level}${line.stage ? ' ' + line.stage : ''} ${line.message}`
        )
        .join('\n'),
    [lines]
  );

  // Baris ERROR/WARN diberi warna berbeda supaya crash langsung terlihat.
  const rendered = useMemo(
    () =>
      lines.map((line, index) => {
        const level = (line.level || '').toUpperCase();
        const color =
          level === 'ERROR'
            ? 'text-red-400'
            : level === 'WARN' || level === 'WARNING'
              ? 'text-amber-300'
              : 'text-emerald-300';
        return (
          <div key={`${line.seq}-${index}`} className={color}>
            {`[${line.created_at || ''}] ${line.level}${line.stage ? ' ' + line.stage : ''} ${line.message}`}
          </div>
        );
      }),
    [lines]
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setError('Log disalin ke clipboard.');
    } catch {
      setError('Gagal menyalin (browser menolak clipboard).');
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `worker-${selected?.id.slice(0, 8) || 'log'}.log`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      {error ? <p className='text-destructive mb-2 text-xs'>{error}</p> : null}
      <div className='overflow-x-auto rounded-lg border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/40 text-muted-foreground text-xs uppercase'>
            <tr>
              <th className='px-3 py-2 text-left'>Task</th>
              <th className='px-3 py-2 text-left'>Status</th>
              <th className='px-3 py-2 text-left'>Progress</th>
              <th className='px-3 py-2 text-left'>Logs</th>
              <th className='px-3 py-2 text-left'>Error</th>
              <th className='px-3 py-2 text-left'>Dibuat</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => setSelected(row)}
                className='cursor-pointer border-t hover:bg-muted/40'
              >
                <td className='px-3 py-2 font-mono text-xs'>{row.id.slice(0, 8)}…</td>
                <td className='px-3 py-2'>
                  <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${STATE_CLASS[stateOf(row.status)]}`}>
                    {stateOf(row.status)}
                  </span>
                </td>
                <td className='px-3 py-2'>{row.progress ?? 0}%</td>
                <td className='px-3 py-2'>{row.log_count}</td>
                <td
                  className='text-destructive max-w-[280px] truncate px-3 py-2 text-xs'
                  title={row.error_message || ''}
                >
                  {row.error_message || '-'}
                </td>
                <td className='px-3 py-2 text-xs'>
                  {row.created_at ? new Date(row.created_at).toLocaleString('id-ID') : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className='flex h-[72vh] w-[92vw] max-w-4xl flex-col gap-2 overflow-hidden sm:max-w-4xl'>
          <DialogHeader className='shrink-0'>
            <DialogTitle className='flex flex-wrap items-center gap-2 font-mono text-sm'>
              {selected?.id}
              {selected ? (
                <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${STATE_CLASS[stateOf(selected.status)]}`}>
                  {stateOf(selected.status)}
                </span>
              ) : null}
              <span className='text-muted-foreground flex items-center gap-1.5 text-[11px] font-normal'>
                <span className='inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500' />
                live 2s · update {updatedAt || '-'} · {lines.length} baris
              </span>
              <span className='ml-auto flex gap-2'>
                <Button
                  size='sm'
                  variant='ghost'
                  onClick={() => setAutoScroll((prev) => !prev)}
                  title='Ikuti baris terbaru secara otomatis'
                >
                  Auto-scroll {autoScroll ? 'ON' : 'OFF'}
                </Button>
                <Button size='sm' variant='outline' onClick={copy} disabled={!lines.length}>
                  Copy
                </Button>
                <Button size='sm' variant='secondary' onClick={download} disabled={!lines.length}>
                  Download
                </Button>
              </span>
            </DialogTitle>
          </DialogHeader>
          <div className='min-h-0 flex-1 overflow-auto rounded-md bg-black p-3 font-mono text-[12.5px] leading-snug whitespace-pre-wrap break-words'>
            {lines.length ? (
              rendered
            ) : (
              <span className='text-emerald-300'>
                Belum ada log untuk task ini. Menunggu worker mengirim log…
              </span>
            )}
            <div ref={bottomRef} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
