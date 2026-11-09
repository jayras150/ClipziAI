/**
 * Base URL backend API.
 *
 * Prioritas:
 *   1. window.__ENV__.NEXT_PUBLIC_API_URL -> diisi /runtime-env.js saat container
 *      start (lihat frontend/docker-entrypoint.sh). Ini yang membuat satu image
 *      Docker bisa dipakai di environment mana pun tanpa rebuild.
 *   2. process.env.NEXT_PUBLIC_API_URL -> nilai yang di-inline Next.js saat build.
 *   3. http://localhost:8000 -> default untuk development lokal.
 */
const FALLBACK_API_BASE_URL = "http://localhost:8000"

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "")
}

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const runtimeUrl = window.__ENV__?.NEXT_PUBLIC_API_URL
    if (runtimeUrl) return stripTrailingSlash(runtimeUrl)
  }

  const buildUrl = process.env.NEXT_PUBLIC_API_URL
  if (buildUrl) return stripTrailingSlash(buildUrl)

  return FALLBACK_API_BASE_URL
}

/**
 * Google OAuth Client ID (publik, aman di-bundle).
 *
 * Kosong berarti tombol "Continue with Google" disembunyikan dan pengguna
 * diarahkan memakai email + kata sandi. Isi dulu Client ID di Google Cloud
 * Console (OAuth 2.0 Client, tipe "Web application") lalu tambahkan origin
 * https://proxyai.live ke Authorized JavaScript origins.
 */
export function getGoogleClientId(): string {
  if (typeof window !== "undefined") {
    const runtimeId = window.__ENV__?.NEXT_PUBLIC_GOOGLE_CLIENT_ID
    if (runtimeId) return runtimeId
  }

  return process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""
}

