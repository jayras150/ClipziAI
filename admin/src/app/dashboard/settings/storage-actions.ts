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
  last_check?: { ok?: boolean; latency_ms?: number; error?: string | null; hint?: string | null; at?: string } | null;
};

export type StorageConfigView = {
  primary_id: string | null;
  mirror_ids: string[];
  items: StorageItem[];
  providers: StorageProvider[];
  warnings?: string[];
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
): Promise<{
  result: { ok: boolean; latency_ms?: number; error?: string | null; hint?: string | null; note?: string | null };
  storage: StorageConfigView;
}> {
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

export type SyncMirrorRow = {
  id: string;
  name: string | null;
  provider: string;
  bucket: string;
  listed: number;
  copied: number;
  skipped: number;
  failed: number;
  bytes: number;
  error: string | null;
};

export type SyncJobStatus = {
  state: 'idle' | 'running' | 'done' | 'cancelled' | 'error';
  mode: 'push' | 'reconcile' | 'heal';
  started_at: string | null;
  finished_at: string | null;
  per_mirror: SyncMirrorRow[];
  total: number;
  done: number;
  copied: number;
  skipped: number;
  failed: number;
  bytes: number;
  current: string;
  error: string | null;
};

export type DomainCheck = {
  domain: string;
  cname_target?: string | null;
  resolved: string[];
  dns_ok: boolean;
  http_status: number | null;
  cert_ok: boolean;
  reachable: boolean;
  hint?: string | null;
  at?: string;
};

/** Mulai sync di background (job) — respons langsung, progres lewat status. */
export async function startStorageSync(
  mode: 'push' | 'reconcile' | 'heal' = 'push',
  limit = 50,
  maxSizeMb = 500
): Promise<{ started: boolean; message?: string; mode?: string }> {
  return adminFetch('/api/admin/settings/storage/sync', {
    method: 'POST',
    body: JSON.stringify({ mode, limit, max_size_mb: maxSizeMb })
  });
}

export async function storageSyncStatus(): Promise<SyncJobStatus> {
  return adminFetch<SyncJobStatus>('/api/admin/settings/storage/sync/status');
}

export async function cancelStorageSync(): Promise<{ cancelled: boolean; message?: string }> {
  return adminFetch('/api/admin/settings/storage/sync/cancel', { method: 'POST' });
}

/** Cari satu objek di semua provider (primary + mirror). */
export async function locateStorageObject(key: string): Promise<{
  key: string;
  found: number;
  locations: {
    id: string;
    name: string | null;
    provider: string;
    bucket: string;
    object_key: string;
    exists: boolean;
    size: number | null;
    url: string | null;
    error?: string;
  }[];
}> {
  return adminFetch(`/api/admin/settings/storage/locate?key=${encodeURIComponent(key)}`);
}

export async function setCustomDomain(id: string, domain: string): Promise<{
  storage: StorageConfigView;
  result: DomainCheck;
}> {
  const data = await adminFetch<{ storage: StorageConfigView; result: DomainCheck }>(
    `/api/admin/settings/storage/${id}/custom-domain`,
    { method: 'POST', body: JSON.stringify({ domain }) }
  );
  revalidatePath('/dashboard/settings/storage');
  return data;
}

export async function checkStorageDomain(domain: string, itemId?: string): Promise<DomainCheck> {
  const data = await adminFetch<{ result: DomainCheck; storage_id: string }>(
    '/api/admin/settings/storage/domain-check',
    { method: 'POST', body: JSON.stringify({ domain, item_id: itemId || null }) }
  );
  return data.result;
}

