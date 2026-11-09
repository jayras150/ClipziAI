"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"

const FEATURES = [
  {
    icon: "✦",
    title: "AI Moment Detection",
    desc: "Temukan bagian menarik dari video panjang berdasarkan percakapan, konteks, dan momen penting.",
  },
  {
    icon: "▤",
    title: "Smart Subtitles",
    desc: "Buat subtitle otomatis agar konten lebih mudah diikuti, termasuk untuk penonton tanpa suara.",
  },
  {
    icon: "▣",
    title: "Vertical Reframing",
    desc: "Siapkan format vertikal untuk Shorts, Reels, dan TikTok dengan komposisi yang lebih sesuai.",
  },
  {
    icon: "◉",
    title: "AI Speaker Focus",
    desc: "Bantu menjaga pembicara tetap menjadi fokus saat video disesuaikan ke rasio vertikal.",
  },
  {
    icon: "⌁",
    title: "Fast Video Workflow",
    desc: "Satukan proses pemilihan momen, pemotongan, dan persiapan hasil dalam satu alur kerja.",
  },
  {
    icon: "↗",
    title: "Export & Share",
    desc: "Siapkan hasil akhir untuk dibagikan ke platform video pendek favoritmu.",
  },
]

const STEPS = [
  { num: "01 / INPUT", title: "Masukkan video", desc: "Unggah video atau masukkan sumber video yang ingin kamu olah." },
  { num: "02 / ANALYZE", title: "AI menganalisis", desc: "AI memproses audio dan konten untuk mencari bagian yang potensial." },
  { num: "03 / CREATE", title: "Buat clips", desc: "Pilih momen, sesuaikan subtitle, dan atur tampilan video." },
  { num: "04 / EXPORT", title: "Export hasilnya", desc: "Simpan video pendek dan bagikan ke platform pilihanmu." },
]

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [fileName, setFileName] = useState("")
  const [year, setYear] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Tahun dihitung di klien agar tidak ada hydration mismatch.
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

  return (
    <div className="landing">
      <header className="container navbar">
        <Link className="brand" href="#home" onClick={closeMenu}>
          <span className="brand-mark">▶</span>
          <span>
            clipzy<em>AI</em>
          </span>
        </Link>
        <nav className={`nav-links${menuOpen ? " open" : ""}`}>
          <a href="#features" onClick={closeMenu}>Fitur</a>
          <a href="#how" onClick={closeMenu}>Cara Kerja</a>
          <a href="#demo" onClick={closeMenu}>Coba Demo</a>
          <a href="#about" onClick={closeMenu}>Tentang</a>
        </nav>
        <div className="nav-actions">
          <a className="btn btn-ghost" href="#features">Jelajahi</a>
          <Link className="btn btn-gold" href="/register">
            Mulai Gratis <span>↗</span>
          </Link>
          <button
            className="menu-toggle"
            aria-label="Buka menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </header>

      <main>
        <section className="container hero" id="home">
          <div>
            <div className="eyebrow">
              <span className="pulse" /> AI-powered video creation
            </div>
            <h1>
              Long videos.
              <br />
              <span className="shine">Short moments.</span>
              <br />
              Big impact.
            </h1>
            <p className="hero-copy">
              Ubah video panjang menjadi konten Shorts, Reels, dan TikTok secara otomatis. Temukan
              momen terbaik, buat subtitle, dan siapkan video untuk dibagikan — lebih cepat dengan
              Clipzy AI.
            </p>
            <div className="hero-buttons">
              <Link href="/register" className="btn btn-gold">
                Mulai Sekarang <span>→</span>
              </Link>
              <a href="#how" className="btn btn-ghost">
                Lihat cara kerja
              </a>
            </div>
            <div className="hero-note">
              <div className="avatars">
                <i className="avatar" />
                <i className="avatar" />
                <i className="avatar" />
              </div>
              <span>Workflow lebih cepat. Kreativitas tetap milikmu.</span>
            </div>
          </div>

          <div className="hero-visual">
            <div className="glow" />
            <div className="app-window">
              <div className="window-top">
                <div className="dots">
                  <i />
                  <i />
                  <i />
                </div>
                <span>CLIPZY STUDIO / PREVIEW</span>
                <span>•••</span>
              </div>
              <div className="preview">
                <div className="play">▶</div>
                <div className="preview-label">
                  <strong>Your next viral moment</strong>
                  AI-selected highlight · 00:42
                </div>
              </div>
              <div className="timeline">
                <div className="timeline-head">
                  <span>GENERATED CLIPS</span>
                  <span>4 clips found</span>
                </div>
                <div className="tracks">
                  <div className="track" />
                  <div className="track" />
                  <div className="track" />
                  <div className="track" />
                </div>
                <div className="progress">
                  <span />
                </div>
              </div>
            </div>
            <div className="float-card">
              AI HIGHLIGHT SCORE
              <strong>94.8 / 100</strong>
            </div>
          </div>
        </section>

        <section className="section container" id="features">
          <div className="section-head">
            <div className="kicker">Powerful features</div>
            <h2>
              Semua yang kamu butuhkan
              <br />
              untuk membuat clips.
            </h2>
            <p>
              Fokus pada ide dan cerita. Clipzy AI membantu mempercepat proses produksi konten
              pendek.
            </p>
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

        <section className="section container" id="how">
          <div className="section-head">
            <div className="kicker">Simple workflow</div>
            <h2>Dari video panjang ke short clips.</h2>
            <p>Empat langkah sederhana untuk memulai proses kreatifmu.</p>
          </div>
          <div className="workflow">
            {STEPS.map((step) => (
              <article className="step" key={step.num}>
                <div className="step-num">{step.num}</div>
                <h3>{step.title}</h3>
                <p>{step.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="section container" id="demo">
          <div className="demo-wrap">
            <div>
              <div className="kicker">Try the experience</div>
              <h2>Siap membuat konten berikutnya?</h2>
              <p>
                Pilih file video dari perangkatmu untuk mencoba interaksi halaman ini. Demo ini
                hanya menampilkan nama file — belum mengunggah atau memproses video ke server.
              </p>
              <a href="#features" className="btn btn-ghost">
                Jelajahi fitur <span>→</span>
              </a>
            </div>
            <div className="upload-box">
              <div className="upload-icon">⇧</div>
              <h3>Pilih video kamu</h3>
              <p>MP4, MOV, atau WebM · Demo antarmuka</p>
              <input
                ref={inputRef}
                type="file"
                accept="video/mp4,video/quicktime,video/webm"
                hidden
                onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
              />
              <button className="btn btn-gold" onClick={() => inputRef.current?.click()}>
                Pilih File Video
              </button>
              <div className="file-name" aria-live="polite">
                {fileName}
              </div>
            </div>
          </div>
          <div className="stats">
            <div className="stat">
              <strong>AI</strong>
              <span>Smart assistance</span>
            </div>
            <div className="stat">
              <strong>9:16</strong>
              <span>Vertical-ready format</span>
            </div>
            <div className="stat">
              <strong>∞</strong>
              <span>Creative possibilities</span>
            </div>
          </div>
        </section>

        <section className="container section" id="about">
          <div className="cta">
            <div className="kicker">Create without limits</div>
            <h2>
              Lebih banyak konten.
              <br />
              Lebih sedikit pekerjaan manual.
            </h2>
            <p>
              Clipzy AI membantu kreator mengubah ide dan video panjang menjadi konten pendek dengan
              workflow yang lebih praktis.
            </p>
            <Link className="btn btn-gold" href="/register">
              Mulai dengan Clipzy AI <span>↗</span>
            </Link>
          </div>
        </section>
      </main>

      <footer>
        <div className="container footer-inner">
          <Link className="brand" href="#home">
            <span className="brand-mark">▶</span>
            <span>
              clipzy<em>AI</em>
            </span>
          </Link>
          <span>© {year ?? ""} Clipzy AI. All rights reserved.</span>
          <div className="footer-links">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <Link href="/login">Masuk</Link>
            <a href="#home">Back to top ↑</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
