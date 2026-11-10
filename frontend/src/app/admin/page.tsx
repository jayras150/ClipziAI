"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import {
  ArrowLeft,
  Ban,
  Coins,
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
  Save,
  ShieldCheck,
  Users,
} from "lucide-react"

import {
  api,
  AdminStatsData,
  AdminUserRow,
  AuditRow,
  WatermarkConfigData,
} from "@/lib/api"
import { readApiError } from "@/lib/api-errors"

type Tab = "overview" | "watermark" | "users" | "audit"

const PLANS = ["free", "standar", "pro", "team"]
const POSITIONS: [string, string][] = [
  ["top-left", "kiri atas"],
  ["top-right", "kanan atas"],
  ["bottom-left", "kiri bawah"],
  ["bottom-right", "kanan bawah"],
  ["center", "tengah"],
]

/** Posisi teks pada preview watermark (skala preview 220px). */
function previewStyle(config: WatermarkConfigData): React.CSSProperties {
  const m = Math.min(26, Math.round(config.margin / 3))
  const base: React.CSSProperties = {
    position: "absolute",
    fontSize: Math.max(10, Math.round(220 * config.scale * 0.22)),
    opacity: config.opacity,
    color: config.text_color,
    fontWeight: 800,
    letterSpacing: 0.3,
    textShadow: "0 2px 8px rgba(0,0,0,.65)",
  }
  switch (config.position) {
    case "top-left":
      return { ...base, left: m, top: m }
    case "top-right":
      return { ...base, right: m, top: m }
    case "bottom-left":
      return { ...base, left: m, bottom: m }
    case "center":
      return { ...base, left: "50%", top: "50%", transform: "translate(-50%,-50%)" }
    default:
      return { ...base, right: m, bottom: m }
  }
}

