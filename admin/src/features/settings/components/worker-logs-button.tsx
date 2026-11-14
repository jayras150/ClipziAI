'use client';

import { useState, useTransition } from 'react';

import { getInstanceLogs } from '@/app/dashboard/workers/actions';

/** Tombol + modal log instance Vast (termasuk opsi daemon/debug). */
export default function WorkerLogsButton({
  instanceId,
  label
}: {
  instanceId: number;
  label?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [warning, setWarning] = useState('');
  const [error, setError] = useState('');
  const [daemon, setDaemon] = useState(false);
  const [tail, setTail] = useState(300);
  const [pending, startTransition] = useTransition();

  const load = () => {
    setError('');
    setWarning('');
    startTransition(async () => {
      const result = await getInstanceLogs(instanceId, tail, daemon);
      if (result.error) {
        setError(result.error);
        return;
      }
      setText(result.text || '');
      if (result.warning) setWarning(result.warning);
    });
  };

  const openModal = () => {
    setOpen(true);
    if (!text) load();
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setError('Browser memblokir clipboard.');
    }
  };

  return (
    <>
      <button
        type='button'
        onClick={openModal}
        className='hover:bg-muted rounded-md border px-2 py-1 text-xs'
      >
        Logs
      </button>

      {open ? (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <div className='bg-background max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-lg border shadow-xl'>
            <div className='flex flex-wrap items-center justify-between gap-2 border-b p-3'>
              <div>
                <p className='text-sm font-medium'>Log instance {instanceId}</p>
                <p className='text-muted-foreground text-xs'>{label || 'worker'}</p>
              </div>
              <div className='flex flex-wrap items-center gap-2 text-xs'>
                <label className='text-muted-foreground flex items-center gap-1'>
                  <input
                    type='checkbox'
                    checked={daemon}
                    onChange={(event) => setDaemon(event.target.checked)}
                  />
                  debug/daemon
                </label>
                <select
                  value={tail}
                  onChange={(event) => setTail(Number(event.target.value))}
                  className='border-input bg-background h-8 rounded-md border px-2'
                >
                  <option value={200}>200 baris</option>
                  <option value={500}>500 baris</option>
                  <option value={1000}>1000 baris</option>
                </select>
                <button
                  type='button'
                  onClick={load}
                  disabled={pending}
                  className='hover:bg-muted rounded-md border px-2 py-1 disabled:opacity-50'
                >
                  {pending ? 'Memuat…' : 'Muat ulang'}
                </button>
                <button
                  type='button'
                  onClick={copy}
                  className='hover:bg-muted rounded-md border px-2 py-1'
                >
                  Copy
                </button>
                <button
                  type='button'
                  onClick={() => setOpen(false)}
                  className='hover:bg-muted rounded-md border px-2 py-1'
                >
                  Tutup
                </button>
              </div>
            </div>
            <div className='max-h-[70vh] overflow-auto p-3'>
              {warning ? <p className='text-xs text-amber-600'>{warning}</p> : null}
              {error ? <p className='text-destructive text-xs'>{error}</p> : null}
              <pre className='text-xs whitespace-pre-wrap'>{text || 'Belum ada log.'}</pre>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
