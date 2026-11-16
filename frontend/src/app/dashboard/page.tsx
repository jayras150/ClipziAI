"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { BrandLogo } from "@/components/BrandingProvider"
import {
  Upload,
  Play,
  Unlink,
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
  ChevronDown,
} from "lucide-react"

import { api, ClipData, MusicTrackData, TaskData } from "@/lib/api"
import { ensureSession, hasSession } from "@/lib/auth"
import { SUBTITLE_STYLE_OPTIONS } from "@/lib/caption-styles"
import StyleRail from "@/components/StyleRail"
import PreviewDock from "@/components/PreviewDock"
import { readApiError } from "@/lib/api-errors"
import { requestYouTubeAccessToken } from "@/lib/social"
import ConfirmDialog from "@/components/ConfirmDialog"
import { ClipzySpinner, InlineSpinner, ProcessingBar } from "@/components/ClipzySpinner"
import ClipModal from "@/components/ClipModal"
import YouTubeUploadProgress from "@/components/YouTubeUploadProgress"
import SiteFooter from "@/components/SiteFooter"
import UserMenu from "@/components/UserMenu"
import NavDrawer from "@/components/NavDrawer"
import YouTubeIcon from "@/components/YouTubeIcon"
import { APP_NAV_LINKS } from "@/lib/nav"

const ACTIVE_STATUSES = ["queued", "processing"]

/** Jendela panjang klip. Hasil akhir mengikuti akhir kalimat (bisa 1:03, 1:16). */
const CLIP_LENGTH_PRESETS = [
  { value: "60-90", label: "60–90 s · 1 min+", min: 60, max: 90 },
  { value: "90-150", label: "90–150 s · 1.5–2.5 min", min: 90, max: 150 },
  { value: "150-240", label: "150–240 s · 2.5–4 min", min: 150, max: 240 },
]

/**
 * Opsi gaya subtitle yang dikirim sebagai `editing_options.caption_style`.
 * Nilainya dipetakan ke preset CAPTION_STYLES di backend
 * (`app/services/processor.py`) — warna, garis tepi, kotak latar, dan posisi.
 */

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  queued: "Queued",
  downloading: "Downloading",
  download_failed: "Download failed",
  downloaded: "Downloaded",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
  error: "Failed",
  cancelled: "Cancelled",
  canceled: "Cancelled",
}

/** Pesan aman untuk user — detail teknis hanya di admin. */
const USER_ERROR_MESSAGE =
  "We couldn't process this video.\n\nSomething went wrong while downloading it.\nPlease try again."

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

function readVideoDuration(file: File): Promise<number | undefined> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement("video")
    video.preload = "metadata"
    const finish = (value?: number) => {
      URL.revokeObjectURL(url)
      resolve(value)
    }
    video.onloadedmetadata = () => finish(Number.isFinite(video.duration) ? video.duration : undefined)
    video.onerror = () => finish(undefined)
    window.setTimeout(() => finish(undefined), 6000)
    video.src = url
  })
}

function videoContentType(file: File): string {
  if (file.type) return file.type.split(";")[0].trim()
  const ext = file.name.split(".").pop()?.toLowerCase()
  return (
    {
      mp4: "video/mp4",
      mov: "video/quicktime",
      avi: "video/x-msvideo",
      webm: "video/webm",
      mkv: "video/x-matroska",
    }[ext || ""] || "video/mp4"
  )
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
  if (!factors) return "Viral score not calculated yet"
  const pct = (key: string) =>
    typeof factors[key] === "number" ? `${Math.round(factors[key] * 100)}%` : "—"
  const lines = [
    `Hook: ${pct("hook")}`,
    `Duration fit: ${pct("duration")}`,
    `Pacing: ${pct("pacing")}`,
    `Emosi: ${pct("emotion")}`,
    `Kejelasan: ${pct("clarity")}`,
  ]
  if (factors.reasoning) lines.push("", String(factors.reasoning))
  if (factors.estimated) lines.push("", "(estimated - older clip without a stored transcript)")
  return lines.join("\n")
}

