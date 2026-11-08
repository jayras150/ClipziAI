"use client"

import Link from "next/link"
import { Zap } from "lucide-react"

export default function Navbar() {
  return (
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
          <Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link>
          <Link href="/pricing" className="hover:text-white transition-colors">Harga</Link>
        </div>
        <div className="flex gap-3">
          <Link href="/login" className="px-6 py-3 bg-white/10 border border-white/20 rounded-lg font-semibold hover:bg-white/20 transition-colors text-sm">Masuk</Link>
          <Link href="/register" className="bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 text-white px-6 py-3 rounded-lg font-semibold hover:scale-105 transition-transform duration-300 shadow-lg shadow-purple-500/30 text-sm">Mulai Gratis</Link>
        </div>
      </div>
    </nav>
  )
}