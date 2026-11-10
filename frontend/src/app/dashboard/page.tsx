"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  Upload,
  Play,
  Youtube,
  Unlink,
  LoaderCircle,
  Link2,
  Trash2,
  Download,
  CheckCircle2,
  Clock,
  AlertTriangle,
  FileVideo,
  RefreshCw,
  Layers,
  Scissors,
  ArrowLeft,
  ClipboardPaste,
  Eraser,
  Zap,
  RotateCcw,
  Droplets,
} from "lucide-react"

import { api, ClipData, MusicTrackData, TaskData } from "@/lib/api"
import { readApiError } from "@/lib/api-errors"
import { requestYouTubeAccessToken } from "@/lib/social"
import ConfirmDialog from "@/components/ConfirmDialog"
import ClipModal from "@/components/ClipModal"
import SiteFooter from "@/components/SiteFooter"
import UserMenu from "@/components/UserMenu"

const ACTIVE_STATUSES = ["queued", "processing"]

/**
 * Opsi gaya subtitle yang dikirim sebagai `editing_options.caption_style`.
 * Nilainya dipetakan ke preset CAPTION_STYLES di backend
 * (`app/services/processor.py`) â€” warna, garis tepi, kotak latar, dan posisi.
 */
const SUBTITLE_STYLE_OPTIONS = [
  { value: "", label: "Bawaan" },
  { value: "classic", label: "Classic putih" },
  { value: "gold", label: "Gold tebal" },
  { value: "boxed", label: "Kotak hitam" },
  { value: "neon", label: "Neon cyan" },
  { value: "top", label: "Atas bersih" },
  { value: "center", label: "Hook tengah" },
]

/** Pratinjau kecil di kartu "Style subtitle" agar gaya terlihat sebelum proses. */
function subtitlePreviewStyle(style: string): React.CSSProperties {
  switch (style) {
    case "gold":
      return { color: "#f4c76b", fontSize: 20, textShadow: "0 0 2px #000, 1px 1px 0 #000, -1px -1px 0 #000" }
    case "neon":
      return { color: "#7ce9dc", fontSize: 20, textShadow: "0 0 6px rgba(124,233,220,.55), 1px 1px 0 #000" }
    case "boxed":
      return { color: "#ffffff", fontSize: 15, background: "rgba(0,0,0,.72)", borderRadius: 3, padding: "3px 8px" }
    case "top":
      return { color: "#ffffff", fontSize: 16, textShadow: "1px 1px 0 #000, -1px -1px 0 #000" }
    case "center":
      return { color: "#f4c76b", fontSize: 22, textShadow: "0 0 3px #000, 2px 2px 0 #000, -2px -2px 0 #000" }
    case "classic":
      return { color: "#ffffff", fontSize: 16, textShadow: "1px 1px 0 #000, -1px -1px 0 #000" }
    default:
      return { color: "#e8e9ee", fontSize: 15 }
  }
}

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  error: "Failed",
  canceled: "Canceled",
}

function statusBadgeClass(status: string): string {
  if (status === "completed") return "ui-badge ui-badge-success"
  if (status === "processing") return "ui-badge ui-badge-gold"
  if (status === "error") return "ui-badge"
  return "ui-badge"
}

function statusBadgeStyle(status: string): React.CSSProperties | undefined {
  if (status === "error") return { background: "rgba(240, 120, 120, 0.14)", color: "#f0a3a3" }
  return undefined
}

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url.slice(0, 42)
  }
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ""
  const mb = bytes / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}

/** Pita skor viral: dipakai untuk warna badge, bar, dan nomor. */
function viralBand(score: number): "excellent" | "good" | "fair" | "low" {
  if (score >= 80) return "excellent"
  if (score >= 65) return "good"
  if (score >= 50) return "fair"
  return "low"
}

/** Tooltip breakdown faktor skor viral (persen 0-100). */
function viralTooltip(factors: Record<string, any> | null | undefined): string {
  if (!factors) return "Skor viral belum dihitung"
  const pct = (key: string) =>
    typeof factors[key] === "number" ? `${Math.round(factors[key] * 100)}%` : "â€”"
  const lines = [
    `Hook: ${pct("hook")}`,
    `Durasi pas: ${pct("duration")}`,
    `Pacing: ${pct("pacing")}`,
    `Emosi: ${pct("emotion")}`,
    `Kejelasan: ${pct("clarity")}`,
  ]
  if (factors.reasoning) lines.push("", String(factors.reasoning))
  if (factors.estimated) lines.push("", "(estimasi â€” klip lama tanpa transkrip tersimpan)")
  return lines.join("\n")
}

