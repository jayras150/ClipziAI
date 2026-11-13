"use client"

import Link from "next/link"
import { BrandLogo, BrandName } from "@/components/BrandingProvider"
import LandingAuth from "@/components/LandingAuth"
import { useEffect, useRef, useState } from "react"

const FEATURES = [
  {
    icon: "✦",
    title: "AI Moment Detection",
    desc: "Scans the transcript to surface hooks, punchlines, and the most engaging moments — no need to rewatch the whole video.",
  },
  {
    icon: "▤",
    title: "Smart Subtitles",
    desc: "Whisper transcribes the audio and burns accurate, timed captions straight into the video.",
  },
  {
    icon: "▣",
    title: "Vertical Reframing",
    desc: "Automatically reframes the main subject to 9:16, ready for Shorts, Reels, and TikTok.",
  },
  {
    icon: "◉",
    title: "AI Speaker Focus",
    desc: "Keeps the speaker centred while the frame is cropped to vertical, so nobody is cut off.",
  },
  {
    icon: "⌁",
    title: "Fast Video Workflow",
    desc: "Moment selection, cutting, subtitles, and rendering run in a single automated pipeline.",
  },
  {
    icon: "↗",
    title: "Export & Share",
    desc: "Publish clips straight to YouTube with AI-suggested titles, descriptions, and tags.",
  },
]

const STEPS = [
  {
    num: "01 / INPUT",
    title: "Add your video",
    desc: "Paste a YouTube, TikTok, or Instagram link — or upload a file directly.",
  },
  {
    num: "02 / ANALYZE",
    title: "AI analyses it",
    desc: "Audio is transcribed and the timeline is scored to find the strongest segments.",
  },
  {
    num: "03 / CREATE",
    title: "Clips are rendered",
    desc: "Highlights are cut, reframed to 9:16, and captions are burned in.",
  },
  {
    num: "04 / EXPORT",
    title: "Download or publish",
    desc: "Grab the MP4 and SRT files, or push them to YouTube in one click.",
  },
]

