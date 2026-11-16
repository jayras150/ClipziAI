/**
 * Popup satu klip: player video + metadata YouTube yang dibuat AI dari transkrip
 * Whispers (judul, deskripsi, tag) + download + upload ke YouTube.
 *
 * Catatan: file ini SENGAJA tanpa directive `"use client"` karena hanya
 * di-import oleh dashboard yang sudah merupakan client boundary. Dengan begitu
 * callback props (onClose/onUpdated/onConnectYouTube) tidak dianggap sebagai
 * props lintas Server→Client yang wajib serializable.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  CheckCircle2,
  Download,
  Sparkles,
  Wand2,
  X,
} from "lucide-react"

import { api, ClipData, ClipThumbnailData } from "@/lib/api"
import { ClipzySpinner } from "@/components/ClipzySpinner"
import YouTubeIcon from "@/components/YouTubeIcon"
import YouTubeUploadCard from "@/components/YouTubeUploadCard"
import AlertDialog from "@/components/AlertDialog"
import YouTubeOpenCard from "@/components/YouTubeOpenCard"
import YouTubeSuccessToast from "@/components/YouTubeSuccessToast"
import {
  DEFAULT_CAPTION_POSITION,
  DEFAULT_CAPTION_STYLE,
  THUMBNAIL_CAPTION_ANCHORS,
  THUMBNAIL_CAPTION_STYLES,
} from "@/lib/caption-catalog"
import { readApiError, readApiErrorInfo } from "@/lib/api-errors"
import { SUBTITLE_STYLE_OPTIONS } from "@/lib/caption-styles"

function formatClock(seconds: number): string {
  const total = Math.max(0, Number(seconds) || 0)
  const m = String(Math.floor(total / 60)).padStart(2, "0")
  const s = String(Math.floor(total % 60)).padStart(2, "0")
  const c = String(Math.floor((total % 1) * 100)).padStart(2, "0")
  return `${m}:${s}.${c}`
}

/**
 * Popup satu klip: player video + metadata YouTube yang dibuat AI dari transkrip
 * Whispers (judul, deskripsi, tag) + download + upload ke YouTube.
 *
 * Metadata tidak pernah memakai template: judul/deskripsi/tag berasal dari
 * transkrip klip (AI menolak membuat kalau transkrip tidak ada).
 */
