/**
 * Sumber tunggal status sesi Clipzy.
 *
 * Kenapa dipisah dari `api.ts`: komponen (Navbar/UserMenu/halaman) butuh tahu
 * status login tanpa memicu request, dan refresh token harus bisa dipakai ulang
 * oleh interceptor tanpa saling impor (hindari circular import).
 */
import axios from "axios"

import { getApiBaseUrl } from "./env"

export const AUTH_EVENT = "clipzy:auth"

export type RefreshResult = { token: string | null; transient: boolean }

function storage(): Storage | null {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function getAccessToken(): string | null {
  return storage()?.getItem("token") ?? null
}

export function getRefreshToken(): string | null {
  return storage()?.getItem("refresh_token") ?? null
}

export function hasSession(): boolean {
  return Boolean(getAccessToken() || getRefreshToken())
}

/** Beri tahu semua tab/komponen bahwa status sesi berubah. */
export function notifyAuthChanged(): void {
  if (typeof window === "undefined") return
  window.dispatchEvent(new Event(AUTH_EVENT))
  try {
    const channel = new BroadcastChannel("clipzy-auth")
    channel.postMessage({ type: "changed", at: Date.now() })
    channel.close()
  } catch {
    /* BroadcastChannel tidak tersedia (browser lama) — event lokal tetap jalan */
  }
}

export function setSession(accessToken: string, refreshToken?: string | null): void {
  const store = storage()
  if (!store) return
  store.setItem("token", accessToken)
  if (refreshToken) store.setItem("refresh_token", refreshToken)
  notifyAuthChanged()
}

export function clearSession(): void {
  const store = storage()
  if (!store) return
  store.removeItem("token")
  store.removeItem("refresh_token")
  notifyAuthChanged()
}

/** Baca klaim `exp` dari JWT tanpa verifikasi (hanya untuk timing refresh). */
export function decodeExp(token: string | null): number | null {
  if (!token) return null
  const payload = token.split(".")[1]
  if (!payload) return null
  try {
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")))
    return typeof json.exp === "number" ? json.exp : null
  } catch {
    return null
  }
}

/** True bila access token tidak ada atau tinggal < skewSeconds detik. */
export function accessTokenNeedsRefresh(skewSeconds = 120): boolean {
  const token = getAccessToken()
  const exp = decodeExp(token)
  if (!token || !exp) return true
  return exp * 1000 - Date.now() <= skewSeconds * 1000
}

let refreshing: Promise<RefreshResult> | null = null

/**
 * Tukar refresh token dengan access token baru.
 *
 * PENTING: kegagalan sesaat (jaringan putus, 5xx, 429, timeout) TIDAK boleh
 * menghapus sesi — hanya 401/403 dari server yang berarti token benar-benar
 * tidak valid. Inilah penyebab "tiba-tiba logout" sebelumnya.
 */
export function refreshAccessToken(): Promise<RefreshResult> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return Promise.resolve({ token: null, transient: false })

  if (!refreshing) {
    refreshing = (async (): Promise<RefreshResult> => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const response = await axios.post(
            `${getApiBaseUrl()}/api/auth/refresh`,
            { refresh_token: refreshToken },
            { timeout: 12000 },
          )
          const access = response.data?.access_token as string | undefined
          const nextRefresh = response.data?.refresh_token as string | undefined
          if (!access) return { token: null, transient: false }
          setSession(access, nextRefresh ?? refreshToken)
          return { token: access, transient: false }
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

/**
 * Pastikan ada access token yang masih berlaku.
 *
 * Return token (boleh `null` bila sesi benar-benar habis / tidak ada).
 */
export async function ensureSession(): Promise<string | null> {
  if (typeof window === "undefined") return null
  const token = getAccessToken()
  if (token && !accessTokenNeedsRefresh()) return token
  if (!token && !getRefreshToken()) return null

  const result = await refreshAccessToken()
  if (result.token) return result.token
  // Gangguan sesaat: tetap di halaman dan pakai token yang ada supaya pengguna
  // tidak terlempar ke login hanya karena server/ jaringan sedang bermasalah.
  if (result.transient) return token
  return null
}
