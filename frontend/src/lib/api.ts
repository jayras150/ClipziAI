import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios"

import { getApiBaseUrl } from "./env"
import { clearSession, refreshAccessToken } from "./auth"


export interface UserProfileData {
  id: string
  email: string | null
  name: string
  avatar_url: string | null
  plan_type: string
  credits_balance: number
  credits_total_earned: number
  credits_total_spent: number
  language: string
  timezone: string
  is_active: boolean
  email_verified: boolean
  two_factor_enabled: boolean
  is_admin: boolean
  created_at: string
}

/** Statistik ringkas untuk dashboard admin. */
export interface AdminStatsData {
  total_users: number
  banned_users: number
  total_tasks: number
  total_clips: number
  credits_spent: number
  completed_tasks: number
  tasks_by_status: Record<string, number>
  tasks_per_day: { date: string | null; count: number }[]
  recent_tasks: {
    id: string
    source_type: string
    status: string
    progress: number
    total_clips: number | null
    user_email: string | null
    created_at: string | null
  }[]
}

/** Konfigurasi watermark platform (diatur admin). */
export interface WatermarkConfigData {
  enabled: boolean
  plans: string[]
  image_url: string | null
  text: string | null
  position: string
  opacity: number
  scale: number
  text_color: string
  margin: number
}

export interface AdminUserRow {
  id: string
  email: string | null
  name: string
  provider?: string
  is_active: boolean
  is_banned: boolean
  created_at: string | null
}

export interface AuditRow {
  id: string
  actor_type: string
  actor_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  ip_address: string | null
  created_at: string | null
}

export interface MusicTrackData {
  id: string
  name: string
  mood: string | null
  duration: number | null
  url: string
}

/** Hasil skor viral klip (dipakai kartu klip di dashboard). */
export interface ViralScoreData {
  clip_id: string
  score: number
  factors: Record<string, any>
  recommended_title: string
  recommended_tags: string[]
  reasoning: string
}

export interface YouTubeDiagnostics {
  configured: boolean
  client_id: string | null
  gis_client_id: string | null
  redirect_uri: string | null
  reachable: boolean
  problem: string | null
  hint: string | null
}

export interface TaskData {
  id: string
  user_id: string
  source_url: string
  source_type: string
  status: string
  progress: number
  total_clips: number | null
  error_message: string | null
  auto_upload_youtube: boolean
  youtube_upload_status: string | null
  youtube_video_id: string | null
  youtube_video_url: string | null
  credits_spent: number
  created_at: string
  completed_at: string | null
}

export interface TaskListData {
  tasks: TaskData[]
  total: number
  page: number
  page_size: number
}

export interface ClipData {
  id: string
  task_id: string
  clip_index: number
  start_time: string
  end_time: string
  duration: number
  title: string
  download_url: string | null
  subtitle_url: string | null
  thumbnail_url: string | null
  file_size: number | null
  viral_score: number | null
  viral_factors: Record<string, any> | null
  ai_suggested_title: string | null
  ai_suggested_description: string | null
  ai_suggested_tags: string[] | null
  youtube_uploaded: boolean
  youtube_video_id: string | null
  editing_applied?: string[] | null
  created_at?: string
}

/** Metadata YouTube satu klip, dibuat AI dari transkrip Whisper. */
export interface ClipMetadataData {
  clip_id: string
  title: string
  description: string
  tags: string[]
  hook: string | null
  language: string | null
  /** Transkrip yang dipakai sebagai dasar metadata. */
  transcript: string
  /** "stored" = dari pipeline, "whisper" = ditranskripsi saat diminta */
  transcript_source: string
  /** "ai" = dibuat model, "manual" = hasil edit pengguna */
  generated_by: string
  ai_available: boolean
  /** "ready" = metadata siap, "preparing" = transkrip klip masih dibuat di server */
  status?: string
  message?: string | null
}

export interface YouTubeUploadResult {
  success: boolean
  youtube_video_id?: string | null
  youtube_video_url?: string | null
  error?: string | null
  title?: string | null
  privacy_status?: string | null
  already_uploaded?: boolean
}

