'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

export type NotificationLogPayload = {
  key?: string;
  kind?: string;
  title?: string;
  severity?: string;
  created_at?: string;
  detail?: string;
  log_text?: string;
  related?: Record<string, unknown>;
};

/** Ambil detail + log lengkap satu notifikasi (tombol "Cek Log"). */
export async function fetchNotificationLog(key: string): Promise<NotificationLogPayload> {
  try {
    return await adminFetch<NotificationLogPayload>(
      `/api/admin/notifications/log?key=${encodeURIComponent(key)}`
    );
  } catch (error) {
    return {
      key,
      detail: error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat log.'
    };
  }
}

export async function markAllNotificationsRead(): Promise<void> {
  try {
    await adminFetch('/api/admin/notifications/read-all', { method: 'POST' });
  } catch {
    /* diamkan: lonceng akan memuat ulang sendiri */
  }
  revalidatePath('/dashboard/notifications');
}
