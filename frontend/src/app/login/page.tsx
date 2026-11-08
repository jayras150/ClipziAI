"use client"

import { useState } from "react"
import Link from "next/link"
import { Mail, Lock, Globe, Twitter, Facebook } from "lucide-react"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

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
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
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
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center px-6">
      <div className="max-w-md w-full">
        <div className="mb-8 text-center">
          <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-pink-500 rounded-lg flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl">⚡</span>
          </div>
          <h2 className="text-2xl font-bold">Masuk ke Clipzi AI</h2>
          <p className="text-gray-400 mt-2">Selamat datang kembali</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Email</label>
            <div className="relative">
              <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                placeholder="you@example.com"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Kata Sandi</label>
            <div className="relative">
              <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                placeholder="••••••••"
              />
            </div>
          </div>

          {error && <p className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-3"
          >
            {loading ? "Memproses..." : "Masuk"}
          </button>

          <p className="text-center text-sm text-gray-400">
            Belum punya akun?{" "}
            <Link href="/register" className="text-blue-400 hover:text-blue-300 font-medium">
              Daftar gratis
            </Link>
          </p>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/20"></div>
            </div>
            <span className="relative flex justify-center text-xs uppercase bg-[#0F172A] px-2 text-gray-500">
              At lanjutkan dengan
            </span>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <button
              onClick={() => handleSocialLogin("google")}
              className="flex items-center justify-center gap-2 p-3 bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition-colors"
            >
              <Globe size={20} />
              <span className="text-sm">Google</span>
            </button>
            <button
              onClick={() => handleSocialLogin("x")}
              className="flex items-center justify-center gap-2 p-3 bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition-colors"
            >
              <Twitter size={20} />
              <span className="text-sm">X</span>
            </button>
            <button
              onClick={() => handleSocialLogin("facebook")}
              className="flex items-center justify-center gap-2 p-3 bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition-colors"
            >
              <Facebook size={20} />
              <span className="text-sm">Facebook</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}