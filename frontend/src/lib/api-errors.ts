/**
 * Ubah error response FastAPI menjadi pesan yang bisa dibaca manusia.
 *
 * FastAPI mengembalikan `detail` sebagai string untuk HTTPException, tetapi
 * sebagai array of objects untuk galat validasi (422). Tanpa normalisasi,
 * `new Error(payload.detail)` akan tampil sebagai "[object Object]".
 */
export function readApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback

  const detail = (payload as { detail?: unknown }).detail

  if (typeof detail === "string" && detail.trim()) return detail

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
