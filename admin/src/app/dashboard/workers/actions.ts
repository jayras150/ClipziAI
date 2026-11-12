"use server";

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export async function destroyInstance(formData: FormData) {
  const instanceId = String(formData.get('instance_id') || '');
  if (instanceId) {
    await adminFetch(`/api/admin/workers/instances/${instanceId}/destroy`, {
      method: 'POST'
    });
    revalidatePath('/dashboard/workers');
  }
}
