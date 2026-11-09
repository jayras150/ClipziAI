"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Mail, ShieldCheck, Youtube, Unlink, LoaderCircle, Save, LogOut, Check } from "lucide-react"

import Navbar from "@/components/Navbar"
import ConfirmDialog from "@/components/ConfirmDialog"
import SiteFooter from "@/components/SiteFooter"
import { api, UserProfileData, YouTubeDiagnostics } from "@/lib/api"
import { readApiError } from "@/lib/api-errors"
import { requestYouTubeAccessToken } from "@/lib/social"

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "id", label: "Bahasa Indonesia" },
]

const TIMEZONES = [
  "Asia/Jakarta",
  "Asia/Makassar",
  "Asia/Jayapura",
  "Asia/Singapore",
  "UTC",
]

export default function ProfilePage() {
  const [token, setToken] = useState("")
  const [profile, setProfile] = useState<UserProfileData | null>(null)
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [diagnostics, setDiagnostics] = useState<YouTubeDiagnostics | null>(null)
  const [youtubeBusy, setYoutubeBusy] = useState(false)
  // Konfirmasi wajib sebelum memutus koneksi YouTube (menghapus token).
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [notice, setNotice] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)

  const [name, setName] = useState("")
  const [language, setLanguage] = useState("en")
  const [timezone, setTimezone] = useState("Asia/Jakarta")
  const [savingProfile, setSavingProfile] = useState(false)

  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [savingPassword, setSavingPassword] = useState(false)

  const load = useCallback(async (authToken: string) => {
    const [profileData, youtubeStatus, youtubeDiag] = await Promise.allSettled([
      api.getProfile(authToken),
      api.getYouTubeStatus(authToken),
      api.getYouTubeDiagnostics(authToken),
    ])

    if (profileData.status === "fulfilled") {
      const data = profileData.value
      setProfile(data)
      setName(data.name)
      setLanguage(data.language || "en")
      setTimezone(data.timezone || "Asia/Jakarta")
    }
    if (youtubeStatus.status === "fulfilled") setYoutube(youtubeStatus.value)
    if (youtubeDiag.status === "fulfilled") setDiagnostics(youtubeDiag.value)
  }, [])

  useEffect(() => {
    const stored = typeof window === "undefined" ? null : localStorage.getItem("token")
    if (!stored) {
      window.location.href = "/login"
      return
    }
    setToken(stored)
    load(stored).finally(() => setLoading(false))
  }, [load])

  const flash = (message: string) => {
    setError("")
    setNotice(message)
    window.setTimeout(() => setNotice(""), 4000)
  }

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!profile) return
    setSavingProfile(true)
    setError("")
    try {
      const updated = await api.updateProfile(token, {
        name: name.trim(),
        language,
        timezone,
      })
      setProfile(updated)
      flash("Profile settings saved.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not save your profile."))
    } finally {
      setSavingProfile(false)
    }
  }

  const savePassword = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters long.")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("The two passwords do not match.")
      return
    }
    setSavingPassword(true)
    try {
      await api.changePassword(token, {
        new_password: newPassword,
        current_password: currentPassword || undefined,
      })
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
      flash("Password updated successfully.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not update your password."))
    } finally {
      setSavingPassword(false)
    }
  }

  const connectYouTube = async () => {
    setYoutubeBusy(true)
    setError("")
    try {
      window.location.href = await api.getYouTubeAuthUrl(token)
    } catch (err: any) {
      const detail = String(err.response?.data?.detail || "")
      const originalMessage = readApiError(err.response?.data, "Could not start the YouTube connection.")

      // 409 = konfigurasi OAuth server belum lengkap (mis. redirect URI belum
      // terdaftar). Pakai alur token Google Identity Services sebagai fallback.
      if (err.response?.status !== 409) {
        setError(originalMessage)
        setYoutubeBusy(false)
        return
      }

      try {
        const diagnostics = await api.getYouTubeDiagnostics(token)
        const accessToken = await requestYouTubeAccessToken(
          diagnostics.gis_client_id || diagnostics.client_id || "",
        )
        const connected = await api.setYouTubeAccessToken(token, accessToken)
        setYoutube({ connected: true, channel_name: connected.channel_name })
        flash(connected.message || "YouTube connected.")
      } catch (fallbackError: any) {
        setError(
          [fallbackError?.message || "Could not connect YouTube.", detail].filter(Boolean).join(" "),
        )
      } finally {
        setYoutubeBusy(false)
      }
    }
  }

  const disconnectYouTube = async () => {
    setYoutubeBusy(true)
    try {
      await api.disconnectYouTube(token)
      setYoutube({ connected: false })
      flash("YouTube channel disconnected.")
    } catch {
      setError("Could not disconnect the YouTube channel.")
    } finally {
      setYoutubeBusy(false)
    }
  }

  const signOut = () => {
    localStorage.removeItem("token")
    localStorage.removeItem("refresh_token")
    window.location.href = "/login"
  }

  if (loading) {
    return (
      <div className="ui-shell">
        <Navbar />
        <main className="ui-container" style={{ padding: "80px 0", textAlign: "center" }}>
          <LoaderCircle size={22} className="animate-spin ui-gold" />
          <p className="ui-muted" style={{ marginTop: 12 }}>
            Loading your profile…
          </p>
        </main>
      </div>
    )
  }

  const initial = (profile?.name || profile?.email || "?").charAt(0).toUpperCase()

  return (
    <div className="ui-shell">
      <Navbar />

      <main className="ui-container ui-container-wide" style={{ padding: "38px 0 70px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 16,
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 26,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              aria-hidden="true"
              style={{
                width: 54,
                height: 54,
                borderRadius: 18,
                display: "grid",
                placeItems: "center",
                fontWeight: 800,
                fontSize: 22,
                color: "#171207",
                background: "linear-gradient(135deg, var(--ui-gold), #ffe3a0)",
              }}
            >
              {initial}
            </div>
            <div>
              <div className="ui-kicker">Account</div>
              <h1 className="ui-title" style={{ fontSize: 26, margin: "4px 0 2px" }}>
                {profile?.name || "Your profile"}
              </h1>
              <p className="ui-muted" style={{ fontSize: 13 }}>
                {profile?.email}
              </p>
            </div>
          </div>

          <button type="button" onClick={signOut} className="ui-btn ui-btn-ghost">
            <LogOut size={15} /> Sign out
          </button>
        </div>

        {notice && (
          <div
            className="ui-alert"
            style={{ marginBottom: 18, borderColor: "rgba(244, 199, 107, 0.45)", color: "var(--ui-gold)" }}
          >
            <Check size={15} /> {notice}
          </div>
        )}
        {error && (
          <div className="ui-alert ui-alert-error" style={{ marginBottom: 18 }}>
            {error}
          </div>
        )}



        <div
          style={{
            display: "grid",
            // 2 kolom di desktop (kartu kanan mengisi ruang kosong), 1 kolom di
            // mobile. Sebelumnya minmax(320px) membuat 3 kolom sempit sehingga
            // kartu "Security" jatuh sendirian dan menyisakan area kosong besar.
            gridTemplateColumns: "repeat(auto-fit, minmax(430px, 1fr))",
            gap: 16,
            alignItems: "start",
          }}
        >
          {/* ---------- Profil ---------- */}
          <form onSubmit={saveProfile} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <h2 className="ui-subtitle">Profile settings</h2>

            <div>
              <label className="ui-label" htmlFor="name">
                Full name
              </label>
              <input
                id="name"
                className="ui-input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>

            <div>
              <label className="ui-label" htmlFor="email">
                Email
              </label>
              <div className="ui-input-wrap">
                <Mail size={17} />
                <input
                  id="email"
                  className="ui-input with-icon"
                  value={profile?.email || ""}
                  readOnly
                  disabled
                />
              </div>
              <p className="ui-hint">Email cannot be changed. Contact support if you need to.</p>
            </div>

            <div>
              <label className="ui-label" htmlFor="language">
                Interface language
              </label>
              <select
                id="language"
                className="ui-input"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
              >
                {LANGUAGES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="ui-label" htmlFor="timezone">
                Timezone
              </label>
              <select
                id="timezone"
                className="ui-input"
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
              >
                {TIMEZONES.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
            </div>

            <button type="submit" className="ui-btn ui-btn-gold" disabled={savingProfile}>
              <Save size={15} /> {savingProfile ? "Saving…" : "Save changes"}
            </button>
          </form>

          {/* ---------- Paket & kredit ---------- */}
          <div className="ui-card" style={{ display: "grid", gap: 14 }}>
            <h2 className="ui-subtitle">Plan &amp; credits</h2>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="ui-muted">Current plan</span>
              <span className="ui-badge ui-badge-gold" style={{ textTransform: "capitalize" }}>
                {profile?.plan_type || "free"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="ui-muted">Credits available</span>
              <strong className="ui-gold">{profile?.credits_balance ?? 0}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="ui-muted">Total earned</span>
              <span>{profile?.credits_total_earned ?? 0}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span className="ui-muted">Total spent</span>
              <span>{profile?.credits_total_spent ?? 0}</span>
            </div>
            <Link href="/pricing" className="ui-btn ui-btn-ghost">
              Compare plans
            </Link>
          </div>

          {/* ---------- Akun terhubung ---------- */}
          <div className="ui-card" style={{ display: "grid", gap: 14 }}>
            <h2 className="ui-subtitle">Connected accounts</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
              <Youtube size={17} className="ui-gold" />
              <span>
                {youtube.connected
                  ? `YouTube: ${youtube.channel_name || "connected"}`
                  : "YouTube is not connected"}
              </span>
            </div>
            <button
              type="button"
              onClick={youtube.connected ? () => setConfirmDisconnect(true) : connectYouTube}
              disabled={youtubeBusy}
              className={youtube.connected ? "ui-btn ui-btn-ghost" : "ui-btn ui-btn-gold"}
            >
              {youtubeBusy ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : youtube.connected ? (
                <Unlink size={15} />
              ) : (
                <Youtube size={15} />
              )}
              {youtube.connected ? "Disconnect" : "Connect YouTube"}
            </button>
            {diagnostics?.configured && diagnostics.problem && (
              <p className="ui-hint" style={{ color: "#f0a3a3" }}>
                {diagnostics.hint} Redirect URI: {diagnostics.redirect_uri}
              </p>
            )}
            {diagnostics && !diagnostics.configured && (
              <p className="ui-hint">YouTube OAuth is not configured on this server yet.</p>
            )}
          </div>

          {/* ---------- Keamanan ---------- */}
          <form onSubmit={savePassword} className="ui-card" style={{ display: "grid", gap: 16 }}>
            <h2 className="ui-subtitle">
              <ShieldCheck size={16} style={{ verticalAlign: "-3px", marginRight: 6 }} />
              Security
            </h2>
            <div>
              <label className="ui-label" htmlFor="current-password">
                Current password
              </label>
              <input
                id="current-password"
                type="password"
                className="ui-input"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                placeholder="Leave empty if you signed up with Google"
              />
            </div>
            <div>
              <label className="ui-label" htmlFor="new-password">
                New password
              </label>
              <input
                id="new-password"
                type="password"
                className="ui-input"
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            <div>
              <label className="ui-label" htmlFor="confirm-password">
                Confirm new password
              </label>
              <input
                id="confirm-password"
                type="password"
                className="ui-input"
                autoComplete="new-password"
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </div>
            <button type="submit" className="ui-btn ui-btn-ghost" disabled={savingPassword}>
              <Save size={15} /> {savingPassword ? "Updating…" : "Update password"}
            </button>
          </form>
        </div>
      </main>

      <SiteFooter />

      <ConfirmDialog
        open={confirmDisconnect}
        title="Disconnect YouTube?"
        description={
          <>
            Clipzy AI will stop auto-uploading clips to{" "}
            <strong>{youtube.channel_name || "your YouTube channel"}</strong> and the stored access token will be
            removed. You can reconnect anytime.
          </>
        }
        confirmLabel="Yes, disconnect"
        cancelLabel="Keep connected"
        danger
        busy={youtubeBusy}
        onCancel={() => setConfirmDisconnect(false)}
        onConfirm={() => {
          setConfirmDisconnect(false)
          void disconnectYouTube()
        }}
      />
    </div>
  )
}
