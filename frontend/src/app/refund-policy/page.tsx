import type { Metadata } from "next"
import Navbar from "@/components/Navbar"
import SiteFooter from "@/components/SiteFooter"

export const metadata: Metadata = {
  title: "Refund Policy — Clipzy AI",
  description: "How credits and refunds work at Clipzy AI.",
}

export default function RefundPolicyPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main className="ui-container ui-legal">
        <div className="ui-kicker">Legal</div>
        <h1>Refund Policy</h1>
        <p className="ui-legal-meta">Last updated: November 2026</p>

        <p>
          We want you to pay only for results you actually receive. This policy explains when you
          get credits back and when a paid subscription can be refunded.
        </p>

        <h2>1. Failed tasks</h2>
        <ul>
          <li>If a task fails because of a problem on our side (worker crash, storage error, timeout), the credits are returned automatically.</li>
          <li>If a task fails because of the source video (private or removed video, unsupported format, DRM-protected file, blocked download), credits are not returned.</li>
          <li>Clips without speech produce no subtitles, but the clips themselves are still delivered and charged.</li>
        </ul>

        <h2>2. Subscription refunds</h2>
        <ul>
          <li>New subscriptions can be refunded within 7 days if you used fewer than 5 credits.</li>
          <li>Renewal charges can be refunded when requested before the renewal period is used.</li>
          <li>Refunds are issued to the original payment method within 5–10 business days.</li>
        </ul>

        <h2>3. Non-refundable cases</h2>
        <ul>
          <li>Credits already consumed by successfully generated clips.</li>
          <li>Accounts suspended for violating our <a href="/terms">Terms of Service</a>.</li>
          <li>Requests made more than 30 days after the charge.</li>
        </ul>

        <h2>4. How to request a refund</h2>
        <p>
          Email <a href="mailto:billing@proxyai.live">billing@proxyai.live</a> with your account
          email, the task ID (available in your dashboard history), and a short description. We reply
          within two business days.
        </p>

        <h2>5. Free credits</h2>
        <p>
          Signup bonus credits are promotional and have no cash value. They are not refundable but
          can be used at any time while your account is active.
        </p>
      </main>
      <SiteFooter />
    </div>
  )
}
