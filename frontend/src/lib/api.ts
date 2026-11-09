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
}

export const api = new ApiClient()