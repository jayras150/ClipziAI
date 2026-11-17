'use client';

import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import { provisionRunner } from '@/app/dashboard/settings/runners/actions';

/**
 * Form "Tambah Runner" versi baru: cukup token GitHub, username, nama repo,
 * workflow file, dan branch/ref. Repo + workflow dibuat otomatis; nama runner
 * mengikuti `owner/repo` (tidak perlu diisi).
 */
export default function RunnerProvision() {
  const [form, setForm] = useState({
    github_token: '',
    owner: '',
    repo: '',
    workflow_file: 'downloader_video.yml',
    git_ref: '',
    weight: '100'
  });
  const [pending, startTransition] = useTransition();
  const [logOpen, setLogOpen] = useState(false);
  const [logData, setLogData] = useState<LogDialogData | null>(null);

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = () => {
    const payload = new FormData();
    Object.entries(form).forEach(([key, value]) => payload.set(key, value));
    startTransition(async () => {
      const result = await provisionRunner(payload);
      setLogData({
        title: result.ok ? 'Runner dibuat' : 'Gagal membuat runner',
        subtitle: form.repo ? `${form.owner || 'auto'}/${form.repo}` : 'GitHub',
        detail: result.message,
        log: result.log_text || result.message
      });
      setLogOpen(true);
      if (result.ok) {
        toast.success(result.message);
        setForm((prev) => ({ ...prev, github_token: '' }));
      } else {
        toast.error(result.message);
      }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tambah Runner (otomatis buat repo)</CardTitle>
        <CardDescription>
          Isi token GitHub + nama repo. Sistem membuat repo (private), memasang workflow
          downloader, lalu menyimpan runner. Nama runner otomatis <code>owner/repo</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid gap-3 md:grid-cols-2'>
          <div>
            <Label>GitHub token (PAT)</Label>
            <Input
              type='password'
              value={form.github_token}
              onChange={set('github_token')}
              placeholder='ghp_…'
              autoComplete='off'
            />
          </div>
          <div>
            <Label>Username / owner</Label>
            <Input value={form.owner} onChange={set('owner')} placeholder='kosong = pemilik token' />
          </div>
          <div>
            <Label>Nama repo</Label>
            <Input value={form.repo} onChange={set('repo')} placeholder='clipzy-downloader' />
          </div>
          <div>
            <Label>Workflow file</Label>
            <Input value={form.workflow_file} onChange={set('workflow_file')} />
          </div>
          <div>
            <Label>Branch / ref</Label>
            <Input value={form.git_ref} onChange={set('git_ref')} placeholder='kosong = default branch' />
          </div>
          <div>
            <Label>Weight (load balancing)</Label>
            <Input value={form.weight} onChange={set('weight')} type='number' min={1} />
          </div>
        </div>
        <div className='flex flex-wrap gap-2'>
          <Button onClick={submit} disabled={pending}>
            {pending ? 'Membuat…' : 'Buat runner + repo'}
          </Button>
          <Button
            variant='outline'
            onClick={() => {
              setLogData({ title: 'Panduan', detail: '', log: 'Token butuh scope: repo (Contents: read/write, Actions: write, Workflows: write).' });
              setLogOpen(true);
            }}
          >
            Scope yang dibutuhkan
          </Button>
        </div>
        <LogDialog open={logOpen} data={logData} loading={pending} onClose={() => setLogOpen(false)} />
      </CardContent>
    </Card>
  );
}
