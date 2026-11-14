'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SubmitButton } from '@/components/ui/submit-button';
import { createRunner, deleteRunner, testRunner, toggleRunner } from '@/app/dashboard/settings/runners/actions';

export type RunnerRow = {
  id: string;
  name: string;
  owner: string;
  repo: string;
  workflow_file: string;
  git_ref: string;
  auth_mode: string;
  has_token: boolean;
  enabled: boolean;
  status: string;
  weight: number;
  cooldown_until: string | null;
  success_count: number;
  failure_count: number;
  last_execution_at: string | null;
  last_error: string | null;
  rate_limit_remaining: number | null;
};

function tone(status: string) {
  if (status === 'active') return 'secondary' as const;
  if (status === 'error') return 'destructive' as const;
  return 'outline' as const;
}

export default function RunnerManager({ runners }: { runners: RunnerRow[] }) {
  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Tambah runner</CardTitle>
          <CardDescription>
            Gunakan PAT fine-grained dengan izin <strong>Actions: write</strong> pada repo yang
            memang diotorisasi. Jangan memakai akun/repo yang tidak berwenang.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={createRunner} className='grid gap-3 md:grid-cols-3'>
            <div className='space-y-1'>
              <Label htmlFor='name'>Nama</Label>
              <Input id='name' name='name' placeholder='github-primary' required />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='owner'>Owner</Label>
              <Input id='owner' name='owner' placeholder='jayras150' required />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='repo'>Repository</Label>
              <Input id='repo' name='repo' placeholder='ClipziAI' required />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='workflow_file'>Workflow file</Label>
              <Input id='workflow_file' name='workflow_file' defaultValue='downloader_video.yml' />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='git_ref'>Branch/ref</Label>
              <Input id='git_ref' name='git_ref' defaultValue='main' />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='weight'>Weight (load balancing)</Label>
              <Input id='weight' name='weight' type='number' min='1' max='1000' defaultValue='100' />
            </div>
            <div className='space-y-1 md:col-span-3'>
              <Label htmlFor='token'>GitHub token (write-only)</Label>
              <Input
                id='token'
                name='token'
                type='password'
                autoComplete='new-password'
                placeholder='github_pat_… (disimpan terenkripsi)'
              />
            </div>
            <div className='md:col-span-3'>
              <SubmitButton pendingLabel='Menyimpan…'>Tambah runner</SubmitButton>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Runner terdaftar ({runners.length})</CardTitle>
          <CardDescription>
            Pemilihan runner memakai weighted random berdasarkan success rate, cooldown, dan status
            kesehatan.
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          {runners.length === 0 ? (
            <p className='text-muted-foreground text-sm'>
              Belum ada runner. Download tetap berjalan di Vast; fallback GitHub hanya dipakai bila
              runner tersedia.
            </p>
          ) : null}
          {runners.map((runner) => {
            const total = runner.success_count + runner.failure_count;
            const rate = total ? Math.round((runner.success_count / total) * 100) : null;
            return (
              <div key={runner.id} className='rounded-lg border p-3'>
                <div className='flex flex-wrap items-center gap-2'>
                  <span className='font-medium'>{runner.name}</span>
                  <Badge variant={tone(runner.status)}>{runner.status}</Badge>
                  {runner.enabled ? (
                    <Badge variant='outline'>enabled</Badge>
                  ) : (
                    <Badge variant='destructive'>disabled</Badge>
                  )}
                  <span className='text-muted-foreground text-xs'>
                    {runner.owner}/{runner.repo} · {runner.workflow_file} · {runner.git_ref}
                  </span>
                </div>
                <div className='text-muted-foreground mt-1 text-xs'>
                  success {runner.success_count} · failure {runner.failure_count}
                  {rate !== null ? ` · rate ${rate}%` : ''} · weight {runner.weight}
                  {runner.rate_limit_remaining !== null
                    ? ` · rate-limit sisa ${runner.rate_limit_remaining}`
                    : ''}
                  {runner.cooldown_until ? ` · cooldown s/d ${runner.cooldown_until}` : ''}
                  {runner.has_token ? '' : ' · token BELUM diisi'}
                </div>
                {runner.last_error ? (
                  <p className='text-destructive mt-1 line-clamp-2 text-xs'>{runner.last_error}</p>
                ) : null}
                <div className='mt-2 flex flex-wrap gap-2'>
                  <form action={testRunner}>
                    <input type='hidden' name='id' value={runner.id} />
                    <SubmitButton size='sm' variant='secondary' pendingLabel='Menguji…'>
                      Test koneksi
                    </SubmitButton>
                  </form>
                  <form action={toggleRunner}>
                    <input type='hidden' name='id' value={runner.id} />
                    <input type='hidden' name='enabled' value={runner.enabled ? '0' : '1'} />
                    <SubmitButton size='sm' variant='outline' pendingLabel='…'>
                      {runner.enabled ? 'Disable' : 'Enable'}
                    </SubmitButton>
                  </form>
                  <form action={deleteRunner}>
                    <input type='hidden' name='id' value={runner.id} />
                    <SubmitButton size='sm' variant='destructive' pendingLabel='Menghapus…'>
                      Hapus
                    </SubmitButton>
                  </form>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
