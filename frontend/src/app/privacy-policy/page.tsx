import type { Metadata } from "next"
import Navbar from "@/components/Navbar"
import SiteFooter from "@/components/SiteFooter"

export const metadata: Metadata = {
  title: "Privacy Policy — Clipzy AI",
  description: "How Clipzy AI collects, uses, and protects your data.",
}

export default function PrivacyPolicyPage() {
  return (
    <div className="ui-shell">
      <Navbar />
      <main className="ui-container ui-legal">
        <div className="ui-kicker">Legal</div>
        <h1>Privacy Policy</h1>
        <p className="ui-legal-meta">Last updated: November 2026</p>

        <p>
          This Privacy Policy explains what information Clipzy AI (&quot;we&quot;, &quot;us&quot;)
          collects when you use our video clipping service, why we collect it, and how you can
          control it.
        </p>

        <h2>1. Information we collect</h2>
        <ul>
          <li><strong>Account data</strong>: name, email address, and a hashed password. We never store plain-text passwords.</li>
          <li><strong>Content data</strong>: video URLs you submit, generated clips, thumbnails, and subtitle files.</li>
          <li><strong>Usage data</strong>: task history, credit balance, and technical logs (IP address, browser type) used for security and debugging.</li>
          <li><strong>Connected accounts</strong>: if you connect YouTube, we store OAuth tokens required to upload videos on your behalf. You can revoke access at any time.</li>
        </ul>

        <h2>2. How we use your data</h2>
        <ul>
          <li>To process your videos: download the source, transcribe audio, generate clips, and store the results.</li>
          <li>To operate your account: authentication, credit accounting, and subscription management.</li>
          <li>To keep the service safe: detecting abuse, rate limiting, and fraud prevention.</li>
          <li>To send transactional emails such as password resets and processing receipts.</li>
        </ul>

        <h2>3. Third-party processors</h2>
        <p>
          We use trusted providers strictly to run the service: cloud GPU compute for rendering,
          object storage for generated files, a managed PostgreSQL database, and AI providers for
          transcription and metadata suggestions. Data is transferred only for the purpose of
          fulfilling your request.
        </p>

        <h2>4. Data retention</h2>
        <p>
          Generated clips remain available while your account is active. Deleting a task removes
          its clips from storage. When you delete your account, personal data is removed within 30
          days, except records we must retain for legal or accounting reasons.
        </p>

        <h2>5. Your rights</h2>
        <ul>
          <li>Access, correct, or delete your personal data.</li>
          <li>Export a copy of your account data.</li>
          <li>Disconnect integrations and revoke OAuth access.</li>
          <li>Lodge a complaint with your local data protection authority.</li>
        </ul>

        <h2>6. Cookies</h2>
        <p>
          We use only essential cookies and local storage required to keep you signed in. We do not
          sell data or use third-party advertising trackers.
        </p>

        <h2>7. Contact</h2>
        <p>
          Questions about this policy? Email <a href="mailto:privacy@proxyai.live">privacy@proxyai.live</a>{" "}
          or use our <a href="/contact">contact page</a>.
        </p>
      </main>
      <SiteFooter />
    </div>
  )
}
