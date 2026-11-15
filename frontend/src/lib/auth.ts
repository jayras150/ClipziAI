/**
 * Sumber tunggal status sesi Clipzy.
 *
 * J9: access/refresh token tidak lagi disimpan di localStorage. Backend
 * menaruhnya di cookie HttpOnly; file ini hanya membaca flag sesi non-HttpOnly
 * dan menyediakan helper refresh/logout/CSRF.
 */
import axios from "axios"

import { getApiBaseUrl } from "./env"

export const AUTH_EVENT = "clipzy:auth"
export const SESSION_COOKIE = "clipzy_session"
export const CSRF_COOKIE = "clipzy_csrf"

export type RefreshResult = { token: string | null; transient: boolean }

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const prefix = `${name}=`
  for (const part of document.cookie.split(";")) {
    const item = part.trim()
    if (item.startsWith(prefix)) {
      try {
        return decodeURIComponent(item.slice(prefix.length))
      } catch {
        return item.slice(prefix.length)
      }
    }
  }
  return null
}

export function getCsrfToken(): string | null {
  return readCookie(CSRF_COOKIE)
}

/** Token Bearer legacy. Cookie auth tidak membutuhkan token ini. */
export function getAccessToken(): string | null {
  return hasSession() ? "cookie" : null
}

/** Refresh token legacy. Refresh sekarang memakai cookie HttpOnly. */
export function getRefreshToken(): string | null {
  return hasSession() ? "cookie" : null
}

export function hasSession(): boolean {
  return readCookie(SESSION_COOKIE) === "1"
}

export function notifyAuthChanged(): void {
  if (typeof window === "undefined") return
  window.dispatchEvent(new Event(AUTH_EVENT))
  try {
    const channel = new BroadcastChannel("clipzy-auth")
    channel.postMessage({ type: "changed", at: Date.now() })
    channel.close()
  } catch {
    /* BroadcastChannel tidak tersedia — event lokal tetap jalan */
  }
}

function clearLegacyStorage(): void {
  try {
    window.localStorage.removeItem("token")
    window.localStorage.removeItem("refresh_token")
  } catch {
    /* storage diblokir */
  }
}

/** Dipertahankan untuk kompatibilitas; sesi sekarang ditulis backend sebagai cookie. */
export function setSession(_accessToken: string, _refreshToken?: string | null): void {
  clearLegacyStorage()
  notifyAuthChanged()
}

export function clearSession(): void {
  clearLegacyStorage()
  if (typeof window !== "undefined") {
    const headers: Record<string, string> = {}
    const csrf = getCsrfToken()
    if (csrf) headers["X-CSRF-Token"] = csrf
    void fetch(`${getApiBaseUrl()}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers,
    }).catch(() => undefined)
  }
  notifyAuthChanged()
}

/** Dipertahankan untuk kompatibilitas timing lama. */
export function decodeExp(_token: string | null): number | null {
  return null
}

export function accessTokenNeedsRefresh(): boolean {
  return !hasSession()
}

let refreshing: Promise<RefreshResult> | null = null

export function refreshAccessToken(): Promise<RefreshResult> {
  if (!hasSession()) return Promise.resolve({ token: null, transient: false })
  if (!refreshing) {
    refreshing = (async (): Promise<RefreshResult> => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const headers: Record<string, string> = { "Content-Type": "application/json" }
          const csrf = getCsrfToken()
          if (csrf) headers["X-CSRF-Token"] = csrf
          const response = await axios.post(
            `${getApiBaseUrl()}/api/auth/refresh`,
            {},
            { headers, withCredentials: true, timeout: 12000 },
          )
          if (response.data?.access_token) {
            return { token: "cookie", transient: false }
          }
          return { token: null, transient: false }
        } catch (error: any) {
          const status = error?.response?.status
          if (status === 401 || status === 403) return { token: null, transient: false }
          if (attempt === 1) return { token: null, transient: true }
          await new Promise((resolve) => setTimeout(resolve, 500))
        }
      }
      return { token: null, transient: true }
    })().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

export async function ensureSession(): Promise<string | null> {
  if (typeof window === "undefined" || !hasSession()) return null
  const result = await refreshAccessToken()
  if (result.token || result.transient) return "cookie"
  return null
}
