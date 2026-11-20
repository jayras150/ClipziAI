'use client';

import { useEffect, useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { loadAiModels, saveAi } from '@/app/dashboard/settings/actions';
import {
  fetchAiPrompts,
  previewAiPrompt,
  saveAiPrompt,
  testAiCapability,
  type PromptPayload
} from '@/app/dashboard/settings/ai/actions';
import type { AiConfig, AiProviderMeta } from '@/lib/clipzi';

const CAPS = [
  { id: 'metadata', label: 'Metadata', capability: 'chat', model: 'model_metadata', endpoint: 'endpoint_chat', prompts: ['metadata_system', 'metadata_user'] },
  { id: 'rerank', label: 'Rerank', capability: 'rerank', model: 'model_rerank', endpoint: 'endpoint_rerank', prompts: ['rerank_system', 'rerank_user'] },
  { id: 'regenerate', label: 'Regenerate', capability: 'regenerate', model: 'model_regenerate', endpoint: 'endpoint_chat', prompts: [] },
  { id: 'transcribe', label: 'Transkripsi', capability: 'transcribe', model: 'model_transcribe', endpoint: 'endpoint_transcribe', prompts: [] },
  { id: 'viral', label: 'Viral Score', capability: 'chat', model: 'model_viral', endpoint: 'endpoint_chat', prompts: ['viral_system', 'viral_user'] }
] as const;

type CapId = (typeof CAPS)[number]['id'] | 'umum';

/** Satu provider + satu API key, endpoint & model per kemampuan (tab di popup). */
export default function AiProviderPanel({
  config,
  providers
}: {
  config: AiConfig;
  providers: AiProviderMeta[];
}) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState(config.provider);
  const [tab, setTab] = useState<CapId>('umum');
  const [form, setForm] = useState<Record<string, unknown>>({ ...config, api_key: '' });
  const [models, setModels] = useState<string[]>([]);
  const [modelInfo, setModelInfo] = useState('');
  const [prompts, setPrompts] = useState<PromptPayload | null>(null);
  const [promptText, setPromptText] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState('');
  // Kredensial PER FITUR: Base URL + API key sendiri-sendiri.
  const [roleBaseUrls, setRoleBaseUrls] = useState<Record<string, string>>(
    (config as unknown as { role_base_urls?: Record<string, string> }).role_base_urls || {}
  );
  const [roleApiKeys, setRoleApiKeys] = useState<Record<string, string>>({});
  const [clearRoleKeys, setClearRoleKeys] = useState<string[]>([]);
  const roleStatuses =
    (config as unknown as { roles?: Array<Record<string, unknown>> }).roles || [];
  const roleStatus = (id: string) => roleStatuses.find((item) => item.role === id) || {};
  const [pending, startTransition] = useTransition();

  const set = (key: string, value: unknown) => setForm((prev) => ({ ...prev, [key]: value }));
  const active = providers.find((item) => item.id === provider);
  const caps = (config.capabilities || {}) as Record<string, { url?: string; model?: string }>;

  useEffect(() => {
    if (!open || prompts) return;
    void fetchAiPrompts().then((result) => {
      if (!result.ok) return;
      setPrompts(result.data);
      setPromptText(result.data.prompts);
    });
  }, [open, prompts]);

  const openProvider = (id: string) => {
    setProvider(id);
    setForm((prev) => ({ ...prev, provider: id }));
    setTab('umum');
    setOpen(true);
  };

  const loadModels = () => {
    setBusy('models');
    startTransition(async () => {
      const result = await loadAiModels({
        provider,
        base_url: String(form.base_url || '') || undefined
      });
      setBusy('');
      const list = (result.models || []).map((item) => item.id);
      setModels(list);
      setModelInfo(
        result.error
          ? result.error
          : result.warning || `${list.length} model tersedia${result.cached ? ' (cache)' : ''}.`
      );
      if (list.length) toast.success(`${list.length} model dimuat.`);
      else toast.error(result.error || result.warning || 'Tidak ada model.');
    });
  };

  const save = () => {
    setBusy('save');
    startTransition(async () => {
      const result = await saveAi({
        ...form,
        provider,
        role_base_urls: roleBaseUrls,
        role_api_keys: Object.fromEntries(
          Object.entries(roleApiKeys).filter(([, value]) => value.trim())
        ),
        clear_role_keys: clearRoleKeys
      });
      setBusy('');
      if (result.ok) {
        setRoleApiKeys({});
        setClearRoleKeys([]);
        toast.success('Setelan AI disimpan & diterapkan.');
      } else toast.error(result.error || 'Gagal menyimpan.');
    });
  };

  const savePrompt = (key: string) => {
    setBusy(`prompt-${key}`);
    startTransition(async () => {
      const result = await saveAiPrompt(key, promptText[key] || '');
      setBusy('');
      if (result.ok) {
        setPrompts(result.data);
        toast.success(`Prompt ${key} disimpan.`);
      } else toast.error(result.error);
    });
  };

  const previewPrompt = (key: string) => {
    setBusy(`preview-${key}`);
    startTransition(async () => {
      const result = await previewAiPrompt(key, promptText[key] || '');
      setBusy('');
      if (result.ok) setPreview(result.data.rendered);
      else toast.error(result.error);
    });
  };

  const testCap = (capability: string, role?: string) => {
    setBusy(`test-${role || capability}`);
    startTransition(async () => {
      const result = await testAiCapability(capability, role);
      setBusy('');
      if (result.ok) toast.success(`${capability}: ${result.data.output.slice(0, 80)}`);
      else toast.error(result.error);
    });
  };

  return (
    <div className='space-y-4'>
      <p className='text-muted-foreground text-sm'>
        Pilih provider, lalu atur endpoint & model per kemampuan. Setiap fitur (Metadata,
        Rerank, Regenerate, Transkripsi, Viral Score) bisa memakai Base URL dan API key
        sendiri-sendiri; kosongkan bila ingin memakai kredensial utama.
      </p>
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {providers.map((item) => (
          <button
            key={item.id}
            type='button'
            onClick={() => openProvider(item.id)}
            className="hover:border-primary flex flex-col items-start gap-1 rounded-lg border p-3 text-left"
          >
            <span className='flex w-full items-center justify-between gap-2'>
              <span className='font-medium'>{item.label}</span>
              {config.provider === item.id ? <Badge>aktif</Badge> : null}
            </span>
            <span className='text-muted-foreground text-xs'>{item.base_url || 'butuh base URL'}</span>
            <span className='text-muted-foreground text-xs'>model default: {item.default_model || '-'}</span>
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className='max-h-[88vh] w-full max-w-3xl overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>{active?.label || provider}</DialogTitle>
          </DialogHeader>

          <div className='flex flex-wrap gap-1 border-b pb-2'>
            {['umum', ...CAPS.map((item) => item.id)].map((item) => (
              <button
                key={item}
                type='button'
                onClick={() => setTab(item as CapId)}
                className={
                  tab === item
                    ? 'bg-primary text-primary-foreground rounded px-2.5 py-1 text-xs'
                    : 'hover:bg-muted rounded px-2.5 py-1 text-xs'
                }
              >
                {item === 'umum' ? 'Umum & API key' : CAPS.find((cap) => cap.id === item)?.label}
              </button>
            ))}
          </div>

          {tab === 'umum' ? (
            <div className='grid gap-3 md:grid-cols-2'>
              <div className='space-y-1'>
                <Label>API key (dipakai semua kemampuan)</Label>
                <Input
                  type='password'
                  value={String(form.api_key || '')}
                  placeholder={config.api_key_set ? `tersimpan (${config.api_key_masked})` : 'sk-...'}
                  onChange={(event) => set('api_key', event.target.value)}
                />
              </div>
              <div className='space-y-1'>
                <Label>Base URL (opsional)</Label>
                <Input
                  value={String(form.base_url || '')}
                  placeholder={active?.base_url || 'https://...'}
                  onChange={(event) => set('base_url', event.target.value)}
                />
              </div>
              {[
                ['temperature', 'Temperature'],
                ['max_tokens', 'Max tokens'],
                ['timeout_seconds', 'Timeout (detik)']
              ].map(([key, label]) => (
                <div key={key} className='space-y-1'>
                  <Label>{label}</Label>
                  <Input
                    type='number'
                    value={String(form[key] ?? '')}
                    onChange={(event) => set(key, Number(event.target.value))}
                  />
                </div>
              ))}
              <label className='flex items-center gap-2 text-sm md:col-span-2'>
                <input
                  type='checkbox'
                  checked={Boolean(form.enabled)}
                  onChange={(event) => set('enabled', event.target.checked)}
                />
                AI aktif (dipakai pipeline)
              </label>
            </div>
          ) : null}

          {CAPS.filter((cap) => cap.id === tab).map((cap) => (
            <div key={cap.id} className='space-y-4'>
              <div className='grid gap-3 md:grid-cols-2'>
                <div className='space-y-1'>
                  <Label>Endpoint {cap.label}</Label>
                  <Input
                    value={String(form[cap.endpoint] || '')}
                    placeholder={caps[cap.capability]?.url || 'kosong = ikut base URL provider'}
                    onChange={(event) => set(cap.endpoint, event.target.value)}
                  />
                </div>
                <div className='space-y-1'>
                  <Label>Model {cap.label}</Label>
                  <Input
                    list={`models-${cap.id}`}
                    value={String(form[cap.model] || '')}
                    placeholder={caps[cap.capability]?.model || 'nama model'}
                    onChange={(event) => set(cap.model, event.target.value)}
                  />
                  <datalist id={`models-${cap.id}`}>
                    {models.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </div>
              </div>
              <div className='space-y-3 rounded-md border p-3'>
                <div className='flex items-center justify-between gap-2'>
                  <p className='text-sm font-medium'>Kredensial {cap.label}</p>
                  <span className='text-muted-foreground text-[11px]'>
                    {Boolean(roleStatus(cap.id).uses_role_key)
                      ? 'API key sendiri'
                      : Boolean(roleStatus(cap.id).has_key)
                        ? 'API key utama'
                        : 'belum ada key'}
                    {Boolean(roleStatus(cap.id).uses_role_base_url)
                      ? ' · base URL sendiri'
                      : ''}
                  </span>
                </div>
                <div className='grid gap-3 md:grid-cols-2'>
                  <div className='space-y-1'>
                    <Label>Base URL khusus {cap.label}</Label>
                    <Input
                      value={roleBaseUrls[cap.id] || ''}
                      placeholder={active?.base_url || 'kosong = ikut Base URL utama'}
                      onChange={(event) =>
                        setRoleBaseUrls((prev) => ({
                          ...prev,
                          [cap.id]: event.target.value
                        }))
                      }
                    />
                  </div>
                  <div className='space-y-1'>
                    <Label>API key khusus {cap.label}</Label>
                    <Input
                      type='password'
                      value={roleApiKeys[cap.id] || ''}
                      placeholder={
                        Boolean(roleStatus(cap.id).has_key)
                          ? 'tersimpan — kosongkan bila tidak diubah'
                          : 'kosong = ikut API key utama'
                      }
                      onChange={(event) =>
                        setRoleApiKeys((prev) => ({
                          ...prev,
                          [cap.id]: event.target.value
                        }))
                      }
                    />
                  </div>
                </div>
                <p className='text-muted-foreground text-xs'>
                  Base URL & API key ini dipakai khusus untuk {cap.label}, sehingga tiap fitur
                  bisa memakai provider berbeda. Kosongkan bila ingin ikut kredensial utama.
                </p>
                {Boolean(roleStatus(cap.id).uses_role_key) ? (
                  <Button
                    variant='ghost'
                    size='sm'
                    onClick={() => {
                      setRoleApiKeys((prev) => ({ ...prev, [cap.id]: '' }));
                      setClearRoleKeys((prev) =>
                        prev.includes(cap.id) ? prev : [...prev, cap.id]
                      );
                    }}
                  >
                    {clearRoleKeys.includes(cap.id)
                      ? 'Key khusus akan dihapus saat Simpan'
                      : 'Hapus key khusus'}
                  </Button>
                ) : null}
              </div>
              <div className='flex flex-wrap gap-2'>
                <Button variant='outline' size='sm' onClick={loadModels} disabled={pending || busy !== ''}>
                  {busy === 'models' ? 'Memuat model…' : 'Muat daftar model'}
                </Button>
                <Button variant='secondary' size='sm' onClick={() => testCap(cap.capability, cap.id)} disabled={pending || busy !== ''}>
                  {busy === `test-${cap.id}` ? 'Menguji…' : 'Test kemampuan'}
                </Button>
              </div>
              {modelInfo ? <p className='text-muted-foreground text-xs'>{modelInfo}</p> : null}

              {cap.prompts.map((key) => (
                <div key={key} className='space-y-1 rounded-md border p-3'>
                  <div className='flex items-center justify-between'>
                    <Label className='font-mono text-xs'>{key}</Label>
                    <div className='flex gap-2'>
                      <Button variant='ghost' size='sm' onClick={() => previewPrompt(key)} disabled={pending}>
                        Pratinjau
                      </Button>
                      <Button size='sm' onClick={() => savePrompt(key)} disabled={pending}>
                        Simpan prompt
                      </Button>
                    </div>
                  </div>
                  <textarea
                    rows={key.endsWith('_system') ? 6 : 4}
                    value={promptText[key] || ''}
                    onChange={(event) => setPromptText((prev) => ({ ...prev, [key]: event.target.value }))}
                    className='border-input bg-background w-full rounded-md border p-2 font-mono text-xs'
                  />
                </div>
              ))}
            </div>
          ))}

          {preview ? (
            <pre className='bg-muted max-h-48 overflow-auto rounded p-2 text-xs whitespace-pre-wrap'>{preview}</pre>
          ) : null}

          <div className='flex flex-wrap gap-2 border-t pt-3'>
            <Button onClick={save} disabled={pending || busy !== ''}>
              {busy === 'save' ? 'Menyimpan…' : 'Simpan setelan'}
            </Button>
            <Button variant='ghost' onClick={() => setOpen(false)}>
              Tutup
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
