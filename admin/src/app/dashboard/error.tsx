'use client';

import Link from 'next/link';
import { useEffect } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

/**
 * Error boundary dashboard.
 *
 * Penyebab paling sering: sesi kedaluwarsa (backend 401) atau API sedang mati.
 * Daripada menampilkan "Something went wrong" generik, tampilkan langkah yang
 * bisa dilakukan admin (masuk lagi / cek status API).
 */
export default function DashboardError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Server Action ID berubah setiap deploy: tab lama yang masih memakai bundle
  // lama akan gagal ("Failed to find Server Action") dan muncul sebagai #441.
  const stale = /Failed to find Server Action|older or newer deployment/i.test(
    error.message
  );

  useEffect(() => {
    console.error('[dashboard]', error.message);
    // Muat ulang otomatis sekali (guard 60 detik) supaya tab lama pulih sendiri
    // saat ada deploy baru, tanpa loop bila error-nya memang dari API.
    try {
      const key = 'clipzi_auto_reload_at';
      const last = Number(window.sessionStorage.getItem(key) || 0);
      if (Date.now() - last > 60_000) {
        window.sessionStorage.setItem(key, String(Date.now()));
        window.location.reload();
      }
    } catch {
      /* abaikan */
    }
  }, [error.message]);

  const isAuth = /\b401\b|expired|Sesi/i.test(error.message);

  return (
    <div className='flex min-h-[60vh] items-center justify-center p-6'>
      <Card className='w-full max-w-lg'>
        <CardHeader>
          <CardTitle>
            {stale ? 'Versi baru terpasang' : isAuth ? 'Sesi berakhir' : 'Halaman gagal dimuat'}
          </CardTitle>
          <CardDescription>
            {stale
              ? 'Dashboard baru saja diperbarui. Halaman dimuat ulang otomatis; jika belum, klik tombol di bawah.'
              : isAuth
                ? 'Token admin sudah kedaluwarsa atau dicabut. Masuk lagi untuk melanjutkan.'
                : 'Terjadi kesalahan saat mengambil data dari API.'}
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-4'>
          <pre className='bg-muted max-h-32 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap'>
            {error.message}
          </pre>
          {error.digest ? (
            <p className='text-muted-foreground text-xs'>
              Kode error (sertakan saat lapor): <code>{error.digest}</code>
            </p>
          ) : null}
          <div className='flex flex-wrap gap-2'>
            <Button onClick={() => window.location.reload()}>Muat ulang sekarang</Button>
            <Button variant='outline' onClick={reset}>
              Coba lagi tanpa reload
            </Button>
            <Button variant='secondary' render={<Link href='/dashboard/overview' />}>
              Ke Overview
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
