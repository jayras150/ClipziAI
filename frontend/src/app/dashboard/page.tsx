"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Upload, Play, Youtube, Unlink, LoaderCircle, Link2 } from "lucide-react"
import { api } from "@/lib/api"
import SiteFooter from "@/components/SiteFooter"

const SAMPLE_PROJECTS = [
  { id: 1, title: "Cooking tutorial", status: "completed", progress: 100, clips: 5 },
  { id: 2, title: "Tech review", status: "processing", progress: 65, clips: 3 },
  { id: 3, title: "Travel vlog", status: "queued", progress: 0, clips: 0 },
]

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"upload" | "projects">("upload")
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeMessage, setYoutubeMessage] = useState("")

  const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem("token"))

  useEffect(() => {
    const token = getToken()
    if (!token) return
    api
      .getYouTubeStatus(token)
      .then(setYoutube)
      .catch(() => setYoutubeMessage("Sign in to view your YouTube status."))

    const status = new URLSearchParams(window.location.search).get("youtube")
    if (status === "connected") setYoutubeMessage("YouTube connected successfully.")
    if (status === "denied") setYoutubeMessage("Izin YouTube dibatalkan.")
    if (status === "error") setYoutubeMessage("YouTube connection failed. Check the Google OAuth configuration.")
  }, [])

  const connectYouTube = async () => {
    const token = getToken()
    if (!token) {
      window.location.href = "/login"
      return
    }
    setYoutubeLoading(true)
    setYoutubeMessage("")
    try {
      window.location.href = await api.getYouTubeAuthUrl(token)
    } catch (error: any) {
      setYoutubeMessage(error.response?.data?.detail || "Could not start the YouTube connection.")
      setYoutubeLoading(false)
    }
  }

  const disconnectYouTube = async () => {
    const token = getToken()
    if (!token) return
    setYoutubeLoading(true)
    try {
      await api.disconnectYouTube(token)
      setYoutube({ connected: false })
      setYoutubeMessage("YouTube connection removed.")
    } catch {
      setYoutubeMessage("Could not remove the YouTube connection.")
    } finally {
      setYoutubeLoading(false)
    }
  }

  return (
    <div className="ui-shell">
      <div className="ui-container ui-nav">
        <Link className="ui-brand" href="/">
          <span className="ui-brand-mark">â–¶</span>
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
              Projects
            </button>
          </div>
        </div>

        {youtubeMessage && (
          <div className="ui-alert" style={{ marginBottom: 20 }}>
            <Link2 size={15} /> {youtubeMessage}
          </div>
        )}


        {activeTab === "upload" ? (
          <div className="ui-card">
            <h2 className="ui-subtitle">Upload video</h2>
            <p className="ui-muted" style={{ marginBottom: 20 }}>
              Paste a video link or upload a file. AI will pick the best moments.
            </p>

            <div className="ui-dropzone">
              <Upload size={40} className="ui-gold" style={{ margin: "0 auto 12px" }} />
              <p style={{ fontSize: 14, color: "#e6e7ea" }}>Click or drag a video file here</p>
              <p className="ui-hint">Max 2 GB · MP4, MOV, AVI</p>
            </div>

            <div style={{ marginTop: 22 }}>
              <label className="ui-label" htmlFor="video-url">
                Or paste a video URL
              </label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input
                  id="video-url"
                  type="text"
                  placeholder="https://youtube.com/watch?v=..."
                  className="ui-input"
                  style={{ flex: "1 1 260px" }}
                />
                <button className="ui-btn ui-btn-gold">
                  <Play size={15} /> Process
                </button>
              </div>
              <p className="ui-hint">
                1 credit per clip. Processing runs on cloud GPUs and the instance shuts down
                automatically when the task finishes.
              </p>
            </div>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 16,
            }}
          >
            {SAMPLE_PROJECTS.map((project) => (
              <article key={project.id} className="ui-card ui-card-hover">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    marginBottom: 16,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 10,
                        display: "grid",
                        placeItems: "center",
                        background: "rgba(233, 189, 101, 0.12)",
                        color: "var(--ui-gold)",
                      }}
                    >
                      <Play size={15} />
                    </div>
                    <h3 className="ui-subtitle" style={{ margin: 0, fontSize: 16 }}>
                      {project.title}
                    </h3>
                  </div>
                  <span
                    className={`ui-badge${
                      project.status === "completed"
                        ? " ui-badge-success"
                        : project.status === "processing"
                          ? " ui-badge-gold"
                          : ""
                    }`}
                  >
                    {project.status}
                  </span>
                </div>

                <div className="ui-progress" style={{ marginBottom: 12 }}>
                  <span style={{ width: `${project.progress}%` }} />
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 12,
                    color: "var(--ui-muted)",
                  }}
                >
                  <span>{project.clips} clips</span>
                  <span>{project.progress}%</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
      <SiteFooter />
    </div>
  )
}

