'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { saveAiEndpoints } from '@/app/dashboard/settings/ai/actions';

type Row = {
  id: string;
  label: string;
  provider: string;
  base_url: string;
  model_metadata: string;
  model_rerank: string;
  model_regenerate: string;
  weight: number;
  enabled: boolean;
  api_key_set?: boolean;
  api_key_masked?: string;
};

type Option = { id: string; label: string };

const TEXT_FIELDS: Array<{
  key: 'label' | 'base_url' | 'model_metadata' | 'model_rerank' | 'model_regenerate';
  label: string;
  placeholder?: string;
}> = [
  { key: 'label', label: 'Label' },
  { key: 'base_url', label: 'Base URL', placeholder: 'kosong = default provider' },
  { key: 'model_metadata', label: 'Model metadata', placeholder: 'openai/gpt-4o-mini' },
  { key: 'model_rerank', label: 'Model rerank', placeholder: 'openai/gpt-4o-mini' },
  { key: 'model_regenerate', label: 'Model regenerate' }
];

/** Multi-endpoint AI: endpoint (provider + key + model) dan rute per fitur. */
export default function AiEndpoints({
  endpoints,
  active,
  providers
}: {
  endpoints: Array<Partial<Row> & { id: string }>;
  active: Record<string, string>;
  providers: Option[];
}) {
  const [rows, setRows] = useState<Row[]>(
    endpoints.map((item) => ({
      id: item.id,
      label: item.label || item.id,
      provider: item.provider || 'openrouter',
      base_url: item.base_url || '',
      model_metadata: item.model_metadata || '',
      model_rerank: item.model_rerank || '',
      model_regenerate: item.model_regenerate || '',
      weight: Number(item.weight || 100),
      enabled: item.enabled !== false,
      api_key_set: item.api_key_set,
      api_key_masked: item.api_key_masked
    }))
  );
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [routes, setRoutes] = useState<Record<string, string>>({
    metadata: active.metadata || '',
    rerank: active.rerank || '',
    regenerate: active.regenerate || ''
  });
  const [saving, setSaving] = useState(false);

  const setRow = (index: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const addRow = () =>
    setRows((prev) => [
      ...prev,
      {
        id: `ep-${Date.now().toString(36)}`,
        label: `Endpoint ${prev.length + 1}`,
        provider: 'openrouter',
        base_url: '',
        model_metadata: '',
        model_rerank: '',
        model_regenerate: '',
        weight: 100,
        enabled: true
      }
    ]);

  const save = () => {
    setSaving(true);
    void saveAiEndpoints({
      endpoints: rows.map((row) => ({ ...row, api_key: keys[row.id] || '' })),
      endpoint_routes: routes
    }).then((result) => {
      setSaving(false);
      if (result.ok) {
        setKeys({});
        toast.success('Endpoint AI disimpan.');
      } else toast.error(result.error);
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Multi-Endpoint AI</CardTitle>
        <CardDescription>
          Daftarkan beberapa endpoint (provider + API key + model) lalu pilih endpoint untuk
          metadata, rerank, atau regenerate. Rerank bisa diarahkan ke OpenRouter terpisah.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='grid gap-3 md:grid-cols-3'>
          {(['metadata', 'rerank', 'regenerate'] as const).map((feature) => (
            <div key={feature}>
              <Label>Endpoint {feature}</Label>
              <select
                className='border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm'
                value={routes[feature] || ''}
                onChange={(event) =>
                  setRoutes((prev) => ({ ...prev, [feature]: event.target.value }))
                }
              >
                <option value=''>Otomatis (bobot tertinggi)</option>
                {rows.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label || row.id}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>

        {rows.map((row, index) => (
          <div key={row.id} className='space-y-2 rounded-md border p-3'>
            <div className='grid gap-2 md:grid-cols-3'>
              {TEXT_FIELDS.map((field) => (
                <div key={field.key}>
                  <Label>{field.label}</Label>
                  <Input
                    value={row[field.key]}
                    placeholder={field.placeholder}
                    onChange={(event) => setRow(index, { [field.key]: event.target.value })}
                  />
                </div>
              ))}
              <div>
                <Label>Provider</Label>
                <select
                  className='border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm'
                  value={row.provider}
                  onChange={(event) => setRow(index, { provider: event.target.value })}
                >
                  {providers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label>API key {row.api_key_set ? `(${row.api_key_masked})` : ''}</Label>
                <Input
                  type='password'
                  value={keys[row.id] || ''}
                  placeholder={row.api_key_set ? 'kosong = tidak diubah' : 'sk-...'}
                  onChange={(event) =>
                    setKeys((prev) => ({ ...prev, [row.id]: event.target.value }))
                  }
                />
              </div>
              <div>
                <Label>Bobot</Label>
                <Input
                  type='number'
                  min={1}
                  value={row.weight}
                  onChange={(event) => setRow(index, { weight: Number(event.target.value) })}
                />
              </div>
              <div className='flex items-end gap-2'>
                <label className='flex items-center gap-2 text-sm'>
                  <input
                    type='checkbox'
                    checked={row.enabled}
                    onChange={(event) => setRow(index, { enabled: event.target.checked })}
                  />
                  Aktif
                </label>
                <Button
                  variant='ghost'
                  size='sm'
                  onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                >
                  Hapus
                </Button>
              </div>
            </div>
          </div>
        ))}

        <div className='flex flex-wrap gap-2'>
          <Button variant='outline' onClick={addRow}>
            + Tambah endpoint
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? 'Menyimpan…' : 'Simpan endpoint'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

