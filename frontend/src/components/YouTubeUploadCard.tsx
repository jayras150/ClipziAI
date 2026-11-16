"use client"

import { useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Check,
  Clock,
  Film,
  Globe,
  Play,
  RotateCcw,
  Shield,
  Upload,
  Zap,
} from "lucide-react"

export type YouTubeUploadCardProps = {
  progress: number
  status?: string
  error?: string | null
  bytesSent?: number
  totalBytes?: number
  title?: string
  durationSeconds?: number
  privacy?: string
  videoUrl?: string
  onRetry?: () => void
}

const STEPS = [
  { title: "Upload", icon: Upload },
  { title: "HD Processing", icon: Film },
  { title: "Checks", icon: Shield },
  { title: "Ready", icon: Play },
]

function stageIndex(percent: number): number {
  if (percent < 55) return 0
  if (percent < 82) return 1
  if (percent < 100) return 2
  return 3
}

function mb(bytes: number): number {
  return Math.max(0, bytes) / (1024 * 1024)
}

function formatDuration(seconds?: number): string {
  const total = Math.max(0, Math.round(seconds || 0))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}

export default function YouTubeUploadCard({
  progress,
  status = "uploading",
  error,
  bytesSent = 0,
  totalBytes = 0,
  title = "clip.mp4",
  durationSeconds,
  privacy = "public",
  videoUrl,
  onRetry,
}: YouTubeUploadCardProps) {
  const percent = Math.max(0, Math.min(100, Math.round(Number(progress) || 0)))
  const isError = status === "error" || Boolean(error)
  const isDone = status === "done" || percent >= 100
  const isPaused = status === "paused"
  const stage = stageIndex(percent)

  const [speed, setSpeed] = useState(0)
  const last = useRef<{ at: number; bytes: number } | null>(null)

  useEffect(() => {
    const now = Date.now()
    const previous = last.current
    if (previous && now > previous.at && bytesSent >= previous.bytes) {
      const deltaBytes = bytesSent - previous.bytes
      const deltaSec = (now - previous.at) / 1000
      if (deltaSec > 0.2) setSpeed(deltaBytes / deltaSec)
    }
    last.current = { at: now, bytes: bytesSent }
  }, [bytesSent])

  const sentMb = mb(bytesSent)
  const totalMb = mb(totalBytes)
  const remainingMb = Math.max(0, totalMb - sentMb)
  const speedMb = mb(speed)
  const etaSec = speedMb > 0.01 ? Math.ceil(remainingMb / speedMb) : 0

  const cardClass = [
    "ytup-card",
    isError ? "is-error" : "",
    isDone ? "is-done" : "",
    isPaused ? "is-paused" : "",
  ]
    .filter(Boolean)
    .join(" ")

  const headline = isError
    ? `Upload failed at ${percent}% — connection lost`
    : isDone
      ? "Published to YouTube!"
      : isPaused
        ? `Upload paused (${percent}%)`
        : stage === 0
          ? `Uploading video... (${percent}%)`
          : stage === 1
            ? "Processing HD & 4K versions..."
            : "Checking copyright & policy..."

  const statusText = isError
    ? "0.0 MB/s"
    : isDone
      ? "Completed"
      : isPaused
        ? "0.0 MB/s"
        : stage === 0
          ? `${speedMb.toFixed(1)} MB/s`
          : stage === 1
            ? "4K VP9 Render"
            : "Content ID Scan"

  const etaText = isError
    ? "Paused due to error"
    : isDone
      ? "Ready to watch"
      : isPaused
        ? "Paused"
        : stage === 0
          ? etaSec > 0
            ? `Est. ${etaSec}s remaining`
            : "Calculating..."
          : `Est. ${Math.max(1, Math.ceil((100 - percent) * 0.25))}s left`

  return (
    <section className={cardClass} aria-label="YouTube upload progress" role="region">
      <header className="ytup-head">
        <div className="ytup-thumb">
          <div className="ytup-badge" aria-hidden="true">
            <Play size={13} fill="#fff" color="#fff" />
          </div>
          <span className="ytup-duration">{formatDuration(durationSeconds)}</span>
        </div>
        <div className="ytup-meta">
          <div className="ytup-title-row">
            <h3 className="ytup-title" title={title}>
              {title}
            </h3>
            <span className="ytup-pill">MP4 • H.264</span>
          </div>
          <div className="ytup-sub">
            <span>
              Privacy: <strong>{privacy}</strong>
            </span>
            <span className="ytup-dot" />
            <span>
              Total: <strong>{totalMb > 0 ? `${totalMb.toFixed(0)} MB` : "—"}</strong>
            </span>
          </div>
        </div>
      </header>

      <section className="ytup-status">
        <div className="ytup-status-top">
          <div className="ytup-status-label">
            <span className={`ytup-status-dot${isError || isDone || isPaused ? "" : " pulsing"}`} />
            <h4 className="ytup-headline">{headline}</h4>
          </div>
          <div className="ytup-percent">{percent}%</div>
        </div>

        <div
          className="ytup-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <div className="ytup-fill" style={{ width: `${percent}%` }} />
        </div>

        <div className="ytup-telemetry">
          <div className="ytup-telemetry-group">
            <span className="ytup-telemetry-item">
              <Upload size={13} />
              <strong>
                {sentMb.toFixed(0)} MB / {totalMb > 0 ? `${totalMb.toFixed(0)} MB` : "—"}
              </strong>
            </span>
            <span className="ytup-telemetry-item">
              <Zap size={13} />
              <strong>{statusText}</strong>
            </span>
          </div>
          <span className="ytup-telemetry-item">
            <Clock size={13} />
            <span>{etaText}</span>
          </span>
        </div>

        {isError ? (
          <div className="ytup-error" role="alert">
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              <AlertTriangle size={16} color="#ef4444" />
              <span>{error || "The upload stopped before YouTube returned a video id."}</span>
            </span>
          </div>
        ) : null}
      </section>

      <section className="ytup-steps" aria-label="Upload stages">
        {STEPS.map((step, index) => {
          const state = isDone
            ? "done"
            : index < stage
              ? "done"
              : index === stage
                ? isError
                  ? "error"
                  : "active"
                : "pending"
          const Icon = step.icon
          const sub = isDone
            ? index === 3
              ? "Live now"
              : "Completed"
            : state === "done"
              ? "Completed"
              : state === "error"
                ? "Failed"
                : state === "active"
                  ? isPaused
                    ? "Paused"
                    : "In progress"
                  : "Pending"
          return (
            <div key={step.title} className={`ytup-step ${state}`}>
              <div className="ytup-step-circle">
                {state === "done" ? <Check size={15} /> : state === "error" ? <AlertTriangle size={14} /> : <Icon size={15} />}
              </div>
              <div className="ytup-step-title">{step.title}</div>
              <div className="ytup-step-sub">{sub}</div>
            </div>
          )
        })}
      </section>

      <footer className="ytup-footer">
        <div className="ytup-visibility">
          <Globe size={13} color="#10b981" />
          <span>
            Visibility: <strong style={{ color: "#f8fafc" }}>{privacy}</strong>
          </span>
        </div>
        <div className="ytup-btn-group">
          <button className="ytup-btn" type="button" disabled title="Upload cannot be paused">
            Pause
          </button>
          {isError && onRetry ? (
            <button className="ytup-btn ytup-btn-primary" type="button" onClick={onRetry}>
              <RotateCcw size={13} /> Retry upload
            </button>
          ) : null}
          {isDone && videoUrl ? (
            <a className="ytup-btn ytup-btn-primary" href={videoUrl} target="_blank" rel="noreferrer">
              <Play size={13} /> Replay
            </a>
          ) : null}
        </div>
      </footer>
    </section>
  )
}
