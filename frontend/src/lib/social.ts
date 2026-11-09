"use client"

/**
 * Helper Google Sign-In (Google Identity Services).
 *
 * Memakai "implicit token flow": browser meminta access token langsung dari
 * Google, lalu token itu dikirim ke backend (/api/auth/social-login) untuk
 * diverifikasi. Tidak ada client secret di frontend.
 */

declare global {
  interface Window {
    google?: {
      accounts?: {
        oauth2?: {
          initTokenClient: (config: {
            client_id: string
            scope: string
            callback: (response: { access_token?: string; error?: string }) => void
            error_callback?: (error: { type?: string; message?: string }) => void
          }) => { requestAccessToken: (overrideConfig?: { prompt?: string }) => void }
        }
      }
    }
  }
}

const GIS_SRC = "https://accounts.google.com/gsi/client"
const GOOGLE_SCOPE = "openid email profile"
const YOUTUBE_SCOPE =
  "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"

let scriptPromise: Promise<void> | null = null

function loadGoogleScript(): Promise<void> {
  if (typeof document === "undefined") return Promise.resolve()
  if (window.google?.accounts?.oauth2) return Promise.resolve()

  if (!scriptPromise) {
    scriptPromise = new Promise<void>((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>(`script[src="${GIS_SRC}"]`)
      const script = existing ?? document.createElement("script")

      script.addEventListener("load", () => resolve())
      script.addEventListener("error", () =>
        reject(new Error("Failed to load Google sign-in script. Check your connection.")),
      )

      if (!existing) {
        script.src = GIS_SRC
        script.async = true
        script.defer = true
        document.head.appendChild(script)
      }
    })
  }

  return scriptPromise
}

/** Minta access token Google; throw Error dengan pesan siap tampil bila gagal. */
export async function requestGoogleAccessToken(clientId: string): Promise<string> {
  return requestTokenWithScope(clientId, GOOGLE_SCOPE, "")
}

/**
 * Minta access token dengan scope YouTube.
 *
 * Alur ini tidak memakai redirect URI, jadi tetap berfungsi walaupun
 * https://<domain>/api/youtube/callback belum terdaftar di Google Console.
 */
export async function requestYouTubeAccessToken(clientId: string): Promise<string> {
  return requestTokenWithScope(clientId, YOUTUBE_SCOPE, "consent")
}

async function requestTokenWithScope(
  clientId: string,
  scope: string,
  prompt: string,
): Promise<string> {
  if (!clientId) {
    throw new Error("Google sign-in is not configured for this deployment.")
  }

  await loadGoogleScript()

  const oauth2 = window.google?.accounts?.oauth2
  if (!oauth2) {
    throw new Error("Google sign-in is unavailable in this browser.")
  }

  return new Promise<string>((resolve, reject) => {
    const client = oauth2.initTokenClient({
      client_id: clientId,
      scope,
      callback: (response) => {
        if (response.error || !response.access_token) {
          reject(new Error(response.error || "Google sign-in was cancelled."))
          return
        }
        resolve(response.access_token)
      },
      error_callback: (error) => {
        reject(new Error(error.message || error.type || "Google sign-in failed."))
      },
    })

    client.requestAccessToken({ prompt })
  })
}
