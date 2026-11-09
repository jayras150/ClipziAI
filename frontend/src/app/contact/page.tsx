import type { Metadata } from "next"
import Link from "next/link"
import Navbar from "@/components/Navbar"
import SiteFooter from "@/components/SiteFooter"

export const metadata: Metadata = {
  title: "Contact — Clipzy AI",
  description: "Get in touch with the Clipzy AI team.",
}

const CHANNELS = [
  {
    label: "Support",
    email: "support@proxyai.live",
    desc: "Task failures, account access, billing questions.",
  },
  {
    label: "Privacy",
    email: "privacy@proxyai.live",
    desc: "Data access, deletion, and privacy requests.",
  },
  {
    label: "Billing",
    email: "billing@proxyai.live",
    desc: "Invoices, refunds, and subscription changes.",
  },
]

export default function ContactPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main className="ui-container ui-legal">
        <div className="ui-kicker">Contact</div>
        <h1>Talk to us</h1>
        <p className="ui-legal-meta">We usually reply within two business days.</p>

        <p>
          Include your account email and, for processing issues, the task ID from your dashboard so
          we can look into it faster.
        </p>

        <div style={{ display: "grid", gap: 14, marginTop: 24 }}>
          {CHANNELS.map((channel) => (
            <div className="ui-card" key={channel.label}>
              <h2 style={{ margin: "0 0 6px", fontSize: 17 }}>{channel.label}</h2>
              <p className="ui-muted" style={{ marginBottom: 8 }}>
                {channel.desc}
              </p>
              <a href={`mailto:${channel.email}`} className="ui-gold" style={{ fontWeight: 700 }}>
                {channel.email}
              </a>
            </div>
          ))}
        </div>

        <h2>Before you write</h2>
        <ul>
          <li>Check the <Link href="/pricing">pricing page</Link> for credit and plan details.</li>
          <li>Read the <Link href="/terms">Terms of Service</Link> and <Link href="/refund-policy">Refund Policy</Link>.</li>
          <li>For YouTube upload errors, reconnect the channel from your dashboard.</li>
        </ul>
      </main>
      <SiteFooter />
    </div>
  )
}
