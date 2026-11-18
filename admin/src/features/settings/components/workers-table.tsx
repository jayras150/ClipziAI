'use client';

import { useEffect, useState } from 'react';

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

/** Tabel task + popup realtime log (klik baris). */
export default function WorkersTable() {
  const [rows, setRows] = useState<WorkerTaskRow[]>([]);
  const [selected, setSelected] = useState<WorkerTaskRow | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    void fetchWorkerTasks().then((result) => {
      setRows(result.items);
      setError(result.error || '');
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    const tick = async () => {
      const result = await fetchWorkerLines(selected.id, 0);
      if (!active) return;
      setLines(result.items);
      setError(result.error || '');
    };
    void tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selected]);

  const text = lines
    .map((line) => `[${line.created_at || ''}] ${line.level}${line.stage ? ' ' + line.stage : ''} ${line.message}`)
    .join('\n');

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
            {rows.length === 0 ? (
              <tr>
                <td className='text-muted-foreground px-3 py-4 text-xs' colSpan={5}>
                  Belum ada task.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const state = stateOf(row.status);
                return (
                  <tr
                    key={row.id}
                    onClick={() => setSelected(row)}
                    className='cursor-pointer border-t hover:bg-muted/40'
                  >
                    <td className='px-3 py-2 font-mono text-xs'>{row.id.slice(0, 8)}…</td>
                    <td className='px-3 py-2'>
                      <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${STATE_CLASS[state]}`}>
                        {state}
                      </span>
                    </td>
                    <td className='px-3 py-2'>{row.progress ?? 0}%</td>
                    <td className='px-3 py-2'>{row.log_count}</td>
                    <td className='px-3 py-2 text-xs'>
                      {row.created_at ? new Date(row.created_at).toLocaleString('id-ID') : '-'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className='max-h-[85vh] w-full max-w-3xl overflow-y-auto'>
          <DialogHeader>
            <DialogTitle className='flex items-center gap-2 font-mono text-sm'>
              {selected?.id}
              {selected ? (
                <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${STATE_CLASS[stateOf(selected.status)]}`}>
                  {stateOf(selected.status)}
                </span>
              ) : null}
            </DialogTitle>
          </DialogHeader>
          <pre className='max-h-[60vh] overflow-auto rounded-md bg-black p-3 font-mono text-[11px] leading-relaxed text-emerald-300'>
            {lines.length ? text : 'Belum ada log untuk task ini (instance dibuat sebelum mirror aktif?).'}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
