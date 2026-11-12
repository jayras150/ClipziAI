'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

/** Simpan setelan ekosistem (domain publik/admin, dukungan, maintenance). */
export async function savePlatform(formData: FormData) {
  const payload: Record<string, unknown> = {
    site_url: String(formData.get('site_url') || ''),
    admin_url: String(formData.get('admin_url') || ''),
    support_email: String(formData.get('support_email') || ''),
    timezone: String(formData.get('timezone') || 'Asia/Jakarta'),
    google_client_id: String(formData.get('google_client_id') || ''),
    maintenance_mode: formData.get('maintenance_mode') === 'on',
    signup_enabled: formData.get('signup_enabled') === 'on'
  };
  await adminFetch('/api/admin/settings/platform', {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
  revalidatePath('/dashboard/settings/platform');
}

/** 1 klik: minta agent VPS menerapkan domain baru. */
export async function applyDomain(formData: FormData) {
  const domain = String(formData.get('domain') || '').trim();
  const adminDomain = String(formData.get('admin_domain') || '').trim();
  if (!domain) return;
  await adminFetch('/api/admin/settings/platform/apply-domain', {
    method: 'POST',
    body: JSON.stringify({
      domain,
      admin_domain: adminDomain || null,
      update_dns: true
    })
  });
  revalidatePath('/dashboard/settings/platform');
}

export async function cancelDomain() {
  await adminFetch('/api/admin/settings/platform/domain-cancel', { method: 'POST' });
  revalidatePath('/dashboard/settings/platform');
}
