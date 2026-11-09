import Link from "next/link"
import {
  Zap,
  Play,
  Upload,
  Film,
  Scissors,
  Captions,
  Crop,
  Cpu,
  Youtube,
  TrendingUp,
  CheckCircle2,
  ArrowRight,
} from "lucide-react"
import Navbar from "@/components/Navbar"
import PricingCards from "@/components/PricingCards"

const FEATURES = [
  {
    icon: Scissors,
    title: "Deteksi momen viral",
    desc: "AI memindai transkrip untuk menemukan hook, punchline, dan momen paling menarik — tanpa perlu menonton ulang video panjang.",
  },
  {
    icon: Crop,
    title: "Smart crop 9:16",
    desc: "Subjek utama dibingkai otomatis ke format vertikal, siap untuk TikTok, Reels, dan Shorts.",
  },
  {
    icon: Captions,
    title: "Subtitle otomatis",
    desc: "Whisper mentranskripsi audio lalu caption dibakar ke video dengan timing yang akurat.",
  },
  {
    icon: Cpu,
    title: "Render di GPU cloud",
    desc: "Rendering memakai GPU Vast.ai sesuai kebutuhan, lalu instance dihentikan otomatis agar hemat biaya.",
  },
  {
    icon: Youtube,
    title: "Upload YouTube",
    desc: "Publikasikan klip langsung dari dashboard dengan metadata (judul, deskripsi, tag) yang disarankan AI.",
  },
  {
    icon: TrendingUp,
    title: "Viral score",
    desc: "Setiap klip diberi skor potensi viral berdasar ritme, hook, dan durasi supaya Anda tahu mana yang diprioritaskan.",
  },
]

const STEPS = [
  {
    title: "Tempel tautan video",
    desc: "YouTube, TikTok, Instagram, atau file video langsung. Durasi panjang tidak masalah.",
  },
  {
    title: "AI memproses",
    desc: "Transkripsi, deteksi momen, crop vertikal, dan pembakaran subtitle dijalankan otomatis.",
  },
  {
    title: "Unduh atau unggah",
    desc: "Klip siap pakai tersimpan di cloud storage; sekali klik bisa diunggah ke YouTube.",
  },
]

const STATS = [
  { value: "3+", label: "klip per task" },
  { value: "9:16", label: "format otomatis" },
  { value: "< 2 menit", label: "proses per video pendek" },
  { value: "100%", label: "cloud, tanpa install" },
]

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0F172A] to-[#1E293B] text-white">
      <Navbar />

      {/* Hero */}
      <section className="pt-32 pb-16 px-6">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <span className="feature-badge mb-6">
              <Zap size={14} /> Didukung AI &amp; GPU cloud
            </span>
            <h1 className="text-4xl md:text-6xl font-bold leading-tight mb-6">
              Ubah video panjang jadi{" "}
              <span className="text-gradient">Shorts viral</span> dalam hitungan menit
            </h1>
            <p className="text-gray-400 text-lg mb-8 max-w-xl">
              Clipzi AI mentranskripsi video, menemukan momen terbaik, membingkainya ke 9:16,
              dan membakar subtitle otomatis. Cukup tempel tautan — sisanya biar AI.
            </p>
            <div className="flex flex-wrap gap-4 mb-10">
              <Link href="/register" className="btn-primary inline-flex items-center gap-2">
                Mulai Gratis <ArrowRight size={18} />
              </Link>
              <Link href="/login" className="btn-secondary inline-flex items-center gap-2">
                <Play size={18} /> Masuk
              </Link>
            </div>
            <ul className="grid sm:grid-cols-2 gap-3 text-sm text-gray-300">
              {[
                "5 kredit gratis untuk mencoba",
                "Tanpa kartu kredit",
                "Watermark bisa dihilangkan",
                "Hasil siap unggah",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-green-400 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {/* Mock preview 9:16 */}
          <div className="flex justify-center lg:justify-end">
            <div className="relative w-[280px] sm:w-[320px] aspect-[9/16] rounded-3xl bg-gradient-to-br from-blue-600/40 via-purple-600/30 to-pink-600/40 border border-white/15 shadow-2xl shadow-purple-500/20 p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-gray-200">
                <span className="px-2 py-1 rounded bg-black/40">Clip 1 · 00:12</span>
                <span className="px-2 py-1 rounded bg-green-500/20 text-green-300">Viral 92</span>
              </div>
              <div className="flex-1 flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-white/15 border border-white/25 flex items-center justify-center">
                  <Play size={28} />
                </div>
              </div>
              <div className="rounded-lg bg-black/50 px-3 py-2 text-sm text-center">
                “Ini alasan kenapa kamu harus mulai hari ini…”
              </div>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="max-w-7xl mx-auto mt-16 grid grid-cols-2 md:grid-cols-4 gap-4">
          {STATS.map((stat) => (
            <div key={stat.label} className="glass-card text-center py-6">
              <div className="text-2xl font-bold text-gradient">{stat.value}</div>
              <div className="text-xs text-gray-400 mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-6 py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              Semua yang dibutuhkan untuk klip viral
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Dari transkripsi sampai upload, dikerjakan otomatis dalam satu alur.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="glass-card hover:border-white/25 transition-colors">
                <div className="w-11 h-11 rounded-lg bg-gradient-to-r from-blue-500 to-pink-500 flex items-center justify-center mb-4">
                  <feature.icon size={22} />
                </div>
                <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Tiga langkah, selesai</h2>
            <p className="text-gray-400">Tanpa timeline, tanpa editing manual.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {STEPS.map((step, index) => (
              <div key={step.title} className="glass-card relative mt-4">
                <span className="absolute -top-4 left-6 w-9 h-9 rounded-full bg-gradient-to-r from-blue-500 to-pink-500 flex items-center justify-center font-bold text-sm">
                  {index + 1}
                </span>
                <h3 className="text-lg font-semibold mt-4 mb-2">{step.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-12 flex flex-wrap justify-center gap-6 text-sm text-gray-400">
            <span className="inline-flex items-center gap-2">
              <Upload size={16} /> Tempel URL atau unggah file
            </span>
            <span className="inline-flex items-center gap-2">
              <Film size={16} /> Klip MP4 + subtitle
            </span>
            <span className="inline-flex items-center gap-2">
              <Youtube size={16} /> Upload ke YouTube
            </span>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-8 border-t border-white/5">
        <PricingCards />
        <div className="text-center pb-12">
          <Link href="/register" className="btn-primary inline-flex items-center gap-2">
            Coba gratis sekarang <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 px-6 py-10">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-gray-400">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-blue-400" />
            <span>© {new Date().getFullYear()} Clipzi AI. Semua hak dilindungi.</span>
          </div>
          <div className="flex gap-6">
            <Link href="/login" className="hover:text-white transition-colors">
              Masuk
            </Link>
            <Link href="/register" className="hover:text-white transition-colors">
              Daftar
            </Link>
            <Link href="/dashboard" className="hover:text-white transition-colors">
              Dashboard
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

