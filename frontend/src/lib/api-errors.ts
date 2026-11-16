/**
 * Ubah error response FastAPI menjadi pesan yang bisa dibaca manusia.
 *
 * FastAPI mengembalikan `detail` sebagai string untuk HTTPException, tetapi
 * sebagai array of objects untuk galat validasi (422). Tanpa normalisasi,
 * `new Error(payload.detail)` akan tampil sebagai "[object Object]".
 */
export type ApiErrorInfo = {
  message: string
  code: string
  href: string
  reason: string
}

/**
 * Versi terstruktur dari `readApiError` untuk error yang membawa `code`.
 *
 * Backend bisa mengembalikan `detail` berupa objek, mis.
 * `{"code": "youtube_thumbnail_forbidden", "message": "...", "verify_url": "..."}`.
 * UI memakai `code` untuk memilih dialog yang tepat (mis. popup verifikasi channel).
 */
export function readApiErrorInfo(payload: unknown, fallback: string): ApiErrorInfo {
  if (!payload || typeof payload !== "object") {
    return { message: fallback, code: "", href: "", reason: "" }
  }

  const detail = (payload as { detail?: unknown }).detail

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const item = detail as {
      code?: unknown
      message?: unknown
      verify_url?: unknown
      reason?: unknown
    }
    const message = typeof item.message === "string" && item.message.trim() ? item.message : fallback
    return {
      message,
      code: typeof item.code === "string" ? item.code : "",
      href: typeof item.verify_url === "string" ? item.verify_url : "",
      reason: typeof item.reason === "string" ? item.reason : "",
    }
  }

  return { message: readApiError(payload, fallback), code: "", href: "", reason: "" }
}

export function readApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback

  const detail = (payload as { detail?: unknown }).detail

  if (typeof detail === "string" && detail.trim()) return detail

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === "string" && message.trim()) return message
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown; msg?: unknown } | undefined
    const message = typeof first?.msg === "string" ? first.msg : ""
    const loc = Array.isArray(first?.loc) ? first.loc : []
    const field = loc.length > 0 ? String(loc[loc.length - 1]) : ""

    if (message) {
      if (field && field !== "body") {
        const pretty = field.charAt(0).toUpperCase() + field.slice(1)
        return `${pretty}: ${message}`
      }
      return message
    }
  }

  return fallback
}
