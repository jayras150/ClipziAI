"use server";

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export type SaveResult = { ok: boolean; error?: string; injected?: string[] };

export async function saveAi(payload: Record<string, unknown>): Promise<SaveResult> {
  try {
    const data = await adminFetch<{ injected?: string[] }>('/api/admin/settings/ai', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    revalidatePath('/dashboard/settings/ai');
    return { ok: true, injected: data.injected };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}

export type TestResult = {
  ok: boolean;
  provider?: string;
  model?: string;
  latency_ms?: number;
  sample?: string;
  finish_reason?: string;
  error?: string;
};

export async function testAi(): Promise<TestResult> {
  try {
    return await adminFetch<TestResult>('/api/admin/settings/ai/test', { method: 'POST' });
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}

export async function saveBranding(payload: Record<string, unknown>): Promise<SaveResult> {
  try {
    await adminFetch('/api/admin/settings/branding', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    revalidatePath('/dashboard/settings/branding');
    return { ok: true };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}

export async function uploadBrandingAsset(formData: FormData): Promise<SaveResult> {
  const kind = String(formData.get('kind') || 'logo');
  const file = formData.get('file');
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: 'Pilih file terlebih dahulu.' };
  }
  const body = new FormData();
  body.set('file', file);
  try {
    const token = await (await import('@/lib/clipzi')).getToken();
    const { API_URL } = await import('@/lib/clipzi');
    const response = await fetch(
      `${API_URL}/api/admin/settings/branding/upload?kind=${encodeURIComponent(kind)}`,
      { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body }
    );
    if (!response.ok) {
      return { ok: false, error: `${response.status} ${(await response.text()).slice(0, 200)}` };
    }
    revalidatePath('/dashboard/settings/branding');
    return { ok: true };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
}