export default function ClipModal({
  clip,
  token,
  youtubeConnected,
  onClose,
  onUpdated,
  onConnectYouTube,
}: {
  clip: ClipData | null
  token: string
  youtubeConnected: boolean
  onClose: () => void
  onUpdated: (clipId: string, patch: Partial<ClipData>) => void
  onConnectYouTube: () => void
}) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [tagsText, setTagsText] = useState("")
  const [transcript, setTranscript] = useState("")
  const [privacy, setPrivacy] = useState("unlisted")
  const [category, setCategory] = useState("22")
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadStats, setUploadStats] = useState<{
    status: string
    bytesSent: number
    totalBytes: number
    error: string | null
  }>({ status: "idle", bytesSent: 0, totalBytes: 0, error: null })
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [ytAlert, setYtAlert] = useState<{ title: string; message: string; detail?: string; href?: string } | null>(null)
  const [uploadUrl, setUploadUrl] = useState("")
  const [thumbs, setThumbs] = useState<ClipThumbnailData | null>(null)
  const [capStyle, setCapStyle] = useState(DEFAULT_CAPTION_STYLE)
  const [capPosition, setCapPosition] = useState<string>(DEFAULT_CAPTION_POSITION)
  const [capText, setCapText] = useState("")
  const [capBusy, setCapBusy] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const capTrackRef = useRef<HTMLDivElement | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)
  const [videoError, setVideoError] = useState(false)
  const [videoRatio, setVideoRatio] = useState<number | null>(null)
  const [filmstrip, setFilmstrip] = useState<{ at_second: number; url: string }[]>([])
  const [ytThumbBusy, setYtThumbBusy] = useState(false)
  const [successOpen, setSuccessOpen] = useState(false)
  const [liveThumb, setLiveThumb] = useState("")
  const [posOpen, setPosOpen] = useState(false)
  const stripRef = useRef<HTMLDivElement | null>(null)
  const draggingRef = useRef(false)
  const [thumbBusy, setThumbBusy] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [editProgress, setEditProgress] = useState(0)
  const [editTrimStart, setEditTrimStart] = useState("")
  const [editTrimEnd, setEditTrimEnd] = useState("")
  const [editSpeed, setEditSpeed] = useState("1")
  const [editFilter, setEditFilter] = useState("none")
  const [editCaption, setEditCaption] = useState("")
  const [editCaptionStyle, setEditCaptionStyle] = useState("classic")
  // Sisa kuota tombol "Regenerate with AI" (maks 3 per klip), dari server.
  const [regenLeft, setRegenLeft] = useState<number | null>(null)

  const autoTried = useRef<Set<string>>(new Set())
  const clipId = clip?.id ?? ""
  const busy = generating || saving || uploading || thumbBusy || editBusy

  const tags = tagsText
    .split(",")
    .map((tag) => tag.trim().replace(/^#/, ""))
    .filter(Boolean)

  const applyMetadata = useCallback(
    (data: { title: string; description: string; tags: string[]; transcript: string; hook?: string | null }) => {
      setTitle(data.title)
      setDescription(data.description)
      setTagsText(data.tags.join(", "))
      setTranscript(data.transcript)
      if (clipId) {
        onUpdated(clipId, {
          ai_suggested_title: data.title || null,
          ai_suggested_description: data.description || null,
          ai_suggested_tags: data.tags,
        })
      }
    },
    [clipId, onUpdated],
  )

  const generate = useCallback(
    async (regenerate: boolean) => {
      if (!clipId) return
      setGenerating(true)
      setError("")
      setNotice(regenerate ? "Writing a new version from the transcript…" : "AI is reading the clip transcript…")
      try {
        const data = await api.generateClipMetadata(token, clipId, regenerate)
        if (typeof data.regenerate_left === "number") setRegenLeft(data.regenerate_left)
        if (data.status === "failed") {
          setNotice("")
          setError(data.message || "This clip has no transcript, so no metadata was created.")
          return
        }
        if (data.status === "preparing") {
          // Klip lama: transkrip dibuat di latar belakang (bisa >1 menit).
          setNotice(data.message || "Clip transcript is being prepared…")
          void pollPrepared(0)
          return
        }
        applyMetadata({
          title: data.title,
          description: data.description,
          tags: data.tags,
          transcript: data.transcript,
          hook: data.hook,
        })
        setNotice("Metadata generated by AI from this clip's Whisper transcript.")
      } catch (err: any) {
        setNotice("")
        setError(readApiError(err.response?.data, "Could not generate metadata from the transcript."))
      } finally {
        setGenerating(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [applyMetadata, clipId, token],
  )

  /** Tunggu transkrip latar belakang selesai, lalu ambil metadata yang sudah tersimpan. */
  const pollPrepared = useCallback(
    async (attempt: number) => {
      if (!clipId) return
      if (attempt >= 60) {
        setNotice("")
        setError("Transcript is still processing. Tap \"Regenerate with AI\" again in a moment.")
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 5000))
      try {
        const data = await api.generateClipMetadata(token, clipId, false)
        if (typeof data.regenerate_left === "number") setRegenLeft(data.regenerate_left)
        if (data.status === "failed") {
          setNotice("")
          setError(data.message || "This clip has no transcript, so no metadata was created.")
          return
        }
        if (data.status === "preparing" || !data.title) {
          await pollPrepared(attempt + 1)
          return
        }
        applyMetadata({
          title: data.title,
          description: data.description,
          tags: data.tags,
          transcript: data.transcript,
          hook: data.hook,
        })
        setNotice("Metadata ready — generated from the clip transcript.")
      } catch (err: any) {
        setNotice("")
        setError(readApiError(err.response?.data, "Could not load metadata after the transcript finished."))
      }
    },
    [applyMetadata, clipId, token],
  )

  // Reset isi form setiap kali klip yang dibuka berubah, lalu minta AI sekali
  // bila klip belum punya metadata.
  useEffect(() => {
    if (!clip) return
    setTitle(clip.ai_suggested_title || "")
    setDescription(clip.ai_suggested_description || "")
    setTagsText((clip.ai_suggested_tags || []).join(", "))
    setTranscript("")
    setError("")
    setNotice("")
    setUploadUrl(
      clip.youtube_video_id ? `https://youtu.be/${clip.youtube_video_id}` : "",
    )
    setThumbs(null)
    const storedThumbs = Array.isArray(clip.viral_factors?.thumbnail_candidates)
      ? (clip.viral_factors?.thumbnail_candidates as ClipThumbnailData["candidates"])
      : []
    if (storedThumbs.length > 0) {
      setThumbs({
        clip_id: clip.id,
        candidates: storedThumbs,
        selected_url: clip.thumbnail_url,
        hook: clip.ai_hook || null,
      })
    }
    setEditOpen(false)
    setEditProgress(0)
    const manual = (clip.viral_factors?.manual_edit || {}) as Record<string, any>
    setEditTrimStart(String(manual.trim_start ?? ""))
    setEditTrimEnd(String(manual.trim_end ?? ""))
    setEditSpeed(String(manual.speed ?? "1"))
    setEditFilter(String(manual.filter_preset ?? "none"))
    setEditCaption(String(manual.caption_text ?? ""))
    setEditCaptionStyle(String(manual.caption_style ?? "classic"))
    if (!clip.ai_suggested_title && !autoTried.current.has(clip.id)) {
      autoTried.current.add(clip.id)
      void generate(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clip?.id])

  useEffect(() => {
    if (!clip) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [clip, busy, onClose])

  const save = async () => {
    if (!clipId) return
    setSaving(true)
    setError("")
    setNotice("")
    try {
      const data = await api.updateClipMetadata(token, clipId, {
        title: title.trim(),
        description,
        tags,
      })
      applyMetadata({ title: data.title, description: data.description, tags: data.tags, transcript: data.transcript })
      setNotice("Metadata saved. Ready to upload.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not save metadata."))
    } finally {
      setSaving(false)
    }
  }

  const upload = async () => {
    if (!clipId) return
    if (!youtubeConnected) {
      setError("YouTube is not connected. Connect it first, then reopen this popup.")
      return
    }
    if (!title.trim()) {
      setError("A title is required before uploading.")
      return
    }
    setUploading(true)
    setUploadProgress(0)
    setUploadStats({
      status: "uploading",
      bytesSent: 0,
      totalBytes: Number(clip.file_size || 0),
      error: null,
    })
    setError("")
    setNotice("")
    try {
      const result = await api.uploadClipToYouTube(token, clipId, {
        title: title.trim(),
        description,
        tags,
        privacy_status: privacy,
        category_id: category,
        force: Boolean(uploadUrl),
      })
      if ("accepted" in result && result.accepted) {
        // 202: server mengunggah di background. Progress di-poll dari backend;
        // UI hanya menampilkan satu kalimat + bar sesuai permintaan produk.
        const final = await api.waitForYouTubeUpload(token, clipId, {
          onProgress: (status) => {
            setUploadProgress((current) =>
              Math.max(current, Math.min(99, Math.round(Number(status.progress) || 0))),
            )
            setUploadStats({
              status: status.status || "uploading",
              bytesSent: Number(status.bytes_sent || 0),
              totalBytes: Number(status.total_bytes || 0) || Number(clip.file_size || 0),
              error: status.error || null,
            })
          },
        })
        if (final.status !== "done" || !final.youtube_video_id) {
          throw new Error(final.error || "Upload stopped before YouTube returned a video id.")
        }
        setUploadProgress(100)
        setUploadStats((prev) => ({
          ...prev,
          status: "done",
          bytesSent: prev.totalBytes,
          error: null,
        }))
        setUploadUrl(final.youtube_video_url || "")
        setNotice("")
        setSuccessOpen(true)
        onUpdated(clipId, {
          youtube_uploaded: true,
          youtube_video_id: final.youtube_video_id,
        })
        return
      }
      const syncResult = result as {
        success?: boolean
        error?: string | null
        youtube_video_url?: string | null
        youtube_video_id?: string | null
        already_uploaded?: boolean
      }
      if (!syncResult.success) {
        throw new Error(syncResult.error || "Upload failed.")
      }
      setUploadUrl(syncResult.youtube_video_url || "")
      if (syncResult.already_uploaded) {
        setNotice("This clip was already uploaded to YouTube.")
      } else {
        setNotice("")
        setSuccessOpen(true)
      }
      onUpdated(clipId, {
        youtube_uploaded: true,
        youtube_video_id: syncResult.youtube_video_id || null,
      })
    } catch (err: any) {
      setNotice("")
      const message = readApiError(err.response?.data, err.message || "YouTube upload failed.")
      setError(message)
      setUploadStats((prev) => ({ ...prev, status: "error", error: message }))
    } finally {
      setUploading(false)
    }
  }

  const generateThumbnails = async () => {
    if (!clipId) return
    setThumbBusy(true)
    setError("")
    setNotice("")
    try {
      const data = await api.generateClipThumbnails(token, clipId)
      setThumbs(data)
      setNotice("Three thumbnail candidates ready. Pick one as the clip poster.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not generate thumbnail candidates."))
    } finally {
      setThumbBusy(false)
    }
  }


  useEffect(() => {
    if (!clipId || !token) return
    let alive = true
    api
      .getClipFilmstrip(token, clipId, 8)
      .then((data) => {
        if (alive) setFilmstrip(Array.isArray(data.frames) ? data.frames : [])
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [clipId, token])

  const seekTo = (seconds: number) => {
    const video = videoRef.current
    if (!video) return
    const max = Math.max(0, (video.duration || 0) - 0.05)
    video.currentTime = Math.max(0, Math.min(max, seconds))
    setCurrentTime(video.currentTime)
  }

  const seekFromPointer = (clientX: number) => {
    const strip = stripRef.current
    if (!strip) return
    const rect = strip.getBoundingClientRect()
    if (!rect.width) return
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    seekTo(ratio * (videoDuration || clip?.duration || 1))
  }

  const applyCaption = async () => {
    if (!clipId) return
    setCapBusy(true)
    setError("")
    setNotice("")
    try {
      const result = await api.applyThumbnailCaption(token, clipId, {
        text: (capText || clip.ai_hook || clip.title || "Sample caption").trim(),
        style: capStyle,
        position: capPosition,
        at_second: currentTime > 0 ? currentTime : undefined,
      })
      setLiveThumb(result.thumbnail_url)
      onUpdated(clipId, { thumbnail_url: result.thumbnail_url })
      if (clip?.youtube_video_id) {
        try {
          await api.pushThumbnailToYouTube(token, clipId)
          setNotice("Thumbnail applied and synced to YouTube automatically.")
        } catch (err: any) {
          const info = readApiErrorInfo(err?.response?.data, "YouTube sync failed.")
          if (info.code === "youtube_thumbnail_forbidden") {
            setNotice("Thumbnail applied. YouTube needs a verified channel to accept it.")
            setYtAlert({
              title: "YouTube needs a verified channel",
              message: info.message,
              detail: info.reason,
              href: info.href || "https://www.youtube.com/verify",
            })
          } else {
            setNotice(`Thumbnail applied. YouTube: ${info.message}`)
          }
        }
      } else {
        setNotice(`Thumbnail applied (${result.style}, ${result.position}).`)
      }
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not render the thumbnail caption."))
    } finally {
      setCapBusy(false)
    }
  }

  const pushThumbnailToYouTube = async () => {
    if (!clipId) return
    setYtThumbBusy(true)
    setError("")
    setNotice("")
    try {
      await api.pushThumbnailToYouTube(token, clipId)
      setNotice("Thumbnail updated on YouTube.")
    } catch (err: any) {
      const info = readApiErrorInfo(err?.response?.data, "Could not set the YouTube thumbnail.")
      if (info.code === "youtube_thumbnail_forbidden") {
        setYtAlert({
          title: "YouTube needs a verified channel",
          message: info.message,
          detail: info.reason,
          href: info.href || "https://www.youtube.com/verify",
        })
      } else {
        setError(info.message)
      }
    } finally {
      setYtThumbBusy(false)
    }
  }

  const chooseThumbnail = async (url: string) => {
    if (!clipId) return
    setThumbBusy(true)
    setError("")
    try {
      const data = await api.selectClipThumbnail(token, clipId, url)
      setThumbs(data)
      onUpdated(clipId, { thumbnail_url: url })
      setNotice("Thumbnail updated.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Could not select that thumbnail."))
    } finally {
      setThumbBusy(false)
    }
  }

  const applyEdit = async () => {
    if (!clipId) return
    const trimStart = parseFloat(editTrimStart)
    const trimEnd = parseFloat(editTrimEnd)
    const speed = parseFloat(editSpeed)
    const caption = editCaption.trim()
    if (
      Number.isNaN(trimStart) &&
      Number.isNaN(trimEnd) &&
      (Number.isNaN(speed) || speed === 1) &&
      editFilter === "none" &&
      !caption
    ) {
      setError("Choose at least one edit: trim, speed, filter, or caption.")
      return
    }
    setEditBusy(true)
    setEditProgress(5)
    setError("")
    setNotice("Rendering clip edit in the background…")
    try {
      await api.editClip(token, clipId, {
        trim_start: Number.isNaN(trimStart) ? 0 : trimStart,
        trim_end: Number.isNaN(trimEnd) ? undefined : trimEnd,
        speed: Number.isNaN(speed) ? 1 : speed,
        filter_preset: editFilter === "none" ? undefined : editFilter,
        caption_text: caption || undefined,
        caption_style: caption ? editCaptionStyle : undefined,
      })
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        const state = await api.getClipEditStatus(token, clipId)
        setEditProgress(state.progress || 0)
        if (state.status === "done") {
          onUpdated(clipId, {
            download_url: state.download_url || clip?.download_url || null,
            thumbnail_url: state.thumbnail_url || clip?.thumbnail_url || null,
            editing_applied: Array.from(
              new Set([...(clip?.editing_applied || []), "trim", "speed", "filter", "caption"]),
            ),
          })
          setNotice("Clip edited. The new video is ready.")
          setEditBusy(false)
          return
        }
        if (state.status === "error") {
          throw new Error(state.error || "Clip edit failed.")
        }
      }
      throw new Error("Clip edit is still running. Reopen this popup in a minute.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, err.message || "Could not edit this clip."))
    } finally {
      setEditBusy(false)
    }
  }

  if (!clip) return null

  const minutes = Math.floor(clip.duration / 60)
  const seconds = Math.round(clip.duration % 60).toString().padStart(2, "0")

  return (
    <div
      className="ui-modal-backdrop"
      role="presentation"
      onClick={() => {
        if (!busy) onClose()
      }}
    >
      <div
        className="clip-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Clip ${clip.clip_index + 1}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="clip-modal-head">
          <div>
            <p className="clip-modal-eyebrow">
              Clip #{clip.clip_index + 1} · {minutes}:{seconds} · {clip.start_time}–{clip.end_time}
            </p>
            <h3 className="ui-subtitle" style={{ margin: 0 }}>
              AI title, description &amp; tags
            </h3>
          </div>
          <button
            type="button"
            className="clip-modal-close"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="clip-modal-body">
          <div className="clip-modal-media">
            <div
              className="clip-media-stage"
              style={{
                aspectRatio: videoRatio ? `${videoRatio}` : undefined,
                maxWidth: videoRatio ? (videoRatio < 1 ? 380 : 460) : undefined,
              }}
            >
              {clip.download_url && !videoError ? (
                <video
                  key={clip.download_url}
                  ref={videoRef}
                  className="clip-modal-video"
                  src={clip.download_url}
                  poster={liveThumb || clip.thumbnail_url || undefined}
                  controls
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={(event) => {
                    const el = event.currentTarget
                    setVideoDuration(el.duration || 0)
                    setCurrentTime(el.currentTime || 0)
                    if (el.videoWidth && el.videoHeight) {
                      setVideoRatio(el.videoWidth / el.videoHeight)
                    }
                  }}
                  onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                  onError={() => setVideoError(true)}
                />
              ) : (
                <div
                  className="clip-modal-video clip-video-fallback"
                  style={{
                    backgroundImage: clip.thumbnail_url
                      ? `url(${clip.thumbnail_url})`
                      : undefined,
                  }}
                >
                  <span>
                    {clip.download_url
                      ? "Video preview unavailable - reopen the clip to refresh the link."
                      : "No video file for this clip."}
                  </span>
                </div>
              )}
            </div>

            {clip.download_url ? (
              <div className="clip-frame-picker">
                <div
                  className="cs-film"
                  ref={stripRef}
                  onPointerDown={(event) => {
                    draggingRef.current = true
                    event.currentTarget.setPointerCapture(event.pointerId)
                    seekFromPointer(event.clientX)
                  }}
                  onPointerMove={(event) => {
                    if (draggingRef.current) seekFromPointer(event.clientX)
                  }}
                  onPointerUp={() => {
                    draggingRef.current = false
                  }}
                  onPointerCancel={() => {
                    draggingRef.current = false
                  }}
                >
                  {filmstrip.map((frame, index) => (
                    <button
                      key={`${frame.at_second}-${index}`}
                      type="button"
                      className="cs-cell"
                      style={{ backgroundImage: `url(${frame.url})` }}
                      onClick={() => seekTo(frame.at_second)}
                      title={`${frame.at_second.toFixed(2)}s`}
                    />
                  ))}
                  {filmstrip.length === 0
                    ? Array.from({ length: 8 }).map((_, index) => (
                        <span key={`empty-${index}`} className="cs-cell" />
                      ))
                    : null}
                  <span
                    className="cs-playhead"
                    style={{
                      left: `${Math.min(
                        100,
                        Math.max(
                          0,
                          (currentTime / (videoDuration || clip.duration || 1)) * 100,
                        ),
                      )}%`,
                    }}
                  />
                </div>
                <input
                  className="cs-range"
                  type="range"
                  min={0}
                  max={Math.max(0.1, videoDuration || clip.duration || 1)}
                  step={0.04}
                  value={Math.min(currentTime, videoDuration || clip.duration || 1)}
                  onChange={(event) => seekTo(Number(event.target.value))}
                  aria-label="Clip timeline"
                />
                <div className="cs-capture-row">
                  <span className="cs-ms">
                    {formatClock(currentTime)} · frame {Math.round(currentTime * 30)}
                  </span>
                  <button
                    type="button"
                    className="cs-btn"
                    onClick={() => setPosOpen((open) => !open)}
                  >
                    Thumbnail position
                  </button>
                  <button
                    type="button"
                    className="cs-btn cs-btn-play"
                    onClick={() => void applyCaption()}
                    disabled={busy || capBusy}
                  >
                    {capBusy ? "Capturing…" : "Capture Thumbnail"}
                  </button>
                  {clip.youtube_video_id ? (
                    <button
                      type="button"
                      className="cs-btn cs-btn-danger"
                      onClick={() => void pushThumbnailToYouTube()}
                      disabled={ytThumbBusy}
                    >
                      {ytThumbBusy ? "Setting…" : "Set on YouTube"}
                    </button>
                  ) : null}
                </div>
                {posOpen ? (
                  <div className="cs-pos-panel">
                    {THUMBNAIL_CAPTION_ANCHORS.map((anchor) => (
                      <button
                        key={`pos-${anchor}`}
                        type="button"
                        className={capPosition === anchor ? "active" : ""}
                        onClick={() => setCapPosition(anchor)}
                        title={anchor}
                      >
                        {anchor.split("-").map((part) => part[0].toUpperCase()).join("")}
                      </button>
                    ))}
                  </div>
                ) : null}
                {liveThumb ? (
                  <div className="cs-live-thumb">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={liveThumb} alt="Current thumbnail preview" />
                    <span>Live thumbnail</span>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="clip-modal-files">
              {clip.download_url && (
                <a
                  className="ui-btn ui-btn-ghost clip-modal-download"
                  href={clip.download_url}
                  target="_blank"
                  rel="noreferrer"
                  download
                >
                  <Download size={14} /> Download MP4
                </a>
              )}
              {clip.subtitle_url && (
                <a
                  className="ui-btn ui-btn-ghost"
                  href={clip.subtitle_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  SRT
                </a>
              )}
            </div>

            <div className="clip-modal-thumbs">
              <div className="clip-modal-thumbs-head">
                <span className="clip-modal-label" style={{ margin: 0 }}>
                  Thumbnail / hook
                </span>
                <button
                  type="button"
                  className="ui-btn ui-btn-ghost"
                  onClick={() => void generateThumbnails()}
                  disabled={busy}
                >
                  {thumbBusy ? <ClipzySpinner size="xs" /> : <Sparkles size={13} />}
                  {thumbs ? "Regenerate 3 picks" : "Generate 3 picks"}
                </button>
              </div>
              {clip.ai_hook && <p className="clip-modal-hook">“{clip.ai_hook}”</p>}
              {thumbs && thumbs.candidates.length > 0 && (
                <div className="clip-thumb-grid">
                  {thumbs.candidates.map((candidate) => (
                    <button
                      key={candidate.url}
                      type="button"
                      className={`clip-thumb-pick${
                        (thumbs.selected_url || clip.thumbnail_url) === candidate.url
                          ? " selected"
                          : ""
                      }`}
                      onClick={() => void chooseThumbnail(candidate.url)}
                      disabled={busy}
                      title={`Frame at ${candidate.at_second.toFixed(1)}s`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={candidate.url} alt={`Thumbnail at ${candidate.at_second}s`} />
                      <span>{candidate.at_second.toFixed(1)}s</span>
                    </button>
                  ))}
                </div>
              )}
            </div>


            <details className="thcap-details" open>
              <summary className="thcap-summary">
                Thumbnail caption ({THUMBNAIL_CAPTION_STYLES.length} styles)
                <span className="thcap-summary-hint">optional</span>
              </summary>
              <div className="clip-modal-thumbs-head">
                <span className="clip-modal-label" style={{ margin: 0 }}>
                  Pick a style and position, then apply
                </span>
                <button
                  type="button"
                  className="ui-btn ui-btn-gold"
                  onClick={() => void applyCaption()}
                  disabled={busy || capBusy}
                >
                  {capBusy ? <ClipzySpinner size="xs" /> : <Sparkles size={13} />}
                  Apply to thumbnail
                </button>
              </div>

              <div className="thcap-wrap">
                <button
                  type="button"
                  className="thcap-nav"
                  onClick={() => capTrackRef.current?.scrollBy({ left: -320, behavior: "smooth" })}
                  aria-label="Scroll caption styles left"
                >
                  ‹
                </button>
                <div className="thcap-track" ref={capTrackRef}>
                  {THUMBNAIL_CAPTION_STYLES.map((style) => (
                    <button
                      key={style.id}
                      type="button"
                      className={`thcap-card${capStyle === style.id ? " active" : ""}`}
                      onClick={() => setCapStyle(style.id)}
                    >
                      <span className="thcap-label">{style.label}</span>
                      <span className="thcap-preview">
                        <span className={style.css}>Sample caption</span>
                      </span>
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="thcap-nav"
                  onClick={() => capTrackRef.current?.scrollBy({ left: 320, behavior: "smooth" })}
                  aria-label="Scroll caption styles right"
                >
                  ›
                </button>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                <div className="thcap-pos">
                  {THUMBNAIL_CAPTION_ANCHORS.map((anchor) => (
                    <button
                      key={anchor}
                      type="button"
                      className={capPosition === anchor ? "active" : ""}
                      onClick={() => setCapPosition(anchor)}
                      title={anchor}
                    >
                      {anchor.split("-").map((part) => part[0].toUpperCase()).join("")}
                    </button>
                  ))}
                </div>
                <input
                  className="ui-input"
                  style={{ flex: 1, minWidth: 200 }}
                  value={capText}
                  maxLength={90}
                  placeholder={clip.ai_hook || clip.title || "Caption text"}
                  onChange={(event) => setCapText(event.target.value)}
                />
              </div>
            </details>

            {clip.ai_hook || clip.ai_viral_reason || clip.viral_score ? (
              <div className="clip-modal-why">
                <p className="clip-modal-why-head">
                  Why this clip
                  {typeof clip.viral_score === "number" ? (
                    <span className="clip-modal-why-score">
                      viral score {Math.round(clip.viral_score)}/100
                    </span>
                  ) : null}
                </p>
                {clip.ai_hook ? <p className="clip-modal-why-hook">“{clip.ai_hook}”</p> : null}
                {clip.ai_viral_reason ? (
                  <p className="clip-modal-why-reason">{clip.ai_viral_reason}</p>
                ) : null}
              </div>
            ) : null}

            <details className="clip-modal-transcript">
              <summary>
                Transcript used by AI
                {transcript ? ` (${transcript.split(/\s+/).filter(Boolean).length} words)` : ""}
              </summary>
              <p>{transcript || "Transcript loads when metadata is generated."}</p>
            </details>
          </div>


          <div className="clip-modal-form">
            <label className="clip-modal-label" htmlFor="clip-modal-title">
              Title <span>{title.length}/100</span>
            </label>
            <input
              id="clip-modal-title"
              className="ui-input"
              value={title}
              maxLength={100}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="AI title (based on the transcript)"
              disabled={generating}
            />

            <label className="clip-modal-label" htmlFor="clip-modal-desc">
              Description <span>{description.length}/5000</span>
            </label>
            <textarea
              id="clip-modal-desc"
              className="ui-input clip-modal-textarea"
              rows={7}
              value={description}
              maxLength={5000}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="AI description + hashtags"
              disabled={generating}
            />

            <label className="clip-modal-label" htmlFor="clip-modal-tags">
              Tag <span>{tags.length} tags</span>
            </label>
            <input
              id="clip-modal-tags"
              className="ui-input"
              value={tagsText}
              onChange={(event) => setTagsText(event.target.value)}
              placeholder="comma separated"
              disabled={generating}
            />

            <div className="clip-modal-actions">
              <button
                type="button"
                className="ui-btn ui-btn-ghost"
                onClick={() => void generate(true)}
                disabled={busy || regenLeft === 0}
                title={
                  regenLeft === 0
                    ? "Regenerate limit reached (3× per clip) — edit manually instead"
                    : "Ask AI for a different title/description/tags"
                }
              >
                {generating ? (
                  <ClipzySpinner size="xs" />
                ) : (
                  <Sparkles size={14} />
                )}
                Regenerate with AI{typeof regenLeft === "number" ? ` (${regenLeft} left)` : ""}
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-gold"
                onClick={() => void save()}
                disabled={busy || !title.trim()}
              >
                {saving ? <ClipzySpinner size="xs" /> : <Wand2 size={14} />}
                Save
              </button>
            </div>

            <details
              className="clip-modal-edit"
              open={editOpen}
              onToggle={(event) => setEditOpen((event.currentTarget as HTMLDetailsElement).open)}
            >
              <summary>Edit this clip in place</summary>
              <p className="ui-hint">
                Trim/speed/filter/caption without creating a new task. The original file is kept
                in the clip metadata for recovery.
              </p>
              <div className="clip-edit-grid">
                <label>
                  Trim start (s)
                  <input
                    type="number"
                    min="0"
                    step="any"
                    className="ui-input"
                    value={editTrimStart}
                    onChange={(event) => setEditTrimStart(event.target.value)}
                    placeholder="0"
                  />
                </label>
                <label>
                  Trim end (s)
                  <input
                    type="number"
                    min="0"
                    step="any"
                    className="ui-input"
                    value={editTrimEnd}
                    onChange={(event) => setEditTrimEnd(event.target.value)}
                    placeholder={`${clip.duration.toFixed(1)}`}
                  />
                </label>
                <label>
                  Speed
                  <select
                    className="ui-input"
                    value={editSpeed}
                    onChange={(event) => setEditSpeed(event.target.value)}
                  >
                    <option value="0.5">0.5×</option>
                    <option value="1">1×</option>
                    <option value="1.5">1.5×</option>
                    <option value="2">2×</option>
                  </select>
                </label>
                <label>
                  Filter
                  <select
                    className="ui-input"
                    value={editFilter}
                    onChange={(event) => setEditFilter(event.target.value)}
                  >
                    <option value="none">none</option>
                    <option value="warm">warm</option>
                    <option value="cool">cool</option>
                    <option value="cinematic">cinematic</option>
                    <option value="bw">b&amp;w</option>
                    <option value="vibrant">vibrant</option>
                    <option value="vintage">vintage</option>
                  </select>
                </label>
                <label>
                  Caption text
                  <input
                    type="text"
                    className="ui-input"
                    value={editCaption}
                    onChange={(event) => setEditCaption(event.target.value)}
                    placeholder="optional overlay"
                  />
                </label>
                <label>
                  Caption style
                  <select
                    className="ui-input"
                    value={editCaptionStyle}
                    onChange={(event) => setEditCaptionStyle(event.target.value)}
                  >
                    {SUBTITLE_STYLE_OPTIONS.map((style) => (
                      <option key={style.value} value={style.value}>
                        {style.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {editBusy && (
                <div className="ui-progress" style={{ marginTop: 10 }}>
                  <span style={{ width: `${editProgress}%` }} />
                </div>
              )}
              <button
                type="button"
                className="ui-btn ui-btn-gold"
                onClick={() => void applyEdit()}
                disabled={busy}
              >
                {editBusy ? <ClipzySpinner size="xs" /> : <Wand2 size={14} />}
                {editBusy ? `Rendering ${editProgress}%` : "Apply clip edit"}
              </button>
            </details>

            <div className="clip-modal-youtube">
              <label className="clip-modal-label" htmlFor="clip-modal-category">
                YouTube category
              </label>
              <select
                id="clip-modal-category"
                className="ui-input"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                disabled={busy}
              >
                <option value="22">People &amp; Blogs</option>
                <option value="24">Entertainment</option>
                <option value="23">Comedy</option>
                <option value="27">Education</option>
                <option value="28">Science &amp; Technology</option>
                <option value="26">Howto &amp; Style</option>
                <option value="20">Gaming</option>
                <option value="10">Music</option>
                <option value="17">Sports</option>
                <option value="25">News &amp; Politics</option>
              </select>

              <label className="clip-modal-label" htmlFor="clip-modal-privacy">
                YouTube privacy
              </label>
              <select
                id="clip-modal-privacy"
                className="ui-input"
                value={privacy}
                onChange={(event) => setPrivacy(event.target.value)}
                disabled={busy}
              >
                <option value="unlisted">Unlisted (link only)</option>
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>

              {uploading || uploadStats.status === "error" ? (
                <YouTubeUploadCard
                  progress={uploadProgress}
                  status={uploadStats.status}
                  error={uploadStats.error}
                  bytesSent={uploadStats.bytesSent}
                  totalBytes={uploadStats.totalBytes || Number(clip.file_size || 0)}
                  title={title || clip.title}
                  durationSeconds={clip.duration}
                  privacy={privacy}
                  videoUrl={uploadUrl}
                  onRetry={() => void upload()}
                />
              ) : youtubeConnected ? (
                <button
                  type="button"
                  className="ui-btn ui-btn-gold clip-modal-upload"
                  onClick={() => void upload()}
                  disabled={busy || !title.trim()}
                >
                  {uploadUrl ? "Re-upload to YouTube" : "Upload to YouTube"}
                  <YouTubeIcon size={15} />
                </button>
              ) : (
                <button
                  type="button"
                  className="ui-btn ui-btn-gold clip-modal-upload"
                  onClick={onConnectYouTube}
                >
                  <YouTubeIcon size={15} /> Connect YouTube first
                </button>
              )}

              {uploadUrl && !uploading ? <YouTubeOpenCard href={uploadUrl} /> : null}

              {!uploading && youtubeConnected && (
                <button
                  type="button"
                  className="ui-btn ui-btn-ghost clip-modal-upload"
                  onClick={onConnectYouTube}
                  disabled={busy}
                >
                  Reconnect YouTube (fixes expired access)
                </button>
              )}
            </div>

            {error && <p className="clip-modal-error">{error}</p>}
            {notice && !error && <p className="clip-modal-notice">{notice}</p>}
          </div>
        </div>
        <YouTubeSuccessToast open={successOpen} onClose={() => setSuccessOpen(false)} />
        <AlertDialog
          open={ytAlert !== null}
          title={ytAlert?.title || ""}
          message={ytAlert?.message || ""}
          detail={ytAlert?.detail}
          actionLabel="Verify channel"
          actionHref={ytAlert?.href}
          onClose={() => setYtAlert(null)}
        />
      </div>
    </div>
  )
}