/** Respons 202 dari POST /api/youtube/upload (unggahan jalan di background). */
export interface YouTubeUploadAccepted {
  accepted: true
  status: string
  clip_id: string
  message?: string
}

export interface YouTubeUploadStatus {
  clip_id: string
  status: "idle" | "uploading" | "done" | "error" | string
  error?: string | null
  youtube_video_id?: string | null
  youtube_video_url?: string | null
}

/** Tebak jenis sumber dari URL agar backend menyiapkan pipeline yang tepat. */
export function detectSourceType(url: string): string {
  const lower = url.toLowerCase()
  if (lower.includes("youtube.com") || lower.includes("youtu.be")) return "youtube"
  if (lower.includes("tiktok.com")) return "tiktok"
  if (lower.includes("instagram.com")) return "instagram"
  if (lower.includes("facebook.com") || lower.includes("fb.watch")) return "facebook"
  if (lower.includes("twitter.com") || lower.includes("x.com")) return "twitter"
  return "direct"
}

export class ApiClient {
  private client: AxiosInstance

  constructor(token?: string) {
    this.client = axios.create({
      // baseURL TIDAK diisi di sini: nilainya harus dibaca saat request dikirim,
      // bukan saat modul di-import. /runtime-env.js bisa saja baru dieksekusi
      // setelah bundle ini dimuat, dan itu akan membuat baseURL jatuh ke
      // http://localhost:8000 pada build produksi.
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })

    this.client.interceptors.request.use((config) => {
      if (!config.baseURL) config.baseURL = getApiBaseUrl()
      return config
    })

    this.client.interceptors.response.use(
      (res) => res,
      async (error) => {
        const status = error.response?.status
        const original = error.config as
          | (InternalAxiosRequestConfig & { _retried?: boolean })
          | undefined
        const url = typeof original?.url === "string" ? original.url : ""
        const isAuthCall = url.includes("/api/auth/")

        // 401 karena access token kedaluwarsa? Tukar refresh token lalu ulangi
        // request sekali. Gangguan sesaat (5xx/jaringan) TIDAK menghapus sesi.
        if (status === 401 && original && !original._retried && !isAuthCall) {
          const result = await refreshAccessToken()
          if (result.token) {
            original._retried = true
            original.headers = {
              ...(original.headers || {}),
              Authorization: `Bearer ${result.token}`,
            } as InternalAxiosRequestConfig["headers"]
            return this.client.request(original)
          }
          if (result.transient) {
            // Biarkan pemanggil menampilkan error; sesi tetap utuh untuk dicoba lagi.
            return Promise.reject(error)
          }
        }

        if (status === 401 && !isAuthCall && typeof window !== "undefined") {
          clearSession()
          if (!window.location.pathname.startsWith("/login")) {
            const next = `${window.location.pathname}${window.location.search}`
            window.location.href = `/login?next=${encodeURIComponent(next)}`
          }
        }
        return Promise.reject(error)
      }
    )

  }

  setToken(token: string) {
    this.client.defaults.headers.common["Authorization"] = `Bearer ${token}`
  }

  setApiKey(apiKey: string) {
    this.client.defaults.headers.common["X-API-Key"] = apiKey
  }

