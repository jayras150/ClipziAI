"use client"

import { Coins } from "lucide-react"

export default function CreditBalance({ credits }: { credits: number }) {
  return (
    <div className="flex items-center gap-3 bg-white/10 border border-white/20 rounded-lg px-4 py-2">
      <span className="text-yellow-400 font-bold">
        <span className="inline-flex items-center gap-1">
          <Coins size={14} /> {credits}
        </span>
      </span>
      <span className="text-xs text-gray-400">credits</span>
    </div>
  )
}