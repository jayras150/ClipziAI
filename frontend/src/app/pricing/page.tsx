import Link from "next/link"
import Navbar from "@/components/Navbar"
import PricingCards from "@/components/PricingCards"

export const metadata = {
  title: "Harga - Clipzi AI",
  description: "Paket Gratis, Standar, Pro, dan Team untuk mengubah video panjang jadi klip vertikal.",
}

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0F172A] to-[#1E293B] text-white">
      <Navbar />
      <main className="pt-28">
        <PricingCards />
        <div className="text-center pb-16">
          <p className="text-gray-400 mb-6">Belum yakin? Mulai dengan paket Gratis — tanpa kartu kredit.</p>
          <Link href="/register" className="btn-primary inline-flex items-center gap-2">
            Daftar gratis
          </Link>
        </div>
      </main>
    </div>
  )
}
