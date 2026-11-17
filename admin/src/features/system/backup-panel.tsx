'use client';

import { useEffect, useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { createBackup, fetchBackups, restoreBackup, type BackupsData } from '@/app/dashboard/system/actions';

const MB = (bytes?: number | null) =>
  bytes ? `${(bytes / 1048576).toFixed(2)} MB` : '-';

/** Backup & restore penuh (DB + env + compose) lewat agent host. */
export default function BackupPanel() {
  const [data, setData] = useState<BackupsData>({ jobs: [], archives: [] });
  const [busy, setBusy] = useState('');
  const [logOpen, setLogOpen] = useState(false);
  const [logData, setLogData] = useState<LogDialogData | null>(null);
  const [pending, startTransition] = useTransition();

  const load = () => {
    void fetchBackups().then((result) => {
      setData(result);
      if (result.error) toast.error(result.error);
    });
  };

  useEffect(load, []);

  const runBackup = () => {
    setBusy('backup');
    startTransition(async () => {
      const result = await createBackup();
      setBusy('');
      setData((prev) => ({ ...prev, jobs: result.jobs?.length ? result.jobs : prev.jobs }));
      setLogData({
        title: result.ok ? 'Backup selesai' : 'Backup gagal',
        subtitle: result.job?.archive || '',
        detail: result.job?.detail || result.error || '',
        log: result.log_text || JSON.stringify(result, null, 2)
      });
      setLogOpen(true);
      if (result.ok) toast.success('Backup dibuat.');
      else toast.error(result.error || result.job?.detail || 'Backup gagal.');
    });
  };

  const runRestore = (archive: string) => {
    const typed = window.prompt(
      `Restore akan MENIMPA database & .env dari arsip ${archive}.\nKetik nama arsip untuk konfirmasi:`
    );
    if (typed !== archive) {
      if (typed !== null) toast.error('Nama arsip tidak cocok — restore dibatalkan.');
      return;
    }
    setBusy('restore');
    startTransition(async () => {
      const result = await restoreBackup(archive);
      setBusy('');
      setLogData({
        title: result.ok ? 'Restore selesai' : 'Restore gagal',
        subtitle: archive,
        detail: [result.job?.detail || result.error || '', result.restart_hint || ''].join(' ').trim(),
        log: result.log_text || JSON.stringify(result, null, 2)
      });
      setLogOpen(true);
      if (result.ok) toast.success('Restore selesai — restart layanan.');
      else toast.error(result.error || result.job?.detail || 'Restore gagal.');
      load();
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Backup &amp; Restore</CardTitle>
        <CardDescription>
          Backup berisi dump database, <code>backend/.env</code>, dan file compose. Media/klip
          tersimpan di object storage dan tidak ikut diarsipkan.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='flex flex-wrap gap-2'>
          <Button onClick={runBackup} disabled={pending || busy !== ''}>
            {busy === 'backup' ? 'Backup berjalan…' : 'Backup sekarang'}
          </Button>
          <Button variant='outline' onClick={load} disabled={pending || busy !== ''}>
            Muat ulang
          </Button>
        </div>

        <div>
          <p className='text-sm font-medium'>Arsip di host</p>
          {data.archives.length === 0 ? (
            <p className='text-muted-foreground text-xs'>Belum ada arsip backup.</p>
          ) : (
            <ul className='mt-1 space-y-1'>
              {data.archives.map((archive) => (
                <li key={archive} className='flex items-center justify-between gap-2 text-xs'>
                  <span className='font-mono'>{archive}</span>
                  <Button
                    size='sm'
                    variant='outline'
                    disabled={pending || busy !== ''}
                    onClick={() => runRestore(archive)}
                  >
                    Restore
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className='text-sm font-medium'>Riwayat</p>
          {data.jobs.length === 0 ? (
            <p className='text-muted-foreground text-xs'>Belum ada job backup/restore.</p>
          ) : (
            <ul className='mt-1 space-y-1 text-xs'>
              {data.jobs.slice(0, 8).map((job) => (
                <li key={job.id} className='flex flex-wrap items-center gap-2'>
                  <span className='font-mono'>{job.kind}</span>
                  <span>{job.archive || '-'}</span>
                  <span>{MB(job.size_bytes)}</span>
                  <span
                    className={
                      job.status === 'success'
                        ? 'text-emerald-500'
                        : job.status === 'error'
                          ? 'text-destructive'
                          : 'text-amber-500'
                    }
                  >
                    {job.status}
                  </span>
                  <span className='text-muted-foreground'>
                    {job.finished_at ? new Date(job.finished_at).toLocaleString('id-ID') : 'berjalan…'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <LogDialog open={logOpen} data={logData} onClose={() => setLogOpen(false)} />
      </CardContent>
    </Card>
  );
}
