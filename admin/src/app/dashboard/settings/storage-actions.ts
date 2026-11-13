"use server";

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export type StorageProvider = {
  id: string;
  label: string;
  endpoint: string;
  region: string;
  path_style: boolean;
  hint: string;
};

export type StorageItem = {
  id: string;
  name: string;
  provider: string;
  bucket: string;
  endpoint: string;
  region: string;
  path_style: boolean;
  public_domain: string;
  path_prefix: string;
  enabled: boolean;
  access_key_masked?: string | null;
  has_credentials?: boolean;
  last_check?: { ok?: boolean; latency_ms?: number; error?: string | null; at?: string } | null;
};

export type StorageConfigView = {
  primary_id: string | null;
  mirror_ids: string[];
  items: StorageItem[];
  providers: StorageProvider[];
};

export async function fetchStorage(): Promise<StorageConfigView> {
  return adminFetch<StorageConfigView>('/api/admin/settings/storage');
}

export async function saveStorage(payload: Record<string, unknown>): Promise<StorageConfigView> {
  const data = await adminFetch<StorageConfigView>('/api/admin/settings/storage', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  revalidatePath('/dashboard/settings/storage');
  return data;
}

export async function deleteStorage(id: string): Promise<StorageConfigView> {
  const data = await adminFetch<StorageConfigView>(`/api/admin/settings/storage/${id}`, {
    method: 'DELETE'
  });
  revalidatePath('/dashboard/settings/storage');
  return data;
}

export async function testStorage(
  id: string
): Promise<{ result: { ok: boolean; latency_ms?: number; error?: string | null }; storage: StorageConfigView }> {
  return adminFetch(`/api/admin/settings/storage/${id}/test`, { method: 'POST' });
}

export async function setPrimaryStorage(id: string): Promise<StorageConfigView> {
  const data = await adminFetch<StorageConfigView>('/api/admin/settings/storage/primary', {
    method: 'PUT',
    body: JSON.stringify({ id })
  });
  revalidatePath('/dashboard/settings/storage');
  return data;
}

export async function setMirrorStorages(ids: string[]): Promise<StorageConfigView> {
  const data = await adminFetch<StorageConfigView>('/api/admin/settings/storage/mirrors', {
    method: 'PUT',
    body: JSON.stringify({ ids })
  });
  revalidatePath('/dashboard/settings/storage');
  return data;
}

export async function syncStorage(): Promise<{ ok: boolean; copied?: number; skipped?: number; failed?: number; error?: string }> {
  return adminFetch('/api/admin/settings/storage/sync?limit=200', { method: 'POST' });
}
