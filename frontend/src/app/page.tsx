import Link from "next/link"
import { Zap, Play, Upload, Film } from "lucide-react"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0F172A] to-[#1E293B] text-white">
      <nav className="fixed top-0 w-full z-50 bg-[#0F172A]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-pink-500 rounded-lg flex items-center justify-center text-xl">
              <Zap size={24} />
            </div>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-pink-400">
              Clipzi <span className="text-yellow-400">AI</span>
            </span>
          </div>
          <div className="hidden md:flex gap-6 text-sm font-medium text-gray-300">
            <Link href="#features" className="hover:text-white transition-colors">Fitur</Link>
            <Link href="#how-it-works" className="hover:text-white transition-colors">Cara Kerja</Link>
            <Link href="#pricing" className="hover:text-white transition-colors">Harga</Link>
          </div>
          <div className="flex gap-3">
            <Link href="/login" className="px-6 py-3 bg-white/10 border border-white/20 rounded-lg font-semibold hover:bg-white/20 transition-colors text-sm">Masuk</Link>
            <Link href="/register" className="btn-primary text-sm">Mulai Gratis</Link>
          </div>
        </div>
      </nav>
    </div>
  )
}