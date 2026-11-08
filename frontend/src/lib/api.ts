import axios, { AxiosInstance } from "axios"

import { getApiBaseUrl } from "./env"

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
}

export const api = new ApiClient()