export default function AdminPage() {
  const [token, setToken] = useState("")
  const [allowed, setAllowed] = useState<boolean | null>(null)
  const [tab, setTab] = useState<Tab>("overview")
  const [stats, setStats] = useState<AdminStatsData | null>(null)
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [audit, setAudit] = useState<AuditRow[]>([])
  const [watermark, setWatermark] = useState<WatermarkConfigData | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  const load = useCallback(async (stored: string, which: Tab) => {
    setBusy(true)
    setError("")
    try {
      if (which === "overview") setStats(await api.getAdminStats(stored))
      if (which === "watermark") setWatermark(await api.getWatermarkConfig(stored))
      if (which === "users") setUsers(await api.listAdminUsers(stored))
      if (which === "audit") setAudit(await api.listAuditLogs(stored))
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Gagal memuat data admin."))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    const stored = typeof window === "undefined" ? null : localStorage.getItem("token")
    if (!stored) {
      window.location.href = "/login"
      return
    }
    setToken(stored)
    api
      .getProfile(stored)
      .then((profile) => {
        setAllowed(Boolean(profile.is_admin))
        if (profile.is_admin) void load(stored, "overview")
      })
      .catch(() => setAllowed(false))
  }, [load])

  const switchTab = (next: Tab) => {
    setTab(next)
    setNotice("")
    if (token) void load(token, next)
  }

  const saveWatermark = async () => {
    if (!watermark || !token) return
    setSaving(true)
    setError("")
    setNotice("")
    try {
      const saved = await api.updateWatermarkConfig(token, watermark)
      setWatermark(saved)
      setNotice("Pengaturan watermark disimpan.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Gagal menyimpan watermark."))
    } finally {
      setSaving(false)
    }
  }

  const toggleBan = async (row: AdminUserRow) => {
    if (!token) return
    setError("")
    try {
      if (row.is_banned) {
        await api.unbanAdminUser(token, row.id)
        setNotice(`User ${row.email} di-unban.`)
      } else {
        const reason = window.prompt(`Alasan ban untuk ${row.email}:`, "manual ban")
        if (!reason) return
        await api.banAdminUser(token, row.id, reason)
        setNotice(`User ${row.email} dibanned.`)
      }
      await load(token, "users")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Gagal mengubah status user."))
    }
  }

  const adjustCredits = async (row: AdminUserRow) => {
    if (!token) return
    const raw = window.prompt(`Tambah/kurangi kredit ${row.email} (contoh: 5 atau -3):`, "5")
    if (!raw) return
    const amount = Number(raw)
    if (!Number.isFinite(amount) || amount === 0) {
      setError("Jumlah kredit tidak valid.")
      return
    }
    try {
      const result = await api.adjustUserCredits(token, row.id, amount, "admin adjustment")
      setNotice(`Kredit ${row.email}: ${amount > 0 ? "+" : ""}${amount} → saldo ${result.new_balance}`)
      await load(token, "audit")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Gagal menyesuaikan kredit."))
    }
  }

  return (
    <div className="ui-shell">
      <header className="ui-container ui-container-wide ui-nav">
        <Link className="ui-brand" href="/">
          <span className="ui-brand-mark">▶</span>
          <span>
            clipzy<em>AI</em>
          </span>
        </Link>
        <nav className="ui-nav-links">
          <Link href="/admin">Admin</Link>
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/pricing">Pricing</Link>
        </nav>
        <div className="ui-nav-actions">
          <span className="ui-badge ui-badge-gold">
            <ShieldCheck size={12} /> admin
          </span>
        </div>
      </header>

      <main className="ui-container ui-container-wide" style={{ padding: "24px 0 52px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <Link className="ui-back" href="/dashboard">
            <ArrowLeft size={14} /> Dashboard
          </Link>
          <div className="ui-kicker">Control room</div>
        </div>
        <h1 className="ui-title" style={{ marginTop: 8 }}>Admin panel</h1>
        <p className="ui-muted" style={{ marginTop: 4 }}>
          Kelola watermark platform, pantau aktivitas, dan atur pengguna.
        </p>

        {error && (
          <div className="ui-alert" style={{ marginTop: 16, borderColor: "rgba(240,120,120,.35)" }}>
            {error}
          </div>
        )}
        {notice && (
          <div className="ui-alert" style={{ marginTop: 16 }}>
            <CheckCircle2 size={15} /> {notice}
          </div>
        )}

        {allowed === null ? (
          <div className="ui-card" style={{ marginTop: 18, textAlign: "center" }}>
            <LoaderCircle className="animate-spin" size={22} />
          </div>
        ) : !allowed ? (
          <div className="ui-card" style={{ marginTop: 18 }}>
            <h2 className="ui-subtitle">Akses ditolak</h2>
            <p className="ui-muted" style={{ marginTop: 6 }}>
              Email akun ini tidak terdaftar di <code>ADMIN_EMAILS</code> pada server.
            </p>
            <Link className="ui-btn ui-btn-ghost" href="/dashboard" style={{ marginTop: 14 }}>
              <ArrowLeft size={14} /> Kembali
            </Link>
          </div>
        ) : (
          <>
            <div className="ui-tabs" style={{ marginTop: 18 }}>
              {(
                [
                  ["overview", "Ringkasan"],
                  ["watermark", "Watermark"],
                  ["users", "Pengguna"],
                  ["audit", "Audit"],
                ] as [Tab, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  className={`ui-tab${tab === key ? " active" : ""}`}
                  onClick={() => switchTab(key)}
                >
                  {label}
                </button>
              ))}
              <button className="ui-tab" onClick={() => switchTab(tab)} disabled={busy}>
                <RefreshCw size={13} /> {busy ? "Memuat…" : "Muat ulang"}
              </button>
            </div>

            {tab === "overview" && (
              <section style={{ marginTop: 16, display: "grid", gap: 14 }}>
                <div className="ui-admin-grid">
                  <div className="ui-stat">
                    <span>Total user</span>
                    <b>{stats?.total_users ?? "—"}</b>
                    <small>{stats?.banned_users ?? 0} banned</small>
                  </div>
                  <div className="ui-stat">
                    <span>Task</span>
                    <b>{stats?.total_tasks ?? "—"}</b>
                    <small>{stats?.completed_tasks ?? 0} selesai</small>
                  </div>
                  <div className="ui-stat">
                    <span>Klip</span>
                    <b>{stats?.total_clips ?? "—"}</b>
                    <small>total dihasilkan</small>
                  </div>
                  <div className="ui-stat">
                    <span>Kredit terpakai</span>
                    <b>{stats?.credits_spent ?? "—"}</b>
                    <small>kumulatif</small>
                  </div>
                </div>

                <div className="ui-card">
                  <h2 className="ui-subtitle">Task per hari · 14 hari</h2>
                  <div className="ui-bars">
                    {(stats?.tasks_per_day || []).map((day) => (
                      <span
                        key={day.date || Math.random()}
                        title={`${day.date}: ${day.count}`}
                        style={{ height: `${Math.min(100, 8 + day.count * 12)}%` }}
                      />
                    ))}
                    {!stats?.tasks_per_day?.length && <span className="ui-muted">Belum ada data</span>}
                  </div>
                </div>

                <div className="ui-card">
                  <h2 className="ui-subtitle">Task terbaru</h2>
                  <table className="ui-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Status</th>
                        <th>Klip</th>
                        <th>Waktu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(stats?.recent_tasks || []).map((task) => (
                        <tr key={task.id}>
                          <td>{task.user_email || "—"}</td>
                          <td>{task.status}</td>
                          <td>{task.total_clips ?? 0}</td>
                          <td>{task.created_at ? new Date(task.created_at).toLocaleString() : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {tab === "watermark" && (
              <section className="ui-admin-split" style={{ marginTop: 16 }}>
                <div className="ui-card">
                  <h2 className="ui-subtitle">Watermark platform</h2>
                  <p className="ui-hint" style={{ marginBottom: 12 }}>
                    Diterapkan otomatis ke plan terpilih (default free), termasuk hasil merge/split.
                  </p>
                  {!watermark ? (
                    <LoaderCircle className="animate-spin" size={20} />
                  ) : (
                    <>
                      <label className="ui-switch" style={{ marginBottom: 12 }}>
                        <input
                          type="checkbox"
                          checked={watermark.enabled}
                          onChange={(e) => setWatermark({ ...watermark, enabled: e.target.checked })}
                        />
                        <span>Aktifkan watermark wajib</span>
                      </label>

                      <div className="ui-opt-grid">
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-text">Teks</label>
                          <input
                            id="wm-text"
                            className="ui-input"
                            value={watermark.text || ""}
                            onChange={(e) => setWatermark({ ...watermark, text: e.target.value })}
                          />
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-image">URL logo (opsional)</label>
                          <input
                            id="wm-image"
                            className="ui-input"
                            placeholder="https://cdn.../logo.png"
                            value={watermark.image_url || ""}
                            onChange={(e) => setWatermark({ ...watermark, image_url: e.target.value || null })}
                          />
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-position">Posisi</label>
                          <select
                            id="wm-position"
                            className="ui-input"
                            value={watermark.position}
                            onChange={(e) => setWatermark({ ...watermark, position: e.target.value })}
                          >
                            {POSITIONS.map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-opacity">Opacity</label>
                          <input
                            id="wm-opacity" type="number" min="0.1" max="1" step="0.05"
                            className="ui-input"
                            value={watermark.opacity}
                            onChange={(e) => setWatermark({ ...watermark, opacity: Number(e.target.value) })}
                          />
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-scale">Ukuran</label>
                          <input
                            id="wm-scale" type="number" min="0.05" max="0.6" step="0.01"
                            className="ui-input"
                            value={watermark.scale}
                            onChange={(e) => setWatermark({ ...watermark, scale: Number(e.target.value) })}
                          />
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-margin">Margin (px)</label>
                          <input
                            id="wm-margin" type="number" min="0" max="200" step="4"
                            className="ui-input"
                            value={watermark.margin}
                            onChange={(e) => setWatermark({ ...watermark, margin: Number(e.target.value) })}
                          />
                        </div>
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="wm-color">Warna teks</label>
                          <input
                            id="wm-color" type="color"
                            className="ui-input"
                            value={watermark.text_color}
                            onChange={(e) => setWatermark({ ...watermark, text_color: e.target.value })}
                          />
                        </div>
                      </div>
                      <div style={{ marginTop: 12 }}>
                        <span className="ui-opt-label">Berlaku untuk plan</span>
                        <div className="ui-switch-list">
                          {PLANS.map((plan) => (
                            <label className="ui-switch" key={plan}>
                              <input
                                type="checkbox"
                                checked={watermark.plans.includes(plan)}
                                onChange={(e) => {
                                  const plans = e.target.checked
                                    ? [...watermark.plans, plan]
                                    : watermark.plans.filter((p) => p !== plan)
                                  setWatermark({ ...watermark, plans: plans.length ? plans : ["free"] })
                                }}
                              />
                              <span>{plan}</span>
                            </label>
                          ))}
                        </div>
                      </div>

                      <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}>
                        <button className="ui-btn ui-btn-gold" onClick={saveWatermark} disabled={saving}>
                          {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
                          Simpan
                        </button>
                        <span className="ui-hint">Berlaku ±60 detik (cache worker).</span>
                      </div>
                    </>
                  )}
                </div>

                <div className="ui-card" style={{ textAlign: "center" }}>
                  <h2 className="ui-subtitle">Preview</h2>
                  <div className="ui-wm-preview">
                    <div className="ui-wm-shade" />
                    {watermark?.text && <span style={previewStyle(watermark)}>{watermark.text}</span>}
                  </div>
                  <p className="ui-hint" style={{ marginTop: 10 }}>
                    9:16 · {watermark?.position} · opacity {watermark?.opacity}
                  </p>
                </div>
              </section>
            )}

            {tab === "users" && (
              <section className="ui-card" style={{ marginTop: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h2 className="ui-subtitle" style={{ margin: 0 }}>
                    <Users size={16} /> Pengguna ({users.length})
                  </h2>
                  <button className="ui-btn ui-btn-ghost" onClick={() => load(token, "users")} disabled={busy}>
                    <RefreshCw size={13} /> {busy ? "Memuat…" : "Muat ulang"}
                  </button>
                </div>
                <table className="ui-table" style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Nama</th>
                      <th>Status</th>
                      <th>Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((row) => (
                      <tr key={row.id}>
                        <td>{row.email || "—"}</td>
                        <td>{row.name}</td>
                        <td>
                          {row.is_banned ? (
                            <span className="ui-badge" style={{ color: "#f0a3a3" }}>banned</span>
                          ) : row.is_active ? (
                            <span className="ui-badge ui-badge-success">aktif</span>
                          ) : (
                            <span className="ui-badge">nonaktif</span>
                          )}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button
                              className="clip-icon-btn"
                              title={row.is_banned ? "Unban" : "Ban user"}
                              onClick={() => toggleBan(row)}
                            >
                              {row.is_banned ? <CheckCircle2 size={13} /> : <Ban size={13} />}
                            </button>
                            <button
                              className="clip-icon-btn"
                              title="Sesuaikan kredit"
                              onClick={() => adjustCredits(row)}
                            >
                              <Coins size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!users.length && (
                      <tr>
                        <td colSpan={4} className="ui-muted">Belum ada data.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </section>
            )}

            {tab === "audit" && (
              <section className="ui-card" style={{ marginTop: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h2 className="ui-subtitle" style={{ margin: 0 }}>Audit log</h2>
                  <button className="ui-btn ui-btn-ghost" onClick={() => load(token, "audit")} disabled={busy}>
                    <RefreshCw size={13} /> {busy ? "Memuat…" : "Muat ulang"}
                  </button>
                </div>
                <table className="ui-table" style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>Waktu</th>
                      <th>Aktor</th>
                      <th>Aksi</th>
                      <th>IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((row) => (
                      <tr key={row.id}>
                        <td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                        <td>{row.actor_email || row.actor_type}</td>
                        <td>{row.action}</td>
                        <td>{row.ip_address || "—"}</td>
                      </tr>
                    ))}
                    {!audit.length && (
                      <tr>
                        <td colSpan={4} className="ui-muted">Belum ada aktivitas.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </section>
            )}


          </>
        )}
      </main>
    </div>
  )

}
