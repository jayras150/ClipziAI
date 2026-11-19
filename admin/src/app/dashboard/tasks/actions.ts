'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch, ApiError } from '@/lib/clipzi';

export type TaskActionResult = {
  ok: boolean;
  status?: string | null;
  message: string;
};

export async function cancelTask(formData: FormData): Promise<TaskActionResult> {
  const tid = String(formData.get('tid') || '');
  if (!tid) return { ok: false, message: 'ID task tidak valid.' };
  try {
    const result = await adminFetch<{
      message: string;
      status: string;
      instances_destroyed?: number;
      destroy_errors?: string[];
    }>(`/api/admin/tasks/${tid}/cancel`, { method: 'POST' });
    revalidatePath('/dashboard/tasks');
    revalidatePath(`/dashboard/tasks/${tid}`);
    return {
      ok: true,
      status: result.status,
      message: result.message || `Task ${tid} dibatalkan`
    };
  } catch (error) {
    const detail =
      error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Gagal membatalkan task.';
    // 400 berarti task sudah terminal (completed/error/cancelled) — bukan kegagalan sistem.
    return { ok: false, message: detail };
  }
}

export async function retryTask(formData: FormData): Promise<TaskActionResult> {
  const tid = String(formData.get('tid') || '');
  if (!tid) return { ok: false, message: 'ID task tidak valid.' };
  try {
    const result = await adminFetch<{ message: string; status: string }>(
      `/api/admin/tasks/${tid}/retry`,
      { method: 'POST' }
    );
    revalidatePath('/dashboard/tasks');
    revalidatePath(`/dashboard/tasks/${tid}`);
    return { ok: true, status: result.status, message: result.message || `Task ${tid} diulang` };
  } catch (error) {
    const detail =
      error instanceof ApiError
        ? error.detail || `HTTP ${error.status}`
        : error instanceof Error
          ? error.message
          : 'Gagal mengulang task.';
    return { ok: false, message: detail };
  }
}
