'use client';

import { useMemo, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';

import {
  downloadWhisperNotebook,
  saveWhisperSource,
  syncWhisperTemplate,
  testWhisperSource
} from '@/app/dashboard/settings/models/actions';
import { ProviderLogo } from './provider-logos';

export type ProviderField = {
  name: string;
  label: string;
  type: 'text' | 'secret';
  required: boolean;
  default: string;
  help: string;
};

export type ProviderMeta = {
  id: string;
  label: string;
  icon: string;
  color: string;
  restore_mode: string;
  template_name: string;
  notebook: string;
  description: string;
  hint: string;
  active: boolean;
  fields: ProviderField[];
};

export type SourceTemplate = {
  provider: string;
  provider_label: string;
  name: string;
  exists: boolean;
  template_hash: string;
  template_id?: string | number | null;
  active: boolean;
};

export type WhisperSourceData = {
  provider: string;
  configured: boolean;
  values: Record<string, string>;
  providers: ProviderMeta[];
  templates?: { items: SourceTemplate[]; active_hash?: string; error?: string };
  warnings?: string[];
};

const MODE_LABEL: Record<string, string> = {
  vast_cloud_copy: 'Vast cloud_copy',
  url_download: 'Unduh model via URL',
  hf_snapshot: 'Unduh dari Hugging Face'
};

function defaultsFor(provider: ProviderMeta): Record<string, string> {
  const values: Record<string, string> = {};
  provider.fields.forEach((field) => {
    values[field.name] = field.default || '';
  });
  return values;
}

export default function WhisperSourcePanel({ data }: { data: WhisperSourceData }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [providerId, setProviderId] = useState(data.provider);
  const [values, setValues] = useState<Record<string, string>>(() => ({
    ...defaultsFor(
      data.providers.find((item) => item.id === data.provider) || data.providers[0]
    ),
    ...data.values
  }));
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const provider = useMemo(
    () => data.providers.find((item) => item.id === providerId) || data.providers[0],
    [data.providers, providerId]
  );
  const activeProvider = data.providers.find((item) => item.id === data.provider);

  const setValue = (name: string, value: string) =>
    setValues((prev) => ({ ...prev, [name]: value }));

  const pickProvider = (next: ProviderMeta) => {
    setProviderId(next.id);
    setMessage('');
    setError('');
    setValues(
      next.id === data.provider ? { ...defaultsFor(next), ...data.values } : defaultsFor(next)
    );
  };

  const runTest = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await testWhisperSource({ provider: provider.id, values });
      if (result.error) {
        setError(result.error);
        return;
      }
      const info = result.data as { label?: string; count?: number };
      setMessage(
        `Koneksi ${info.label || provider.label} berhasil: ${info.count ?? 0} model terdeteksi.`
      );
    });
  };

  const runSave = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveWhisperSource({ provider: provider.id, values });
      if (result.error) {
        setError(result.error);
        return;
      }
      const payload = result.data as {
        template?: {
          name?: string;
          action?: string;
          template_hash?: string;
          activated?: boolean;
          error?: string;
        };
      };
      const tpl = payload.template || {};
      if (tpl.error) {
        setError(`Kredensial tersimpan, tetapi template Vast gagal: ${tpl.error}`);
      } else if (tpl.name) {
        setMessage(
          `Tersimpan. Template "${tpl.name}" ${
            tpl.action === 'updated' ? 'diperbarui' : 'dibuat'
          }${tpl.activated ? ' dan langsung diaktifkan' : ''}${
            tpl.template_hash ? ` (hash ${tpl.template_hash.slice(0, 8)}…​)` : ''
          }.`
        );
      } else {
        setMessage('Kredensial tersimpan.');
      }
      router.refresh();
    });
  };

  const runTemplate = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await syncWhisperTemplate(provider.id);
      if (result.error) {
        setError(result.error);
        return;
      }
      const payload = result.data as { name?: string; action?: string; template_hash?: string };
      setMessage(
        `Template ${payload.name || provider.template_name} ${
          payload.action === 'updated' ? 'diperbarui' : 'dibuat'
        }${payload.template_hash ? ` · hash ${payload.template_hash.slice(0, 8)}…​` : ''}.`
      );
      router.refresh();
    });
  };

  const runNotebook = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await downloadWhisperNotebook(provider.id);
      if (result.error || !result.data) {
        setError(result.error || 'Notebook tidak tersedia.');
        return;
      }
      const blob = new Blob([result.data.content], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = result.data.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage(`Notebook ${result.data.filename} diunduh.`);
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sumber model Whisper</CardTitle>
        <CardDescription>
          Pilih provider, simpan kredensial, lalu template Vast{' '}
          <code>Clipzy &lt;Provider&gt;</code> dibuat dan diaktifkan otomatis.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5'>
          {data.providers.map((item) => {
            const isActive = item.id === data.provider;
            const isSelected = item.id === provider?.id;
            return (
              <button
                key={item.id}
                type='button'
                onClick={() => pickProvider(item)}
                aria-pressed={isSelected}
                className={[
                  'flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition',
                  'hover:border-foreground/30 hover:bg-muted/60',
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/40'
                    : 'border-border bg-card shadow-xs'
                ].join(' ')}
              >
                <ProviderLogo icon={item.icon} color={item.color} size={20} />
                <span className='min-w-0 flex-1'>
                  <span className='block truncate font-medium'>{item.label}</span>
                  <span className='text-muted-foreground block truncate text-xs'>
                    {MODE_LABEL[item.restore_mode] || item.restore_mode}
                  </span>
                </span>
                {isActive ? <Badge variant='secondary'>aktif</Badge> : null}
              </button>
            );
          })}
        </div>

        {provider ? (
          <p className='text-muted-foreground text-sm'>{provider.description}</p>
        ) : null}

        <div className='grid gap-3 sm:grid-cols-2'>
          {(provider?.fields || []).map((field) => (
            <div key={field.name} className='space-y-1'>
              <Label htmlFor={`field-${field.name}`}>
                {field.label}
                {field.required ? <span className='text-destructive'> *</span> : null}
              </Label>
              <Input
                id={`field-${field.name}`}
                type={field.type === 'secret' ? 'password' : 'text'}
                value={values[field.name] ?? ''}
                placeholder={
                  field.type === 'secret'
                    ? data.provider === provider?.id
                      ? 'Kosongkan untuk memakai nilai tersimpan'
                      : 'Isi kredensial'
                    : field.default
                }
                onChange={(event) => setValue(field.name, event.target.value)}
                autoComplete='off'
              />
              {field.help ? (
                <p className='text-muted-foreground text-xs'>{field.help}</p>
              ) : null}
            </div>
          ))}
        </div>

        {provider?.hint ? (
          <p className='text-muted-foreground rounded-md border border-dashed p-2 text-xs'>
            {provider.hint}
          </p>
        ) : null}

        <div className='flex flex-wrap gap-2'>
          <Button variant='outline' onClick={runTest} disabled={pending}>
            Uji koneksi
          </Button>
          <Button onClick={runSave} disabled={pending}>
            Simpan &amp; buat template
          </Button>
          <Button variant='secondary' onClick={runTemplate} disabled={pending}>
            Segarkan template Vast
          </Button>
          <Button variant='ghost' onClick={runNotebook} disabled={pending}>
            Unduh notebook Colab
          </Button>
        </div>

        {message ? (
          <p className='text-sm text-emerald-600 dark:text-emerald-400'>{message}</p>
        ) : null}
        {error ? <p className='text-destructive text-sm'>{error}</p> : null}

        {(data.warnings || []).length > 0 ? (
          <ul className='text-muted-foreground list-disc pl-5 text-xs'>
            {data.warnings?.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        ) : null}

        <Separator />

        <div className='space-y-2'>
          <p className='text-sm font-medium'>Template Vast per provider</p>
          {data.templates?.error ? (
            <p className='text-destructive text-xs'>{data.templates.error}</p>
          ) : null}
          <ul className='space-y-1 text-sm'>
            {(data.templates?.items || []).map((item) => (
              <li key={item.provider} className='flex flex-wrap items-center gap-2'>
                <span className='w-40 truncate'>{item.name}</span>
                <Badge variant={item.exists ? 'secondary' : 'outline'}>
                  {item.exists ? 'terpasang' : 'belum ada'}
                </Badge>
                {item.active ? <Badge>aktif di dispatch</Badge> : null}
                {item.template_hash ? (
                  <code className='text-muted-foreground text-xs'>
                    {item.template_hash.slice(0, 8)}…
                  </code>
                ) : null}
              </li>
            ))}
          </ul>
          {activeProvider ? (
            <p className='text-muted-foreground text-xs'>
              Provider aktif sekarang: <strong>{activeProvider.label}</strong> · restore{' '}
              {MODE_LABEL[activeProvider.restore_mode] || activeProvider.restore_mode}
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
