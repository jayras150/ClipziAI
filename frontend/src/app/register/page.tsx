"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { User, Mail, Lock } from "lucide-react"

import { getApiBaseUrl, getGoogleClientId } from "@/lib/env"
import { readApiError } from "@/lib/api-errors"
import { requestGoogleAccessToken } from "@/lib/social"

export default function RegisterPage() {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleClientId, setGoogleClientId] = useState("")

  useEffect(() => setGoogleClientId(getGoogleClientId()), [])

  const finishSignup = (accessToken: string, refreshToken?: string) => {
    localStorage.setItem("token", accessToken)
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken)
    window.location.href = "/dashboard"
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.")
      return
    }

    setLoading(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
        }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(
          readApiError(payload, "Could not create your account. Please try again."),
        )
      }
      if (!payload?.access_token) throw new Error("The server did not return a token. Try again.")
      finishSignup(payload.access_token, payload.refresh_token)
    } catch (err) {
      let message =
        err instanceof TypeError
          ? "Cannot reach the server. Check your connection and try again."
          : err instanceof Error
            ? err.message
            : "Sign up failed. Please try again."
      if (/already registered|already exists/i.test(message)) {
        message = "This email is already registered. Try signing in instead."
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignup = async () => {
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
      if (!response.ok) throw new Error(readApiError(payload, "Google sign-up failed."))
      if (!payload?.access_token) throw new Error("The server did not return a token. Try again.")
      finishSignup(payload.access_token, payload.refresh_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-up failed.")
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
          <Link className="ui-btn ui-btn-ghost" href="/login">
            Sign in
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
        <div style={{ width: "min(440px, calc(100vw - 44px))" }}>
          <div style={{ textAlign: "center", marginBottom: 26 }}>
            <div className="ui-brand-mark" style={{ margin: "0 auto 14px", width: 42, height: 42 }}>
              ▶
            </div>
            <h2 className="ui-title" style={{ fontSize: 28 }}>
              Create your <span className="ui-shine">Clipzy AI</span> account
            </h2>
            <p className="ui-muted" style={{ marginTop: 8 }}>
              5 free credits included. No credit card required.
            </p>
          </div>

          <form onSubmit={handleRegister} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <div>
              <label className="ui-label" htmlFor="name">
                Full name
              </label>
              <div className="ui-input-wrap">
                <User size={17} />
                <input
                  id="name"
                  type="text"
                  required
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="Alex Carter"
                />
              </div>
            </div>

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
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="At least 8 characters"
                />
              </div>
            </div>

            {error && <div className="ui-alert ui-alert-error">{error}</div>}

            <button type="submit" disabled={loading} className="ui-btn ui-btn-gold ui-btn-block">
              {loading ? "Creating account..." : "Create account"}
            </button>

            <p className="ui-muted" style={{ fontSize: 11.5, lineHeight: 1.7, textAlign: "center" }}>
              By creating an account you agree to our{" "}
              <Link href="/terms" className="ui-gold">Terms of Service</Link> and{" "}
              <Link href="/privacy-policy" className="ui-gold">Privacy Policy</Link>.
            </p>
          </form>

          <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
            {googleClientId ? (
              <button
                type="button"
                onClick={handleGoogleSignup}
                disabled={googleLoading}
                className="ui-btn ui-btn-ghost ui-btn-block"
              >
                {googleLoading ? "Connecting to Google..." : "Continue with Google"}
              </button>
            ) : (
              <p className="ui-muted" style={{ fontSize: 12, textAlign: "center", lineHeight: 1.7 }}>
                Google sign-in is not configured on this deployment yet. Email sign-up works right
                away.
              </p>
            )}
            <p className="ui-muted" style={{ textAlign: "center", fontSize: 13 }}>
              Already have an account?{" "}
              <Link href="/login" className="ui-gold" style={{ fontWeight: 700 }}>
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}

