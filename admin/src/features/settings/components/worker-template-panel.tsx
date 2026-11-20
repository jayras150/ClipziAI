'use client';

import { useEffect, useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  createVastTemplate,
  loadVastTemplateStatus,
  syncVastTemplate,
  type VastTemplateStatus
} from '@/app/dashboard/settings/vast/actions';

/** Satu-satunya panel template worker: build dari image + env pipeline (auto model). */
export default function WorkerTemplatePanel({ status }: { status: VastTemplateStatus }) {
  const [data, setData] = useState<VastTemplateStatus>(status);
  const [name, setName] = useState(status.template_name || 'clipzi-worker');
  const [image, setImage] = useState(status.worker_image || '');
  const [disk, setDisk] = useState(String(status.worker_disk || 40));
  const [adopt, setAdopt] = useState('');
  const [busy, setBusy] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [pending, startTransition] = useTransition();

  const refresh = () => {
    startTransition(async () => {
      const result = await loadVastTemplateStatus();
      if ('error' in result && result.error) {
        toast.error(String(result.error));
        return;
      }
      const next = result as VastTemplateStatus;
      setData(next);
      setName((prev) => prev || next.template_name || 'clipzi-worker');
      setImage((prev) => prev || next.worker_image || '');
      setDisk((prev) => prev || String(next.worker_disk || 40));
    });
  };

  useEffect(() => {
    setData(status);
  }, [status]);

  const runSync = (adoptHash?: string) => {
    setBusy(adoptHash ? 'adopt' : 'sync');
    setMessage('');
    setWarnings([]);
    startTransition(async () => {
      const result = await syncVastTemplate({
        name: name.trim() || undefined,
        image: image.trim() || undefined,
        disk_space: disk ? Number(disk) : undefined,
        activate: true,
        adopt_hash: adoptHash
      });
      setBusy('');
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      const payload = result.data;
      setWarnings(payload.warnings || []);
      setMessage(
        adoptHash
          ? `Template ${adoptHash.slice(0, 10)}… diadopsi dan dipakai dispatch.`
          : payload.template_hash
            ? `Template ${payload.name || name} tersinkron (${payload.env_count || 0} env) dan aktif.`
            : 'Template dibuat tetapi hash belum terbaca — isi manual di kolom Template hash.'
      );
      toast.success('Template worker tersinkron.');
      if (adoptHash) setAdopt('');
      refresh();
    });
  };

  const runCreate = () => {
    setBusy('create');
    setMessage('');
    setWarnings([]);
    startTransition(async () => {
      // Nama otomatis (clipzi-worker-N) + image dipin ke digest terbaru.
      const result = await createVastTemplate({
        image: image.trim() || undefined,
        disk_space: disk ? Number(disk) : undefined,
        activate: true,
        include_env: true,
        sync_env_vars: true,
        auto_name: true,
        pin_digest: true
      });
      setBusy('');
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      const payload = result.data;
      setWarnings(payload.warnings || []);
      setMessage(
        payload.template_hash
          ? `Template ${payload.name || '(baru)'} dibuat (${payload.env_count || 0} env) dan aktif untuk dispatch.`
          : 'Template dibuat tetapi hash belum terbaca — isi manual di kolom Template hash.'
      );
      toast.success('Template worker baru dibuat.');
      if (payload.name) setName(payload.name);
      refresh();
    });
  };

  const drift = Boolean(data.drift);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Worker Template</CardTitle>
        <CardDescription>
          Satu template untuk semua provider/model. Env dibekukan dari image + env pipeline
          (otomatis memuat pengaturan provider model aktif), lalu hash-nya dipakai dispatch.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-center gap-2 text-xs'>
          <Badge variant={data.template_hash ? 'secondary' : 'destructive'}>
            {data.template_hash ? `hash ${data.template_hash.slice(0, 12)}…` : 'belum ada template'}
          </Badge>
          <Badge variant={data.ready ? 'secondary' : 'outline'}>
            {data.ready ? 'siap dispatch' : 'belum siap'}
          </Badge>
          <Badge variant={drift ? 'destructive' : 'outline'}>
            {drift ? 'perlu sync (env berubah)' : 'template sinkron'}
          </Badge>
          <span className='text-muted-foreground'>
            {data.env_count ?? 0} env dibekukan · limit {data.env_limit || 4096} char
          </span>
          {data.last_synced_at ? (
            <span className='text-muted-foreground'>
              sync terakhir {new Date(data.last_synced_at).toLocaleString('id-ID')}
            </span>
          ) : null}
          {data.active_provider ? (
            <span className='text-muted-foreground'>provider aktif: {data.active_provider}</span>
          ) : null}
        </div>

        {data.missing_required?.length ? (
          <p className='text-xs text-amber-600'>Env wajib belum terisi: {data.missing_required.join(', ')}</p>
        ) : null}

        <div className='grid gap-3 md:grid-cols-3'>
          <div className='space-y-1'>
            <Label htmlFor='wt-name'>Nama template</Label>
            <Input id='wt-name' value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className='space-y-1'>
            <Label htmlFor='wt-image'>Image worker</Label>
            <Input id='wt-image' value={image} onChange={(event) => setImage(event.target.value)} placeholder='sujinwo555/clipzi-backend:worker' />
          </div>
          <div className='space-y-1'>
            <Label htmlFor='wt-disk'>Disk template (GB)</Label>
            <Input id='wt-disk' type='number' min={10} max={500} value={disk} onChange={(event) => setDisk(event.target.value)} />
          </div>
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <Button onClick={runCreate} disabled={pending || busy !== ''}>
            {busy === 'create' ? 'Membuat template baru…' : 'Buat template baru (auto nama)'}
          </Button>
          <Button variant='outline' onClick={() => runSync()} disabled={pending || busy !== ''}>
            {busy === 'sync' ? 'Menyinkronkan…' : 'Update template aktif'}
          </Button>
          <Button variant='outline' onClick={refresh} disabled={pending || busy !== ''}>
            Muat status
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          &ldquo;Buat template baru&rdquo; selalu membuat template berbeda (
          <code>clipzi-worker-1</code>, <code>-2</code>, …) memakai env backend terbaru dan image
          yang dipin ke digest build terbaru, lalu otomatis diaktifkan untuk dispatch.
        </p>

        <div className='rounded-md border border-dashed p-3'>
          <p className='text-sm font-medium'>Adopsi template lama (opsional)</p>
          <p className='text-muted-foreground text-xs'>
            Kalau sudah punya template per-provider lama, tempel hash-nya agar dipakai tanpa membuat baru.
          </p>
          <div className='mt-2 flex flex-wrap gap-2'>
            <Input value={adopt} onChange={(event) => setAdopt(event.target.value)} placeholder='hash template lama' className='max-w-xs' />
            <Button variant='secondary' onClick={() => runSync(adopt.trim())} disabled={!adopt.trim() || pending || busy !== ''}>
              {busy === 'adopt' ? 'Mengadopsi…' : 'Adopsi hash'}
            </Button>
          </div>
        </div>

        {message ? <p className='text-xs text-emerald-600'>{message}</p> : null}
        {warnings.length ? (
          <ul className='list-disc space-y-1 pl-4 text-xs text-amber-600'>
            {warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