export default function DashboardPage() {
  const [token, setToken] = useState("")
  const [activeTab, setActiveTab] = useState<"upload" | "projects">("upload")
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeMessage, setYoutubeMessage] = useState("")
  // Plan user aktif — dipakai untuk chip "Watermark Clipzy aktif" (plan free).
  const [planType, setPlanType] = useState("")
  // Konfirmasi wajib sebelum memutus koneksi YouTube (menghapus token tersimpan).
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)

  const [tasks, setTasks] = useState<TaskData[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [urlValue, setUrlValue] = useState("")
  const [startTimeValue, setStartTimeValue] = useState("")
  const [endTimeValue, setEndTimeValue] = useState("")
  const [aspectRatioValue, setAspectRatioValue] = useState("9:16")
  const [captionTextValue, setCaptionTextValue] = useState("")
  const [captionStyle, setCaptionStyle] = useState("")
  const [speedValue, setSpeedValue] = useState("1.0")
  // Fase 2: gaya & polish
  const [filterPreset, setFilterPreset] = useState("none")
  const [blurFill, setBlurFill] = useState(false)
  const [trimSilence, setTrimSilence] = useState(false)
  const [cleanAudio, setCleanAudio] = useState(false)
  const [watermarkUrl, setWatermarkUrl] = useState("")
  const [watermarkPosition, setWatermarkPosition] = useState("bottom-right")
  const [introUrl, setIntroUrl] = useState("")
  const [outroUrl, setOutroUrl] = useState("")
  // Auto zoom follow-speaker
  const [autoZoom, setAutoZoom] = useState("off")
  const [zoomLevel, setZoomLevel] = useState("1.3")
  // Musik latar
  const [musicLibrary, setMusicLibrary] = useState<MusicTrackData[]>([])
  const [musicUrl, setMusicUrl] = useState("")
  const [musicVolume, setMusicVolume] = useState("0.22")
  const [musicDucking, setMusicDucking] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [taskError, setTaskError] = useState("")
  const [notice, setNotice] = useState("")

  const [openTaskId, setOpenTaskId] = useState("")
  const [clips, setClips] = useState<ClipData[]>([])
  const [clipsLoading, setClipsLoading] = useState(false)
  // Editing lanjutan: pilih klip untuk digabung / potong
  const [selectedClips, setSelectedClips] = useState<string[]>([])
  const [composeTransition, setComposeTransition] = useState("fade")
  const [splitAt, setSplitAt] = useState<Record<string, string>>({})
  const [editingBusy, setEditingBusy] = useState(false)
  // Skor viral: tombol â†» per klip sedang menghitung ulang?
  const [scoreBusy, setScoreBusy] = useState<Record<string, boolean>>({})
  // Popup klip: player video + metadata AI (judul/deskripsi/tag) + download + upload YouTube
  const [modalClipId, setModalClipId] = useState("")


  const fileInputRef = useRef<HTMLInputElement>(null)


  const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem("token"))

  /** Klip yang sedang dibuka di popup (selalu ambil versi terbaru dari state). */
  const modalClip = clips.find((item) => item.id === modalClipId) || null

  /** Sinkronkan perubahan dari popup (metadata AI / upload YouTube) ke kartu klip. */
  const patchClip = useCallback((clipId: string, patch: Partial<ClipData>) => {
    setClips((current) =>
      current.map((item) => (item.id === clipId ? { ...item, ...patch } : item)),
    )
  }, [])

  const loadClips = useCallback(async (authToken: string, taskId: string) => {
    setClipsLoading(true)
    try {
      setClips(await api.getTaskClips(authToken, taskId))
    } catch {
      setClips([])
    } finally {
      setClipsLoading(false)
    }
  }, [])

  const refreshTasks = useCallback(async (authToken: string) => {
    try {
      const data = await api.listTasks(authToken)
      setTasks(data.tasks)
      return data.tasks
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not load your projects."))
      return []
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => {
    const stored = getToken()
    if (!stored) {
      window.location.href = "/login"
      return
    }
    setToken(stored)
    refreshTasks(stored)

    api
      .getYouTubeStatus(stored)
      .then(setYoutube)
      .catch(() => setYoutubeMessage("Could not load your YouTube status."))

    api
      .getProfile(stored)
      .then((profile) => setPlanType(profile.plan_type))
      .catch(() => setPlanType(""))

    // Library musik latar (track disimpan di R2).
    api
      .getMusicLibrary(stored)
      .then(setMusicLibrary)
      .catch(() => setMusicLibrary([]))

    const params = new URLSearchParams(window.location.search)
    const prefill = params.get("video_url")
    if (prefill) {
      setUrlValue(prefill)
      setActiveTab("upload")
    }
    const status = params.get("youtube")
    if (status === "connected") setYoutubeMessage("YouTube connected successfully.")
    if (status === "denied") setYoutubeMessage("YouTube permission was cancelled.")
    if (status === "error") setYoutubeMessage("YouTube connection failed. Check the Google OAuth configuration.")
  }, [refreshTasks])

  // Poll daftar task selama masih ada yang queued/processing.
  useEffect(() => {
    if (!token) return
    const hasActive = tasks.some((task) => ACTIVE_STATUSES.includes(task.status))
    if (!hasActive) return
    const timer = window.setInterval(async () => {
      const fresh = await refreshTasks(token)
      const openTask = fresh.find((task) => task.id === openTaskId)
      if (openTask && openTask.status === "completed") {
        loadClips(token, openTask.id)
      }
    }, 5000)
    return () => window.clearInterval(timer)
  }, [token, tasks, openTaskId, refreshTasks, loadClips])

  const connectYouTube = async () => {
    const stored = getToken()
    if (!stored) {
      window.location.href = "/login"
      return
    }
    setYoutubeLoading(true)
    setYoutubeMessage("")
    try {
      window.location.href = await api.getYouTubeAuthUrl(stored)
    } catch (error: any) {
      const detail = String(error.response?.data?.detail || "")
      const originalMessage = readApiError(error.response?.data, "Could not start the YouTube connection.")

      // 409 = konfigurasi OAuth server belum lengkap (contoh paling umum:
      // redirect URI belum terdaftar di Google Cloud Console). Pakai alur token
      // Google Identity Services yang tidak membutuhkan redirect URI sama sekali.
      if (error.response?.status !== 409) {
        setYoutubeMessage(originalMessage)
        setYoutubeLoading(false)
        return
      }

      try {
        setYoutubeMessage("Opening Google consentâ€¦")
        const diagnostics = await api.getYouTubeDiagnostics(stored)
        const accessToken = await requestYouTubeAccessToken(
          diagnostics.gis_client_id || diagnostics.client_id || "",
        )
        const connected = await api.setYouTubeAccessToken(stored, accessToken)
        setYoutube({ connected: true, channel_name: connected.channel_name })
        setYoutubeMessage(connected.message || "YouTube connected.")
      } catch (fallbackError: any) {
        setYoutubeMessage([fallbackError?.message || "Could not connect YouTube.", detail].filter(Boolean).join(" "))
      } finally {
        setYoutubeLoading(false)
      }
    }
  }

  const disconnectYouTube = async () => {
    const stored = getToken()
    if (!stored) return
    setYoutubeLoading(true)
    try {
      await api.disconnectYouTube(stored)
      setYoutube({ connected: false })
      setYoutubeMessage("YouTube connection removed.")
    } catch {
      setYoutubeMessage("Could not remove the YouTube connection.")
    } finally {
      setYoutubeLoading(false)
    }
  }

  const submitUrl = async (event: React.FormEvent) => {
    event.preventDefault()
    const stored = getToken()
    if (!stored) {
      window.location.href = "/login"
      return
    }
    const url = urlValue.trim()
    if (!/^https?:\/\/.+\..+/i.test(url)) {
      setTaskError("Enter a valid video URL (starting with http:// or https://).")
      return
    }
    setSubmitting(true)
    setTaskError("")
    setNotice("")
    try {
      const editingOptions: Record<string, any> = {}
      const startTime = parseFloat(startTimeValue)
      const endTime = parseFloat(endTimeValue)
      const caption = captionTextValue.trim()
      const speed = parseFloat(speedValue)
      if (!Number.isNaN(startTime)) editingOptions.start_time = startTime
      if (!Number.isNaN(endTime)) editingOptions.end_time = endTime
      if (aspectRatioValue) editingOptions.aspect_ratio = aspectRatioValue
      if (caption) editingOptions.caption_text = caption
      if (captionStyle) editingOptions.caption_style = captionStyle
      if (!Number.isNaN(speed) && speed !== 1) editingOptions.speed = speed

      // Fase 2: gaya & polish
      if (filterPreset && filterPreset !== "none") editingOptions.filter_preset = filterPreset
      if (blurFill) editingOptions.blur_fill = true
      if (trimSilence) editingOptions.remove_silence = true
      if (cleanAudio) editingOptions.enhance_audio = true
      const watermark = watermarkUrl.trim()
      if (watermark) {
        editingOptions.watermark_url = watermark
        editingOptions.watermark_position = watermarkPosition
      }
      const intro = introUrl.trim()
      if (intro) editingOptions.intro_url = intro
      const outro = outroUrl.trim()
      if (outro) editingOptions.outro_url = outro

      // Auto zoom follow-speaker
      if (autoZoom === "speaker") {
        editingOptions.auto_zoom = "speaker"
        const zoom = parseFloat(zoomLevel)
        if (!Number.isNaN(zoom) && zoom !== 1) editingOptions.zoom_level = zoom
      }

      // Musik latar
      if (musicUrl) {
        editingOptions.music_url = musicUrl
        const vol = parseFloat(musicVolume)
        if (!Number.isNaN(vol)) editingOptions.music_volume = vol
        editingOptions.music_ducking = musicDucking
      }

      const task = await api.createTask(stored, url, editingOptions)
      setUrlValue("")
      if (task.status === "error") {
        setTaskError(task.error_message || "The task was created but could not be sent to a GPU worker.")
      } else {
        setNotice("Task created â€” Clipzy AI is processing your video.")
      }
      await refreshTasks(stored)
      setActiveTab("projects")
      setOpenTaskId(task.id)
      loadClips(stored, task.id)
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not start processing this video."))
    } finally {
      setSubmitting(false)
    }
  }

  /** Tempel link dari clipboard; browser bisa menolak (butuh HTTPS + izin). */
  const pasteFromClipboard = async () => {
    setTaskError("")
    setNotice("")
    try {
      if (!navigator.clipboard?.readText) throw new Error("Clipboard API tidak tersedia")
      const text = (await navigator.clipboard.readText()).trim()
      if (!text) {
        setNotice("Clipboard kosong â€” salin link video dulu.")
        return
      }
      setUrlValue(text)
      setNotice("Link ditempel dari clipboard.")
    } catch {
      setTaskError("Browser memblokir akses clipboard. Klik kolom URL lalu tekan Ctrl+V.")
    }
  }

  /** Kosongkan kolom URL dan kembalikan fokus ke input. */
  const clearUrl = () => {
    setUrlValue("")
    setTaskError("")
    setNotice("")
    document.getElementById("video-url")?.focus()
  }

  /** Reset semua opsi editing (URL tidak ikut dihapus — itu fungsi Clear). */
  const resetEditingOptions = () => {
    setStartTimeValue("")
    setEndTimeValue("")
    setAspectRatioValue("9:16")
    setCaptionTextValue("")
    setCaptionStyle("")
    setSpeedValue("1.0")
    setFilterPreset("none")
    setBlurFill(false)
    setTrimSilence(false)
    setCleanAudio(false)
    setWatermarkUrl("")
    setWatermarkPosition("bottom-right")
    setIntroUrl("")
    setOutroUrl("")
    setAutoZoom("off")
    setZoomLevel("1.3")
    setMusicUrl("")
    setMusicVolume("0.22")
    setMusicDucking(true)
    setTaskError("")
    setNotice("Opsi editing dikembalikan ke default.")
  }

  /** Kembali ke halaman sebelumnya; kalau tidak ada riwayat, ke landing. */
  const goBack = () => {
    if (typeof window === "undefined") return
    if (window.history.length > 1) window.history.back()
    else window.location.href = "/"
  }

  const openTask = (task: TaskData) => {
    setOpenTaskId(task.id)
    loadClips(token, task.id)
  }

  const removeTask = async (taskId: string) => {
    if (!window.confirm("Delete this project?")) return
    try {
      await api.deleteTask(token, taskId)
      if (openTaskId === taskId) {
        setOpenTaskId("")
        setClips([])
      }
      await refreshTasks(token)
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not delete the project."))
    }
  }
  const toggleClipSelection = (clipId: string) => {
    setSelectedClips((current) =>
      current.includes(clipId) ? current.filter((id) => id !== clipId) : [...current, clipId],
    )
  }

  /** Hitung ulang skor viral satu klip (tombol â†» di kartu klip). */
  const recalcViralScore = async (clip: ClipData) => {
    if (!openTaskId) return
    setScoreBusy((current) => ({ ...current, [clip.id]: true }))
    setTaskError("")
    setNotice("")
    try {
      const result = await api.getViralScore(token, clip.id, true)
      setNotice(`Skor viral klip #${clip.clip_index + 1} diperbarui: ${Math.round(result.score)}/100`)
      await loadClips(token, openTaskId)
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not recalculate the viral score."))
    } finally {
      setScoreBusy((current) => {
        const next = { ...current }
        delete next[clip.id]
        return next
      })
    }
  }

  const mergeSelectedClips = async () => {
    if (!openTaskId || selectedClips.length < 2) return
    setEditingBusy(true)
    setTaskError("")
    setNotice("")
    try {
      const task = await api.composeClips(token, openTaskId, selectedClips, composeTransition)
      setNotice(
        task.status === "error"
          ? task.error_message || "Compose dibuat tetapi gagal dikirim ke worker."
          : `Gabungan ${selectedClips.length} klip sedang diproses.`,
      )
      setSelectedClips([])
      await refreshTasks(token)
      setActiveTab("projects")
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not merge the selected clips."))
    } finally {
      setEditingBusy(false)
    }
  }

  const splitClipAt = async (clip: ClipData) => {
    if (!openTaskId) return
    const value = parseFloat(splitAt[clip.id] || "")
    if (Number.isNaN(value) || value <= 0 || value >= clip.duration) {
      setTaskError(`Titik potong harus antara 0 dan ${clip.duration.toFixed(1)} detik.`)
      return
    }
    setEditingBusy(true)
    setTaskError("")
    setNotice("")
    try {
      const task = await api.splitClip(token, openTaskId, clip.id, value)
      setNotice(
        task.status === "error"
          ? task.error_message || "Split dibuat tetapi gagal dikirim ke worker."
          : `Klip #${clip.clip_index} dipotong di ${value.toFixed(1)} detik.`,
      )
      await refreshTasks(token)
      setActiveTab("projects")
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not split this clip."))
    } finally {
      setEditingBusy(false)
    }
  }



  const onPickFile = (file: File | null) => {
    if (!file) return
    setTaskError("")
    setNotice(
      `"${file.name}" selected. Direct file upload is not available yet â€” paste a YouTube, TikTok or Instagram link above to start processing.`,
    )
  }

  const openTaskData = tasks.find((task) => task.id === openTaskId) || null
  // Contoh teks pratinjau: pakai caption yang diketik user agar terasa nyata.
  const subtitlePreviewText = (captionTextValue.trim() || "Contoh caption").slice(0, 24)
  // Estimasi kasar untuk user; kalau trim diisi, hitung dari durasi potongan.
  const trimSeconds = (() => {
    const start = parseFloat(startTimeValue)
    const end = parseFloat(endTimeValue)
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) return end - start
    return null
  })()
  const renderEstimate = trimSeconds
    ? `≈ ${trimSeconds.toFixed(1)}s per klip · estimasi render ±${Math.max(
        2,
        Math.round((trimSeconds * 3) / 60),
      )} menit`
    : "3 klip · estimasi render ±3–5 menit · 1 credit/klip"

  return (
    <div className="ui-shell">
      <header className="ui-container ui-container-wide ui-nav">
        <Link className="ui-brand" href="/">
          <span className="ui-brand-mark">â–¶</span>
          <span>
            clipzy<em>AI</em>
          </span>
        </Link>
        <nav className="ui-nav-links">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/#features">Features</Link>
          <Link href="/#how">How it works</Link>
          <Link href="/#demo">Demo</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/contact">Contact</Link>
        </nav>
        <div className="ui-nav-actions">
          {youtube.connected ? (
            <>
              <span
                className="ui-chip ui-chip-success"
                title={`YouTube: ${youtube.channel_name || "connected"}`}
              >
                <Youtube size={14} />
                {youtube.channel_name || "YouTube connected"}
              </span>
              {/* Tombol ini TIDAK langsung memutus koneksi: buka konfirmasi dulu. */}
              <button
                type="button"
                onClick={() => setConfirmDisconnect(true)}
                disabled={youtubeLoading}
                className="ui-btn ui-btn-ghost"
              >
                {youtubeLoading ? <LoaderCircle size={15} className="animate-spin" /> : <Unlink size={15} />}
                Disconnect
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={connectYouTube}
              disabled={youtubeLoading}
              className="ui-btn ui-btn-ghost"
            >
              {youtubeLoading ? <LoaderCircle size={15} className="animate-spin" /> : <Youtube size={15} />}
              Connect YouTube
            </button>
          )}
          <UserMenu />
        </div>
      </header>

      <main className="ui-container ui-container-wide" style={{ padding: "24px 0 52px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 16,
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: 26,
          }}
        >
          <div>
            <button type="button" className="ui-back" onClick={goBack} title="Kembali ke halaman sebelumnya">
              <ArrowLeft size={14} /> Kembali
            </button>
            <div className="ui-kicker" style={{ marginTop: 14 }}>Studio</div>
            <h1 className="ui-title" style={{ marginTop: 8 }}>
              Dashboard
            </h1>
            <p className="ui-muted" style={{ marginTop: 6 }}>
              Manage your video projects and connect your YouTube channel.
            </p>
          </div>
          <div className="ui-tabs">
            <button
              className={`ui-tab${activeTab === "upload" ? " active" : ""}`}
              onClick={() => setActiveTab("upload")}
            >
              Upload
            </button>
            <button
              className={`ui-tab${activeTab === "projects" ? " active" : ""}`}
              onClick={() => setActiveTab("projects")}
            >
              Projects{tasks.length ? ` (${tasks.length})` : ""}
            </button>
          </div>
        </div>

        {youtubeMessage && (
          <div className="ui-alert" style={{ marginBottom: 20 }}>
            <Link2 size={15} /> {youtubeMessage}
          </div>
        )}
        {taskError && (
          <div className="ui-alert" style={{ marginBottom: 20, borderColor: "rgba(240,120,120,.35)" }}>
            <AlertTriangle size={15} /> {taskError}
          </div>
        )}
        {notice && (
          <div className="ui-alert" style={{ marginBottom: 20 }}>
            <CheckCircle2 size={15} /> {notice}
          </div>
        )}


        {activeTab === "upload" ? (
          <div className="ui-stack">
            {/* 1) Kartu upload â€” selalu paling atas. */}
            <section className="ui-card ui-upload-hero">
              <div
                className="ui-dropzone"
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click()
                }}
              >
                <div className="ui-drop-icon">
                  <Upload size={26} />
                </div>
                <p className="ui-drop-title">Drop your video here</p>
                <p className="ui-hint" style={{ marginTop: 6 }}>
                  Click to browse or drag a file â€” you can also paste a link below.
                </p>
                <div className="ui-drop-formats">
                  <span>MP4</span>
                  <span>MOV</span>
                  <span>AVI</span>
                  <span>MAX 2 GB</span>
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
              />
              <p className="ui-hint" style={{ textAlign: "center", marginTop: 10 }}>
                Direct file upload is still rolling out â€” paste a link below for now.
              </p>
            </section>

            {/* 2) Form paste link, lalu 3) opsi editing. */}
            {/* noValidate: validasi dilakukan sendiri di submitUrl supaya pesan
                error konsisten berbahasa Inggris (bukan tooltip bawaan browser). */}
            <form className="ui-card ui-link-card" onSubmit={submitUrl} noValidate>
              <h2 className="ui-subtitle">Paste video link</h2>
              <p className="ui-muted" style={{ marginBottom: 16 }}>
                Clipzy AI picks the best moments, captions them, and crops to the ratio you choose.
              </p>

              <label className="ui-label" htmlFor="video-url">
                Video URL
              </label>
              <div className="ui-url-row">
                <div className="ui-url-field">
                  <Link2 size={16} />
                  <input
                    id="video-url"
                    type="url"
                    value={urlValue}
                    onChange={(event) => setUrlValue(event.target.value)}
                    placeholder="https://youtube.com/watch?v=..."
                    className="ui-input"
                  />
                </div>
                <div className="ui-url-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn-paste"
                    onClick={pasteFromClipboard}
                    title="Paste a link from the clipboard"
                  >
                    <ClipboardPaste size={15} /> Paste
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-clear"
                    onClick={clearUrl}
                    disabled={!urlValue}
                    title="Clear the URL field"
                  >
                    <Eraser size={15} /> Clear
                  </button>
                </div>
              </div>

              {/* Opsi editing manual (Fase 1) â€” setiap kontrol jadi kartu sendiri. */}
              <div className="ui-opt-grid">
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="start-time">Mulai detik</label>
                  <input
                    id="start-time"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="0"
                    value={startTimeValue}
                    onChange={(e) => setStartTimeValue(e.target.value)}
                    className="ui-input"
                  />
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="end-time">Akhir detik</label>
                  <input
                    id="end-time"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="kosong"
                    value={endTimeValue}
                    onChange={(e) => setEndTimeValue(e.target.value)}
                    className="ui-input"
                  />
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="aspect-ratio">Rasio</label>
                  <select
                    id="aspect-ratio"
                    value={aspectRatioValue}
                    onChange={(e) => setAspectRatioValue(e.target.value)}
                    className="ui-input"
                  >
                    <option value="9:16">9:16 vertikal</option>
                    <option value="1:1">1:1 persegi</option>
                    <option value="16:9">16:9 landskap</option>
                  </select>
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="caption-text">Caption</label>
                  <input
                    id="caption-text"
                    type="text"
                    placeholder="teks overlay"
                    value={captionTextValue}
                    onChange={(e) => setCaptionTextValue(e.target.value)}
                    className="ui-input"
                  />
                </div>
                {/* Gaya subtitle: mengatur warna/ketebalan/posisi subtitle SRT
                    yang dibakar (force_style) sekaligus caption teks di atas. */}
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="caption-style">Style subtitle</label>
                  <select
                    id="caption-style"
                    value={captionStyle}
                    onChange={(e) => setCaptionStyle(e.target.value)}
                    className="ui-input"
                  >
                    {SUBTITLE_STYLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <div className="ui-sub-preview" aria-hidden="true">
                    <span style={subtitlePreviewStyle(captionStyle)}>{subtitlePreviewText}</span>
                  </div>
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="speed">Kecepatan</label>
                  <select
                    id="speed"
                    value={speedValue}
                    onChange={(e) => setSpeedValue(e.target.value)}
                    className="ui-input"
                  >
                    <option value="0.25">0.25Ã—</option>
                    <option value="0.5">0.5Ã—</option>
                    <option value="1">1Ã—</option>
                    <option value="1.5">1.5Ã—</option>
                    <option value="2">2Ã—</option>
                    <option value="4">4Ã—</option>
                  </select>
                </div>
              </div>
                {/* Opsi lanjutan (Fase 2) â€” kartu per kontrol. */}
                <details className="ui-opt-details" style={{ marginTop: 14 }}>
                  <summary>Opsi editing lanjutan</summary>
                  <div className="ui-opt-panel">
                    <div className="ui-opt-grid">
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="filter-preset">Filter</label>
                        <select
                          id="filter-preset"
                          value={filterPreset}
                          onChange={(e) => setFilterPreset(e.target.value)}
                          className="ui-input"
                        >
                          <option value="none">none</option>
                          <option value="warm">warm</option>
                          <option value="cool">cool</option>
                          <option value="cinematic">cinematic</option>
                          <option value="bw">b&amp;w</option>
                          <option value="vibrant">vibrant</option>
                          <option value="vintage">vintage</option>
                        </select>
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="watermark-url">Watermark PNG</label>
                        <input
                          id="watermark-url"
                          type="url"
                          placeholder="https://.../logo.png"
                          value={watermarkUrl}
                          onChange={(e) => setWatermarkUrl(e.target.value)}
                          className="ui-input"
                        />
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="watermark-position">Posisi watermark</label>
                        <select
                          id="watermark-position"
                          value={watermarkPosition}
                          onChange={(e) => setWatermarkPosition(e.target.value)}
                          className="ui-input"
                        >
                          <option value="top-left">kiri atas</option>
                          <option value="top-right">kanan atas</option>
                          <option value="bottom-left">kiri bawah</option>
                          <option value="bottom-right">kanan bawah</option>
                          <option value="center">tengah</option>
                        </select>
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="auto-zoom">Auto zoom</label>
                        <select
                          id="auto-zoom"
                          value={autoZoom}
                          onChange={(e) => setAutoZoom(e.target.value)}
                          className="ui-input"
                        >
                          <option value="off">off</option>
                          <option value="speaker">ikut pembicara</option>
                        </select>
                      </div>
                      {autoZoom === "speaker" && (
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="zoom-level">Level zoom</label>
                          <select
                            id="zoom-level"
                            value={zoomLevel}
                            onChange={(e) => setZoomLevel(e.target.value)}
                            className="ui-input"
                          >
                            <option value="1">1.0Ã—</option>
                            <option value="1.3">1.3Ã—</option>
                            <option value="1.6">1.6Ã—</option>
                            <option value="2">2.0Ã—</option>
                          </select>
                        </div>
                      )}
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="music-track">Musik</label>
                        <select
                          id="music-track"
                          value={musicUrl}
                          onChange={(e) => setMusicUrl(e.target.value)}
                          className="ui-input"
                        >
                          <option value="">tanpa musik</option>
                          {musicLibrary.map((track) => (
                            <option key={track.id} value={track.url}>
                              {track.name}
                              {track.mood ? ` Â· ${track.mood}` : ""}
                            </option>
                          ))}
                        </select>
                      </div>
                      {musicUrl && (
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="music-volume">Volume musik</label>
                          <select
                            id="music-volume"
                            value={musicVolume}
                            onChange={(e) => setMusicVolume(e.target.value)}
                            className="ui-input"
                          >
                            <option value="0.12">12%</option>
                            <option value="0.22">22%</option>
                            <option value="0.35">35%</option>
                            <option value="0.5">50%</option>
                          </select>
                        </div>
                      )}
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="intro-url">Intro URL</label>
                        <input
                          id="intro-url"
                          type="url"
                          placeholder="https://.../intro.mp4"
                          value={introUrl}
                          onChange={(e) => setIntroUrl(e.target.value)}
                          className="ui-input"
                        />
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="outro-url">Outro URL</label>
                        <input
                          id="outro-url"
                          type="url"
                          placeholder="https://.../outro.mp4"
                          value={outroUrl}
                          onChange={(e) => setOutroUrl(e.target.value)}
                          className="ui-input"
                        />
                      </div>
                    </div>

                    <div className="ui-switch-list">
                      <label className="ui-switch">
                        <input type="checkbox" id="blur-fill" checked={blurFill} onChange={(e) => setBlurFill(e.target.checked)} />
                        <span>Blur-fill background</span>
                      </label>
                      <label className="ui-switch">
                        <input type="checkbox" id="trim-silence" checked={trimSilence} onChange={(e) => setTrimSilence(e.target.checked)} />
                        <span>Buang jeda (jump cuts)</span>
                      </label>
                      <label className="ui-switch">
                        <input type="checkbox" id="clean-audio" checked={cleanAudio} onChange={(e) => setCleanAudio(e.target.checked)} />
                        <span>Perbaiki audio</span>
                      </label>
                      {musicUrl && (
                        <label className="ui-switch">
                          <input
                            type="checkbox"
                            id="music-ducking"
                            checked={musicDucking}
                            onChange={(e) => setMusicDucking(e.target.checked)}
                          />
                          <span>Ducking musik saat bicara</span>
                        </label>
                      )}
                    </div>
                  </div>
                </details>

                <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <button type="submit" className="ui-btn ui-btn-gold" disabled={submitting}>
                    {submitting ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />}
                    {submitting ? "Startingâ€¦" : "Process"}
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-ghost"
                    onClick={resetEditingOptions}
                    disabled={submitting}
                    title="Kembalikan semua opsi editing ke default"
                  >
                    <RotateCcw size={14} /> Reset opsi
                  </button>
                  {planType === "free" && (
                    <span
                      className="ui-badge ui-badge-gold"
                      style={{ gap: 5 }}
                      title="Semua klip plan free otomatis diberi watermark Clipzy. Upgrade untuk menghapus."
                    >
                      <Droplets size={12} /> Watermark Clipzy aktif
                    </span>
                  )}
                  <span className="ui-hint" style={{ margin: 0 }}>
                    {renderEstimate}
                  </span>
                </div>
            </form>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 className="ui-subtitle" style={{ margin: 0 }}>
                Projects
              </h2>
              <button className="ui-btn ui-btn-ghost" onClick={() => refreshTasks(token)} disabled={tasksLoading}>
                <RefreshCw size={14} /> {tasksLoading ? "Loadingâ€¦" : "Refresh"}
              </button>
            </div>


            {tasksLoading && tasks.length === 0 ? (
              <div className="ui-card" style={{ textAlign: "center" }}>
                <LoaderCircle className="animate-spin" size={22} />
              </div>
            ) : tasks.length === 0 ? (
              <div className="ui-card" style={{ textAlign: "center" }}>
                <FileVideo size={32} className="ui-gold" style={{ margin: "0 auto 10px" }} />
                <p className="ui-muted">No projects yet.</p>
                <button className="ui-btn ui-btn-gold" style={{ marginTop: 14 }} onClick={() => setActiveTab("upload")}>
                  <Play size={15} /> Add your first video
                </button>
              </div>
            ) : (
              <div className="task-grid">
                {tasks.map((task) => (
                  <article key={task.id} className="ui-card ui-card-hover">
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: 10,
                        marginBottom: 14,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: 10,
                            display: "grid",
                            placeItems: "center",
                            background: "rgba(233, 189, 101, 0.12)",
                            color: "var(--ui-gold)",
                            flex: "0 0 auto",
                          }}
                        >
                          {task.status === "completed" ? (
                            <CheckCircle2 size={15} />
                          ) : task.status === "error" ? (
                            <AlertTriangle size={15} />
                          ) : task.status === "queued" ? (
                            <Clock size={15} />
                          ) : (
                            <LoaderCircle size={15} className="animate-spin" />
                          )}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <h3
                            className="ui-subtitle"
                            style={{
                              margin: 0,
                              fontSize: 15,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {sourceHost(task.source_url)}
                          </h3>
                          <span className="ui-hint">
                            {task.source_type} Â· {formatDate(task.created_at)}
                          </span>
                        </div>
                      </div>
                      <span className={statusBadgeClass(task.status)} style={statusBadgeStyle(task.status)}>
                        {STATUS_LABEL[task.status] ?? task.status}
                      </span>
                    </div>

                    <div className="ui-progress" style={{ marginBottom: 12 }}>
                      <span style={{ width: `${task.status === "completed" ? 100 : task.progress}%` }} />
                    </div>

                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 12,
                        color: "var(--ui-muted)",
                        marginBottom: 12,
                      }}
                    >
                      <span>{task.total_clips ?? 0} clips</span>
                      <span>{task.status === "completed" ? 100 : task.progress}%</span>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button
                        className="ui-btn ui-btn-ghost"
                        style={{ fontSize: 12, padding: "8px 12px" }}
                        onClick={() => openTask(task)}
                      >
                        View clips
                      </button>
                      <button
                        className="ui-btn ui-btn-ghost"
                        style={{ fontSize: 12, padding: "8px 12px" }}
                        onClick={() => removeTask(task.id)}
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>

                    {task.status === "error" && task.error_message && (
                      <p className="ui-hint" style={{ marginTop: 10, color: "#f0a3a3" }}>
                        {task.error_message}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            )}


            {openTaskData && (
              <div className="ui-card">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                    flexWrap: "wrap",
                  }}
                >
                  <h3 className="ui-subtitle" style={{ margin: 0, fontSize: 17 }}>
                    Clips Â· {sourceHost(openTaskData.source_url)}
                  </h3>
                  <span className={statusBadgeClass(openTaskData.status)} style={statusBadgeStyle(openTaskData.status)}>
                    {STATUS_LABEL[openTaskData.status] ?? openTaskData.status}
                  </span>
                </div>

                {clipsLoading ? (
                  <p className="ui-hint" style={{ marginTop: 14 }}>
                    Loading clipsâ€¦
                  </p>
                ) : clips.length === 0 ? (
                  <p className="ui-hint" style={{ marginTop: 14 }}>
                    {openTaskData.status === "error"
                      ? openTaskData.error_message || "This task failed before producing clips."
                      : "No clips yet â€” this panel refreshes automatically while the task runs."}
                  </p>
                ) : (
                  <>
                    {/* Editing lanjutan: gabung klip terpilih (compose) */}
                    {clips.length > 1 && (
                      <div
                        style={{
                          display: "flex",
                          gap: 8,
                          alignItems: "center",
                          flexWrap: "wrap",
                          marginTop: 14,
                        }}
                      >
                        <span style={{ fontSize: 12, color: "var(--ui-muted)" }}>
                          Centang klip untuk digabung ({selectedClips.length} dipilih)
                        </span>
                        <select
                          id="compose-transition"
                          value={composeTransition}
                          onChange={(e) => setComposeTransition(e.target.value)}
                          className="ui-input"
                          style={{
                            width: 120,
                            padding: "6px 8px",
                            fontSize: 12,
                            background: "#171a22",
                            color: "#f5f5f2",
                            border: "1px solid var(--ui-line)",
                          }}
                        >
                          <option value="fade">fade</option>
                          <option value="wipeleft">wipe</option>
                          <option value="dissolve">dissolve</option>
                          <option value="none">tanpa transisi</option>
                        </select>
                        <button
                          id="merge-clips"
                          type="button"
                          className="ui-btn ui-btn-gold"
                          style={{ fontSize: 12, padding: "8px 12px" }}
                          disabled={selectedClips.length < 2 || editingBusy}
                          onClick={mergeSelectedClips}
                        >
                          <Layers size={13} /> Gabung {selectedClips.length || ""}
                        </button>
                      </div>
                    )}
                    <div className="clip-grid">
                      {clips.map((clip) => {
                        const score = typeof clip.viral_score === "number" ? clip.viral_score : null
                        const band = viralBand(score ?? 0)
                        const factorLabel =
                          typeof clip.viral_factors?.label === "string" ? clip.viral_factors.label : ""
                        const estimated = Boolean(clip.viral_factors?.estimated)
                        // Judul default pipeline ("Clip 2 - youtube") tidak layak jadi hook.
                        const hookText =
                          clip.ai_suggested_title ||
                          (/^Clip \d+ - /i.test(clip.title || "") ? "" : clip.title)
                        return (
                          <article key={clip.id} className="clip-card">
                            <div className="clip-media">
                              {clip.download_url ? (
                                <video
                                  className="clip-video"
                                  src={clip.download_url}
                                  poster={clip.thumbnail_url || undefined}
                                  muted
                                  loop
                                  playsInline
                                  preload="metadata"
                                  onMouseEnter={(event) => {
                                    void event.currentTarget.play().catch(() => {})
                                  }}
                                  onMouseLeave={(event) => {
                                    event.currentTarget.pause()
                                    event.currentTarget.currentTime = 0
                                  }}
                                />
                              ) : (
                                <div
                                  className="clip-video"
                                  style={{
                                    background: clip.thumbnail_url
                                      ? `url(${clip.thumbnail_url}) center / cover`
                                      : "linear-gradient(160deg,#2a2213,#141821)",
                                  }}
                                />
                              )}
                              <div className="clip-shade" />
                              <button
                                type="button"
                                className="clip-open"
                                aria-label={`Buka klip ${clip.clip_index + 1}`}
                                title="Buka video, metadata AI, download, upload YouTube"
                                onClick={() => setModalClipId(clip.id)}
                              />
                              <span className="clip-index">#{clip.clip_index + 1}</span>

                              {/* Viral Index bubble â€” klik = hitung ulang skor */}
                              <button
                                type="button"
                                className={`viral-bubble ${band}`}
                                style={
                                  {
                                    "--viral": `${Math.max(0, Math.min(100, score ?? 0))}`,
                                  } as React.CSSProperties
                                }
                                title={viralTooltip(clip.viral_factors)}
                                disabled={Boolean(scoreBusy[clip.id])}
                                onClick={() => recalcViralScore(clip)}
                              >
                                <span className="viral-ring">
                                  <span className="viral-num">
                                    {score === null ? "â€”" : Math.round(score)}
                                    {estimated && score !== null ? <sup>â‰ˆ</sup> : null}
                                  </span>
                                </span>
                                <span className="viral-meta">
                                  <span className="viral-cap">Viral Index</span>
                                  <span className="viral-state">
                                    {scoreBusy[clip.id] ? "Menghitungâ€¦" : factorLabel || "Belum dinilai"}
                                  </span>
                                </span>
                              </button>

                              {hookText && (
                                <p className="clip-hook">
                                  <span>{hookText}</span>
                                </p>
                              )}
                            </div>

                            <div className="clip-body">
                              <div className="clip-meta">
                                <span>{formatDuration(clip.duration)}</span>
                                {clip.file_size ? (
                                  <>
                                    <b>â€¢</b>
                                    <span>{formatSize(clip.file_size)}</span>
                                  </>
                                ) : null}
                                {clip.subtitle_url ? (
                                  <>
                                    <b>â€¢</b>
                                    <span>subtitle</span>
                                  </>
                                ) : null}
                              </div>

                              <div className="clip-actions">
                                <label className="clip-pick" title="Pilih untuk digabung">
                                  <input
                                    type="checkbox"
                                    className="clip-select"
                                    checked={selectedClips.includes(clip.id)}
                                    onChange={() => toggleClipSelection(clip.id)}
                                  />
                                  <span>Gabung</span>
                                </label>

                                <div className="clip-split">
                                  <input
                                    type="number"
                                    min="0"
                                    step="0.5"
                                    placeholder={`${(clip.duration / 2).toFixed(1)}`}
                                    value={splitAt[clip.id] ?? ""}
                                    onChange={(e) =>
                                      setSplitAt((current) => ({ ...current, [clip.id]: e.target.value }))
                                    }
                                    className="ui-input clip-split-input"
                                    title="Titik potong (detik)"
                                  />
                                  <button
                                    type="button"
                                    className="clip-icon-btn"
                                    title="Split di titik ini"
                                    disabled={editingBusy}
                                    onClick={() => splitClipAt(clip)}
                                  >
                                    <Scissors size={13} />
                                  </button>
                                </div>

                                <div className="clip-files">
                                  {clip.download_url && (
                                    <a
                                      className="clip-icon-btn gold"
                                      href={clip.download_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      title="Download MP4"
                                    >
                                      <Download size={13} />
                                    </a>
                                  )}
                                  {clip.subtitle_url && (
                                    <a
                                      className="clip-icon-btn"
                                      href={clip.subtitle_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      title="Download SRT"
                                    >
                                      SRT
                                    </a>
                                  )}
                                </div>
                              </div>
                            </div>
                          </article>
                        )
                      })}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </main>
      <SiteFooter />

      <ConfirmDialog
        open={confirmDisconnect}
        title="Disconnect YouTube?"
        description={
          <>
            Clipzy AI will stop auto-uploading clips to{" "}
            <strong>{youtube.channel_name || "your YouTube channel"}</strong> and the stored access token will be
            removed. Your clips and projects stay untouched â€” you can reconnect anytime.
          </>
        }
        confirmLabel="Yes, disconnect"
        cancelLabel="Keep connected"
        danger
        busy={youtubeLoading}
        onCancel={() => setConfirmDisconnect(false)}
        onConfirm={() => {
          setConfirmDisconnect(false)
          void disconnectYouTube()
        }}
      />

      <ClipModal
        clip={modalClip}
        token={token}
        youtubeConnected={Boolean(youtube.connected)}
        onClose={() => setModalClipId("")}
        onUpdated={patchClip}
        onConnectYouTube={() => {
          setModalClipId("")
          void connectYouTube()
        }}
      />
    </div>
  )
}
