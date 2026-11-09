import type { Metadata } from "next"
import Navbar from "@/components/Navbar"
import SiteFooter from "@/components/SiteFooter"

export const metadata: Metadata = {
  title: "Terms of Service — Clipzy AI",
  description: "The rules for using Clipzy AI video clipping service.",
}

export default function TermsPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main className="ui-container ui-legal">
        <div className="ui-kicker">Legal</div>
        <h1>Terms of Service</h1>
        <p className="ui-legal-meta">Last updated: November 2026</p>

        <p>
          By creating a Clipzy AI account you agree to these Terms. If you do not agree, please do
          not use the service.
        </p>

        <h2>1. The service</h2>
        <p>
          Clipzy AI converts long-form videos into short vertical clips: it downloads your source,
          transcribes audio, detects highlights, reframes to 9:16, burns subtitles, and stores the
          results. Processing runs on cloud GPU capacity that is created and released per task.
        </p>

        <h2>2. Your account</h2>
        <ul>
          <li>You must provide accurate information and keep your credentials secure.</li>
          <li>You are responsible for all activity under your account.</li>
          <li>One account per person or team; sharing credentials is not allowed.</li>
        </ul>

        <h2>3. Acceptable use</h2>
        <ul>
          <li>Only upload content you own or have permission to process.</li>
          <li>Do not process illegal, hateful, or infringing material.</li>
          <li>Do not attempt to bypass limits, scrape the service, or disrupt other users.</li>
          <li>Respect the terms of the platforms you download from and upload to.</li>
        </ul>

        <h2>4. Credits and subscriptions</h2>
        <ul>
          <li>Each generated clip costs 1 credit. New accounts receive 5 free credits.</li>
          <li>Credits reset monthly according to your plan and do not roll over.</li>
          <li>Subscriptions renew automatically until cancelled from your dashboard.</li>
          <li>Refunds are handled according to our <a href="/refund-policy">Refund Policy</a>.</li>
        </ul>

        <h2>5. Availability</h2>
        <p>
          Processing depends on third-party cloud capacity. We aim for high availability but cannot
          guarantee uninterrupted service. If a task fails for reasons on our side, credits are
          returned automatically.
        </p>

        <h2>6. Intellectual property</h2>
        <p>
          You keep ownership of the content you submit and the clips generated from it. You grant us
          a limited license to store and process that content to operate the service. The Clipzy AI
          brand, code, and design remain our property.
        </p>

        <h2>7. Limitation of liability</h2>
        <p>
          The service is provided &quot;as is&quot;. To the maximum extent permitted by law, our
          liability is limited to the amount you paid in the previous three months.
        </p>

        <h2>8. Changes and termination</h2>
        <p>
          We may update these Terms or suspend accounts that violate them. Material changes will be
          announced before they take effect.
        </p>

        <h2>9. Contact</h2>
        <p>
          Questions? Email <a href="mailto:support@proxyai.live">support@proxyai.live</a> or use our{" "}
          <a href="/contact">contact page</a>.
        </p>
      </main>
      <SiteFooter />
    </div>
  )
}
