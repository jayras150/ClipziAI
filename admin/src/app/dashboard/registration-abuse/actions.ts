'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

function _error(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Permintaan ke server gagal. Coba lagi.';
}

export async function saveDeviceReputationSettings(payload: {
  enforce_device_claim: boolean;
  signup_bonus: number;
}) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      '/api/admin/registration-abuse/settings',
      { method: 'PUT', body: JSON.stringify(payload) }
    );
    revalidatePath('/dashboard/registration-abuse');
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function trustDevice(deviceId: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      `/api/admin/registration-abuse/${encodeURIComponent(deviceId)}/trust`,
      { method: 'POST' }
    );
    revalidatePath('/dashboard/registration-abuse');
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}

export async function resetDeviceClaim(deviceId: string) {
  try {
    const data = await adminFetch<Record<string, unknown>>(
      `/api/admin/registration-abuse/${encodeURIComponent(deviceId)}/reset-claim`,
      { method: 'POST' }
    );
    revalidatePath('/dashboard/registration-abuse');
    return { ok: true, data };
  } catch (error) {
    return { error: _error(error) };
  }
}
