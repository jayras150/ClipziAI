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
  useEffect(() => {
    console.error('[dashboard]', error.message);
  }, [error]);

  const isAuth = /\b401\b|expired|Sesi/i.test(error.message);

  return (
    <div className='flex min-h-[60vh] items-center justify-center p-6'>
      <Card className='w-full max-w-lg'>
        <CardHeader>
          <CardTitle>{isAuth ? 'Sesi berakhir' : 'Halaman gagal dimuat'}</CardTitle>
          <CardDescription>
            {isAuth
              ? 'Token admin sudah kedaluwarsa atau dicabut. Masuk lagi untuk melanjutkan.'
              : 'Terjadi kesalahan saat mengambil data dari API.'}
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-4'>
          <pre className='bg-muted max-h-32 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap'>
            {error.message}
          </pre>
          <div className='flex flex-wrap gap-2'>
            <Button onClick={reset}>Coba lagi</Button>
            <Button variant='outline' render={<Link href='/dashboard/overview' />}>
              Ke Overview
            </Button>
            <Button variant='secondary' render={<Link href='/auth/sign-in' />}>
              Masuk ulang
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
