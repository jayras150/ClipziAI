'use server';

import { adminFetch } from '@/lib/clipzi';

export type AuditDetail = {
  id?: string;
  action?: string;
  actor_email?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  created_at?: string | null;
  old_values?: unknown;
  new_values?: unknown;
  metadata?: unknown;
  user_agent?: string | null;
  ip_address?: string | null;
  related_error?: string;
  log_text?: string;
};

export async function fetchAuditDetail(id: string): Promise<AuditDetail> {
  try {
    return await adminFetch<AuditDetail>(`/api/admin/audit/detail/${id}`);
  } catch (error) {
    return {
      id,
      related_error:
        error instanceof Error ? error.message.replace(/^\d{3}\s+/, '') : 'Gagal memuat detail.'
    };
  }
}
