import Link from "next/link"
import Navbar from "@/components/Navbar"
import SiteFooter from "@/components/SiteFooter"
import PricingCards from "@/components/PricingCards"

export const metadata = {
  title: "Pricing — Clipzy AI",
  description: "Free, Standard, Pro, and Team plans for turning long videos into vertical clips.",
}

export default function PricingPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main>
        <PricingCards />
        <div className="ui-container" style={{ textAlign: "center", padding: "8px 0 70px" }}>
          <p className="ui-muted" style={{ marginBottom: 18 }}>
            Not sure yet? Start on the Free plan — no credit card required.
          </p>
          <Link href="/register" className="ui-btn ui-btn-gold">
            Create free account
          </Link>
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}

