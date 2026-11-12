"use client";

import { useState, useTransition } from 'react';

import { saveAi, testAi, type TestResult } from '@/app/dashboard/settings/actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { AiConfig } from '@/lib/clipzi';

type Props = { config: AiConfig };

export default function AiForm({ config }: Props) {
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
  const [pending, startTransition] = useTransition();

  const set = (key: keyof typeof form, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = () => {
    setMessage('');
    setError('');
    startTransition(async () => {
      const result = await saveAi({ ...form, api_key: form.api_key || undefined });
      if (result.ok) {
        setMessage(
          'Tersimpan. Env di-inject: ' + (result.injected || []).join(', ')
        );
        setForm((prev) => ({ ...prev, api_key: '' }));
      } else {
        setError(result.error || 'Gagal menyimpan.');
      }
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

  return (
    <div className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle>Provider</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-2'>
          <div className='space-y-2'>
            <Label htmlFor='provider'>Provider</Label>
            <select
              id='provider'
              className='border-input bg-background h-9 w-full rounded-md border px-3 text-sm'
              value={form.provider}
              onChange={(event) => set('provider', event.target.value)}
            >
              {config.providers.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
          </div>
          <div className='space-y-2'>
            <Label htmlFor='base_url'>Base URL (opsional)</Label>
            <Input
              id='base_url'
              placeholder={config.effective_base_url || 'default provider'}
              value={form.base_url}
              onChange={(event) => set('base_url', event.target.value)}
            />
          </div>
          <div className='space-y-2 md:col-span-2'>
            <Label htmlFor='api_key'>API Key</Label>
            <Input
              id='api_key'
              type='password'
              placeholder={config.api_key_set ? 'Tersimpan: ' + config.api_key_masked : 'Belum ada'}
              value={form.api_key}
              onChange={(event) => set('api_key', event.target.value)}
            />
            <p className='text-muted-foreground text-xs'>
              Kosongkan bila tidak ingin mengganti key. Disimpan terenkripsi di database.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-4 md:grid-cols-3'>
          <div className='space-y-2'>
            <Label htmlFor='model_metadata'>Metadata</Label>
            <Input
              id='model_metadata'
              value={form.model_metadata}
              onChange={(event) => set('model_metadata', event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='model_rerank'>Rerank</Label>
            <Input
              id='model_rerank'
              value={form.model_rerank}
              onChange={(event) => set('model_rerank', event.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='model_regenerate'>Regenerate</Label>
            <Input
              id='model_regenerate'
              value={form.model_regenerate}
              onChange={(event) => set('model_regenerate', event.target.value)}
            />
          </div>
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
        <Button onClick={onSubmit} disabled={pending}>
          {pending ? 'Menyimpan...' : 'Simpan'}
        </Button>
        <Button variant='outline' onClick={onTest} disabled={pending}>
          Test Connection
        </Button>
      </div>
    </div>
  );
}
