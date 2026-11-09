"use client"

import { useCallback, useEffect, useState } from "react"

import { getApiBaseUrl, getGoogleClientId } from "@/lib/env"
import { readApiError } from "@/lib/api-errors"
import { requestGoogleAccessToken } from "@/lib/social"

type Provider = "google" | "x" | "facebook"

const LABELS: Record<Provider, string> = {
  google: "Google",
  x: "X",
  facebook: "Facebook",
}

const ICONS: Record<Provider, string> = {
  google: "G",
  x: "𝕏",
  facebook: "f",
}

interface Props {
  /** "login" | "signup" — hanya memengaruhi teks tombol. */
  mode: "login" | "signup"
  /** Dipanggil setelah backend mengembalikan token. */
  onSuccess: (accessToken: string, refreshToken?: string) => void
}

/**
 * Deretan tombol login sosial (Google, X, Facebook).
 *
 * Status aktif diambil dari backend (`/api/auth/social-providers`), jadi tombol
 * yang belum punya kredensial tampil nonaktif dengan keterangan, bukan diam
 * saat diklik.
 */
export default function SocialButtons({ mode, onSuccess }: Props) {
  const [googleClientId, setGoogleClientId] = useState("")
  const [providers, setProviders] = useState<Record<Provider, boolean>>({
    google: false,
    x: false,
    facebook: false,
  })
  const [busy, setBusy] = useState<Provider | null>(null)
  const [message, setMessage] = useState("")

  useEffect(() => {
    setGoogleClientId(getGoogleClientId())

    fetch(`${getApiBaseUrl()}/api/auth/social-providers`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return
        setProviders({
          google: Boolean(data.google),
          x: Boolean(data.x),
          facebook: Boolean(data.facebook),
        })
      })
      .catch(() => {
        // Biarkan default (nonaktif) bila backend tidak bisa dihubungi.
      })
  }, [])

  const googleReady = providers.google && Boolean(googleClientId)

  const startProvider = useCallback(
    async (provider: Provider) => {
      setMessage("")
      setBusy(provider)

      try {
        const nativeProviders: Provider[] = ["x", "facebook"]
        if (nativeProviders.includes(provider)) {
          setMessage(
            `${LABELS[provider]} sign-in is not enabled yet. Add ${provider.toUpperCase()}_CLIENT_ID and ${provider.toUpperCase()}_CLIENT_SECRET on the server, then it will work automatically.`,
          )
          return
        }

        if (!googleClientId) {
          setMessage(
            "Google sign-in needs a Client ID. Set NEXT_PUBLIC_GOOGLE_CLIENT_ID on the deployment.",
          )
          return
        }

        const googleToken = await requestGoogleAccessToken(googleClientId)
        const response = await fetch(`${getApiBaseUrl()}/api/auth/social-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, access_token: googleToken }),
        })
        const payload = await response.json().catch(() => null)

        if (!response.ok) throw new Error(readApiError(payload, `${LABELS[provider]} sign-in failed.`))
        if (!payload?.access_token) throw new Error("The server did not return a token. Try again.")

        onSuccess(payload.access_token, payload.refresh_token)
      } catch (error) {
        setMessage(error instanceof Error ? error.message : `${LABELS[provider]} sign-in failed.`)
      } finally {
        setBusy(null)
      }
    },
    [googleClientId, onSuccess],
  )

  const isEnabled = (provider: Provider) => provider === "google" && googleReady

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#6f7381", fontSize: 11 }}>
        <span style={{ flex: 1, height: 1, background: "var(--ui-line)" }} />
        or continue with
        <span style={{ flex: 1, height: 1, background: "var(--ui-line)" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        {(Object.keys(LABELS) as Provider[]).map((provider) => {
          const enabled = isEnabled(provider)
          return (
            <button
              key={provider}
              type="button"
              onClick={() => startProvider(provider)}
              disabled={busy !== null}
              aria-disabled={!enabled}
              title={
                enabled
                  ? `${mode === "signup" ? "Sign up" : "Sign in"} with ${LABELS[provider]}`
                  : `${LABELS[provider]} sign-in is not configured yet`
              }
              className="ui-btn ui-btn-ghost"
              style={{ gap: 8, opacity: enabled ? 1 : 0.55 }}
            >
              <span aria-hidden="true" style={{ fontWeight: 700 }}>
                {ICONS[provider]}
              </span>
              {busy === provider ? "..." : LABELS[provider]}
            </button>
          )
        })}
      </div>

      {!googleReady && (
        <p className="ui-muted" style={{ fontSize: 12, textAlign: "center", lineHeight: 1.7 }}>
          Social sign-in is being set up. Email and password work right away.
        </p>
      )}

      {message && (
        <div className="ui-alert ui-alert-error" role="status">
          {message}
        </div>
      )}
    </div>
  )
}
