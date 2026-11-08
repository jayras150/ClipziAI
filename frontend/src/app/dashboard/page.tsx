"use client"

import { useEffect, useState } from "react"
import { Upload, Play, Youtube, Link2, Unlink, LoaderCircle } from "lucide-react"
import { api } from "@/lib/api"

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState("upload")
  const [youtube, setYoutube] = useState<{ connected: boolean; channel_name?: string }>({ connected: false })
  const [youtubeLoading, setYoutubeLoading] = useState(false)
  const [youtubeMessage, setYoutubeMessage] = useState("")

  const getToken = () => typeof window === "undefined" ? null : localStorage.getItem("token")

  useEffect(() => {
    const token = getToken()
    if (!token) return
    api.getYouTubeStatus(token).then(setYoutube).catch(() => setYoutubeMessage("Masuk untuk melihat status YouTube."))

    const status = new URLSearchParams(window.location.search).get("youtube")
    if (status === "connected") setYoutubeMessage("YouTube berhasil terhubung.")
    if (status === "denied") setYoutubeMessage("Izin YouTube dibatalkan.")
    if (status === "error") setYoutubeMessage("Koneksi YouTube gagal. Periksa konfigurasi Google OAuth.")
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
      setYoutubeMessage(error.response?.data?.detail || "Tidak dapat memulai koneksi YouTube.")
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
      setYoutubeMessage("Koneksi YouTube berhasil dihapus.")
    } catch {
      setYoutubeMessage("Koneksi YouTube tidak dapat dihapus.")
    } finally {
      setYoutubeLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0F172A] text-white">
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-pink-400">Dashboard</h1>
            <p className="text-gray-400 mt-1">Kelola proyek video Anda</p>
          </div>
          <div className="flex gap-3 items-center">
            <button
              onClick={youtube.connected ? disconnectYouTube : connectYouTube}
              disabled={youtubeLoading}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors disabled:opacity-60 ${youtube.connected ? "border-red-400/40 bg-red-500/10 text-red-200 hover:bg-red-500/20" : "border-red-400/40 bg-red-500/15 text-red-100 hover:bg-red-500/25"}`}
            >
              {youtubeLoading ? <LoaderCircle size={16} className="animate-spin" /> : youtube.connected ? <Unlink size={16} /> : <Youtube size={16} />}
              {youtube.connected ? `YouTube: ${youtube.channel_name || "Terhubung"}` : "Hubungkan YouTube"}
            </button>
            <button onClick={() => setActiveTab("upload")} className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${activeTab === "upload" ? "bg-blue-500 text-white" : "bg-white/10 border border-white/20 text-gray-300 hover:bg-white/20"}`}>
              Upload
            </button>
            <button onClick={() => setActiveTab("projects")} className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${activeTab === "projects" ? "bg-blue-500 text-white" : "bg-white/10 border border-white/20 text-gray-300 hover:bg-white/20"}`}>
              Proyek
            </button>
          </div>
        </div>

        {youtubeMessage && (
          <div className="mb-6 rounded-lg border border-blue-400/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-100 flex items-center gap-2">
            <Link2 size={16} /> {youtubeMessage}
          </div>
        )}

        {activeTab === "upload" ? (
          <div className="glass-card">
            <h2 className="font-bold mb-6">Unggah Video</h2>
            <div className="border-2 border-dashed border-white/20 rounded-xl p-8 text-center hover:border-blue-500/50 transition-colors cursor-pointer">
              <div className="flex flex-col items-center gap-3">
                <Upload size={48} className="text-blue-400" />
                <p className="text-gray-300">Klik atau seret file video di sini</p>
                <p className="text-xs text-gray-500">Maksimal 2GB • MP4, MOV, AVI</p>
              </div>
            </div>
            <div className="mt-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">Atau tempel URL video</label>
              <div className="input-group">
                <input type="text" placeholder="https://youtube.com/watch?v=..." className="w-full pl-4 pr-10 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
                <button className="btn-primary px-4 py-3 ml-2 text-sm">Proses</button>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              { id: 1, title: "Tutorial Memasak", status: "completed", progress: 100, clips: 5 },
              { id: 2, title: "Review Teknologi", status: "processing", progress: 65, clips: 3 },
              { id: 3, title: "Vlog Perjalanan", status: "queued", progress: 0, clips: 0 },
            ].map((project) => (
              <div key={project.id} className="glass-card hover:border-blue-500/50 transition-all duration-300">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400">
                      <Play size={16} />
                    </div>
                    <h3 className="font-bold">{project.title}</h3>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${project.status === "completed" ? "bg-green-500/20 text-green-400" : project.status === "processing" ? "bg-blue-500/20 text-blue-400" : "bg-gray-500/20 text-gray-400"}`}>
                    {project.status}
                  </span>
                </div>
                <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden mb-4">
                  <div className={`h-full bg-gradient-to-r from-blue-500 to-pink-500 transition-all duration-500`} style={{ width: `${project.progress}%` }}></div>
                </div>
                <div className="flex justify-between items-center text-sm text-gray-400">
                  <span>{project.clips} klip</span>
                  <span>{project.progress}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}