const STUDIO_PILLS = [
  "✂ AI clipping",
  "▤ AI captioning",
  "▣ AI reframe 9:16",
  "◉ Speaker focus",
  "⌁ AI hook titles",
  "↗ One-click export",
]

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [fileName, setFileName] = useState("")
  const [videoUrl, setVideoUrl] = useState("")
  const [year, setYear] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Year is computed on the client to avoid hydration mismatch.
  useEffect(() => setYear(new Date().getFullYear()), [])

  const onPickFile = (file: File | null) => {
    if (!file) {
      setFileName("")
      return
    }
    const size = (file.size / (1024 * 1024)).toFixed(2)
    setFileName(`✓ ${file.name} · ${size} MB`)
  }

  const closeMenu = () => setMenuOpen(false)

  // Tombol "Get clips": kirim user ke dashboard (sudah login) atau register,
  // sekalian membawa link yang ditempel agar dashboard bisa prefil.
  const submitVideo = (event: React.FormEvent) => {
    event.preventDefault()
    const loggedIn = typeof window !== "undefined" && Boolean(localStorage.getItem("token"))
    const target = loggedIn ? "/dashboard" : "/register"
    const trimmed = videoUrl.trim()
    const query = trimmed ? `?video_url=${encodeURIComponent(trimmed)}` : ""
    window.location.href = `${target}${query}`
  }

  return (
    <div className="landing">
      <header className="container navbar">
        <BrandLogo variant="landing" href="#home" onClick={closeMenu} />
        <nav className={`nav-links${menuOpen ? " open" : ""}`}>
          <a href="#features" onClick={closeMenu}>Features</a>
          <a href="#how" onClick={closeMenu}>How it works</a>
          <a href="#demo" onClick={closeMenu}>Demo</a>
          <Link href="/pricing" onClick={closeMenu}>Pricing</Link>
        </nav>
        <div className="nav-actions">
          <LandingAuth />
          <button
            className="menu-toggle"
            aria-label="Toggle menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </header>

      <main>
        <section className="container hero hero-v2" id="home">
          <div className="studio-panel">
            {/* Card "app window" gaya referensi: video di dalam preview card */}
            <div className="studio-window">
              <div className="studio-window-bar">
                <span className="studio-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="studio-window-title">CLIPZY STUDIO / PREVIEW</span>
                <span className="studio-window-more" aria-hidden="true">
                  •••
                </span>
              </div>

              <div className="studio-video-frame">
                <video
                  className="studio-video"
                  src="/media/hook.mp4"
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                  aria-label="Clipzy AI preview clip"
                />
                <span className="studio-play" aria-hidden="true">
                  ▶
                </span>
                <div className="studio-video-label">
                  <strong>Your next viral moment</strong>
                  AI-selected highlight · 00:42
                </div>
                <span className="studio-score">SCORE 94.8</span>
              </div>

              <div className="studio-timeline">
                <div className="studio-timeline-head">
                  <span>GENERATED CLIPS</span>
                  <span>6 clips found</span>
                </div>
                <div className="studio-tracks" aria-hidden="true">
                  <span className="studio-track" />
                  <span className="studio-track" />
                  <span className="studio-track" />
                  <span className="studio-track" />
                </div>
                <div className="studio-progress" aria-hidden="true">
                  <span />
                </div>
              </div>
            </div>

            <form className="studio-bar" onSubmit={submitVideo}>
              <span className="studio-bar-icon" aria-hidden="true">
                🔗
              </span>
              <input
                className="studio-bar-input"
                value={videoUrl}
                onChange={(event) => setVideoUrl(event.target.value)}
                placeholder="Drop a long video link and…"
                aria-label="Video link"
              />
              <button type="submit" className="btn btn-gold studio-cta">
                Get clips <span>→</span>
              </button>
            </form>
            <p className="studio-bar-help">
              Paste a YouTube, TikTok or Instagram link — clips come back captioned, scored and
              reframed for every feed.
            </p>

            <div className="studio-pills">
              {STUDIO_PILLS.map((pill) => (
                <span className="studio-pill" key={pill}>
                  {pill}
                </span>
              ))}
            </div>
          </div>

          <div className="hero-copy-block">
            <h1>
              Long videos. <span className="shine">Short moments.</span>
              <br />
              Big impact.
            </h1>
            <p className="hero-copy">
              Turn long videos into Shorts, Reels, and TikToks automatically. Clipzy AI finds the best
              moments, writes the subtitles, and prepares every clip for publishing — in minutes,
              not hours.
            </p>
            <div className="hero-buttons">
              <Link href="/register" className="btn btn-gold">
                Start free <span>→</span>
              </Link>
              <a href="#how" className="btn btn-ghost">
                See how it works
              </a>
            </div>
            <div className="hero-note">
              <div className="avatars">
                <i className="avatar" />
                <i className="avatar" />
                <i className="avatar" />
              </div>
              <span>5 free credits. No credit card required.</span>
            </div>
          </div>
        </section>

        <section className="section container" id="features">
          <div className="section-head">
            <div className="kicker">Powerful features</div>
            <h2>
              Everything you need
              <br />
              to ship more clips.
            </h2>
            <p>Focus on the story. Clipzy AI handles the repetitive editing work.</p>
          </div>
          <div className="feature-grid">
            {FEATURES.map((feature) => (
              <article className="feature" key={feature.title}>
                <div className="feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.desc}</p>
              </article>
            ))}
          </div>
        </section>



        

        <section className="section container how" id="how">
          <div className="section-head">
            <div className="kicker">Workflow</div>
            <h2>
              From long video
              <br />
              to ready-to-post clips.
            </h2>
            <p>Four automated steps. No editing skills needed.</p>
          </div>
          <div className="steps">
            {STEPS.map((step) => (
              <div className="step" key={step.num}>
                <div className="step-num">{step.num}</div>
                <h4>{step.title}</h4>
                <p>{step.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="section container" id="demo">
          <div className="demo">
            <div>
              <div className="kicker">Try it</div>
              <h2>Drop a video and see the highlights.</h2>
              <p>
                Sign in to start processing. Clips are generated with subtitles, a 9:16 crop, and
                AI-suggested titles you can edit before exporting.
              </p>
              <ul className="demo-list">
                <li>Highlights detected from the transcript</li>
                <li>Auto-captions with word-level timing</li>
                <li>Ready for Shorts, Reels, and TikTok</li>
              </ul>
            </div>
            <div>
              <div className="dropzone" onClick={() => inputRef.current?.click()}>
                <div className="drop-icon">⇪</div>
                <strong>Drop your video here</strong>
                <span>MP4, MOV, or paste a YouTube link</span>
                <button
                  type="button"
                  className="btn btn-gold"
                  onClick={(event) => {
                    event.stopPropagation()
                    inputRef.current?.click()
                  }}
                >
                  Choose file
                </button>
                <input
                  ref={inputRef}
                  type="file"
                  accept="video/*"
                  hidden
                  onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
                />
              </div>
              {fileName && <div className="file-name">{fileName}</div>}
              <p className="drop-help">
                Max 2 GB per file. Uploading requires an account —{" "}
                <Link href="/register">create one free</Link>.
              </p>
            </div>
          </div>
        </section>

        <section className="container stats">
          <div className="section-head center">
            <div className="kicker">Built for creators</div>
            <h2>Numbers that matter.</h2>
          </div>
          <div className="stat-grid">
            <div className="stat">
              <strong>10×</strong>
              <span>Faster than manual editing</span>
            </div>
            <div className="stat">
              <strong>3 min</strong>
              <span>Average render time per video</span>
            </div>
            <div className="stat">
              <strong>9:16</strong>
              <span>Ready for every vertical feed</span>
            </div>
            <div className="stat">
              <strong>5</strong>
              <span>Free credits on signup</span>
            </div>
          </div>
        </section>

        <section className="container">
          <div className="cta">
            <h2>
              Ready to turn long videos
              <br />
              into clips that perform?
            </h2>
            <p>Create an account and get 5 free credits. No credit card required.</p>
            <div className="hero-buttons">
              <Link href="/register" className="btn btn-gold">
                Create free account <span>→</span>
              </Link>
              <Link href="/pricing" className="btn btn-ghost">
                View pricing
              </Link>
            </div>
          </div>
        </section>

        <footer className="container footer">
          <BrandLogo variant="landing" href="#home" />
          <p>AI-powered video clipping for creators.</p>
          <div className="footer-links">
            <Link href="/pricing">Pricing</Link>
            <Link href="/privacy-policy">Privacy Policy</Link>
            <Link href="/terms">Terms of Service</Link>
            <Link href="/refund-policy">Refund Policy</Link>
            <Link href="/contact">Contact</Link>
          </div>
          <div className="footer-note">
            © {year ?? 2026} <BrandName />. All rights reserved.
          </div>
        </footer>
      </main>
    </div>
  )
}
