import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

import { REFRESH_COOKIE, TOKEN_COOKIE, refreshAccessToken } from '@/lib/clipzi';

const PUBLIC_PREFIXES = ['/auth', '/_next', '/favicon', '/images', '/api'];

/** Ambil `exp` (detik) dari payload JWT tanpa verifikasi tanda tangan. */
function tokenExpiry(token: string): number | null {
  const parts = token.split('.');
  if (parts.length < 2) return null;
  try {
    const payload = JSON.parse(
      Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8')
    ) as { exp?: number };
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

function secondsLeft(token: string): number {
  const exp = tokenExpiry(token);
  if (!exp) return -1;
  return exp - Math.floor(Date.now() / 1000);
}

const ACCESS_COOKIE_MAX_AGE = 60 * 60 * 12; // cookie boleh hidup 12 jam
const REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // refresh 30 hari

/**
 * Guard + penyegaran sesi.
 *
 * Access token backend hanya berlaku 60 menit, sedangkan dashboard dipakai
 * berjam-jam. Dulu cookie bertahan 12 jam tanpa refresh, sehingga semua halaman
 * menampilkan "Something went wrong" (401) setelah satu jam. Sekarang:
 *   - token yang tinggal < 2 menit (atau hilang) diperbarui otomatis;
 *   - cookie baru ditulis ke response DAN request, jadi render saat ini ikut
 *     memakai token segar;
 *   - bila refresh gagal (dicabut/kedaluwarsa) -> redirect ke login.
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const accessToken = request.cookies.get(TOKEN_COOKIE)?.value ?? '';
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value ?? '';
  const needsRefresh = !accessToken || secondsLeft(accessToken) < 120;

  if (!needsRefresh) return NextResponse.next();

  if (!refreshToken) {
    const url = request.nextUrl.clone();
    url.pathname = '/auth/sign-in';
    url.search = pathname === '/dashboard' ? '' : '?expired=1';
    return NextResponse.redirect(url);
  }

  const refreshed = await refreshAccessToken(refreshToken);
  if (!refreshed) {
    const url = request.nextUrl.clone();
    url.pathname = '/auth/sign-in';
    url.search = '?expired=1';
    const response = NextResponse.redirect(url);
    response.cookies.delete(TOKEN_COOKIE);
    response.cookies.delete(REFRESH_COOKIE);
    return response;
  }

  // Token baru harus terlihat oleh server component pada request ini juga.
  request.cookies.set(TOKEN_COOKIE, refreshed.access_token);
  request.cookies.set(REFRESH_COOKIE, refreshed.refresh_token);

  const response = NextResponse.next({ request });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(TOKEN_COOKIE, refreshed.access_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure,
    path: '/',
    maxAge: ACCESS_COOKIE_MAX_AGE
  });
  response.cookies.set(REFRESH_COOKIE, refreshed.refresh_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure,
    path: '/',
    maxAge: REFRESH_COOKIE_MAX_AGE
  });
  return response;
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)'
  ]
};

