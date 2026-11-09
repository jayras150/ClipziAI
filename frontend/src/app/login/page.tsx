"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Mail, Lock } from "lucide-react"

import { getApiBaseUrl, getGoogleClientId } from "@/lib/env"
import { readApiError } from "@/lib/api-errors"
import { requestGoogleAccessToken } from "@/lib/social"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleClientId, setGoogleClientId] = useState("")

  // Client ID dibaca dari runtime-env.js (diisi container saat start).
  useEffect(() => setGoogleClientId(getGoogleClientId()), [])

  const finishLogin = (accessToken: string, refreshToken?: string) => {
    localStorage.setItem("token", accessToken)
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken)
    window.location.href = "/dashboard"
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(readApiError(payload, "Incorrect email or password."))
      if (!payload?.access_token) throw new Error("The server did not return a token. Try again.")
      finishLogin(payload.access_token, payload.refresh_token)
    } catch (err) {
      const message =
        err instanceof TypeError
          ? "Cannot reach the server. Check your connection and try again."
          : err instanceof Error
            ? err.message
            : "Sign in failed. Please try again."
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setError("")
    setGoogleLoading(true)
    try {
      const googleAccessToken = await requestGoogleAccessToken(googleClientId)
      const response = await fetch(`${getApiBaseUrl()}/api/auth/social-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "google", access_token: googleAccessToken }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(readApiError(payload, "Google sign-in failed."))
      if (!payload?.access_token) throw new Error("The server did not return a token. Try again.")
      finishLogin(payload.access_token, payload.refresh_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed.")
    } finally {
      setGoogleLoading(false)
    }
  }


  return (
    <div className="ui-shell">
      <div className="ui-container ui-nav">
        <Link className="ui-brand" href="/">
          <span className="ui-brand-mark">▶</span>
          <span>
            clipzy<em>AI</em>
          </span>
        </Link>
        <div className="ui-nav-actions">
          <Link className="ui-btn ui-btn-ghost" href="/register">
            Sign up
          </Link>
        </div>
      </div>

      <main
        style={{
          display: "grid",
          placeItems: "center",
          minHeight: "calc(100vh - 76px)",
          padding: "48px 0 64px",
        }}
      >
        <div style={{ width: "min(420px, calc(100vw - 44px))" }}>
          <div style={{ textAlign: "center", marginBottom: 26 }}>
            <div className="ui-brand-mark" style={{ margin: "0 auto 14px", width: 42, height: 42 }}>
              ▶
            </div>
            <h2 className="ui-title" style={{ fontSize: 28 }}>
              Sign in to <span className="ui-shine">Clipzy AI</span>
            </h2>
            <p className="ui-muted" style={{ marginTop: 8 }}>
              Welcome back. Pick up where you left off.
            </p>
          </div>

          <form onSubmit={handleLogin} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <div>
              <label className="ui-label" htmlFor="email">
                Email
              </label>
              <div className="ui-input-wrap">
                <Mail size={17} />
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div>
              <label className="ui-label" htmlFor="password">
                Password
              </label>
              <div className="ui-input-wrap">
                <Lock size={17} />
                <input
                  id="password"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {error && <div className="ui-alert ui-alert-error">{error}</div>}

            <button type="submit" disabled={loading} className="ui-btn ui-btn-gold ui-btn-block">
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
            {googleClientId ? (
              <button
                type="button"
                onClick={handleGoogleLogin}
                disabled={googleLoading}
                className="ui-btn ui-btn-ghost ui-btn-block"
              >
                {googleLoading ? "Connecting to Google..." : "Continue with Google"}
              </button>
            ) : (
              <p className="ui-muted" style={{ fontSize: 12, textAlign: "center", lineHeight: 1.7 }}>
                Google sign-in is not configured on this deployment yet. Use your email and
                password — it works right away.
              </p>
            )}
            <p className="ui-muted" style={{ textAlign: "center", fontSize: 13 }}>
              No account?{" "}
              <Link href="/register" className="ui-gold" style={{ fontWeight: 700 }}>
                Create one free
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
