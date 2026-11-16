'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { fetchNotificationLog } from '@/app/dashboard/notifications/actions';

export type AlertItem = {
  key: string;
  severity: 'error' | 'warning' | 'info' | string;
  title: string;
  body: string;
  detail?: string;
  href?: string;
  created_at?: string;
  kind?: string;
  read?: boolean;
};

const SEVERITY: Record<string, string> = {
  error: 'bg-red-500/15 text-red-300 border-red-500/40',
  warning: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  info: 'bg-sky-500/15 text-sky-300 border-sky-500/40'
};

function fmtDate(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

/** Daftar alert admin: sumber sama dengan lonceng header + tombol Cek Log. */
export function AlertsList({ items }: { items: AlertItem[] }) {
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<LogDialogData | null>(null);

  const visible = filter === 'all' ? items : items.filter((item) => item.severity === filter);

  const openLog = async (item: AlertItem) => {
    setOpen(true);
    setLoading(true);
    setData({
      title: item.title,
      subtitle: `${item.severity.toUpperCase()} · ${fmtDate(item.created_at)}`,
      detail: item.detail || item.body
    });
    const payload = await fetchNotificationLog(item.key);
    setLoading(false);
    setData({
      title: payload.title || item.title,
      subtitle: `${(payload.severity || item.severity).toUpperCase()} · ${fmtDate(
        payload.created_at || item.created_at
      )}`,
      detail: payload.detail || item.detail || item.body,
      log: payload.log_text || ''
    });
  };

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap gap-2'>
        {(['all', 'error', 'warning', 'info'] as const).map((value) => (
          <Button
            key={value}
            size='sm'
            variant={filter === value ? 'secondary' : 'outline'}
            onClick={() => setFilter(value)}
          >
            {value === 'all' ? `Semua (${items.length})` : value}
          </Button>
        ))}
      </div>

      {visible.length === 0 ? (
        <Card>
          <CardContent className='text-muted-foreground py-10 text-center text-sm'>
            Tidak ada alert pada filter ini.
          </CardContent>
        </Card>
      ) : (
        visible.map((item) => (
          <Card key={item.key}>
            <CardContent className='flex flex-wrap items-start justify-between gap-3 py-4'>
              <div className='min-w-0 flex-1 space-y-1'>
                <div className='flex flex-wrap items-center gap-2'>
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${
                      SEVERITY[item.severity] || SEVERITY.info
                    }`}
                  >
                    {item.severity}
                  </span>
                  <span className='text-sm font-medium'>{item.title}</span>
                  <span className='text-muted-foreground text-xs'>{fmtDate(item.created_at)}</span>
                </div>
                <p className='text-muted-foreground text-sm whitespace-pre-wrap'>
                  {item.detail || item.body}
                </p>
              </div>
              <div className='flex flex-wrap gap-2'>
                <Button size='sm' variant='outline' onClick={() => void openLog(item)}>
                  Detail / Cek Log
                </Button>
                {item.href ? (
                  <Button size='sm' variant='secondary' render={<Link href={item.href} />}>
                    Buka
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ))
      )}

      <LogDialog open={open} data={data} loading={loading} onClose={() => setOpen(false)} />
    </div>
  );
}
