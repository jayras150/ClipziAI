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
} from "lucide-react"

import { api, ClipData, TaskData } from "@/lib/api"
import { readApiError } from "@/lib/api-errors"
import { requestYouTubeAccessToken } from "@/lib/social"
import SiteFooter from "@/components/SiteFooter"

const ACTIVE_STATUSES = ["queued", "processing"]

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

export default function DashboardPage() {
  const [token, setToken] = useState("")
  const [activeTab, setActiveTab] = useState<"upload" | "projects">("upload")
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeMessage, setYoutubeMessage] = useState("")

  const [tasks, setTasks] = useState<TaskData[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [urlValue, setUrlValue] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [taskError, setTaskError] = useState("")
  const [notice, setNotice] = useState("")

  const [openTaskId, setOpenTaskId] = useState("")
  const [clips, setClips] = useState<ClipData[]>([])
  const [clipsLoading, setClipsLoading] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)


  const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem("token"))

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
      const needsFallback =
        error.response?.status === 409 && /redirect[ _]uri/i.test(detail) && /mismatch|terdaftar/i.test(detail)

      if (!needsFallback) {
        setYoutubeMessage(readApiError(error.response?.data, "Could not start the YouTube connection."))
        setYoutubeLoading(false)
        return
      }

      // Redirect URI belum terdaftar di Google Console → pakai alur token Google
      // Identity Services (tidak memerlukan redirect URI sama sekali).
      try {
        setYoutubeMessage("Opening Google consent…")
        const diagnostics = await api.getYouTubeDiagnostics(stored)
        const accessToken = await requestYouTubeAccessToken(diagnostics.client_id || "")
        const connected = await api.setYouTubeAccessToken(stored, accessToken)
        setYoutube({ connected: true, channel_name: connected.channel_name })
        setYoutubeMessage(connected.message || "YouTube connected.")
      } catch (fallbackError: any) {
        setYoutubeMessage(fallbackError?.message || "Could not connect YouTube.")
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
      const task = await api.createTask(stored, url)
      setUrlValue("")
      if (task.status === "error") {
        setTaskError(task.error_message || "The task was created but could not be sent to a GPU worker.")
      } else {
        setNotice("Task created — Clipzy AI is processing your video.")
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

  const onPickFile = (file: File | null) => {
    if (!file) return
    setTaskError("")
    setNotice(
      `"${file.name}" selected. Direct file upload is not available yet — paste a YouTube, TikTok or Instagram link above to start processing.`,
    )
  }

  const openTaskData = tasks.find((task) => task.id === openTaskId) || null

  return (
    <div className="ui-shell">
      <div className="ui-container ui-nav">
        <Link className="ui-brand" href="/">
          <span className="ui-brand-mark">▶</span>
          <span>
            clipzy<em>AI</em>
          </span>
        </Link>
        <nav className="ui-nav-links">
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/profile">Profile</Link>
        </nav>
        <div className="ui-nav-actions">
          <button
            onClick={youtube.connected ? disconnectYouTube : connectYouTube}
            disabled={youtubeLoading}
            className="ui-btn ui-btn-ghost"
          >
            {youtubeLoading ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : youtube.connected ? (
              <Unlink size={15} />
            ) : (
              <Youtube size={15} />
            )}
            {youtube.connected ? `YouTube: ${youtube.channel_name || "Connected"}` : "Connect YouTube"}
          </button>
        </div>
      </div>

      <main className="ui-container" style={{ padding: "38px 0 70px" }}>
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
            <div className="ui-kicker">Studio</div>
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
          <div className="ui-card">
            <h2 className="ui-subtitle">Upload video</h2>
            <p className="ui-muted" style={{ marginBottom: 20 }}>
              Paste a video link and Clipzy AI will pick the best moments, caption them, and crop to 9:16.
            </p>

            <form onSubmit={submitUrl}>
              <label className="ui-label" htmlFor="video-url">
                Video URL
              </label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input
                  id="video-url"
                  type="url"
                  value={urlValue}
                  onChange={(event) => setUrlValue(event.target.value)}
                  placeholder="https://youtube.com/watch?v=..."
                  className="ui-input"
                  style={{ flex: "1 1 260px" }}
                />
                <button type="submit" className="ui-btn ui-btn-gold" disabled={submitting}>
                  {submitting ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />}
                  {submitting ? "Starting…" : "Process"}
                </button>
              </div>
              <p className="ui-hint">
                YouTube, TikTok, Instagram, Facebook and X links are supported. 1 credit per clip.
              </p>
            </form>

            <div style={{ marginTop: 22 }}>
              <div
                className="ui-dropzone"
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click()
                }}
              >
                <Upload size={40} className="ui-gold" style={{ margin: "0 auto 12px" }} />
                <p style={{ fontSize: 14, color: "#e6e7ea" }}>Click or drag a video file here</p>
                <p className="ui-hint">Max 2 GB · MP4, MOV, AVI</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                hidden
                onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
              />
              <p className="ui-hint" style={{ marginTop: 10 }}>
                Direct file upload is still rolling out — paste a link above for now.
              </p>
            </div>
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
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
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
                            {task.source_type} · {formatDate(task.created_at)}
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
                  <p className="ui-hint" style={{ marginTop: 14 }}>
                    {openTaskData.status === "error"
                      ? openTaskData.error_message || "This task failed before producing clips."
                      : "No clips yet — this panel refreshes automatically while the task runs."}
                  </p>
                ) : (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
                      gap: 14,
                      marginTop: 16,
                    }}
                  >
                    {clips.map((clip) => (
                      <div
                        key={clip.id}
                        style={{
                          border: "1px solid rgba(255,255,255,.08)",
                          borderRadius: 14,
                          overflow: "hidden",
                          background: "#12141a",
                        }}
                      >
                        <div
                          style={{
                            aspectRatio: "9 / 16",
                            position: "relative",
                            background: clip.thumbnail_url
                              ? `url(${clip.thumbnail_url}) center / cover`
                              : "linear-gradient(160deg,#2a2213,#141821)",
                          }}
                        >
                          <span
                            style={{
                              position: "absolute",
                              left: 10,
                              top: 10,
                              fontSize: 11,
                              padding: "3px 8px",
                              borderRadius: 999,
                              background: "rgba(0,0,0,.6)",
                              color: "#f4d99a",
                            }}
                          >
                            #{clip.clip_index + 1}
                          </span>
                          {typeof clip.viral_score === "number" && (
                            <span
                              style={{
                                position: "absolute",
                                right: 10,
                                top: 10,
                                fontSize: 11,
                                padding: "3px 8px",
                                borderRadius: 999,
                                background: "rgba(244,199,107,.18)",
                                color: "#f4d99a",
                              }}
                            >
                              {Math.round(clip.viral_score)}
                            </span>
                          )}
                        </div>
                        <div style={{ padding: 12, display: "grid", gap: 8 }}>
                          <strong style={{ fontSize: 13.5 }}>
                            {clip.title || `Clip ${clip.clip_index + 1}`}
                          </strong>
                          <span style={{ fontSize: 11.5, color: "var(--ui-muted)" }}>
                            {formatDuration(clip.duration)}
                            {clip.file_size ? ` · ${formatSize(clip.file_size)}` : ""}
                          </span>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {clip.download_url && (
                              <a
                                className="ui-btn ui-btn-gold"
                                style={{ fontSize: 12, padding: "8px 12px" }}
                                href={clip.download_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Download size={13} /> MP4
                              </a>
                            )}
                            {clip.subtitle_url && (
                              <a
                                className="ui-btn ui-btn-ghost"
                                style={{ fontSize: 12, padding: "8px 12px" }}
                                href={clip.subtitle_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                SRT
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
      <SiteFooter />
    </div>
  )
}
