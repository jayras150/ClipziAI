'use server';

import { revalidatePath } from 'next/cache';

import { adminFetch } from '@/lib/clipzi';

function refresh() {
  revalidatePath('/dashboard/settings/youtube');
}

/**
 * Simpan cookies YouTube.
 *
 * Menerima teks cookies.txt ATAU base64; base64 dikonversi & divalidasi di
 * backend, lalu disimpan terenkripsi di tabel rotasi + setelan platform.
 */
export async function saveYoutubeCookies(formData: FormData) {
  const mode = String(formData.get('mode') || 'db');
  const label = String(formData.get('label') || '').trim() || 'akun-1';
  const raw = String(formData.get('cookies') || '').trim();
  const base64 = String(formData.get('cookies_base64') || '').trim();

  if (!raw && !base64) {
    refresh();
    return;
  }

  await adminFetch('/api/admin/ytdlp-cookies/settings', {
    method: 'PUT',
    body: JSON.stringify({
      mode,
      label,
      cookies_base64: base64 || undefined
    })
  });

  // Bila admin menempel format Netscape, simpan lewat endpoint rotasi DB.
  if (raw) {
    await adminFetch('/api/admin/ytdlp-cookies', {
      method: 'POST',
      body: JSON.stringify({ label, cookies: raw })
    });
  }

  refresh();
}

export async function probeCookie(formData: FormData) {
  const id = String(formData.get('cid') || '');
  if (!id) return;
  await adminFetch(`/api/admin/ytdlp-cookies/${id}/probe`, { method: 'POST' });
  refresh();
}

export async function probeAllCookies() {
  await adminFetch('/api/admin/ytdlp-cookies/probe-all', { method: 'POST' });
  refresh();
}

export async function setCookieStatus(formData: FormData) {
  const id = String(formData.get('cid') || '');
  const action = String(formData.get('action') || 'disable');
  if (!id) return;
  await adminFetch(`/api/admin/ytdlp-cookies/${id}/${action}`, { method: 'POST' });
  refresh();
}

export async function deleteCookie(formData: FormData) {
  const id = String(formData.get('cid') || '');
  if (!id) return;
  await adminFetch(`/api/admin/ytdlp-cookies/${id}`, { method: 'DELETE' });
  refresh();
}
