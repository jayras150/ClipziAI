'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

/** Server actions untuk registry prompt AI + multi-endpoint. */

export type PromptMeta = {
  key: string;
  label?: string;
  group?: string;
  features?: string[];
  variables?: string[];
  is_custom?: boolean;
};

export type PromptPayload = {
  prompts: Record<string, string>;
  overrides: Record<string, string>;
  defaults: Record<string, string>;
  meta: PromptMeta[];
  variables: Record<string, string[]>;
  sample_context: Record<string, Record<string, string>>;
  history?: Array<{ key: string; at: string; by?: string; action?: string; chars?: number }>;
};

function _error(error: unknown): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: string }).message;
    if (message) return message;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Request gagal. Coba lagi.';
}

export async function fetchAiPrompts(): Promise<
  { ok: true; data: PromptPayload } | { ok: false; error: string }
> {
  try {
    const data = await adminFetch<PromptPayload>('/api/admin/settings/ai/prompts');
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: _error(error) };
  }
}

export async function saveAiPrompt(key: string, text: string) {
  try {
    const data = await adminFetch<PromptPayload>('/api/admin/settings/ai/prompts', {
      method: 'PUT',
      body: JSON.stringify({ key, text })
    });
    revalidatePath('/dashboard/settings/ai');
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function resetAiPrompt(key: string) {
  try {
    const data = await adminFetch<PromptPayload>(
      `/api/admin/settings/ai/prompts/${key}/reset`,
      { method: 'POST' }
    );
    revalidatePath('/dashboard/settings/ai');
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function previewAiPrompt(key: string, text: string) {
  try {
    const data = await adminFetch<{ rendered: string; is_default: boolean }>(
      `/api/admin/settings/ai/prompts/${key}/preview`,
      { method: 'POST', body: JSON.stringify({ key, text }) }
    );
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function testAiPrompt(key: string, text: string) {
  try {
    const data = await adminFetch<{ output: string; elapsed: number; log_text: string }>(
      `/api/admin/settings/ai/prompts/${key}/test`,
      { method: 'POST', body: JSON.stringify({ key, text }) }
    );
    return { ok: true as const, data };
  } catch (error) {
    const detail = (error as { detail?: { log_text?: string } })?.detail;
    return { ok: false as const, error: _error(error), log_text: detail?.log_text || '' };
  }
}

export async function saveAiEndpoints(payload: {
  endpoints: Array<Record<string, unknown>>;
  endpoint_routes: Record<string, string>;
}) {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/settings/ai', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    revalidatePath('/dashboard/settings/ai');
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}


export async function testAiCapability(capability: string) {
  try {
    const data = await adminFetch<{
      ok: boolean;
      capability: string;
      endpoint: string;
      model: string;
      elapsed: number;
      output: string;
      log_text: string;
    }>(`/api/admin/settings/ai/test?capability=${encodeURIComponent(capability)}`, {
      method: 'POST'
    });
    return { ok: true as const, data };
  } catch (error) {
    const detail = (error as { detail?: unknown })?.detail;
    const log = typeof detail === 'object' ? (detail as { log_text?: string }).log_text || '' : '';
    return { ok: false as const, error: _error(error), log_text: log };
  }
}