export default function DashboardPage() {
  const [token, setToken] = useState("")
  const [activeTab, setActiveTab] = useState<"upload" | "projects">("upload")

  /** Pindah tab + simpan ke URL (?tab=) dan localStorage. */
  const changeTab = (tab: "upload" | "projects") => {
    setActiveTab(tab)
    try {
      window.localStorage.setItem("clipzi.dashboard.tab", tab)
      const url = new URL(window.location.href)
      url.searchParams.set("tab", tab)
      window.history.replaceState(null, "", url.toString())
    } catch {
      /* localStorage/URL tidak tersedia — abaikan */
    }
  }

  // Saat halaman di-refresh, kembalikan tab terakhir (kecuali URL menentukan).
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search)
      const fromUrl = params.get("tab")
      const saved = window.localStorage.getItem("clipzi.dashboard.tab")
      const next = fromUrl === "projects" || fromUrl === "upload" ? fromUrl : saved
      if (next === "projects") setActiveTab("projects")
    } catch {
      /* abaikan */
    }
  }, [])
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeMessage, setYoutubeMessage] = useState("")
  // Plan user aktif — dipakai untuk chip "Watermark Clipzy aktif" (plan free).
  const [planType, setPlanType] = useState("")
  // Konfirmasi wajib sebelum memutus koneksi YouTube (menghapus token tersimpan).
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  // Konfirmasi hapus project lewat dialog aplikasi (bukan window.confirm).
  const [confirmDeleteTask, setConfirmDeleteTask] = useState<{ id: string; label: string } | null>(
    null,
  )
  const [deletingTask, setDeletingTask] = useState(false)
  // Dropdown kecil di tombol channel YouTube (isi: Disconnect).
  const [ytMenuOpen, setYtMenuOpen] = useState(false)
  const ytMenuRef = useRef<HTMLDivElement>(null)
  // Task yang sedang dicoba ulang lewat tombol Try Again.
  const [retryingTaskId, setRetryingTaskId] = useState("")

  // Tutup dropdown channel YouTube saat klik di luar atau tekan Escape.
  useEffect(() => {
    if (!ytMenuOpen) return
    const onPointerDown = (event: MouseEvent) => {
      if (ytMenuRef.current && !ytMenuRef.current.contains(event.target as Node)) {
        setYtMenuOpen(false)
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setYtMenuOpen(false)
    }
    document.addEventListener("mousedown", onPointerDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onPointerDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [ytMenuOpen])

  const [tasks, setTasks] = useState<TaskData[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [urlValue, setUrlValue] = useState("")
  const [startTimeValue, setStartTimeValue] = useState("")
  const [endTimeValue, setEndTimeValue] = useState("")
  const [aspectRatioValue, setAspectRatioValue] = useState("9:16")
  const [captionTextValue, setCaptionTextValue] = useState("")
  const [captionStyle, setCaptionStyle] = useState("")
  const [speedValue, setSpeedValue] = useState("1")
  // Panjang klip = jendela target (soft): hasil akhir mengikuti batas kalimat,
  // jadi boleh 1:03 / 1:16 — tidak dipaksa bulat 1 menit.
  const [clipLength, setClipLength] = useState("60-90")
  const [clipLengthCustom, setClipLengthCustom] = useState({ min: "", max: "" })
  const [clipsQuota, setClipsQuota] = useState("auto")
  // Fase 2: gaya & polish
  const [filterPreset, setFilterPreset] = useState("none")
  const [blurFill, setBlurFill] = useState(false)
  const [trimSilence, setTrimSilence] = useState(false)
  const [cleanAudio, setCleanAudio] = useState(false)
  const [watermarkUrl, setWatermarkUrl] = useState("")
  const [watermarkBusy, setWatermarkBusy] = useState(false)
  const [watermarkPosition, setWatermarkPosition] = useState("bottom-right")
  const [introUrl, setIntroUrl] = useState("")
  const [outroUrl, setOutroUrl] = useState("")
  // Auto zoom follow-speaker
  const [autoZoom, setAutoZoom] = useState("off")
  const [zoomLevel, setZoomLevel] = useState("1.3")
  const [autoZoomSplit, setAutoZoomSplit] = useState(true)
  // Musik latar
  const [musicLibrary, setMusicLibrary] = useState<MusicTrackData[]>([])
  const [musicUrl, setMusicUrl] = useState("")
  const [musicVolume, setMusicVolume] = useState("0.22")
  const [musicDucking, setMusicDucking] = useState(true)
  // Batch E: upload langsung, multi-segmen, caption custom, Ken Burns, B-roll.
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [segments, setSegments] = useState<
    { start: string; end: string; mute: boolean }[]
  >([])
  const [captionColor, setCaptionColor] = useState("")
  const [captionSize, setCaptionSize] = useState("")
  const [captionFont, setCaptionFont] = useState("")
  const [captionKaraoke, setCaptionKaraoke] = useState(true)
  const [kenBurns, setKenBurns] = useState(false)
  const [panDirection, setPanDirection] = useState("zoom-in")
  const [kenBurnsZoom, setKenBurnsZoom] = useState("1.12")
  const [overlayUrl, setOverlayUrl] = useState("")
  const [overlayPosition, setOverlayPosition] = useState("bottom-right")
  const [overlayScale, setOverlayScale] = useState("0.32")
  const [overlayOpacity, setOverlayOpacity] = useState("1")
  const [overlayStart, setOverlayStart] = useState("")
  const [overlayEnd, setOverlayEnd] = useState("")
  const [bulkUploading, setBulkUploading] = useState(false)
  const [bulkPrivacy, setBulkPrivacy] = useState("unlisted")
  const [bulkPublishAt, setBulkPublishAt] = useState("")
  const [cardUploading, setCardUploading] = useState<Record<string, boolean>>({})
  const [cardUploadProgress, setCardUploadProgress] = useState<Record<string, number>>({})
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
  // Skor viral: tombol ↻ per klip sedang menghitung ulang?
  const [scoreBusy, setScoreBusy] = useState<Record<string, boolean>>({})
  // Popup klip: player video + metadata AI (judul/deskripsi/tag) + download + upload YouTube
  const [modalClipId, setModalClipId] = useState("")


  const fileInputRef = useRef<HTMLInputElement>(null)


  const getToken = () => (hasSession() ? "cookie" : null)

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
    let cancelled = false

    const boot = async () => {
      // Coba pulihkan sesi dulu (refresh bila access token hampir habis).
      // Hanya kalau benar-benar tidak ada sesi, pengguna diarahkan ke login.
      const stored = await ensureSession()
      if (cancelled) return
      if (!stored) {
        const next = `${window.location.pathname}${window.location.search}`
        window.location.href = `/login?next=${encodeURIComponent(next)}`
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
        // Hanya paksa tab Upload kalau user datang dengan link video.
        changeTab("upload")
      }

      const status = params.get("youtube")
      if (status === "connected") setYoutubeMessage("YouTube connected successfully.")
      if (status === "denied") setYoutubeMessage("YouTube permission was cancelled.")
      if (status === "error") setYoutubeMessage("YouTube connection failed. Check the Google OAuth configuration.")
    }

    void boot()
    return () => {
      cancelled = true
    }
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
        setYoutubeMessage("Opening Google consent…")
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

      // Panjang klip (soft window) + jumlah klip
      if (clipLength === "custom") {
        const customMin = parseFloat(clipLengthCustom.min)
        const customMax = parseFloat(clipLengthCustom.max)
        if (!Number.isNaN(customMin)) editingOptions.target_duration_min = Math.max(60, customMin)
        if (!Number.isNaN(customMax)) editingOptions.target_duration_max = Math.max(60, customMax)
      } else {
        const preset = CLIP_LENGTH_PRESETS.find((item) => item.value === clipLength)
        if (preset) {
          editingOptions.target_duration_min = preset.min
          editingOptions.target_duration_max = preset.max
        }
      }
      if (clipsQuota !== "auto") {
        const quota = parseInt(clipsQuota, 10)
        if (!Number.isNaN(quota)) editingOptions.max_clips = quota
      }

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
        editingOptions.auto_zoom_split = autoZoomSplit
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

      // Multi-segment trim + mute per segmen
      if (segments.length > 0) {
        const parsedSegments = segments.map((segment) => ({
          start: parseFloat(segment.start),
          end: parseFloat(segment.end),
          mute: segment.mute,
        }))
        if (
          parsedSegments.some(
            (segment) =>
              Number.isNaN(segment.start) ||
              Number.isNaN(segment.end) ||
              segment.start < 0 ||
              segment.end <= segment.start,
          )
        ) {
          setTaskError("Each segment needs a start and end time, with end greater than start.")
          setSubmitting(false)
          return
        }
        editingOptions.segments = parsedSegments
      }

      // Caption custom + karaoke
      if (captionColor) editingOptions.caption_color = captionColor
      const customCaptionSize = parseFloat(captionSize)
      if (!Number.isNaN(customCaptionSize) && customCaptionSize > 0) {
        editingOptions.caption_size = customCaptionSize
      }
      if (captionFont) editingOptions.caption_font = captionFont
      editingOptions.caption_karaoke = captionKaraoke

      // Ken Burns / manual pan (auto zoom follow-speaker tetap prioritas)
      if (autoZoom !== "speaker" && kenBurns) {
        editingOptions.ken_burns = true
        editingOptions.pan_direction = panDirection
        const kbZoom = parseFloat(kenBurnsZoom)
        if (!Number.isNaN(kbZoom)) editingOptions.ken_burns_zoom = kbZoom
      }

      // B-roll / PIP overlay
      const overlay = overlayUrl.trim()
      if (overlay) {
        editingOptions.overlay_url = overlay
        editingOptions.overlay_position = overlayPosition
        const scale = parseFloat(overlayScale)
        const opacity = parseFloat(overlayOpacity)
        if (!Number.isNaN(scale)) editingOptions.overlay_scale = scale
        if (!Number.isNaN(opacity)) editingOptions.overlay_opacity = opacity
        const oStart = parseFloat(overlayStart)
        const oEnd = parseFloat(overlayEnd)
        if (!Number.isNaN(oStart)) editingOptions.overlay_start = oStart
        if (!Number.isNaN(oEnd)) editingOptions.overlay_end = oEnd
      }

      const task = await api.createTask(stored, url, editingOptions)
      setUrlValue("")
      if (task.status === "error") {
        setTaskError(USER_ERROR_MESSAGE)
      } else {
        setNotice("Task created — Clipzy AI is processing your video.")
      }
      await refreshTasks(stored)
      changeTab("projects")
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
      if (!navigator.clipboard?.readText) throw new Error("Clipboard API is not available")
      const text = (await navigator.clipboard.readText()).trim()
      if (!text) {
        setNotice("Clipboard is empty - copy a video link first.")
        return
      }
      setUrlValue(text)
      setNotice("Link pasted from clipboard.")
    } catch {
      setTaskError("Your browser blocked clipboard access. Click the URL field and press Ctrl+V.")
    }
  }

  /** Upload logo watermark dari perangkat user (bukan menempel URL). */
  const uploadWatermark = async (file: File | null) => {
    if (!file) return
    const stored = getToken()
    if (!stored) return
    setWatermarkBusy(true)
    setTaskError("")
    setNotice("")
    try {
      const result = await api.uploadUserWatermark(stored, file)
      setWatermarkUrl(result.watermark_url)
      setNotice("Watermark uploaded — it will be applied to the rendered clip.")
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not upload the watermark."))
    } finally {
      setWatermarkBusy(false)
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
    setSpeedValue("1")
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
    setAutoZoomSplit(true)
    setMusicUrl("")
    setMusicVolume("0.22")
    setMusicDucking(true)
    setSegments([])
    setCaptionColor("")
    setCaptionSize("")
    setCaptionFont("")
    setCaptionKaraoke(true)
    setKenBurns(false)
    setPanDirection("zoom-in")
    setKenBurnsZoom("1.12")
    setOverlayUrl("")
    setOverlayPosition("bottom-right")
    setOverlayScale("0.32")
    setOverlayOpacity("1")
    setOverlayStart("")
    setOverlayEnd("")
    setBulkPublishAt("")
    setTaskError("")
    setNotice("Editing options reset to default.")
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
    setDeletingTask(true)
    setTaskError("")
    try {
      await api.deleteTask(token, taskId)
      if (openTaskId === taskId) {
        setOpenTaskId("")
        setClips([])
      }
      setNotice("Project deleted.")
      await refreshTasks(token)
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not delete the project."))
    } finally {
      setDeletingTask(false)
      setConfirmDeleteTask(null)
    }
  }
  const toggleClipSelection = (clipId: string) => {
    setSelectedClips((current) =>
      current.includes(clipId) ? current.filter((id) => id !== clipId) : [...current, clipId],
    )
  }

  /** Hitung ulang skor viral satu klip (tombol ↻ di kartu klip). */
  const recalcViralScore = async (clip: ClipData) => {
    if (!openTaskId) return
    setScoreBusy((current) => ({ ...current, [clip.id]: true }))
    setTaskError("")
    setNotice("")
    try {
      const result = await api.getViralScore(token, clip.id, true)
      setNotice(`Viral score for clip #${clip.clip_index + 1} updated: ${Math.round(result.score)}/100`)
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
          ? USER_ERROR_MESSAGE
          : `Merging ${selectedClips.length} clip(s) — processing.`,
      )
      setSelectedClips([])
      await refreshTasks(token)
      changeTab("projects")
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
      setTaskError(`Split point must be between 0 and ${clip.duration.toFixed(1)} seconds.`)
      return
    }
    setEditingBusy(true)
    setTaskError("")
    setNotice("")
    try {
      const task = await api.splitClip(token, openTaskId, clip.id, value)
      setNotice(
        task.status === "error"
          ? USER_ERROR_MESSAGE
          : `Clip #${clip.clip_index} split at ${value.toFixed(1)} seconds.`,
      )
      await refreshTasks(token)
      changeTab("projects")
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not split this clip."))
    } finally {
      setEditingBusy(false)
    }
  }



  /** Upload langsung ke storage (presigned PUT) lalu isi URL untuk diproses. */
  const onPickFile = async (file: File | null) => {
    if (!file) return
    const stored = getToken()
    if (!stored) {
      window.location.href = "/login"
      return
    }
    if (file.size > 2 * 1024 * 1024 * 1024) {
      setTaskError("Video is too large. Maximum size is 2 GB.")
      return
    }
    setTaskError("")
    setNotice("")
    setUploadingFile(true)
    setUploadProgress(0)
    try {
      const duration = await readVideoDuration(file)
      if (duration !== undefined && duration < 60) {
        setTaskError("Video must be at least 1 minute long so clips can end on a full sentence.")
        return
      }
      const contentType = videoContentType(file)
      const presign = await api.presignUpload(stored, {
        filename: file.name,
        content_type: contentType,
        size: file.size,
        duration_seconds: duration,
      })
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open("PUT", presign.upload_url)
        xhr.setRequestHeader("Content-Type", contentType)
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            setUploadProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
          }
        }
        xhr.onload = () =>
          xhr.status >= 200 && xhr.status < 300
            ? resolve()
            : reject(new Error(`Storage upload failed (HTTP ${xhr.status}).`))
        xhr.onerror = () => reject(new Error("Storage upload failed. Check the bucket CORS policy."))
        xhr.send(file)
      })
      setUrlValue(presign.public_url)
      setUploadProgress(100)
      setNotice(`"${file.name}" uploaded. Review the options, then click Process video.`)
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, error.message || "Could not upload the video."))
    } finally {
      setUploadingFile(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  /** Upload cepat satu klip dari kartu memakai metadata AI yang tersimpan. */
  const uploadClipFromCard = async (clip: ClipData) => {
    if (!token || cardUploading[clip.id]) return
    if (!youtube.connected) {
      void connectYouTube()
      return
    }
    setCardUploading((current) => ({ ...current, [clip.id]: true }))
    setCardUploadProgress((current) => ({ ...current, [clip.id]: 0 }))
    setTaskError("")
    setNotice("")
    try {
      await api.quickUploadClipToYouTube(token, clip.id, bulkPrivacy)
      patchClip(clip.id, { youtube_uploaded: true })
      const status = await api.waitForYouTubeUpload(token, clip.id, {
        timeoutMs: 10 * 60 * 1000,
        intervalMs: 5000,
        onProgress: (next) => {
          setCardUploadProgress((current) => ({
            ...current,
            [clip.id]: Math.max(
              current[clip.id] || 0,
              Math.min(99, Math.round(Number(next.progress) || 0)),
            ),
          }))
        },
      })
      if (status.status === "done") {
        setCardUploadProgress((current) => ({ ...current, [clip.id]: 100 }))
        patchClip(clip.id, {
          youtube_uploaded: true,
          youtube_video_id: status.youtube_video_id || null,
        })
        setNotice(`Clip #${clip.clip_index + 1} uploaded to YouTube.`)
      } else if (status.status === "error") {
        setTaskError(status.error || "YouTube upload failed. Check your quota and connection.")
      }
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not upload this clip to YouTube."))
    } finally {
      setCardUploading((current) => {
        const next = { ...current }
        delete next[clip.id]
        return next
      })
      setCardUploadProgress((current) => {
        const next = { ...current }
        delete next[clip.id]
        return next
      })
    }
  }

  /** Antre unggahan beberapa klip sekaligus, opsional dengan jadwal publish. */
  const bulkUploadSelected = async () => {
    if (!token || selectedClips.length === 0 || bulkUploading) return
    if (!youtube.connected) {
      void connectYouTube()
      return
    }
    setBulkUploading(true)
    setTaskError("")
    setNotice("")
    try {
      const result = await api.bulkUploadToYouTube(
        token,
        selectedClips,
        bulkPrivacy,
        bulkPublishAt ? new Date(bulkPublishAt).toISOString() : undefined,
      )
      setNotice(
        `${result.queued} clip(s) queued for YouTube${bulkPublishAt ? " (scheduled)" : ""}.`,
      )
      setSelectedClips([])
    } catch (error: any) {
      setTaskError(readApiError(error.response?.data, "Could not queue the selected clips."))
    } finally {
      setBulkUploading(false)
    }
  }

  const openTaskData = tasks.find((task) => task.id === openTaskId) || null
  // Contoh teks pratinjau: pakai caption yang diketik user agar terasa nyata.
  const subtitlePreviewText = (captionTextValue.trim() || "Sample caption").slice(0, 24)
  // Nama track musik terpilih untuk badge di kartu preview.
  const selectedMusic = musicLibrary.find((track) => track.url === musicUrl)
  const previewMusicName = selectedMusic
    ? `${selectedMusic.name}${selectedMusic.mood ? ` · ${selectedMusic.mood}` : ""}`
    : ""
  // Estimasi kasar untuk user; kalau trim diisi, hitung dari durasi potongan.
  const trimSeconds = (() => {
    const start = parseFloat(startTimeValue)
    const end = parseFloat(endTimeValue)
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) return end - start
    return null
  })()
  const activeTaskForBanner =
    tasks.find((task) => ACTIVE_STATUSES.includes(task.status)) || null

  /** Try Again: pakai task yang sama (backend idempotent, tanpa task baru). */
  const retryFailedTask = async (task: TaskData) => {
    if (!token || retryingTaskId) return
    setRetryingTaskId(task.id)
    setTaskError("")
    setNotice("")
    try {
      const updated = await api.retryTask(token, task.id)
      setTasks((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setNotice("Task resubmitted. The download will start again.")
    } catch (error) {
      setTaskError(
        readApiError(
          (error as { response?: { data?: unknown } })?.response?.data,
          "This task can't be retried yet. Please try again.",
        ),
      )
    } finally {
      setRetryingTaskId("")
    }
  }

  const renderEstimate = trimSeconds
    ? `≈ ${trimSeconds.toFixed(1)}s per clip · estimated render ±${Math.max(
        2,
        Math.round((trimSeconds * 3) / 60),
      )} min`
    : "3 clips · estimated render ±3–5 min · 1 credit/clip"

  return (
    <div className="ui-shell">
      <header className="ui-container ui-container-wide ui-nav">
        <NavDrawer activeHref="/dashboard" />
        <BrandLogo />
        <nav className="ui-nav-links">
          {APP_NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href}>
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="ui-nav-actions">
          {youtube.connected ? (
            <div className="ui-yt" ref={ytMenuRef}>
              <button
                type="button"
                className="ui-btn-yt"
                onClick={() => setYtMenuOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={ytMenuOpen}
                title={`YouTube: ${youtube.channel_name || "connected"}`}
                disabled={youtubeLoading}
              >
                {youtubeLoading ? (
                  <ClipzySpinner size="xs" />
                ) : (
                  <YouTubeIcon size={18} className="yt-icon" />
                )}
                <span className="ui-yt-name">{youtube.channel_name || "YouTube connected"}</span>
                <ChevronDown size={14} className="ui-yt-chevron" />
              </button>
              {ytMenuOpen && (
                <div className="ui-dropdown ui-dropdown-sm" role="menu">
                  <div className="ui-dropdown-note">
                    Connected as {youtube.channel_name || "YouTube"}
                  </div>
                  <button
                    type="button"
                    className="ui-dropdown-item danger"
                    role="menuitem"
                    disabled={youtubeLoading}
                    onClick={() => {
                      setYtMenuOpen(false)
                      setConfirmDisconnect(true)
                    }}
                  >
                    <Unlink size={15} /> Disconnect
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={connectYouTube}
              disabled={youtubeLoading}
              className="ui-btn ui-btn-ghost"
            >
              {youtubeLoading ? <ClipzySpinner size="xs" /> : <YouTubeIcon size={15} />}
              Connect YouTube
            </button>
          )}
          <UserMenu
            youtube={{
              connected: Boolean(youtube.connected),
              channelName: youtube.channel_name,
              loading: youtubeLoading,
            }}
            onConnectYouTube={() => void connectYouTube()}
            onDisconnectYouTube={() => setConfirmDisconnect(true)}
          />
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
            <button type="button" className="ui-back" onClick={goBack} title="Go back to the previous page">
              <ArrowLeft size={14} /> Back
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
              onClick={() => changeTab("upload")}
            >
              Upload
            </button>
            <button
              className={`ui-tab${activeTab === "projects" ? " active" : ""}`}
              onClick={() => changeTab("projects")}
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
            {/* 1) Kartu upload — selalu paling atas. */}
            <section className="ui-card ui-upload-hero">
              <div
                className="ui-dropzone"
                onClick={() => {
                  if (!uploadingFile) fileInputRef.current?.click()
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if ((event.key === "Enter" || event.key === " ") && !uploadingFile) {
                    fileInputRef.current?.click()
                  }
                }}
              >
                <div className="ui-drop-icon">
                  {uploadingFile ? <ClipzySpinner size="md" /> : <Upload size={26} />}
                </div>
                <p className="ui-drop-title">
                  {uploadingFile ? `Uploading… ${uploadProgress}%` : "Drop your video here"}
                </p>
                <p className="ui-hint" style={{ marginTop: 6 }}>
                  {uploadingFile
                    ? "Keep this tab open while the file goes directly to storage."
                    : "Click to browse or drag a file — you can also paste a link below."}
                </p>
                {uploadingFile && (
                  <div className="ui-progress" style={{ width: "100%", marginTop: 12 }}>
                    <span style={{ width: `${uploadProgress}%` }} />
                  </div>
                )}
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
                accept="video/mp4,video/quicktime,video/x-msvideo,video/webm,video/x-matroska,video/*"
                hidden
                disabled={uploadingFile}
                onChange={(event) => void onPickFile(event.target.files?.[0] ?? null)}
              />
              <p className="ui-hint" style={{ textAlign: "center", marginTop: 10 }}>
                Upload goes straight to R2/S3 — the API only signs a temporary URL.
              </p>
            </section>

            {/* 2) Form paste link, lalu 3) opsi editing. */}
            {/* noValidate: validation lives in submitUrl so the message
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

              {/* Opsi editing manual (Fase 1) — setiap kontrol jadi kartu sendiri. */}
              <div className="ui-opt-grid">
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="start-time">Start (s)</label>
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
                  <label className="ui-opt-label" htmlFor="end-time">End (s)</label>
                  <input
                    id="end-time"
                    type="number"
                    min="0"
                    step="any"
                    placeholder="optional"
                    value={endTimeValue}
                    onChange={(e) => setEndTimeValue(e.target.value)}
                    className="ui-input"
                  />
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="aspect-ratio">Aspect ratio</label>
                  <select
                    id="aspect-ratio"
                    value={aspectRatioValue}
                    onChange={(e) => setAspectRatioValue(e.target.value)}
                    className="ui-input"
                  >
                    <option value="9:16">9:16 vertical</option>
                    <option value="1:1">1:1 square</option>
                    <option value="16:9">16:9 landscape</option>
                  </select>
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="caption-text">Caption</label>
                  <input
                    id="caption-text"
                    type="text"
                    placeholder="overlay text"
                    value={captionTextValue}
                    onChange={(e) => setCaptionTextValue(e.target.value)}
                    className="ui-input"
                  />
                </div>
                {/* Subtitle style: horizontal rail, scrollable left/right. */}
                <div className="ui-opt ui-opt-wide">
                  <span className="ui-opt-label">Subtitle style</span>
                  <StyleRail
                    options={SUBTITLE_STYLE_OPTIONS}
                    value={captionStyle}
                    previewText={subtitlePreviewText}
                    onChange={setCaptionStyle}
                  />
                </div>
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="speed">Speed</label>
                  <select
                    id="speed"
                    value={speedValue}
                    onChange={(e) => setSpeedValue(e.target.value)}
                    className="ui-input"
                  >
                    <option value="0.25">0.25×</option>
                    <option value="0.5">0.5×</option>
                    <option value="1">1×</option>
                    <option value="1.5">1.5×</option>
                    <option value="2">2×</option>
                    <option value="4">4×</option>
                  </select>
                </div>

                {/* Panjang klip (kanan kartu Speed). Soft target: batas akhir
                    follows the sentence end, so results can be 1:03 / 1:16. */}
                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="clip-length">
                    Clip length
                  </label>
                  <select
                    id="clip-length"
                    value={clipLength}
                    onChange={(e) => setClipLength(e.target.value)}
                    className="ui-input"
                  >
                    {CLIP_LENGTH_PRESETS.map((preset) => (
                      <option key={preset.value} value={preset.value}>
                        {preset.label}
                      </option>
                    ))}
                    <option value="custom">Custom…</option>
                  </select>
                  {clipLength === "custom" && (
                    <div className="clip-length-custom">
                      <input
                        type="number"
                        min="60"
                        step="5"
                        placeholder="min (s)"
                        className="ui-input"
                        value={clipLengthCustom.min}
                        onChange={(e) =>
                          setClipLengthCustom((current) => ({ ...current, min: e.target.value }))
                        }
                      />
                      <input
                        type="number"
                        min="60"
                        step="5"
                        placeholder="max (s)"
                        className="ui-input"
                        value={clipLengthCustom.max}
                        onChange={(e) =>
                          setClipLengthCustom((current) => ({ ...current, max: e.target.value }))
                        }
                      />
                    </div>
                  )}
                  <span className="ui-hint">
                    Cuts land on finished sentences — 1:03 or 1:16 is normal.
                  </span>
                </div>

                <div className="ui-opt">
                  <label className="ui-opt-label" htmlFor="clips-count">
                    Clips
                  </label>
                  <select
                    id="clips-count"
                    value={clipsQuota}
                    onChange={(e) => setClipsQuota(e.target.value)}
                    className="ui-input"
                  >
                    <option value="auto">Auto (by video length)</option>
                    {[3, 4, 6, 8, 10].map((count) => (
                      <option key={count} value={count}>
                        {count} clips
                      </option>
                    ))}
                  </select>
                  <span className="ui-hint">
                    Auto: 3 clips / 15 min · 6 / 30 min · 8 / 1 h · 10 / 2 h
                  </span>
                </div>
              </div>
                {/* Opsi lanjutan (Fase 2) — kartu per kontrol. */}
                <details className="ui-opt-details" style={{ marginTop: 14 }}>
                  <summary>Advanced editing options</summary>
                  <div className="ui-opt-panel">
                    <div className="ui-opt ui-opt-wide">
                      <div className="ui-opt-head">
                        <label className="ui-opt-label">Multi-segment trim</label>
                        <button
                          type="button"
                          className="ui-btn ui-btn-ghost"
                          onClick={() =>
                            setSegments((current) =>
                              current.length >= 12
                                ? current
                                : [...current, { start: "", end: "", mute: false }],
                            )
                          }
                          disabled={segments.length >= 12}
                        >
                          + Add segment
                        </button>
                      </div>
                      <span className="ui-hint">
                        One output clip, concatenated in this order. Times are source seconds.
                      </span>
                      {segments.length > 0 && (
                        <div className="segment-list">
                          {segments.map((segment, index) => (
                            <div className="segment-row" key={index}>
                              <span className="segment-index">{index + 1}</span>
                              <input
                                type="number"
                                min="0"
                                step="any"
                                placeholder="start (s)"
                                className="ui-input"
                                value={segment.start}
                                onChange={(event) =>
                                  setSegments((current) =>
                                    current.map((item, itemIndex) =>
                                      itemIndex === index
                                        ? { ...item, start: event.target.value }
                                        : item,
                                    ),
                                  )
                                }
                              />
                              <input
                                type="number"
                                min="0"
                                step="any"
                                placeholder="end (s)"
                                className="ui-input"
                                value={segment.end}
                                onChange={(event) =>
                                  setSegments((current) =>
                                    current.map((item, itemIndex) =>
                                      itemIndex === index
                                        ? { ...item, end: event.target.value }
                                        : item,
                                    ),
                                  )
                                }
                              />
                              <label className="segment-mute" title="Mute this segment">
                                <input
                                  type="checkbox"
                                  checked={segment.mute}
                                  onChange={(event) =>
                                    setSegments((current) =>
                                      current.map((item, itemIndex) =>
                                        itemIndex === index
                                          ? { ...item, mute: event.target.checked }
                                          : item,
                                      ),
                                    )
                                  }
                                />
                                mute
                              </label>
                              <button
                                type="button"
                                className="clip-icon-btn"
                                title="Remove segment"
                                onClick={() =>
                                  setSegments((current) =>
                                    current.filter((_, itemIndex) => itemIndex !== index),
                                  )
                                }
                              >
                                ×
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
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
                        <label className="ui-opt-label" htmlFor="caption-color">
                          Caption color
                        </label>
                        <input
                          id="caption-color"
                          type="color"
                          className="ui-input"
                          value={captionColor || "#F4C76B"}
                          onChange={(e) => setCaptionColor(e.target.value)}
                        />
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="caption-size">
                          Caption size (px)
                        </label>
                        <input
                          id="caption-size"
                          type="number"
                          min="12"
                          max="160"
                          placeholder="auto"
                          className="ui-input"
                          value={captionSize}
                          onChange={(e) => setCaptionSize(e.target.value)}
                        />
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="caption-font">
                          Caption font
                        </label>
                        <select
                          id="caption-font"
                          className="ui-input"
                          value={captionFont}
                          onChange={(e) => setCaptionFont(e.target.value)}
                        >
                          <option value="">Preset font</option>
                          <option value="sans">DejaVu Sans</option>
                          <option value="serif">DejaVu Serif</option>
                          <option value="mono">DejaVu Sans Mono</option>
                        </select>
                      </div>
                      <div className="ui-opt">
                        <span className="ui-opt-label">Karaoke highlight</span>
                        <label className="ui-switch">
                          <input
                            type="checkbox"
                            checked={captionKaraoke}
                            onChange={(e) => setCaptionKaraoke(e.target.checked)}
                          />
                          <span>Highlight active word</span>
                        </label>
                      </div>
                      <div className="ui-opt">
                        <span className="ui-opt-label">Watermark logo (upload)</span>
                        <label className="ui-file-btn" aria-disabled={watermarkBusy}>
                          <input
                            id="watermark-file"
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            disabled={watermarkBusy}
                            onChange={(event) => {
                              const file = event.target.files?.[0] ?? null
                              event.target.value = ""
                              void uploadWatermark(file)
                            }}
                          />
                          <Upload size={14} />
                          <span>
                            {watermarkBusy
                              ? "Uploading…"
                              : watermarkUrl
                                ? "Replace logo"
                                : "Choose image"}
                          </span>
                        </label>
                        <span className="ui-hint">PNG, JPEG or WEBP · max 2 MB</span>
                        {watermarkUrl && (
                          <div className="wm-logo-row">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={watermarkUrl} alt="Your watermark" />
                            <button
                              type="button"
                              className="ui-btn ui-btn-ghost"
                              onClick={() => setWatermarkUrl("")}
                              disabled={watermarkBusy}
                            >
                              Remove
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="watermark-position">Watermark position</label>
                        <select
                          id="watermark-position"
                          value={watermarkPosition}
                          onChange={(e) => setWatermarkPosition(e.target.value)}
                          className="ui-input"
                        >
                          <option value="top-left">Top left</option>
                          <option value="top-right">Top right</option>
                          <option value="bottom-left">Bottom left</option>
                          <option value="bottom-right">Bottom right</option>
                          <option value="center">Center</option>
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
                          <option value="speaker">Follow speaker</option>
                        </select>
                      </div>
                      {autoZoom === "speaker" && (
                        <>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="zoom-level">Level zoom</label>
                            <select
                              id="zoom-level"
                              value={zoomLevel}
                              onChange={(e) => setZoomLevel(e.target.value)}
                              className="ui-input"
                            >
                              <option value="1">1.0×</option>
                              <option value="1.3">1.3×</option>
                              <option value="1.6">1.6×</option>
                              <option value="2">2.0×</option>
                            </select>
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="auto-zoom-split">
                              Split 2 orang
                            </label>
                            <label className="ui-switch">
                              <input
                                type="checkbox"
                                id="auto-zoom-split"
                                checked={autoZoomSplit}
                                onChange={(e) => setAutoZoomSplit(e.target.checked)}
                              />
                              <span>Top/bottom when far apart</span>
                            </label>
                          </div>
                        </>
                      )}
                      <div className="ui-opt">
                        <span className="ui-opt-label">Ken Burns / manual pan</span>
                        <label className="ui-switch">
                          <input
                            type="checkbox"
                            checked={kenBurns}
                            disabled={autoZoom === "speaker"}
                            onChange={(e) => setKenBurns(e.target.checked)}
                          />
                          <span>Animate camera</span>
                        </label>
                      </div>
                      {kenBurns && autoZoom !== "speaker" && (
                        <>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="pan-direction">
                              Camera direction
                            </label>
                            <select
                              id="pan-direction"
                              className="ui-input"
                              value={panDirection}
                              onChange={(e) => setPanDirection(e.target.value)}
                            >
                              <option value="zoom-in">Zoom in</option>
                              <option value="zoom-out">Zoom out</option>
                              <option value="left-right">Pan left → right</option>
                              <option value="right-left">Pan right → left</option>
                              <option value="top-bottom">Pan top → bottom</option>
                              <option value="bottom-top">Pan bottom → top</option>
                              <option value="center">Static center</option>
                            </select>
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="kenburns-zoom">
                              Camera zoom
                            </label>
                            <select
                              id="kenburns-zoom"
                              className="ui-input"
                              value={kenBurnsZoom}
                              onChange={(e) => setKenBurnsZoom(e.target.value)}
                            >
                              <option value="1.08">1.08×</option>
                              <option value="1.12">1.12×</option>
                              <option value="1.2">1.20×</option>
                              <option value="1.35">1.35×</option>
                            </select>
                          </div>
                        </>
                      )}
                      <div className="ui-opt">
                        <label className="ui-opt-label" htmlFor="music-track">Music</label>
                        <select
                          id="music-track"
                          value={musicUrl}
                          onChange={(e) => setMusicUrl(e.target.value)}
                          className="ui-input"
                        >
                          <option value="">no music</option>
                          {musicLibrary.map((track) => (
                            <option key={track.id} value={track.url}>
                              {track.name}
                              {track.mood ? ` · ${track.mood}` : ""}
                            </option>
                          ))}
                        </select>
                      </div>
                      {musicUrl && (
                        <div className="ui-opt">
                          <label className="ui-opt-label" htmlFor="music-volume">Music volume</label>
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
                      <div className="ui-opt ui-opt-wide">
                        <label className="ui-opt-label" htmlFor="overlay-url">
                          B-roll / PIP overlay URL
                        </label>
                        <input
                          id="overlay-url"
                          type="url"
                          placeholder="https://.../broll.mp4 or .png"
                          className="ui-input"
                          value={overlayUrl}
                          onChange={(e) => setOverlayUrl(e.target.value)}
                        />
                        <span className="ui-hint">
                          Second video/image. Video loops; image stays static.
                        </span>
                      </div>
                      {overlayUrl.trim() && (
                        <>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="overlay-position">
                              Overlay position
                            </label>
                            <select
                              id="overlay-position"
                              className="ui-input"
                              value={overlayPosition}
                              onChange={(e) => setOverlayPosition(e.target.value)}
                            >
                              <option value="top-left">Top left</option>
                              <option value="top-right">Top right</option>
                              <option value="bottom-left">Bottom left</option>
                              <option value="bottom-right">Bottom right</option>
                              <option value="center">Center</option>
                            </select>
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="overlay-scale">
                              Overlay width
                            </label>
                            <select
                              id="overlay-scale"
                              className="ui-input"
                              value={overlayScale}
                              onChange={(e) => setOverlayScale(e.target.value)}
                            >
                              <option value="0.2">20%</option>
                              <option value="0.32">32%</option>
                              <option value="0.45">45%</option>
                              <option value="0.6">60%</option>
                            </select>
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="overlay-opacity">
                              Overlay opacity
                            </label>
                            <select
                              id="overlay-opacity"
                              className="ui-input"
                              value={overlayOpacity}
                              onChange={(e) => setOverlayOpacity(e.target.value)}
                            >
                              <option value="1">100%</option>
                              <option value="0.8">80%</option>
                              <option value="0.6">60%</option>
                              <option value="0.4">40%</option>
                            </select>
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="overlay-start">
                              Overlay start (s)
                            </label>
                            <input
                              id="overlay-start"
                              type="number"
                              min="0"
                              step="any"
                              placeholder="0"
                              className="ui-input"
                              value={overlayStart}
                              onChange={(e) => setOverlayStart(e.target.value)}
                            />
                          </div>
                          <div className="ui-opt">
                            <label className="ui-opt-label" htmlFor="overlay-end">
                              Overlay end (s)
                            </label>
                            <input
                              id="overlay-end"
                              type="number"
                              min="0"
                              step="any"
                              placeholder="clip end"
                              className="ui-input"
                              value={overlayEnd}
                              onChange={(e) => setOverlayEnd(e.target.value)}
                            />
                          </div>
                        </>
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
                        <span>Remove silence (jump cuts)</span>
                      </label>
                      <label className="ui-switch">
                        <input type="checkbox" id="clean-audio" checked={cleanAudio} onChange={(e) => setCleanAudio(e.target.checked)} />
                        <span>Clean audio</span>
                      </label>
                      {musicUrl && (
                        <label className="ui-switch">
                          <input
                            type="checkbox"
                            id="music-ducking"
                            checked={musicDucking}
                            onChange={(e) => setMusicDucking(e.target.checked)}
                          />
                          <span>Duck music while speaking</span>
                        </label>
                      )}
                    </div>
                  </div>
                </details>

                <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <button type="submit" className="ui-btn ui-btn-gold" disabled={submitting || uploadingFile}>
                    {submitting || uploadingFile ? <ClipzySpinner size="xs" /> : <Play size={15} />}
                    {uploadingFile ? `Uploading ${uploadProgress}%` : submitting ? "Starting…" : "Process"}
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-ghost"
                    onClick={resetEditingOptions}
                    disabled={submitting}
                    title="Reset all editing options to default"
                  >
                    <RotateCcw size={14} /> Reset options
                  </button>
                  {planType === "free" && (
                    <Link
                      href="/pricing"
                      className="ui-btn ui-btn-ghost ui-watermark-cta"
                      title="Free-plan clips include the Clipzy watermark. Upgrade to remove it."
                    >
                      <Droplets size={13} /> Remove watermark?
                    </Link>
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
                <RefreshCw size={14} /> {tasksLoading ? "Loading…" : "Refresh"}
              </button>
            </div>


            {tasksLoading && tasks.length === 0 ? (
              <div className="ui-card" style={{ textAlign: "center" }}>
                <ClipzySpinner size="md" />
              </div>
            ) : tasks.length === 0 ? (
              <div className="ui-card" style={{ textAlign: "center" }}>
                <FileVideo size={32} className="ui-gold" style={{ margin: "0 auto 10px" }} />
                <p className="ui-muted">No projects yet.</p>
                <button className="ui-btn ui-btn-gold" style={{ marginTop: 14 }} onClick={() => changeTab("upload")}>
                  <Play size={15} /> Add your first video
                </button>
              </div>
            ) : (
              <div className="task-grid">
              {activeTaskForBanner ? (
                <div style={{ gridColumn: "1 / -1" }}>
                  <ProcessingBar
                    title="AI is processing your video"
                    hint="Progress updates automatically. You can close this page."
                    progress={activeTaskForBanner.progress}
                  />
                </div>
              ) : null}
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
                            <ClipzySpinner size="xs" />
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
                            {task.source_type} · {formatDate(task.created_at)}
                          </span>
                        </div>
                      </div>
                      <span
                        className={statusBadgeClass(task.status)}
                        style={{ ...statusBadgeStyle(task.status), display: "inline-flex", alignItems: "center", gap: 6 }}
                      >
                        {ACTIVE_STATUSES.includes(task.status) ? <InlineSpinner /> : null}
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
                        onClick={() => setConfirmDeleteTask({ id: task.id, label: sourceHost(task.source_url) })}
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>

                    {task.status === "error" && (
                      <div className="task-error-card">
                        <p>{task.user_message || USER_ERROR_MESSAGE}</p>
                        {task.can_retry ? (
                          <button
                            type="button"
                            className="ui-btn ui-btn-gold"
                            disabled={retryingTaskId === task.id}
                            onClick={() => void retryFailedTask(task)}
                          >
                            {retryingTaskId === task.id ? (
                              <ClipzySpinner size="xs" />
                            ) : (
                              <RefreshCw size={13} />
                            )}
                            Try Again
                          </button>
                        ) : (
                          <span className="ui-hint">
                            Retry limit reached. Contact support if the problem continues.
                          </span>
                        )}
                      </div>
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
                    Clips · {sourceHost(openTaskData.source_url)}
                  </h3>
                  <span className={statusBadgeClass(openTaskData.status)} style={statusBadgeStyle(openTaskData.status)}>
                    {STATUS_LABEL[openTaskData.status] ?? openTaskData.status}
                  </span>
                </div>

                {clipsLoading ? (
                  <p className="ui-hint" style={{ marginTop: 14 }}>
                    Loading clips…
                  </p>
                ) : clips.length === 0 ? (
                  openTaskData.status === "error" ? (
                    <div className="task-error-card" style={{ marginTop: 14 }}>
                      <p>{openTaskData.user_message || USER_ERROR_MESSAGE}</p>
                      {openTaskData.can_retry ? (
                        <button
                          type="button"
                          className="ui-btn ui-btn-gold"
                          disabled={retryingTaskId === openTaskData.id}
                          onClick={() => void retryFailedTask(openTaskData)}
                        >
                          {retryingTaskId === openTaskData.id ? (
                            <ClipzySpinner size="xs" />
                          ) : (
                            <RefreshCw size={13} />
                          )}
                          Try Again
                        </button>
                      ) : (
                        <span className="ui-hint">
                          Retry limit reached. Contact support if the problem continues.
                        </span>
                      )}
                    </div>
                  ) : (
                    <p className="ui-hint" style={{ marginTop: 14 }}>
                      No clips yet — this panel refreshes automatically while the task runs.
                    </p>
                  )
                ) : (
                  <>
                    {/* Advanced editing: merge clips / queue selected uploads */}
                    {clips.length > 1 && (
                      <div className="clip-bulk-bar">
                        <span style={{ fontSize: 12, color: "var(--ui-muted)" }}>
                          Selected: {selectedClips.length} clip(s)
                        </span>
                        <select
                          id="compose-transition"
                          value={composeTransition}
                          onChange={(e) => setComposeTransition(e.target.value)}
                          className="ui-input clip-bulk-small"
                        >
                          <option value="fade">fade</option>
                          <option value="wipeleft">wipe</option>
                          <option value="dissolve">dissolve</option>
                          <option value="none">no transition</option>
                        </select>
                        <button
                          id="merge-clips"
                          type="button"
                          className="ui-btn ui-btn-gold clip-bulk-small"
                          disabled={selectedClips.length < 2 || editingBusy}
                          onClick={mergeSelectedClips}
                        >
                          <Layers size={13} /> Merge
                        </button>
                        <span className="clip-bulk-divider" />
                        <select
                          id="bulk-privacy"
                          className="ui-input clip-bulk-small"
                          value={bulkPrivacy}
                          onChange={(e) => setBulkPrivacy(e.target.value)}
                          title="Privacy for uploads"
                        >
                          <option value="unlisted">Unlisted</option>
                          <option value="public">Public</option>
                          <option value="private">Private</option>
                        </select>
                        <input
                          id="bulk-publish-at"
                          type="datetime-local"
                          className="ui-input clip-bulk-small"
                          value={bulkPublishAt}
                          onChange={(e) => setBulkPublishAt(e.target.value)}
                          title="Optional schedule (YouTube publishAt)"
                        />
                        <button
                          type="button"
                          className="ui-btn ui-btn-gold clip-bulk-small"
                          disabled={selectedClips.length === 0 || bulkUploading}
                          onClick={() => void bulkUploadSelected()}
                        >
                          {bulkUploading ? (
                            <ClipzySpinner size="xs" />
                          ) : (
                            <YouTubeIcon size={14} />
                          )}
                          Upload selected
                        </button>
                      </div>
                    )}
                    <div className="clip-grid">
                      {clips.map((clip, clipIndex) => {
                        const score = typeof clip.viral_score === "number" ? clip.viral_score : null
                        const band = viralBand(score ?? 0)
                        const estimated = Boolean(clip.viral_factors?.estimated)
                        // Judul kartu: judul AI → kalimat pembuka klip (hasil
                        // planner) → judul lama; judul default "Clip N - ..." dibuang.
                        const firstSentence =
                          typeof clip.viral_factors?.first_sentence === "string"
                            ? clip.viral_factors.first_sentence.replace(/\s+/g, " ").trim()
                            : ""
                        const hookText =
                          clip.ai_suggested_title ||
                          (firstSentence ? firstSentence.slice(0, 110) : "") ||
                          (/^Clip \d+ - /i.test(clip.title || "") ? "" : clip.title)
                        return (
                          <article
                            key={clip.id}
                            className={`clip-card${selectedClips.includes(clip.id) ? " selected" : ""}`}
                          >
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
                                  className="clip-fallback"
                                  style={{
                                    background: clip.thumbnail_url
                                      ? `url(${clip.thumbnail_url}) center / cover`
                                      : "linear-gradient(160deg,#2a2213,#141821)",
                                  }}
                                >
                                  <Play size={20} />
                                </div>
                              )}
                              <div className="clip-shade" />
                              <button
                                type="button"
                                className="clip-open"
                                aria-label={`Open clip ${clipIndex + 1}`}
                                title="Open video, AI metadata, download, upload to YouTube"
                                onClick={() => setModalClipId(clip.id)}
                              />
                              <span className="clip-index">
                                {String(clipIndex + 1).padStart(2, "0")}
                                <i>/{clips.length}</i>
                              </span>
                              <span className="clip-play" aria-hidden="true">
                                <Play size={16} />
                              </span>

                              {/* Viral Index bubble — klik = hitung ulang skor */}
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
                                    {score === null ? "—" : Math.round(score)}
                                    {estimated && score !== null ? <sup>≈</sup> : null}
                                  </span>
                                </span>
                              </button>
                              {clip.youtube_uploaded && (
                                <a
                                  className="clip-yt-badge"
                                  href={
                                    clip.youtube_video_id
                                      ? `https://youtu.be/${clip.youtube_video_id}`
                                      : "#"
                                  }
                                  target="_blank"
                                  rel="noreferrer"
                                  title="Open on YouTube"
                                >
                                  <YouTubeIcon size={12} /> Uploaded
                                </a>
                              )}
                            </div>

                            <div className="clip-body">
                              <p className="clip-title">
                                {hookText || `Clip ${clipIndex + 1}`}
                              </p>
                              <div className="clip-meta">
                                <span>{formatDuration(clip.duration)}</span>
                                {clip.file_size ? (
                                  <>
                                    <b>•</b>
                                    <span>{formatSize(clip.file_size)}</span>
                                  </>
                                ) : null}
                                {clip.subtitle_url ? (
                                  <>
                                    <b>•</b>
                                    <span>subtitle</span>
                                  </>
                                ) : null}
                              </div>

                              {cardUploading[clip.id] && (
                                <YouTubeUploadProgress
                                  progress={cardUploadProgress[clip.id] || 0}
                                />
                              )}

                              <div className="clip-actions">
                                <label className="clip-pick" title="Select for merge/upload">
                                  <input
                                    type="checkbox"
                                    className="clip-select"
                                    checked={selectedClips.includes(clip.id)}
                                    onChange={() => toggleClipSelection(clip.id)}
                                  />
                                  <span>Select</span>
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
                                    title="Split point (seconds)"
                                  />
                                  <button
                                    type="button"
                                    className="clip-icon-btn"
                                    title="Split at this point"
                                    disabled={editingBusy}
                                    onClick={() => splitClipAt(clip)}
                                  >
                                    <Scissors size={13} />
                                  </button>
                                </div>

                                <button
                                  type="button"
                                  className="clip-icon-btn"
                                  title={
                                    clip.youtube_uploaded
                                      ? "Re-upload this clip to YouTube"
                                      : "Upload this clip to YouTube"
                                  }
                                  disabled={Boolean(cardUploading[clip.id])}
                                  onClick={() => void uploadClipFromCard(clip)}
                                >
                                  {cardUploading[clip.id] ? (
                                    <ClipzySpinner size="xs" />
                                  ) : (
                                    <YouTubeIcon size={13} />
                                  )}
                                </button>

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

      {activeTab === "upload" && (
        <PreviewDock
          poster={clips[0]?.thumbnail_url || null}
          caption={subtitlePreviewText}
          captionStyle={captionStyle}
          aspectRatio={aspectRatioValue}
          filterPreset={filterPreset}
          blurFill={blurFill}
          watermarkUrl={watermarkUrl}
          watermarkPosition={watermarkPosition}
          speed={speedValue}
          musicName={previewMusicName}
          musicDucking={musicDucking}
          removeSilence={trimSilence}
          cleanAudio={cleanAudio}
          autoZoom={autoZoom}
          introUrl={introUrl}
          outroUrl={outroUrl}
        />
      )}

      <ConfirmDialog
        open={confirmDisconnect}
        title="Disconnect YouTube?"
        description={
          <>
            Clipzy AI will stop auto-uploading clips to{" "}
            <strong>{youtube.channel_name || "your YouTube channel"}</strong> and the stored access token will be
            removed. Your clips and projects stay untouched — you can reconnect anytime.
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

      <ConfirmDialog
        open={Boolean(confirmDeleteTask)}
        title="Delete this project?"
        description={
          <>
            <strong>{confirmDeleteTask?.label || "This project"}</strong> and all of its generated
            clips will be removed permanently. Clips already uploaded to YouTube are not affected.
            This action cannot be undone.
          </>
        }
        confirmLabel="Delete project"
        cancelLabel="Keep project"
        danger
        busy={deletingTask}
        onCancel={() => {
          if (!deletingTask) setConfirmDeleteTask(null)
        }}
        onConfirm={() => {
          if (confirmDeleteTask) void removeTask(confirmDeleteTask.id)
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
