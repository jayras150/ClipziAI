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

export type WorkerLogsResult = {
  source?: string;
  text?: string;
  warning?: string;
  error?: string;
};

export async function getInstanceLogs(
  instanceId: number,
  tail = 300,
  daemon = false
): Promise<WorkerLogsResult> {
  try {
    return await adminFetch<WorkerLogsResult>(
      `/api/admin/workers/instances/${instanceId}/logs?tail=${tail}&daemon=${
        daemon ? 'true' : 'false'
      }`
    );
  } catch (error) {
    return {
      error: error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat log.'
    };
  }
}
