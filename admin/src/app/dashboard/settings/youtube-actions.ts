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

/* ------------------------------------------------------------------ */
/* Encode base64 & simpan (dipakai komponen client cookie-importer)    */
/* ------------------------------------------------------------------ */

export type CookieSummary = {
  cookie_count?: number;
  domains?: string[];
  earliest_expiry?: string | null;
  bytes?: number;
};

export type EncodeResult = {
  base64?: string;
  summary?: CookieSummary;
  error?: string;
};

function _errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.replace(/^\d{3}\s+/, '');
  }
  return 'Permintaan ke server gagal. Coba lagi.';
}

export async function encodeCookieText(text: string): Promise<EncodeResult> {
  if (!text.trim()) return { error: 'Isi cookies masih kosong.' };
  try {
    return await adminFetch<EncodeResult>('/api/admin/ytdlp-cookies/encode', {
      method: 'POST',
      body: JSON.stringify({ cookies: text })
    });
  } catch (error) {
    return { error: _errorText(error) };
  }
}

export async function saveCookieInput(input: {
  source: 'netscape' | 'base64';
  text: string;
  label: string;
  storeBase64: boolean;
}): Promise<{ ok?: boolean; error?: string; notice?: string }> {
  const text = input.text.trim();
  if (!text) return { error: 'Isi cookies masih kosong.' };
  const label = input.label.trim() || 'akun-1';
  const body =
    input.source === 'netscape'
      ? { label, cookies: text, store_base64: input.storeBase64 }
      : { label, cookies_base64: text, store_base64: input.storeBase64 };
  try {
    await adminFetch('/api/admin/ytdlp-cookies', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    refresh();
    return {
      ok: true,
      notice: input.storeBase64
        ? 'Cookies disimpan & base64 global untuk ENV diperbarui.'
        : 'Cookies disimpan tanpa base64 ENV.'
    };
  } catch (error) {
    return { error: _errorText(error) };
  }
}

export async function getCookieBase64(
  id: string
): Promise<{ label?: string; base64?: string; error?: string }> {
  if (!id) return { error: 'ID cookies tidak valid.' };
  try {
    return await adminFetch<{ label: string; base64: string }>(
      `/api/admin/ytdlp-cookies/${id}/base64`
    );
  } catch (error) {
    return { error: _errorText(error) };
  }
}

export async function saveCookieBase64ToEnv(
  id: string
): Promise<{ ok?: boolean; error?: string; notice?: string }> {
  if (!id) return { error: 'ID cookies tidak valid.' };
  try {
    const data = await adminFetch<{ label?: string }>(
      `/api/admin/ytdlp-cookies/${id}/base64/store`,
      { method: 'POST' }
    );
    refresh();
    return { ok: true, notice: `Base64 ${data.label || 'cookies'} dijadikan ENV.` };
  } catch (error) {
    return { error: _errorText(error) };
  }
}
