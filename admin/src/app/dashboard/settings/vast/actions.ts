'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

/** Server actions panel Vast.ai (config, env, billing, test). */

function _error(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Permintaan ke server gagal. Coba lagi.';
}

export async function saveVastConfig(payload: Record<string, unknown>) {
  try {
    const data = await adminFetch<Record<string, unknown>>('/api/admin/settings/vast', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, config: data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function resetVastConfig() {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/settings/vast/reset',
      { method: 'POST' }
    );
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, config: data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function testVastConnection() {
  try {
    return await adminFetch<Record<string, unknown>>('/api/admin/settings/vast/test', {
      method: 'POST'
    });
  } catch (error) {
    return { ok: false, error: _error(error) };
  }
}

export async function loadVastConnections() {
  try {
    return await adminFetch<{
      connections: Array<{ id: string; name: string }>;
      configured: string;
      valid: boolean;
      selected: string | null;
      error: string | null;
    }>('/api/admin/settings/vast/connections');
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function autoVastConnection() {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/settings/vast/connections/auto',
      { method: 'POST' }
    );
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function testVastOffers(limit = 5) {
  try {
    return await adminFetch<Record<string, unknown>>(
      `/api/admin/settings/vast/offers?limit=${limit}`,
      { method: 'POST' }
    );
  } catch (error) {
    return { error: _error(error) };
  }
}

/** Status template worker (hash aktif, image, env yang akan dibekukan). */
export type VastTemplateStatus = {
  template_hash: string;
  template_name: string;
  worker_image: string;
  worker_disk: number;
  onstart: string;
  docker_options: string;
  env_keys: string[];
  env_count: number;
  missing_required: string[];
  api_key_set: boolean;
  ready: boolean;
  /** Deteksi template basi (env berubah setelah sync terakhir). */
  fingerprint?: string;
  stored_fingerprint?: string;
  drift?: boolean;
  env_count_current?: number;
  last_synced_at?: string | null;
  active_provider?: string | null;
  template_image?: string | null;
  template_disk?: number | null;
  env_limit?: number;
  env_len?: number;
  env_skipped?: string[];
};

export async function loadVastTemplateStatus() {
  try {
    return await adminFetch<VastTemplateStatus>('/api/admin/settings/vast/template');
  } catch (error) {
    return { error: _error(error) };
  }
}

/** Buat template Vast.ai dari image worker + env pipeline, lalu aktifkan. */
export async function createVastTemplate(payload: {
  name?: string;
  image?: string;
  disk_space?: number;
  include_env?: boolean;
  sync_env_vars?: boolean;
  public?: boolean;
  activate?: boolean;
}) {
  try {
    const data = await adminFetch<{
      ok: boolean;
      template_hash: string;
      template_id: number | null;
      name: string;
      image: string;
      disk_space: number;
      env_count: number;
      env_keys: string[];
      env_sync: Record<string, unknown>;
      warnings: string[];
      activated: boolean;
    }>('/api/admin/settings/vast/template/create', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    revalidatePath('/dashboard/settings/vast');
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function exportVastEnv(reveal: boolean) {
  try {
    return await adminFetch<{ text: string; reveal: boolean }>(
      `/api/admin/settings/vast/env/text?reveal=${reveal ? 'true' : 'false'}`
    );
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function syncVastEnv(keys: string[] | null, dryRun: boolean) {
  try {
    return await adminFetch<Record<string, unknown>>(
      '/api/admin/settings/vast/env/sync',
      {
        method: 'POST',
        body: JSON.stringify({ keys, dry_run: dryRun })
      }
    );
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function loadVastBilling(params: {
  start?: string;
  end?: string;
  type?: string;
}) {
  const query = new URLSearchParams();
  if (params.start) query.set('start_date', params.start);
  if (params.end) query.set('end_date', params.end);
  if (params.type) query.set('invoice_type', params.type);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  try {
    return await adminFetch<Record<string, unknown>>(
      `/api/admin/settings/vast/billing${suffix}`
    );
  } catch (error) {
    return { ok: false, error: _error(error) };
  }
}


export type TemplateSyncResult = {
  ok?: boolean;
  adopted?: boolean;
  template_hash?: string;
  name?: string;
  image?: string;
  disk_space?: number;
  env_count?: number;
  env_keys?: string[];
  env_skipped?: string[];
  env_len?: number;
  warnings?: string[];
  activated?: boolean;
  fingerprint?: string;
  error?: string;
};

/** Buat/update SATU template worker lalu aktifkan untuk dispatch. */
export async function syncVastTemplate(payload: {
  name?: string;
  image?: string;
  disk_space?: number;
  activate?: boolean;
  adopt_hash?: string;
}) {
  try {
    const data = await adminFetch<TemplateSyncResult>(
      '/api/admin/settings/vast/template/sync',
      { method: 'POST', body: JSON.stringify(payload) }
    );
    revalidatePath('/dashboard/settings/instance');
    revalidatePath('/dashboard/settings/vast');
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}
