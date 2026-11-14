'use client';

import { useState, useTransition } from 'react';

import { getCookieBase64, saveCookieBase64ToEnv } from '@/app/dashboard/settings/youtube-actions';

/** Tombol base64 per akun: copy ke clipboard / jadikan base64 global ENV. */
export default function CookieBase64Actions({ id }: { id: string }) {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const copy = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await getCookieBase64(id);
      if (result.error || !result.base64) {
        setError(result.error || 'Base64 tidak tersedia.');
        return;
      }
      try {
        await navigator.clipboard.writeText(result.base64);
        setMessage('Base64 disalin.');
      } catch {
        setError('Browser memblokir clipboard.');
      }
    });
  };

  const store = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveCookieBase64ToEnv(id);
      if (result.error) {
        setError(result.error);
        return;
      }
      setMessage(result.notice || 'Base64 ENV diperbarui.');
    });
  };

  return (
    <div className='flex flex-col items-end gap-1'>
      <div className='flex flex-wrap justify-end gap-1'>
        <button
          type='button'
          onClick={copy}
          disabled={pending}
          className='hover:bg-muted rounded-md border px-2 py-1 text-xs disabled:opacity-50'
        >
          Copy base64
        </button>
        <button
          type='button'
          onClick={store}
          disabled={pending}
          className='hover:bg-muted rounded-md border px-2 py-1 text-xs disabled:opacity-50'
        >
          Jadikan ENV
        </button>
      </div>
      {message ? <span className='text-[11px] text-emerald-600'>{message}</span> : null}
      {error ? <span className='text-destructive text-[11px]'>{error}</span> : null}
    </div>
  );
}
