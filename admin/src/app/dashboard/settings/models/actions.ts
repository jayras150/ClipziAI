'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

function _error(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Permintaan ke server gagal. Coba lagi.';
}

export async function scanWhisperModels() {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/whisper-models/scan',
      { method: 'POST' }
    );
    revalidatePath('/dashboard/settings/models');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function activateWhisperModel(id: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      `/api/admin/whisper-models/${encodeURIComponent(id)}/activate`,
      { method: 'POST' }
    );
    revalidatePath('/dashboard/settings/models');
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function deleteWhisperModel(id: string, deleteDrive: boolean) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      `/api/admin/whisper-models/${encodeURIComponent(id)}?delete_drive=${
        deleteDrive ? 'true' : 'false'
      }`,
      { method: 'DELETE' }
    );
    revalidatePath('/dashboard/settings/models');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function saveWhisperColabNotebook(notebookFileId: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/whisper-models/colab',
      {
        method: 'PUT',
        body: JSON.stringify({ notebook_file_id: notebookFileId })
      }
    );
    revalidatePath('/dashboard/settings/models');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function downloadWhisperColabNotebook() {
  try {
    const data = await adminFetch<{ filename: string; content: string }>(
      '/api/admin/whisper-models/colab/notebook'
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function downloadWhisperNotebook(provider: string) {
  try {
    const data = await adminFetch<{ filename: string; content: string; provider: string }>(
      `/api/admin/whisper-models/colab/notebook?provider=${encodeURIComponent(provider)}`
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function fetchWhisperSource() {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/whisper-models/source');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function saveWhisperSource(payload: {
  provider: string;
  values: Record<string, string>;
  auto_template?: boolean;
  activate?: boolean;
}) {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/whisper-models/source', {
      method: 'PUT',
      body: JSON.stringify({
        auto_template: true,
        activate: true,
        ...payload
      })
    });
    revalidatePath('/dashboard/settings/models');
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function testWhisperSource(payload: {
  provider: string;
  values: Record<string, string>;
}) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/whisper-models/source/test',
      { method: 'POST', body: JSON.stringify(payload) }
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function syncWhisperTemplate(provider: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/whisper-models/source/template',
      { method: 'POST', body: JSON.stringify({ provider, activate: true }) }
    );
    revalidatePath('/dashboard/settings/models');
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

