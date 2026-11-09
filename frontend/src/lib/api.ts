import axios, { AxiosInstance } from "axios"

import { getApiBaseUrl } from "./env"

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
  created_at: string
}

export interface YouTubeDiagnostics {
  configured: boolean
  client_id: string | null
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
  ai_suggested_title: string | null
  ai_suggested_description: string | null
  ai_suggested_tags: string[] | null
  youtube_uploaded: boolean
  youtube_video_id: string | null
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
      // Dibaca saat runtime agar NEXT_PUBLIC_API_URL bisa diganti tanpa rebuild image.
      baseURL: getApiBaseUrl(),
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })

    this.client.interceptors.response.use(
      (res) => res,
      (error) => {
        if (error.response?.status === 401) {
          // Token expired or invalid
          if (typeof window !== "undefined") {
            localStorage.removeItem("token")
            window.location.href = "/login"
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

  async createTask(token: string, sourceUrl: string): Promise<TaskData> {
    const response = await this.client.post<TaskData>(
      "/api/tasks/",
      { source_url: sourceUrl, source_type: detectSourceType(sourceUrl) },
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

  async getTaskClips(token: string, taskId: string): Promise<ClipData[]> {
    const response = await this.client.get<ClipData[]>(`/api/tasks/${taskId}/clips`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }

  async deleteTask(token: string, taskId: string): Promise<{ message: string }> {
    const response = await this.client.delete<{ message: string }>(`/api/tasks/${taskId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.data
  }
}

export const api = new ApiClient()