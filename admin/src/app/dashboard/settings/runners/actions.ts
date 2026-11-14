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
