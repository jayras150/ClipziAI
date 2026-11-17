'use client';

import { useState, useTransition } from 'react';

import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { probeCookieResult } from '@/app/dashboard/settings/youtube-actions';

/**
 * Tombol "Uji" cookies: memanggil probe dan menampilkan hasilnya di dialog
 * (OK/GAGAL + log lengkap yang bisa di-copy). Sebelumnya hasil probe dibuang
 * sehingga admin tidak tahu apa-apa.
 */
export default function CookieProbeButton({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<LogDialogData | null>(null);
  const [pending, startTransition] = useTransition();

  const run = () => {
    setOpen(true);
    setData({ title: 'Menguji cookies…', subtitle: 'Menghubungi YouTube', log: '' });
    startTransition(async () => {
      const result = await probeCookieResult(id);
      setData({
        title: result.ok ? 'Cookies OK' : 'Cookies gagal',
        subtitle: `${result.status || '-'} · ${new Date().toLocaleString('id-ID')}`,
        detail: result.error || 'Probe selesai.',
        log: result.log_text || ''
      });
    });
  };

  return (
    <>
      <button
        type='button'
        onClick={run}
        disabled={pending}
        className='hover:bg-muted rounded-md border px-2.5 py-1 text-xs disabled:opacity-50'
      >
        {pending ? 'Menguji…' : 'Uji'}
      </button>
      <LogDialog open={open} data={data} loading={pending} onClose={() => setOpen(false)} />
    </>
  );
}
