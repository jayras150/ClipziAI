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
