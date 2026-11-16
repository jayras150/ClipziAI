'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { fetchAuditDetail } from '@/app/dashboard/audit/actions';

/** Tombol "Detail / Cek Log" untuk satu baris audit. */
export function AuditDetailButton({ id, label }: { id: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<LogDialogData | null>(null);

  const openDetail = async () => {
    setOpen(true);
    setLoading(true);
    const detail = await fetchAuditDetail(id);
    setLoading(false);
    const diff = {
      old_values: detail.old_values ?? null,
      new_values: detail.new_values ?? null,
      metadata: detail.metadata ?? null,
      ip: detail.ip_address ?? null,
      user_agent: detail.user_agent ?? null,
      resource: `${detail.resource_type || '-'} / ${detail.resource_id || '-'}`
    };
    setData({
      title: `${detail.action || 'Audit'}${label ? ` — ${label}` : ''}`,
      subtitle: `${detail.actor_email || 'system'} · ${detail.created_at || '-'}`,
      detail: detail.related_error || '',
      log: detail.log_text || JSON.stringify(diff, null, 2)
    });
  };

  return (
    <>
      <Button size='sm' variant='outline' onClick={() => void openDetail()}>
        Detail / Cek Log
      </Button>
      <LogDialog open={open} data={data} loading={loading} onClose={() => setOpen(false)} />
    </>
  );
}
