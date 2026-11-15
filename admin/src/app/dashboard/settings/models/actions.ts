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
    return { error: _error(error) };
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
    return { error: _error(error) };
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
    return { error: _error(error) };
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
    return { error: _error(error) };
  }
}

export async function downloadWhisperColabNotebook() {
  try {
    const data = await adminFetch<{ filename: string; content: string }>(
      '/api/admin/whisper-models/colab/notebook'
    );
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}

