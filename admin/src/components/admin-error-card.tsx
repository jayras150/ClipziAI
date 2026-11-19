'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';
import { useState } from 'react';

/** Tampilan aman saat API/DB tidak tersedia — tidak melempar error, sehingga
 * halaman tidak jatuh ke error boundary (React #441). */
export function AdminErrorCard({
  title,
  message,
  onRetry,
  linkLabel = 'Ke Overview',
  linkHref = '/dashboard/overview'
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  linkLabel?: string;
  linkHref?: string;
}) {
  const [retrying, setRetrying] = useState(false);
  return (
    <Card className='border-destructive/50 bg-destructive/5'>
      <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2.5'>
        <CardTitle className='text-sm text-destructive flex items-center gap-2'>
          <span role='img' aria-label='peringatan'>⚠️</span>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <p className='text-sm text-destructive/80'>{message}</p>
        <div className='flex flex-wrap gap-2'>
          {onRetry ? (
            <Button
              size='sm'
              onClick={() => {
                setRetrying(true);
                onRetry();
                setRetrying(false);
              }}
              disabled={retrying}
            >
              {retrying ? 'Memuat ulang…' : 'Coba lagi'}
            </Button>
          ) : null}
          <Button size='sm' variant='outline' asChild>
            <Link href={linkHref}>{linkLabel}</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
