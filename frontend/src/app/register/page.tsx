"use client"

import { useState } from "react"
import Link from "next/link"
import { Mail, Lock, User } from "lucide-react"

import { getApiBaseUrl } from "@/lib/env"

export default function RegisterPage() {
  const [formData, setFormData] = useState({ name: "", email: "", password: "" })
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || "Pendaftaran gagal.")
      localStorage.setItem("token", payload.access_token)
      localStorage.setItem("refresh_token", payload.refresh_token)
      window.location.href = "/dashboard"
    } catch (err: any) {
      setError(err.message || "Pendaftaran gagal. Coba lagi.")
    } finally {
      setLoading(false)
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
            Masuk
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
            <div className="ui-brand-mark" style={{ margin: "0 auto 14px", width: 42, height: 42 }}>▶</div>
            <h2 className="ui-title" style={{ fontSize: 28 }}>
              Daftar <span className="ui-shine">Clipzy AI</span>
            </h2>
            <p className="ui-muted" style={{ marginTop: 8 }}>
              Dapatkan <span className="ui-gold">5 kredit gratis</span> untuk mencoba fitur dasar.
            </p>
          </div>

          <form onSubmit={handleRegister} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <div>
              <label className="ui-label" htmlFor="name">Nama Lengkap</label>
              <div className="ui-input-wrap">
                <User size={17} />
                <input
                  id="name"
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="ui-input with-icon"
                  placeholder="Nama Anda"
                />
              </div>
            </div>

            <div>
              <label className="ui-label" htmlFor="email">Email</label>
              <div className="ui-input-wrap">
                <Mail size={17} />
                <input
                  id="email"
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
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
                  minLength={8}
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="ui-input with-icon"
                  placeholder="••••••••"
                />
              </div>
              <p className="ui-hint">Minimal 8 karakter</p>
            </div>

            {error && <div className="ui-alert ui-alert-error">{error}</div>}

            <button type="submit" disabled={loading} className="ui-btn ui-btn-gold ui-btn-block">
              {loading ? "Memproses..." : "Daftar Gratis"}
            </button>

            <p className="ui-muted" style={{ textAlign: "center", fontSize: 13 }}>
              Sudah punya akun?{" "}
              <Link href="/login" className="ui-gold" style={{ fontWeight: 700 }}>
                Masuk di sini
              </Link>
            </p>
          </form>
        </div>
      </main>
    </div>
  )
}
