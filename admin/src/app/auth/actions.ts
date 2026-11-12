"use server";

import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { API_URL, TOKEN_COOKIE } from '@/lib/clipzi';

export type AuthState = { error?: string };

export async function signIn(
  _prev: AuthState,
  formData: FormData
): Promise<AuthState> {
  const email = String(formData.get('email') || '').trim();
  const password = String(formData.get('password') || '');
  if (!email || !password) return { error: 'Email dan password wajib diisi.' };

  let token = '';
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
    const data = (await response.json()) as { access_token?: string };
    token = data.access_token || '';
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
  store.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 60 * 60 * 12
  });
  redirect('/dashboard/overview');
}

export async function signOut() {
  const store = await cookies();
  store.delete(TOKEN_COOKIE);
  redirect('/auth/sign-in');
}
