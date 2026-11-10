"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import {
  CheckCircle2,
  Download,
  LoaderCircle,
  Sparkles,
  Wand2,
  X,
  Youtube,
} from "lucide-react"

import { api, ClipData } from "@/lib/api"
import { readApiError } from "@/lib/api-errors"

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
  const [privacy, setPrivacy] = useState("public")
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [uploadUrl, setUploadUrl] = useState("")

  const autoTried = useRef<Set<string>>(new Set())
  const clipId = clip?.id ?? ""
  const busy = generating || saving || uploading

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
      setNotice(regenerate ? "Membuat versi baru dari transkrip…" : "AI membaca transkrip klip…")
      try {
        const data = await api.generateClipMetadata(token, clipId, regenerate)
        if (data.status === "preparing") {
          // Klip lama: transkrip dibuat di latar belakang (bisa >1 menit).
          setNotice(data.message || "Transkrip klip sedang dibuat…")
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
        setNotice("Metadata dibuat AI dari transkrip Whisper klip ini.")
      } catch (err: any) {
        setNotice("")
        setError(readApiError(err.response?.data, "Gagal membuat metadata dari transkrip."))
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
      if (attempt >= 30) {
        setNotice("")
        setError("Transkrip klip masih diproses. Coba tekan \"Generate ulang AI\" beberapa saat lagi.")
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 6000))
      try {
        const data = await api.generateClipMetadata(token, clipId, false)
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
        setNotice("Metadata siap: dibuat AI dari transkrip klip.")
      } catch (err: any) {
        setNotice("")
        setError(readApiError(err.response?.data, "Gagal memuat metadata setelah transkrip selesai."))
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
      setNotice("Metadata disimpan. Siap dipakai untuk upload.")
    } catch (err: any) {
      setError(readApiError(err.response?.data, "Gagal menyimpan metadata."))
    } finally {
      setSaving(false)
    }
  }

  const upload = async () => {
    if (!clipId) return
    if (!youtubeConnected) {
      setError("Akun YouTube belum terhubung. Hubungkan dulu, lalu buka popup ini lagi.")
      return
    }
    if (!title.trim()) {
      setError("Judul wajib diisi sebelum upload.")
      return
    }
    setUploading(true)
    setError("")
    setNotice("Mengunggah video ke YouTube… jangan tutup popup ini.")
    try {
      const result = await api.uploadClipToYouTube(token, clipId, {
        title: title.trim(),
        description,
        tags,
        privacy_status: privacy,
        force: Boolean(uploadUrl),
      })
      if (!result.success) {
        throw new Error(result.error || "Upload gagal.")
      }
      setUploadUrl(result.youtube_video_url || "")
      setNotice(
        result.already_uploaded
          ? "Klip ini memang sudah pernah diunggah ke YouTube."
          : "Berhasil diunggah ke YouTube.",
      )
      onUpdated(clipId, {
        youtube_uploaded: true,
        youtube_video_id: result.youtube_video_id || null,
      })
    } catch (err: any) {
      setNotice("")
      setError(readApiError(err.response?.data, err.message || "Upload ke YouTube gagal."))
    } finally {
      setUploading(false)
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
        aria-label={`Klip ${clip.clip_index + 1}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="clip-modal-head">
          <div>
            <p className="clip-modal-eyebrow">
              Klip #{clip.clip_index + 1} · {minutes}:{seconds} · {clip.start_time}–{clip.end_time}
            </p>
            <h3 className="ui-subtitle" style={{ margin: 0 }}>
              Judul, deskripsi &amp; tag dari AI
            </h3>
          </div>
          <button
            type="button"
            className="clip-modal-close"
            onClick={onClose}
            disabled={busy}
            aria-label="Tutup"
          >
            <X size={16} />
          </button>
        </div>

        <div className="clip-modal-body">
          <div className="clip-modal-media">
            {clip.download_url ? (
              <video
                className="clip-modal-video"
                src={clip.download_url}
                poster={clip.thumbnail_url || undefined}
                controls
                autoPlay
                playsInline
              />
            ) : (
              <div
                className="clip-modal-video"
                style={{
                  background: clip.thumbnail_url
                    ? `url(${clip.thumbnail_url}) center / cover`
                    : "linear-gradient(160deg,#2a2213,#141821)",
                }}
              />
            )}

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

            <details className="clip-modal-transcript">
              <summary>
                Transkrip yang dipakai AI
                {transcript ? ` (${transcript.split(/\s+/).filter(Boolean).length} kata)` : ""}
              </summary>
              <p>{transcript || "Transkrip dimuat saat metadata dibuat."}</p>
            </details>
          </div>


          <div className="clip-modal-form">
            <label className="clip-modal-label" htmlFor="clip-modal-title">
              Judul <span>{title.length}/100</span>
            </label>
            <input
              id="clip-modal-title"
              className="ui-input"
              value={title}
              maxLength={100}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Judul dari AI (berdasarkan transkrip)"
              disabled={generating}
            />

            <label className="clip-modal-label" htmlFor="clip-modal-desc">
              Deskripsi <span>{description.length}/5000</span>
            </label>
            <textarea
              id="clip-modal-desc"
              className="ui-input clip-modal-textarea"
              rows={7}
              value={description}
              maxLength={5000}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Deskripsi + hashtag dari AI"
              disabled={generating}
            />

            <label className="clip-modal-label" htmlFor="clip-modal-tags">
              Tag <span>{tags.length} tag</span>
            </label>
            <input
              id="clip-modal-tags"
              className="ui-input"
              value={tagsText}
              onChange={(event) => setTagsText(event.target.value)}
              placeholder="pisahkan dengan koma"
              disabled={generating}
            />

            <div className="clip-modal-actions">
              <button
                type="button"
                className="ui-btn ui-btn-ghost"
                onClick={() => void generate(true)}
                disabled={busy}
              >
                {generating ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                Generate ulang AI
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-gold"
                onClick={() => void save()}
                disabled={busy || !title.trim()}
              >
                {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Wand2 size={14} />}
                Simpan
              </button>
            </div>

            <div className="clip-modal-youtube">
              <label className="clip-modal-label" htmlFor="clip-modal-privacy">
                Privasi YouTube
              </label>
              <select
                id="clip-modal-privacy"
                className="ui-input"
                value={privacy}
                onChange={(event) => setPrivacy(event.target.value)}
                disabled={busy}
              >
                <option value="public">Publik</option>
                <option value="unlisted">Unlisted (tautan saja)</option>
                <option value="private">Privat</option>
              </select>

              {youtubeConnected ? (
                <button
                  type="button"
                  className="ui-btn ui-btn-gold clip-modal-upload"
                  onClick={() => void upload()}
                  disabled={busy || !title.trim()}
                >
                  {uploading ? (
                    <LoaderCircle size={15} className="animate-spin" />
                  ) : (
                    <Youtube size={15} />
                  )}
                  {uploadUrl ? "Upload ulang ke YouTube" : "Upload ke YouTube"}
                </button>
              ) : (
                <button
                  type="button"
                  className="ui-btn ui-btn-gold clip-modal-upload"
                  onClick={onConnectYouTube}
                >
                  <Youtube size={15} /> Hubungkan YouTube dulu
                </button>
              )}

              {uploadUrl && (
                <Link
                  className="clip-modal-link"
                  href={uploadUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <CheckCircle2 size={13} /> Buka di YouTube
                </Link>
              )}
            </div>

            {error && <p className="clip-modal-error">{error}</p>}
            {notice && !error && <p className="clip-modal-notice">{notice}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

