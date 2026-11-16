'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';

export type LogDialogData = {
  title: string;
  subtitle?: string;
  detail?: string;
  log?: string;
};

/**
 * Dialog log seragam untuk Workers / Alerts / Audit.
 *
 * Menampilkan ringkasan error, potongan log apa adanya, dan tombol
 * Copy / Download agar admin bisa melampirkan bukti saat audit.
 */
export function LogDialog({
  open,
  data,
  loading,
  error,
  onClose
}: {
  open: boolean;
  data: LogDialogData | null;
  loading?: boolean;
  error?: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) setCopied(false);
  }, [open]);

  const payload = [data?.detail, data?.log].filter(Boolean).join('\n\n');
  const filename = (data?.title || 'log').replace(/[^a-z0-9-_]+/gi, '-').toLowerCase();

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(payload);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => (value ? undefined : onClose())}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>{data?.title || 'Log'}</DialogTitle>
          <DialogDescription>{data?.subtitle || 'Detail teknis untuk audit'}</DialogDescription>
        </DialogHeader>

        {loading ? <p className='text-muted-foreground text-sm'>Memuat log…</p> : null}
        {error ? <p className='text-destructive text-sm'>{error}</p> : null}

        {data?.detail ? (
          <div>
            <p className='text-muted-foreground mb-1 text-xs font-medium uppercase'>Pesan error</p>
            <p className='text-sm whitespace-pre-wrap'>{data.detail}</p>
          </div>
        ) : null}

        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium uppercase'>Log</p>
          <pre className='bg-muted max-h-[50vh] overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap'>
            {payload || 'Tidak ada log untuk entri ini.'}
          </pre>
        </div>

        <div className='flex flex-wrap justify-end gap-2'>
          <Button variant='outline' size='sm' onClick={() => void onCopy()} disabled={!payload}>
            {copied ? 'Tersalin' : 'Copy'}
          </Button>
          {payload ? (
            <Button
              variant='outline'
              size='sm'
              onClick={() => {
                const blob = new Blob([payload], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `${filename || 'log'}.txt`;
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              Download .txt
            </Button>
          ) : null}
          <Button size='sm' onClick={onClose}>
            Tutup
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
