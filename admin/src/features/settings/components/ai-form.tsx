'use client';

import { useMemo, useState, useTransition } from 'react';

import { loadAiModels, saveAi, testAi, type ModelsResult, type TestResult } from '@/app/dashboard/settings/actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { AiConfig, AiProviderMeta } from '@/lib/clipzi';

type Props = { config: AiConfig; providers: AiProviderMeta[] };

/**
 * Dropdown sederhana bergaya template (input + daftar tersaring) supaya bisa
 * dipakai tanpa ketergantungan komponen tambahan.
 */
function ComboField({
  label,
  value,
  onChange,
  options,
  placeholder,
  searchPlaceholder
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string; hint?: string }[];
  placeholder?: string;
  searchPlaceholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options.slice(0, 300);
    return options
      .filter(
        (option) =>
          option.value.toLowerCase().includes(needle) ||
          option.label.toLowerCase().includes(needle)
      )
      .slice(0, 300);
  }, [options, query]);

  return (
    <div className='relative space-y-2'>
      <Label>{label}</Label>
      <Input
        value={open ? query : value}
        placeholder={open ? searchPlaceholder || 'cari...' : placeholder}
        onFocus={() => {
          setOpen(true);
          setQuery('');
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open ? (
        <div className='bg-popover absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border shadow-md'>
          {filtered.length ? (
            filtered.map((option) => (
              <button
                key={option.value}
                type='button'
                className='hover:bg-accent flex w-full flex-col items-start px-3 py-2 text-left text-sm'
                onMouseDown={(event) => {
                  event.preventDefault();
                  onChange(option.value);
                  setOpen(false);
                  setQuery('');
                }}
              >
                <span className='font-medium'>{option.value}</span>
                {option.label !== option.value || option.hint ? (
                  <span className='text-muted-foreground text-xs'>
                    {[option.label, option.hint].filter(Boolean).join(' · ')}
                  </span>
                ) : null}
              </button>
            ))
          ) : (
            <p className='text-muted-foreground px-3 py-2 text-sm'>Tidak ada hasil.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function AiForm({ config, providers }: Props) {
  const [form, setForm] = useState({
    enabled: config.enabled,
    provider: config.provider,
    base_url: config.base_url,
    api_key: '',
    model_metadata: config.model_metadata,
    model_rerank: config.model_rerank,
    model_regenerate: config.model_regenerate,
    temperature: config.temperature,
    max_tokens: config.max_tokens,
    timeout_seconds: config.timeout_seconds,
    max_retries: config.max_retries,
    rerank_enabled: config.rerank_enabled,
    metadata_enabled: config.metadata_enabled,
    rerank_budget_seconds: config.rerank_budget_seconds,
    metadata_budget_seconds: config.metadata_budget_seconds
  });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [test, setTest] = useState<TestResult | null>(null);
  const [models, setModels] = useState<ModelsResult | null>(null);
  const [pending, startTransition] = useTransition();

  const set = (key: keyof typeof form, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const activeProvider = providers.find((item) => item.id === form.provider);

  const onSubmit = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveAi({ ...form, api_key: form.api_key || undefined });
      if (result.ok) {
        setMessage('Tersimpan. Env di-inject: ' + (result.injected || []).join(', '));
        setForm((prev) => ({ ...prev, api_key: '' }));
        // Setelah kredensial tersimpan, langsung muat daftar model nyata.
        const loaded = await loadAiModels({ provider: form.provider, base_url: form.base_url });
        setModels(loaded);
      } else {
        setError(result.error || 'Gagal menyimpan.');
      }
    });
  };

  const onLoadModels = () => {
    setModels(null);
    setError('');
    startTransition(async () => {
      const loaded = await loadAiModels({ provider: form.provider, base_url: form.base_url });
      setModels(loaded);
      if (!loaded.ok) setError(loaded.error || 'Gagal memuat daftar model.');
    });
  };

  const onTest = () => {
    setTest(null);
    setError('');
    startTransition(async () => {
      const result = await testAi();
      setTest(result);
      if (!result.ok) setError(result.error || 'Provider tidak merespons.');
    });
  };

  const modelOptions = (models?.models || []).map((item) => ({
    value: item.id,
    label: item.id,
    hint: item.owned_by || undefined
  }));

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Provider</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-2'>
          <ComboField
            label='Provider'
            value={form.provider}
            placeholder='pilih provider'
            searchPlaceholder='cari provider (openrouter, groq, ...)'
            onChange={(value) => {
              set('provider', value);
              const meta = providers.find((item) => item.id === value);
              if (meta?.base_url) set('base_url', '');
              if (meta?.default_model && !form.model_metadata) set('model_metadata', meta.default_model);
              setModels(null);
            }}
            options={providers.map((item) => ({
              value: item.id,
              label: item.label,
              hint: item.base_url || 'butuh base URL manual'
            }))}
          />
          <div className='space-y-2'>
            <Label htmlFor='base_url'>Base URL</Label>
            <Input
              id='base_url'
              placeholder={activeProvider?.base_url || 'https://...'}
              value={form.base_url}
              onChange={(event) => set('base_url', event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>
              Kosongkan untuk memakai default provider
              {activeProvider?.base_url ? `: ${activeProvider.base_url}` : ''}.
            </p>
          </div>
          <div className='space-y-2'>
            <Label htmlFor='api_key'>API key {config.api_key_set ? `(tersimpan: ${config.api_key_masked})` : ''}</Label>
            <Input
              id='api_key'
              type='password'
              placeholder={config.api_key_set ? 'biarkan kosong bila tidak diubah' : 'sk-...'}
              value={form.api_key}
              onChange={(event) => set('api_key', event.target.value)}
            />
          </div>
          <div className='flex items-end gap-2'>
            <Button
              type='button'
              variant='outline'
              className='gap-2'
              onClick={onLoadModels}
              disabled={pending}
            >
              {pending ? <ClipzySpinner size='xs' variant='ring' /> : null}
              {pending ? 'Memuat…' : 'Muat daftar model'}
            </Button>
            {models?.ok ? (
              <Badge variant='secondary'>
                {models.count} model{models.cached ? ' (cache)' : ''}
              </Badge>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-3'>
          <ComboField
            label='Model metadata'
            value={form.model_metadata}
            placeholder='pilih / ketik model'
            searchPlaceholder='cari nama atau id model'
            onChange={(value) => set('model_metadata', value)}
            options={modelOptions}
          />
          <ComboField
            label='Model rerank'
            value={form.model_rerank}
            searchPlaceholder='cari nama atau id model'
            onChange={(value) => set('model_rerank', value)}
            options={modelOptions}
          />
          <ComboField
            label='Model regenerate'
            value={form.model_regenerate}
            searchPlaceholder='cari nama atau id model'
            onChange={(value) => set('model_regenerate', value)}
            options={modelOptions}
          />
          <p className='text-muted-foreground text-xs md:col-span-3'>
            {modelOptions.length
              ? `${modelOptions.length} model tersedia. Klik “Muat daftar model” setelah menyimpan API key untuk memperbarui daftar.`
              : 'Daftar model belum dimuat — isi API key lalu simpan, atau klik “Muat daftar model”. Nama model juga bisa diketik manual.'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Perilaku</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-3'>
          <div className='space-y-2'>
            <Label htmlFor='temperature'>Temperature</Label>
            <Input
              id='temperature'
              type='number'
              step='0.1'
              value={form.temperature}
              onChange={(event) => set('temperature', Number(event.target.value))}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='max_tokens'>Max tokens</Label>
            <Input
              id='max_tokens'
              type='number'
              value={form.max_tokens}
              onChange={(event) => set('max_tokens', Number(event.target.value))}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='timeout_seconds'>Timeout (detik)</Label>
            <Input
              id='timeout_seconds'
              type='number'
              value={form.timeout_seconds}
              onChange={(event) => set('timeout_seconds', Number(event.target.value))}
            />
          </div>
          <div className='space-y-2'>
            <Label>Rerank momen viral</Label>
            <Button
              type='button'
              variant={form.rerank_enabled ? 'default' : 'outline'}
              onClick={() => set('rerank_enabled', !form.rerank_enabled)}
            >
              {form.rerank_enabled ? 'Aktif' : 'Nonaktif'}
            </Button>
          </div>
          <div className='space-y-2'>
            <Label>Metadata AI</Label>
            <Button
              type='button'
              variant={form.metadata_enabled ? 'default' : 'outline'}
              onClick={() => set('metadata_enabled', !form.metadata_enabled)}
            >
              {form.metadata_enabled ? 'Aktif' : 'Nonaktif'}
            </Button>
          </div>
          <div className='space-y-2'>
            <Label>AI aktif</Label>
            <Button
              type='button'
              variant={form.enabled ? 'default' : 'outline'}
              onClick={() => set('enabled', !form.enabled)}
            >
              {form.enabled ? 'Aktif' : 'Nonaktif'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {message ? <Badge variant='secondary'>{message}</Badge> : null}
      {error ? <p className='text-destructive text-sm'>{error}</p> : null}
      {test && test.ok ? (
        <p className='text-sm'>
          Test OK - {test.model} - {test.latency_ms} ms - sample:{' '}
          <code>{test.sample || '(kosong)'}</code>
        </p>
      ) : null}

      <div className='flex gap-2'>
        <Button className='gap-2' onClick={onSubmit} disabled={pending}>
          {pending ? <ClipzySpinner size='xs' variant='ring' /> : null}
          {pending ? 'Menyimpan…' : 'Simpan'}
        </Button>
        <Button variant='outline' className='gap-2' onClick={onTest} disabled={pending}>
          {pending ? <ClipzySpinner size='xs' variant='ring' /> : null}
          Test Connection
        </Button>
      </div>
    </div>
  );
}

