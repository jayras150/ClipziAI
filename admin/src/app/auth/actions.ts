"use server";

import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { API_URL, REFRESH_COOKIE, TOKEN_COOKIE } from '@/lib/clipzi';

export type AuthState = { error?: string };

const ACCESS_MAX_AGE = 60 * 60 * 12;
const REFRESH_MAX_AGE = 60 * 60 * 24 * 30;

export async function signIn(
  _prev: AuthState,
  formData: FormData
): Promise<AuthState> {
  const email = String(formData.get('email') || '').trim();
  const password = String(formData.get('password') || '');
  if (!email || !password) return { error: 'Email dan password wajib diisi.' };

  let token = '';
  let refresh = '';
  try {
    const response = await fetch(`${API_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      cache: 'no-store'
    });
    if (!response.ok) {
      return { error: 'Login gagal. Periksa email dan password.' };
    }
    const data = (await response.json()) as {
      access_token?: string;
      refresh_token?: string;
    };
    token = data.access_token || '';
    refresh = data.refresh_token || '';
  } catch {
    return { error: 'Tidak bisa menghubungi API. Coba lagi.' };
  }
  if (!token) return { error: 'API tidak mengembalikan token.' };

  // Pastikan akun ini memang admin sebelum menyimpan sesi.
  const me = await fetch(`${API_URL}/api/admin/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store'
  });
  if (!me.ok) return { error: 'Akun ini bukan admin.' };

  const store = await cookies();
  const secure = process.env.NODE_ENV === 'production';
  store.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure,
    path: '/',
    maxAge: ACCESS_MAX_AGE
  });
  // Refresh token membuat sesi bertahan 30 hari dan bisa diperbarui otomatis
  // oleh middleware (tanpa ini, dashboard mati setiap 60 menit).
  if (refresh) {
    store.set(REFRESH_COOKIE, refresh, {
      httpOnly: true,
      sameSite: 'lax',
      secure,
      path: '/',
      maxAge: REFRESH_MAX_AGE
    });
  }
  redirect('/dashboard/overview');
}

export async function signOut() {
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  // Catat ke audit log (best-effort; jangan gagal logout kalau API mati).
  if (token) {
    try {
      await fetch(`${API_URL}/api/admin/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store'
      });
    } catch {
      /* abaikan */
    }
  }
  store.delete(TOKEN_COOKIE);
  store.delete(REFRESH_COOKIE);
  redirect('/auth/sign-in?logged_out=1');
}

/** Cabut semua sesi (semua perangkat) lalu keluar. */
export async function signOutEverywhere() {
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${API_URL}/api/admin/auth/logout-all`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store'
      });
    } catch {
      /* abaikan */
    }
  }
  store.delete(TOKEN_COOKIE);
  store.delete(REFRESH_COOKIE);
  redirect('/auth/sign-in?logged_out=1');
}

