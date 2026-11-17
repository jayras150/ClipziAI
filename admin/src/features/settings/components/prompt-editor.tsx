'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { LogDialog, type LogDialogData } from '@/components/ui/log-dialog';
import {
  fetchAiPrompts,
  previewAiPrompt,
  resetAiPrompt,
  saveAiPrompt,
  testAiPrompt,
  type PromptMeta,
  type PromptPayload
} from '@/app/dashboard/settings/ai/actions';

/** Editor registry prompt AI: preview, simpan, reset, test ke model aktif. */
export default function PromptEditor() {
  const [data, setData] = useState<PromptPayload | null>(null);
  const [key, setKey] = useState('metadata_system');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState('');
  const [preview, setPreview] = useState('');
  const [logOpen, setLogOpen] = useState(false);
  const [logData, setLogData] = useState<LogDialogData | null>(null);

  const load = () => {
    void fetchAiPrompts().then((result) => {
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      setData(result.data);
      setKey((prev) =>
        result.data.prompts[prev] !== undefined ? prev : result.data.meta[0]?.key || 'metadata_system'
      );
    });
  };

  useEffect(load, []);

  useEffect(() => {
    if (!data) return;
    setText(data.prompts[key] || '');
    setPreview('');
  }, [data, key]);

  const meta: PromptMeta | undefined = useMemo(
    () => data?.meta.find((item) => item.key === key),
    [data, key]
  );
  const variables = data?.variables?.[key] || [];
  const isDefault = Boolean(data) && (data?.prompts[key] || '') === (data?.defaults[key] || '');

  const doPreview = () => {
    setBusy('preview');
    void previewAiPrompt(key, text).then((result) => {
      setBusy('');
      if (result.ok) {
        setPreview(result.data.rendered);
        toast.success('Pratinjau dibuat.');
      } else toast.error(result.error);
    });
  };

  const doSave = () => {
    setBusy('save');
    void saveAiPrompt(key, text).then((result) => {
      setBusy('');
      if (result.ok) {
        setData(result.data);
        toast.success('Prompt disimpan — task berikutnya memakai versi ini.');
      } else toast.error(result.error);
    });
  };

  const doReset = () => {
    setBusy('reset');
    void resetAiPrompt(key).then((result) => {
      setBusy('');
      if (result.ok) {
        setData(result.data);
        toast.success('Prompt dikembalikan ke default.');
      } else toast.error(result.error);
    });
  };

  const doTest = () => {
    setBusy('test');
    void testAiPrompt(key, text).then((result) => {
      setBusy('');
      setLogData({
        title: result.ok ? 'Prompt diuji ke model' : 'Uji prompt gagal',
        subtitle: `${key} - ${meta?.label || ''}`,
        detail: result.ok ? `Selesai dalam ${result.data.elapsed}s` : result.error,
        log: (result.ok ? result.data.log_text : (result as { log_text?: string }).log_text) || ''
      });
      setLogOpen(true);
      if (result.ok) toast.success('Model menjawab — lihat log.');
      else toast.error(result.error);
    });
  };

  const insert = (variable: string) => setText((prev) => `${prev}{{${variable}}}`);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prompt AI (registry)</CardTitle>
        <CardDescription>
          Prompt metadata Shorts, rerank klip, dan viral score bisa diubah di sini. Perubahan
          langsung dipakai task berikutnya dan riwayatnya tersimpan.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='grid gap-3 md:grid-cols-2'>
          <div>
            <label className='text-sm font-medium'>Prompt</label>
            <select
              className='border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm'
              value={key}
              onChange={(event) => setKey(event.target.value)}
            >
              {(data?.meta || []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.group ? `${item.group} — ` : ''}
                  {item.label || item.key}
                  {item.is_custom ? ' (kustom)' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className='text-muted-foreground text-xs'>
            <p className='font-medium'>Dipakai untuk</p>
            <p>{(meta?.features || []).join(', ') || '-'}</p>
            <p className='mt-1'>
              Default: {isDefault ? 'ya (bawaan)' : 'tidak — sedang memakai versi kustom'}
            </p>
          </div>
        </div>

        {variables.length ? (
          <div>
            <label className='text-sm font-medium'>Variabel</label>
            <div className='mt-1 flex flex-wrap gap-1'>
              {variables.map((variable) => (
                <button
                  key={variable}
                  type='button'
                  onClick={() => insert(variable)}
                  className='bg-muted rounded px-2 py-0.5 font-mono text-xs'
                >
                  {'{{' + variable + '}}'}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div>
          <label className='text-sm font-medium'>Isi prompt</label>
          <textarea
            rows={14}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder='Kosong = pakai prompt bawaan kode. Isi untuk override (pakai variabel di atas).'
            className='border-input bg-background mt-1 w-full rounded-md border p-2 font-mono text-xs'
          />
        </div>

        <div className='flex flex-wrap gap-2'>
          <Button onClick={doSave} disabled={busy !== ''}>
            Simpan
          </Button>
          <Button variant='outline' onClick={doPreview} disabled={busy !== ''}>
            Pratinjau
          </Button>
          <Button variant='outline' onClick={doTest} disabled={busy !== ''}>
            Test ke model
          </Button>
          <Button variant='ghost' onClick={doReset} disabled={busy !== '' || isDefault}>
            Reset default
          </Button>
          <Button variant='ghost' onClick={load} disabled={busy !== ''}>
            Muat ulang
          </Button>
        </div>

        {preview ? (
          <div>
            <label className='text-sm font-medium'>Hasil render (sample)</label>
            <pre className='bg-muted mt-1 max-h-64 overflow-auto rounded p-2 text-xs whitespace-pre-wrap'>
              {preview}
            </pre>
          </div>
        ) : null}

        {data?.history?.length ? (
          <div>
            <label className='text-sm font-medium'>Riwayat perubahan</label>
            <ul className='text-muted-foreground mt-1 space-y-0.5 text-xs'>
              {data.history.slice(0, 8).map((entry, index) => (
                <li key={entry.at + '-' + index}>
                  {new Date(entry.at).toLocaleString('id-ID')} · {entry.key} · {entry.action} ·{' '}
                  {entry.chars ?? 0} chars {entry.by ? `· ${entry.by}` : ''}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <LogDialog
          open={logOpen}
          data={logData}
          loading={busy === 'test'}
          onClose={() => setLogOpen(false)}
        />
      </CardContent>
    </Card>
  );
}

