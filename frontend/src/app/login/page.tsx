"use client"

import { useState } from "react"
import Link from "next/link"
import { Mail, Lock } from "lucide-react"

import { getApiBaseUrl } from "@/lib/env"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || "Email atau kata sandi salah.")
      localStorage.setItem("token", payload.access_token)
      localStorage.setItem("refresh_token", payload.refresh_token)
      window.location.href = "/dashboard"
    } catch (err: any) {
      setError(err.message || "Login gagal. Coba lagi.")
    } finally {
      setLoading(false)
    }
  }

  const handleSocialLogin = (provider: string) => {
    console.log(`Login with ${provider}`)
    // TODO: Redirect to OAuth provider
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
            Daftar
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
            <div className="ui-brand-mark" style={{ margin: "0 auto 14px", width: 42, height: 42 }}>▶</div>
            <h2 className="ui-title" style={{ fontSize: 28 }}>
              Masuk ke <span className="ui-shine">Clipzy AI</span>
            </h2>
            <p className="ui-muted" style={{ marginTop: 8 }}>
              Selamat datang kembali. Lanjutkan membuat klip.
            </p>
          </div>

          <form onSubmit={handleLogin} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <div>
              <label className="ui-label" htmlFor="email">Email</label>
              <div className="ui-input-wrap">
                <Mail size={17} />
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div>
              <label className="ui-label" htmlFor="password">Kata Sandi</label>
              <div className="ui-input-wrap">
                <Lock size={17} />
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="ui-input with-icon"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {error && <div className="ui-alert ui-alert-error">{error}</div>}

            <button type="submit" disabled={loading} className="ui-btn ui-btn-gold ui-btn-block">
              {loading ? "Memproses..." : "Masuk"}
            </button>

            <p className="ui-muted" style={{ textAlign: "center", fontSize: 13 }}>
              Belum punya akun?{" "}
              <Link href="/register" className="ui-gold" style={{ fontWeight: 700 }}>
                Daftar gratis
              </Link>
            </p>

            <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#6f7381", fontSize: 11 }}>
              <span style={{ flex: 1, height: 1, background: "var(--ui-line)" }} />
              atau lanjutkan dengan
              <span style={{ flex: 1, height: 1, background: "var(--ui-line)" }} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
              <button type="button" onClick={() => handleSocialLogin("google")} className="ui-btn ui-btn-ghost">
                Google
              </button>
              <button type="button" onClick={() => handleSocialLogin("x")} className="ui-btn ui-btn-ghost">
                X
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  )
}
