"use server";

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export type ProxyItem = {
  url: string;
  label?: string | null;
  scheme?: string;
  status?: string;
  latency_ms?: number | null;
  exit_ip?: string | null;
  last_checked?: string | null;
  error?: string | null;
  has_credentials?: boolean;
};

export type ProxyPoolView = {
  enabled: boolean;
  auto_use: boolean;
  rotation: string;
  filter: Record<string, unknown>;
  updated_at: string | null;
  items: ProxyItem[];
  active_count: number;
  active_txt_lines: number;
  active_txt_bytes: number;
};

export type ParseResult = {
  items: { url: string; label?: string | null; scheme?: string }[];
  errors: { line: number; value: string; reason: string }[];
  total: number;
  valid: number;
  duplicate: number;
  preview?: string[];
  files?: { name: string | null; valid?: number; duplicate?: number; errors?: number; error?: string }[];
};

export type FilterStatus = {
  status: 'idle' | 'running' | 'done';
  total: number;
  tested: number;
  active: number;
  dead: number;
  started_at: string | null;
  finished_at: string | null;
  target?: string;
  error?: string | null;
};

/** Preview normalisasi dari teks (tanpa menyimpan). */
export async function parseProxyText(text: string): Promise<ParseResult> {
  return adminFetch<ParseResult>('/api/admin/settings/proxies/parse', {
    method: 'POST',
    body: JSON.stringify({ text })
  });
}

/** Upload BANYAK file .txt proxy -> digabung & dinormalkan (preview). */
export async function uploadProxyFiles(formData: FormData): Promise<ParseResult> {
  const { API_URL, getToken } = await import('@/lib/clipzi');
  const token = await getToken();
  const response = await fetch(`${API_URL}/api/admin/settings/proxies/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${(await response.text()).slice(0, 200)}`);
  }
  return (await response.json()) as ParseResult;
}

/** Simpan daftar proxy (tanpa uji). */
export async function saveProxies(items: ProxyItem[]): Promise<ProxyPoolView> {
  const pool = await adminFetch<ProxyPoolView>('/api/admin/settings/proxies', {
    method: 'PUT',
    body: JSON.stringify({ items })
  });
  revalidatePath('/dashboard/settings/youtube');
  return pool;
}

/** START FILTER ACTIVE PROXY (job background). */
export async function startProxyFilter(params: {
  text?: string;
  items?: ProxyItem[];
  timeout_s?: number;
  concurrency?: number;
  check_youtube?: boolean;
}): Promise<{ started: boolean; total?: number; message?: string }> {
  const result = await adminFetch<{ started: boolean; total?: number; message?: string }>(
    '/api/admin/settings/proxies/filter',
    { method: 'POST', body: JSON.stringify(params) }
  );
  revalidatePath('/dashboard/settings/youtube');
  return result;
}

export async function proxyFilterStatus(): Promise<FilterStatus> {
  return adminFetch<FilterStatus>('/api/admin/settings/proxies/filter/status');
}

export async function fetchProxyPool(): Promise<ProxyPoolView> {
  return adminFetch<ProxyPoolView>('/api/admin/settings/proxies');
}

export async function clearProxies(): Promise<ProxyPoolView> {
  const pool = await adminFetch<ProxyPoolView>('/api/admin/settings/proxies', { method: 'DELETE' });
  revalidatePath('/dashboard/settings/youtube');
  return pool;
}

export async function toggleProxies(payload: {
  enabled?: boolean;
  auto_use?: boolean;
}): Promise<ProxyPoolView> {
  const pool = await adminFetch<ProxyPoolView>('/api/admin/settings/proxies/toggle', {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
  revalidatePath('/dashboard/settings/youtube');
  return pool;
}
