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

export type StoredWorkerLog = {
  id: string;
  worker_instance_id: string | null;
  task_id: string | null;
  instance_id: number | null;
  outcome: string;
  state: string | null;
  reason: string | null;
  gpu_name: string | null;
  created_at: string | null;
  size: number;
  log_text?: string;
};

export async function getStoredWorkerLog(logId: string): Promise<StoredWorkerLog | null> {
  try {
    return await adminFetch<StoredWorkerLog>(`/api/admin/workers/logs/${logId}`);
  } catch {
    return null;
  }
}

export async function clearWorkerLogs(): Promise<void> {
  await adminFetch('/api/admin/workers/logs/clear', { method: 'POST' });
  revalidatePath('/dashboard/workers');
}

export type WorkerLogsResult = {
  source?: string;
  text?: string;
  warning?: string;
  error?: string;
};

export async function getInstanceLogs(
  instanceId: number,
  tail = 1000,
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
