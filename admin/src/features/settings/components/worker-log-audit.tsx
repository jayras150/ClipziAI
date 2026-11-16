'use client';

import { useState, useTransition } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import {
  clearWorkerLogs,
  getStoredWorkerLog,
  type StoredWorkerLog
} from '@/app/dashboard/workers/actions';

function fmtDate(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('id-ID');
}

const OUTCOME_STYLE: Record<string, string> = {
  success: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  failed: 'bg-red-500/15 text-red-300 border-red-500/40',
  cancelled: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  running: 'bg-sky-500/15 text-sky-300 border-sky-500/40'
};

/** Daftar log worker tersimpan (audit) + tombol hapus semua. */
export function WorkerLogAudit({ logs }: { logs: StoredWorkerLog[] }) {
  const [items, setItems] = useState(logs);
  const [filter, setFilter] = useState<'failed' | 'all'>('failed');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [data, setData] = useState<LogDialogData | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  const visible = filter === 'all' ? items : items.filter((item) => item.outcome !== 'success');

  const openLog = async (row: StoredWorkerLog) => {
    setDialogOpen(true);
    setLoading(true);
    setData(null);
    const full = await getStoredWorkerLog(row.id);
    setLoading(false);
    setData({
      title: `Worker ${row.outcome} — instance ${row.instance_id ?? '-'}`,
      subtitle: `${row.gpu_name || 'GPU tidak diketahui'} · ${fmtDate(row.created_at)}`,
      detail: String(full?.reason || row.reason || ''),
      log: String(full?.log_text || '')
    });
  };

  return (
    <Card>
      <CardHeader className='flex flex-row flex-wrap items-center justify-between gap-2'>
        <div>
          <CardTitle>Log worker tersimpan</CardTitle>
          <CardDescription>
            Log instance GPU yang gagal disalin sebelum instance dihapus (untuk audit).
          </CardDescription>
        </div>
        <div className='flex flex-wrap gap-2'>
          <Button
            size='sm'
            variant={filter === 'failed' ? 'secondary' : 'outline'}
            onClick={() => setFilter('failed')}
          >
            Gagal
          </Button>
          <Button
            size='sm'
            variant={filter === 'all' ? 'secondary' : 'outline'}
            onClick={() => setFilter('all')}
          >
            Semua ({items.length})
          </Button>
          <Button
            size='sm'
            variant='destructive'
            disabled={!items.length || pending}
            onClick={() => setConfirmOpen(true)}
          >
            Clear All Logs Workers
          </Button>
        </div>
      </CardHeader>
      <CardContent className='space-y-2'>
        {visible.length === 0 ? (
          <p className='text-muted-foreground text-sm'>
            Belum ada log tersimpan. Log akan muncul otomatis saat instance GPU gagal.
          </p>
        ) : (
          visible.map((row) => (
            <div
              key={row.id}
              className='flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm'
            >
              <div className='min-w-0 flex-1'>
                <div className='flex flex-wrap items-center gap-2'>
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${
                      OUTCOME_STYLE[row.outcome] || OUTCOME_STYLE.running
                    }`}
                  >
                    {row.outcome}
                  </span>
                  <span className='font-medium'>instance {row.instance_id ?? '-'}</span>
                  <span className='text-muted-foreground text-xs'>{row.gpu_name || '-'}</span>
                  <span className='text-muted-foreground text-xs'>{fmtDate(row.created_at)}</span>
                </div>
                <p className='text-muted-foreground mt-1 line-clamp-2 text-xs'>
                  {row.reason || 'Tanpa pesan'}
                </p>
              </div>
              <Button size='sm' variant='outline' onClick={() => void openLog(row)}>
                Log
              </Button>
            </div>
          ))
        )}
      </CardContent>

      <LogDialog open={dialogOpen} data={data} loading={loading} onClose={() => setDialogOpen(false)} />

      <ConfirmDialog
        open={confirmOpen}
        title='Hapus semua log worker?'
        description='Semua log worker tersimpan akan dihapus permanen. Riwayat task tidak terpengaruh.'
        confirmLabel='Ya, hapus semua'
        cancelLabel='Batal'
        loading={pending}
        onOpenChange={(next) => setConfirmOpen(next)}
        onConfirm={() => {
          startTransition(async () => {
            await clearWorkerLogs();
            setItems([]);
            setConfirmOpen(false);
          });
        }}
      />
    </Card>
  );
}