  async getYouTubeAuthUrl(token: string): Promise<string> {
    const response = await this.client.get<{ auth_url: string }>("/api/youtube/auth-url", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data.auth_url
  }

  async getYouTubeStatus(token: string) {
    const response = await this.client.get<{
      connected: boolean
      channel_id?: string
      channel_name?: string
      message?: string
    }>("/api/youtube/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async disconnectYouTube(token: string) {
    const response = await this.client.delete("/api/youtube/disconnect", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /** Simpan access token YouTube dari Google Identity Services (fallback tanpa redirect URI). */
  async setYouTubeAccessToken(token: string, accessToken: string) {
    const response = await this.client.post<{
      connected: boolean
      channel_id?: string
      channel_name?: string
      message?: string
    }>(
      "/api/youtube/token",
      { access_token: accessToken },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  async getYouTubeDiagnostics(token: string): Promise<YouTubeDiagnostics> {
    const response = await this.client.get<YouTubeDiagnostics>("/api/youtube/diagnostics", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async getProfile(token: string): Promise<UserProfileData> {
    const response = await this.client.get<UserProfileData>("/api/users/profile", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async updateProfile(
    token: string,
    payload: { name?: string; language?: string; timezone?: string },
  ): Promise<UserProfileData> {
    const response = await this.client.put<UserProfileData>("/api/users/profile", payload, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async changePassword(
    token: string,
    payload: { new_password: string; current_password?: string },
  ): Promise<{ message: string }> {
    const response = await this.client.put<{ message: string }>("/api/users/password", payload, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async createTask(
    token: string,
    sourceUrl: string,
    editingOptions?: Record<string, any>
  ): Promise<TaskData> {
    const response = await this.client.post<TaskData>(
      "/api/tasks/",
      {
        source_url: sourceUrl,
        source_type: detectSourceType(sourceUrl),
        ...editingOptions,
      },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  async listTasks(token: string, pageSize = 20): Promise<TaskListData> {
    const response = await this.client.get<TaskListData>(`/api/tasks/?page=1&page_size=${pageSize}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async getTask(token: string, taskId: string): Promise<TaskData> {
    const response = await this.client.get<TaskData>(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /** Daftar musik latar yang tersedia (library di R2). */
  async getMusicLibrary(token: string): Promise<MusicTrackData[]> {
    const response = await this.client.get<MusicTrackData[]>("/api/music", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /**
   * Skor viral satu klip (0–100 + breakdown faktor).
   * `force` = hitung ulang walau skor sudah tersimpan.
   */
  async getViralScore(token: string, clipId: string, force = false): Promise<ViralScoreData> {
    const response = await this.client.get<ViralScoreData>(
      `/api/youtube/viral-score/${clipId}${force ? "?force=true" : ""}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /* ---------- Admin (akses ditentukan ADMIN_EMAILS di server) ---------- */
  async getAdminStats(token: string): Promise<AdminStatsData> {
    const response = await this.client.get<AdminStatsData>("/api/admin/system/stats", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async getWatermarkConfig(token: string): Promise<WatermarkConfigData> {
    const response = await this.client.get<WatermarkConfigData>("/api/admin/settings/watermark", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async updateWatermarkConfig(
    token: string,
    payload: Partial<WatermarkConfigData>,
  ): Promise<WatermarkConfigData> {
    const response = await this.client.put<WatermarkConfigData>(
      "/api/admin/settings/watermark",
      payload,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Upload file logo watermark ke R2 (bukan menempel URL). */
  async uploadWatermarkLogo(token: string, file: File): Promise<WatermarkConfigData> {
    const form = new FormData()
    form.append("file", file)
    const response = await this.client.post<WatermarkConfigData>(
      "/api/admin/settings/watermark/logo",
      form,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      },
    )
    return response.data
  }

  /** Upload logo watermark milik user ke R2 (bukan menempel URL). */
  async uploadUserWatermark(
    token: string,
    file: File,
  ): Promise<{ watermark_url: string; size: number }> {
    const form = new FormData()
    form.append("file", file)
    const response = await this.client.post<{ watermark_url: string; size: number }>(
      "/api/users/watermark",
      form,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      },
    )
    return response.data
  }

  async listAdminUsers(token: string): Promise<AdminUserRow[]> {
    const response = await this.client.get<AdminUserRow[]>("/api/admin/users/", {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /** Ban/unban memakai query param (sesuai endpoint backend). */
  async banAdminUser(token: string, userId: string, reason: string): Promise<{ message: string }> {
    const response = await this.client.post(
      `/api/admin/users/${userId}/ban?reason=${encodeURIComponent(reason)}`,
      null,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  async unbanAdminUser(token: string, userId: string): Promise<{ message: string }> {
    const response = await this.client.post(`/api/admin/users/${userId}/unban`, null, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async adjustUserCredits(
    token: string,
    userId: string,
    amount: number,
    description: string,
  ): Promise<{ message: string; new_balance: number }> {
    const qs = new URLSearchParams({ amount: String(amount), description }).toString()
    const response = await this.client.post(
      `/api/admin/users/${userId}/credits/adjust?${qs}`,
      null,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  async listAuditLogs(token: string, limit = 50): Promise<AuditRow[]> {
    const response = await this.client.get<AuditRow[]>(`/api/admin/audit/?limit=${limit}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /** Gabungkan beberapa klip menjadi satu video (transisi opsional). */
  async composeClips(
    token: string,
    taskId: string,
    clipIds: string[],
    transition = "fade",
  ): Promise<TaskData> {
    const response = await this.client.post<TaskData>(
      `/api/tasks/${taskId}/compose`,
      { clip_ids: clipIds, transition },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Potong satu klip menjadi dua bagian di detik `atTime`. */
  async splitClip(
    token: string,
    taskId: string,
    clipId: string,
    atTime: number,
  ): Promise<TaskData> {
    const response = await this.client.post<TaskData>(
      `/api/tasks/${taskId}/split`,
      { clip_id: clipId, at_time: atTime },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }


  async getTaskClips(token: string, taskId: string): Promise<ClipData[]> {
    const response = await this.client.get<ClipData[]>(`/api/tasks/${taskId}/clips`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  /**
   * Minta AI membuat metadata (judul/deskripsi/tag) dari transkrip klip.
   * `regenerate` = paksa versi baru walau metadata sudah tersimpan.
   */
  async generateClipMetadata(
    token: string,
    clipId: string,
    regenerate = false,
  ): Promise<ClipMetadataData> {
    const response = await this.client.post<ClipMetadataData>(
      `/api/clips/${clipId}/metadata`,
      { regenerate },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Simpan hasil edit manual judul/deskripsi/tag. */
  async updateClipMetadata(
    token: string,
    clipId: string,
    payload: { title: string; description: string; tags: string[] },
  ): Promise<ClipMetadataData> {
    const response = await this.client.patch<ClipMetadataData>(
      `/api/clips/${clipId}/metadata`,
      payload,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Unggah satu klip ke YouTube memakai metadata yang sudah disetujui. */
  async uploadClipToYouTube(
    token: string,
    clipId: string,
    payload: {
      title: string
      description: string
      tags: string[]
      privacy_status: string
      category_id?: string
      force?: boolean
    },
  ): Promise<YouTubeUploadResult | YouTubeUploadAccepted> {
    const response = await this.client.post<YouTubeUploadResult | YouTubeUploadAccepted>(
      "/api/youtube/upload",
      {
        clip_id: clipId,
        auto_generate_metadata: false,
        force: payload.force ?? false,
        metadata: {
          title: payload.title,
          description: payload.description,
          tags: payload.tags,
          privacy_status: payload.privacy_status,
          category_id: payload.category_id ?? "22",
        },
      },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Status unggahan (dipakai untuk polling setelah respons 202). */
  async getYouTubeUploadStatus(token: string, clipId: string): Promise<YouTubeUploadStatus> {
    const response = await this.client.get<YouTubeUploadStatus>(
      `/api/youtube/upload/status/${clipId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    return response.data
  }

  /** Poll status sampai selesai/gagal, dengan batas waktu agar UI tidak macet. */
  async waitForYouTubeUpload(
    token: string,
    clipId: string,
    options: { timeoutMs?: number; intervalMs?: number } = {},
  ): Promise<YouTubeUploadStatus> {
    const timeoutMs = options.timeoutMs ?? 15 * 60 * 1000
    const intervalMs = options.intervalMs ?? 4000
    const started = Date.now()
    while (Date.now() - started < timeoutMs) {
      const status = await this.getYouTubeUploadStatus(token, clipId)
      if (status.status === "done" || status.status === "error") return status
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    return {
      clip_id: clipId,
      status: "error",
      error:
        "Upload is still running on the server. Reopen this popup in a few minutes to see the link.",
    }
  }

  async deleteTask(token: string, taskId: string): Promise<{ message: string }> {
    const response = await this.client.delete<{ message: string }>(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }
}

export const api = new ApiClient()