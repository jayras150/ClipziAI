'use server';

import { adminFetch } from '@/lib/clipzi';

export type AdminNotification = {
  key: string;
  severity: 'error' | 'warning' | 'info' | string;
  title: string;
  body: string;
  href: string;
  created_at: string;
  kind: string;
  read: boolean;
};

export type NotificationsPayload = {
  items: AdminNotification[];
  unread_count: number;
  generated_at: string;
};

function _error(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Gagal memuat notifikasi.';
}

export async function fetchAdminNotifications() {
  try {
    const data = await adminFetch<NotificationsPayload>('/api/admin/notifications');
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function markAdminNotificationsRead(keys: string[]) {
  try {
    const data = await adminFetch<{ ok: boolean; read: number }>(
      '/api/admin/notifications/read',
      { method: 'POST', body: JSON.stringify({ keys }) }
    );
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}

export async function markAllAdminNotificationsRead() {
  try {
    const data = await adminFetch<{ ok: boolean; read: number }>(
      '/api/admin/notifications/read-all',
      { method: 'POST' }
    );
    return { ok: true as const, data };
  } catch (error) {
    return { ok: false as const, error: _error(error) };
  }
}
