'use client';

import { useState, useTransition } from 'react';

import { Input } from '@/components/ui/input';
import {
  encodeCookieText,
  saveCookieInput,
  type CookieSummary
} from '@/app/dashboard/settings/youtube-actions';

/**
 * Form importer cookies: tempel Netscape ATAU base64.
 * Tombol Encode menghasilkan base64 (tanpa menyimpan), lalu "Simpan cookies"
 * menyimpan baris cookies + base64 global untuk ENV worker.
 */
export default function CookieImporter() {
  const [source, setSource] = useState<'netscape' | 'base64'>('netscape');
  const [text, setText] = useState('');
  const [encoded, setEncoded] = useState('');
  const [summary, setSummary] = useState<CookieSummary | null>(null);
  const [label, setLabel] = useState('akun-1');
  const [storeBase64, setStoreBase64] = useState(true);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [pending, startTransition] = useTransition();

  const encode = () => {
    setError('');
    setNotice('');
    startTransition(async () => {
      const result = await encodeCookieText(text);
      if (result.error) {
        setError(result.error);
        setEncoded('');
        setSummary(null);
        return;
      }
      setEncoded(result.base64 || '');
      setSummary(result.summary || null);
      setNotice('Base64 berhasil dibuat. Periksa lalu klik Simpan cookies.');
    });
  };

  const save = () => {
    setError('');
    setNotice('');
    startTransition(async () => {
      const result = await saveCookieInput({ source, text, label, storeBase64 });
      if (result.error) {
        setError(result.error);
        return;
      }
      setNotice(result.notice || 'Cookies disimpan.');
    });
  };

  const copy = async () => {
    if (!encoded) return;
    try {
      await navigator.clipboard.writeText(encoded);
      setNotice('Base64 disalin ke clipboard.');
    } catch {
      setError('Browser memblokir clipboard. Salin manual dari kotak base64.');
    }
  };

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center gap-3 text-sm'>
        <label className='flex items-center gap-1'>
          <input
            type='radio'
            checked={source === 'netscape'}
            onChange={() => {
              setSource('netscape');
              setEncoded('');
              setSummary(null);
            }}
          />
          Netscape (cookies.txt)
        </label>
        <label className='flex items-center gap-1'>
          <input
            type='radio'
            checked={source === 'base64'}
            onChange={() => {
              setSource('base64');
              setEncoded('');
              setSummary(null);
            }}
          />
          Base64
        </label>
      </div>

      <div>
        <label className='text-muted-foreground mb-1 block text-xs'>
          {source === 'netscape' ? 'Isi cookies.txt (Netscape)' : 'Base64 cookies.txt'}
        </label>
        <textarea
          rows={5}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={
            source === 'netscape'
              ? '# Netscape HTTP Cookie File ...'
              : 'Tempel base64 (boleh dengan prefix data:text/plain;base64,)'
          }
          className='border-input bg-background w-full rounded-md border p-2 font-mono text-xs'
        />
      </div>

      {source === 'netscape' ? (
        <div className='space-y-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <button
              type='button'
              onClick={encode}
              disabled={pending || !text.trim()}
              className='hover:bg-muted rounded-md border px-3 py-1 text-xs disabled:opacity-50'
            >
              Encode → Base64
            </button>
            {encoded ? (
              <button
                type='button'
                onClick={copy}
                className='hover:bg-muted rounded-md border px-3 py-1 text-xs'
              >
                Copy base64
              </button>
            ) : null}
          </div>
          {encoded ? (
            <textarea
              readOnly
              rows={3}
              value={encoded}
              className='border-input bg-muted/40 w-full rounded-md border p-2 font-mono text-[11px]'
            />
          ) : null}
        </div>
      ) : null}

      {summary ? (
        <p className='text-muted-foreground text-xs'>
          {summary.cookie_count ?? 0} cookie · domain{' '}
          {(summary.domains || []).join(', ') || '-'} · kedaluwarsa tercepat{' '}
          {summary.earliest_expiry || '-'} · {summary.bytes ?? 0} byte
        </p>
      ) : null}

      <div className='flex flex-wrap items-end gap-3'>
        <div>
          <label className='text-muted-foreground mb-1 block text-xs'>Label akun</label>
          <Input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder='akun-1'
            className='h-9 w-40'
          />
        </div>
        <label className='text-muted-foreground flex items-center gap-2 text-xs'>
          <input
            type='checkbox'
            checked={storeBase64}
            onChange={(event) => setStoreBase64(event.target.checked)}
          />
          Simpan base64 untuk ENV worker
        </label>
        <button
          type='button'
          onClick={save}
          disabled={pending || !text.trim()}
          className='bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-xs disabled:opacity-50'
        >
          {pending ? 'Menyimpan…' : 'Simpan cookies'}
        </button>
      </div>

      {notice ? <p className='text-xs text-emerald-600'>{notice}</p> : null}
      {error ? <p className='text-destructive text-xs'>{error}</p> : null}
      <p className='text-muted-foreground text-xs'>
        Cookies disimpan per akun di DB (dipilih acak saat download). Base64 global hanya
        fallback ENV bila pool DB kosong. Base64 tiap akun bisa diambil lewat tombol
        “Copy base64” di tabel.
      </p>
    </div>
  );
}
