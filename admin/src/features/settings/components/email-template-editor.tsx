'use client';

import { useEffect, useMemo, useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import {
  fetchEmailTemplates,
  previewEmailTemplate,
  resetEmailTemplate,
  saveEmailTemplate,
  testEmailKind,
  type EmailTemplate
} from '@/app/dashboard/settings/smtp/actions';

const KIND_LABEL: Record<string, string> = {
  welcome: 'Welcome (setelah daftar)',
  verify: 'Verifikasi email',
  otp: 'Kode OTP',
  reset: 'Reset password',
  notify: 'Notifikasi pengguna',
  report: 'Laporan otomatis'
};

/** Editor template email (HTML/CSS) per jenis + pratinjau + test kirim. */
export default function EmailTemplateEditor() {
  const [templates, setTemplates] = useState<Record<string, EmailTemplate>>({});
  const [defaults, setDefaults] = useState<Record<string, EmailTemplate>>({});
  const [variables, setVariables] = useState<Record<string, string[]>>({});
  const [kinds, setKinds] = useState<string[]>([]);
  const [kind, setKind] = useState('welcome');
  const [subject, setSubject] = useState('');
  const [html, setHtml] = useState('');
  const [preview, setPreview] = useState('');
  const [to, setTo] = useState('');
  const [pending, startTransition] = useTransition();
  const [logOpen, setLogOpen] = useState(false);
  const [logData, setLogData] = useState<LogDialogData | null>(null);

  useEffect(() => {
    void fetchEmailTemplates().then((result) => {
      if (!result.ok || !result.data) return;
      setKinds(result.data.kinds || []);
      setTemplates(result.data.templates || {});
      setDefaults(result.data.defaults || {});
      setVariables(result.data.variables || {});
    });
  }, []);

  useEffect(() => {
    const current = templates[kind];
    if (current) {
      setSubject(current.subject || '');
      setHtml(current.html || '');
      setPreview('');
    }
  }, [kind, templates]);

  const chips = useMemo(() => variables[kind] || [], [variables, kind]);
  const isDefault =
    Boolean(defaults[kind]) &&
    defaults[kind].subject === subject &&
    defaults[kind].html === html;

  const doPreview = () => {
    startTransition(async () => {
      const result = await previewEmailTemplate(kind, subject, html);
      if (result.ok && result.data) {
        setPreview(result.data.html || '');
        toast.success('Pratinjau dibuat.');
      } else toast.error(result.error || 'Gagal membuat pratinjau.');
    });
  };

  const doSave = () => {
    startTransition(async () => {
      const result = await saveEmailTemplate(kind, subject, html);
      if (result.ok) {
        setTemplates((prev) => ({ ...prev, [kind]: { subject, html } }));
        toast.success('Template disimpan.');
      } else toast.error(result.error || 'Gagal menyimpan template.');
    });
  };

  const doReset = () => {
    startTransition(async () => {
      const result = await resetEmailTemplate(kind);
      if (result.ok && defaults[kind]) {
        setSubject(defaults[kind].subject || '');
        setHtml(defaults[kind].html || '');
        toast.success('Template dikembalikan ke default.');
      } else toast.error(result.error || 'Gagal reset template.');
    });
  };

  const doTest = () => {
    if (!to.trim()) {
      toast.error('Isi email tujuan dulu.');
      return;
    }
    startTransition(async () => {
      const result = await testEmailKind(to.trim(), kind);
      setLogData({
        title: result.ok ? 'Email uji terkirim' : 'Email uji gagal',
        subtitle: `${kind} -> ${to}`,
        detail: result.ok ? '' : result.error || '',
        log:
          (result.data as { log_text?: string } | undefined)?.log_text ||
          JSON.stringify(result, null, 2)
      });
      setLogOpen(true);
      if (result.ok) toast.success('Email uji terkirim.');
      else toast.error(result.error || 'Gagal mengirim email uji.');
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email Template</CardTitle>
        <CardDescription>
          Ubah subject + HTML/CSS per jenis email. Placeholder {'{{nama}}'} diganti otomatis
          saat dikirim. Reset untuk kembali ke default.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid gap-3 md:grid-cols-2'>
          <div>
            <Label>Jenis email</Label>
            <select
              className='border-input bg-background h-9 w-full rounded-md border px-3 text-sm'
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              {(kinds.length ? kinds : Object.keys(KIND_LABEL)).map((item) => (
                <option key={item} value={item}>
                  {KIND_LABEL[item] || item}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Subject</Label>
            <Input value={subject} onChange={(event) => setSubject(event.target.value)} />
          </div>
        </div>

        <div>
          <Label>Variabel tersedia</Label>
          <div className='mt-1 flex flex-wrap gap-1'>
            {chips.length === 0 ? (
              <span className='text-muted-foreground text-xs'>-</span>
            ) : (
              chips.map((chip) => (
                <button
                  key={chip}
                  type='button'
                  className='bg-muted rounded px-2 py-0.5 font-mono text-xs'
                  onClick={() => setHtml((prev) => `${prev}{{${chip}}}`)}
                >
                  {'{{' + chip + '}}'}
                </button>
              ))
            )}
          </div>
        </div>

        <div>
          <Label>HTML / CSS email</Label>
          <textarea
            rows={12}
            value={html}
            onChange={(event) => setHtml(event.target.value)}
            className='border-input bg-background mt-1 w-full rounded-md border p-2 font-mono text-xs'
          />
        </div>

        <div className='flex flex-wrap items-end gap-2'>
          <div className='min-w-[220px] flex-1'>
            <Label>Email tujuan (test kirim)</Label>
            <Input
              value={to}
              onChange={(event) => setTo(event.target.value)}
              placeholder='admin@domain.com'
            />
          </div>
          <Button onClick={doSave} disabled={pending}>
            Simpan
          </Button>
          <Button variant='outline' onClick={doPreview} disabled={pending}>
            Pratinjau
          </Button>
          <Button variant='outline' onClick={doTest} disabled={pending}>
            Kirim test
          </Button>
          <Button variant='ghost' onClick={doReset} disabled={pending || isDefault}>
            Reset default
          </Button>
        </div>

        {preview ? (
          <div>
            <Label>Pratinjau</Label>
            <iframe
              title='preview'
              className='mt-1 h-72 w-full rounded-md border bg-white'
              srcDoc={preview}
            />
          </div>
        ) : null}

        <LogDialog open={logOpen} data={logData} loading={pending} onClose={() => setLogOpen(false)} />
      </CardContent>
    </Card>
  );
}

