'use client';

import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { fetchWorkerLines, fetchWorkerTasks, type WorkerTaskRow } from '@/app/dashboard/workers/actions';

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

  useEffect(() => {
    void fetchWorkerTasks().then((result) => {
      setRows(result.items);
      setError(result.error || '');
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    setLines([]);
    const tick = async () => {
      const lastSeq = lines.length ? lines[lines.length - 1].seq : 0;
      const result = await fetchWorkerLines(selected.id, lastSeq);
      if (!active) return;
      setLines((prev) => {
        const merged = lastSeq ? [...prev, ...result.items] : result.items;
        return merged.slice(-3000);
      });
      setUpdatedAt(new Date().toLocaleTimeString('id-ID'));
      setError(result.error || '');
    };
    void tick();
    const timer = window.setInterval(tick, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

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
                <td className='px-3 py-2 text-xs'>
                  {row.created_at ? new Date(row.created_at).toLocaleString('id-ID') : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className='flex h-[94vh] w-[99vw] max-w-[99vw] flex-col gap-2 overflow-hidden sm:max-w-[99vw]'>
          <DialogHeader className='shrink-0'>
            <DialogTitle className='flex flex-wrap items-center gap-2 font-mono text-sm'>
              {selected?.id}
              {selected ? (
                <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${STATE_CLASS[stateOf(selected.status)]}`}>
                  {stateOf(selected.status)}
                </span>
              ) : null}
              <span className='text-muted-foreground text-[11px] font-normal'>
                auto-refresh 2s · update {updatedAt || '-'} · {lines.length} baris
              </span>
              <span className='ml-auto flex gap-2'>
                <Button size='sm' variant='outline' onClick={copy} disabled={!lines.length}>
                  Copy
                </Button>
                <Button size='sm' variant='secondary' onClick={download} disabled={!lines.length}>
                  Download
                </Button>
              </span>
            </DialogTitle>
          </DialogHeader>
          <pre className='min-h-0 flex-1 overflow-auto rounded-md bg-black p-4 font-mono text-[13.5px] leading-snug text-emerald-300 whitespace-pre-wrap break-words'>
            {lines.length ? text : 'Belum ada log untuk task ini. Menunggu worker mengirim log…'}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
