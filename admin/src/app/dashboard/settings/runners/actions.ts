'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

/** Server actions untuk runner downloader (GitHub Actions fallback). */

export async function createRunner(formData: FormData) {
  const payload = {
    name: String(formData.get('name') || '').trim(),
    owner: String(formData.get('owner') || '').trim(),
    repo: String(formData.get('repo') || '').trim(),
    workflow_file: String(formData.get('workflow_file') || 'downloader_video.yml').trim(),
    git_ref: String(formData.get('git_ref') || 'main').trim(),
    auth_mode: 'pat',
    weight: Number(formData.get('weight') || 100),
    enabled: true,
    token: String(formData.get('token') || '').trim() || undefined
  };
  if (!payload.name || !payload.owner || !payload.repo) return;
  await adminFetch('/api/admin/settings/runners/', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  revalidatePath('/dashboard/settings/runners');
}

export async function toggleRunner(formData: FormData) {
  const id = String(formData.get('id') || '');
  const enabled = String(formData.get('enabled') || '') === '1';
  if (!id) return;
  await adminFetch(`/api/admin/settings/runners/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled })
  });
  revalidatePath('/dashboard/settings/runners');
}

export async function testRunner(formData: FormData) {
  const id = String(formData.get('id') || '');
  if (!id) return;
  await adminFetch(`/api/admin/settings/runners/${id}/test`, { method: 'POST' });
  revalidatePath('/dashboard/settings/runners');
}

export async function deleteRunner(formData: FormData) {
  const id = String(formData.get('id') || '');
  if (!id) return;
  await adminFetch(`/api/admin/settings/runners/${id}`, { method: 'DELETE' });
  revalidatePath('/dashboard/settings/runners');
}

/** Status workflow di repo runner (preflight). */
export type WorkflowResult = {
  ok?: boolean;
  repo?: string;
  path?: string;
  ref?: string;
  default_branch?: string | null;
  repo_empty?: boolean;
  exists?: boolean;
  up_to_date?: boolean;
  sha?: string | null;
  size?: number | null;
  commit_url?: string | null;
  actions_enabled?: boolean | null;
  workflow_registered?: boolean | null;
  error?: string | null;
  action?: string;
  message?: string;
  branch?: string;
};

function _errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    // adminFetch membentuk "502 detail"; buang kode status agar pesan rapi.
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Permintaan ke GitHub gagal. Coba lagi.';
}

export async function checkRunnerWorkflow(id: string): Promise<WorkflowResult> {
  if (!id) return { error: 'Runner tidak valid.' };
  try {
    const data = await adminFetch<WorkflowResult>(
      `/api/admin/settings/runners/${id}/workflow`
    );
    return data;
  } catch (error) {
    return { error: _errorMessage(error) };
  }
}

export async function installRunnerWorkflow(
  id: string,
  force: boolean
): Promise<WorkflowResult> {
  if (!id) return { error: 'Runner tidak valid.' };
  try {
    const data = await adminFetch<WorkflowResult>(
      `/api/admin/settings/runners/${id}/workflow`,
      { method: 'POST', body: JSON.stringify({ force }) }
    );
    revalidatePath('/dashboard/settings/runners');
    return data;
  } catch (error) {
    return { error: _errorMessage(error) };
  }
}
