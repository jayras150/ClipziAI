'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { getInstanceLogs } from '@/app/dashboard/workers/actions';

const AUTO_REFRESH_MS = 5000;
const DEFAULT_TAIL = 1000;

/**
 * Tombol + modal log instance Vast.
 *
 * Log selalu ter-update sendiri (polling 5 detik) selama modal terbuka —
 * tombol "Muat ulang" tetap ada untuk refresh manual. `tail` default 1000 baris.
 * Posisi scroll tetap di bawah saat ada baris baru, kecuali admin scroll ke atas.
 */
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
  const [tail, setTail] = useState(DEFAULT_TAIL);
  const [auto, setAuto] = useState(true);
  const [pending, setPending] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const inFlight = useRef(false);
  const stickToBottom = useRef(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const fetchLogs = useCallback(
    async (nextTail: number, nextDaemon: boolean, silent: boolean) => {
      // Jangan tumpuk request saat polling lebih cepat dari respons Vast.
      if (inFlight.current) return;
      inFlight.current = true;
      if (!silent) setPending(true);
      try {
        const result = await getInstanceLogs(instanceId, nextTail, nextDaemon);
        if (result.error) {
          setError(result.error);
          return;
        }
        setError('');
        setText(result.text || '');
        setWarning(result.warning || '');
        setUpdatedAt(new Date());
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : 'Gagal memuat log.');
      } finally {
        inFlight.current = false;
        if (!silent) setPending(false);
      }
    },
    [instanceId]
  );

  // Polling hanya menjadwalkan fetch (tidak setState saat effect berjalan).
  useEffect(() => {
    if (!open || !auto) return;
    const timer = setInterval(() => void fetchLogs(tail, daemon, true), AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [open, auto, tail, daemon, fetchLogs]);

  // Tempel ke baris paling bawah selama admin belum scroll ke atas.
  useEffect(() => {
    const box = scrollRef.current;
    if (!box || !text || !stickToBottom.current) return;
    box.scrollTop = box.scrollHeight;
  }, [text]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  /** Buka modal + muat log (1000 baris) saat itu juga. */
  const openModal = () => {
    setOpen(true);
    void fetchLogs(tail, daemon, false);
  };

  const changeTail = (value: number) => {
    setTail(value);
    void fetchLogs(value, daemon, false);
  };

  const changeDaemon = (value: boolean) => {
    setDaemon(value);
    void fetchLogs(tail, value, false);
  };

  const changeAuto = (value: boolean) => {
    setAuto(value);
    if (value) void fetchLogs(tail, daemon, false);
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
                <p className='text-sm font-medium'>
                  Log instance {instanceId}
                  {auto ? (
                    <span className='ml-2 inline-flex items-center gap-1 text-[11px] font-normal text-emerald-600'>
                      <span className='size-1.5 animate-pulse rounded-full bg-emerald-500' />
                      live {AUTO_REFRESH_MS / 1000}s
                    </span>
                  ) : null}
                </p>
                <p className='text-muted-foreground text-xs'>
                  {label || 'worker'}
                  {updatedAt
                    ? ` · diperbarui ${updatedAt.toLocaleTimeString('id-ID')}`
                    : ' · memuat…'}
                </p>
              </div>
              <div className='flex flex-wrap items-center gap-2 text-xs'>
                <label className='text-muted-foreground flex items-center gap-1'>
                  <input
                    type='checkbox'
                    checked={auto}
                    onChange={(event) => changeAuto(event.target.checked)}
                  />
                  auto
                </label>
                <label className='text-muted-foreground flex items-center gap-1'>
                  <input
                    type='checkbox'
                    checked={daemon}
                    onChange={(event) => changeDaemon(event.target.checked)}
                  />
                  debug/daemon
                </label>
                <select
                  value={tail}
                  onChange={(event) => changeTail(Number(event.target.value))}
                  className='border-input bg-background h-8 rounded-md border px-2'
                >
                  <option value={200}>200 baris</option>
                  <option value={500}>500 baris</option>
                  <option value={1000}>1000 baris</option>
                  <option value={2000}>2000 baris</option>
                </select>
                <button
                  type='button'
                  onClick={() => void fetchLogs(tail, daemon, false)}
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
            <div
              ref={scrollRef}
              onScroll={(event) => {
                const box = event.currentTarget;
                stickToBottom.current =
                  box.scrollHeight - box.scrollTop - box.clientHeight < 48;
              }}
              className='max-h-[70vh] overflow-auto p-3'
            >
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
