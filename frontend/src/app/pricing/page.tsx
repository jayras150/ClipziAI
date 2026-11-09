import Link from "next/link"
import Navbar from "@/components/Navbar"
import PricingCards from "@/components/PricingCards"

export const metadata = {
  title: "Harga — Clipzy AI",
  description: "Paket Gratis, Standar, Pro, dan Team untuk mengubah video panjang jadi klip vertikal.",
}

export default function PricingPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main>
        <PricingCards />
        <div className="ui-container" style={{ textAlign: "center", padding: "8px 0 70px" }}>
          <p className="ui-muted" style={{ marginBottom: 18 }}>
            Belum yakin? Mulai dengan paket Gratis — tanpa kartu kredit.
          </p>
          <Link href="/register" className="ui-btn ui-btn-gold">
            Daftar gratis
          </Link>
        </div>
      </main>
    </div>
  )
}
