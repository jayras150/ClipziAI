"use client"

import Link from "next/link"

const PLANS = [
  {
    name: "Free",
    price: "Free",
    period: "",
    credits: "5 credits, one-time",
    duration: "Up to 5 minutes",
    features: ["9:16 smart crop", "Auto subtitles", "Clipzy watermark"],
    popular: false,
  },
  {
    name: "Standard",
    price: "Rp 99,000",
    period: "/month",
    credits: "30 credits/month",
    duration: "Up to 30 minutes",
    features: [
      "Everything in Free",
      "Auto zoom",
      "Blurred background",
      "YouTube upload",
      "No watermark",
    ],
    popular: false,
  },
  {
    name: "Pro",
    price: "Rp 249,000",
    period: "/month",
    credits: "100 credits/month",
    duration: "Up to 60 minutes",
    features: [
      "Everything in Standard",
      "All editing tools",
      "AI viral scoring",
      "AI metadata",
      "AI thumbnails",
      "Priority queue",
    ],
    popular: true,
  },
  {
    name: "Team",
    price: "Rp 499,000",
    period: "/month",
    credits: "300 credits/month",
    duration: "Up to 120 minutes",
    features: ["Everything in Pro", "5+ team members", "Team management", "Shared credits"],
    popular: false,
  },
]

export default function PricingCards() {
  return (
    <div className="ui-container" style={{ padding: "70px 0 24px" }}>
      <div style={{ textAlign: "center", maxWidth: 620, margin: "0 auto 42px" }}>
        <div className="ui-kicker">Pricing</div>
        <h2 className="ui-title" style={{ margin: "12px 0" }}>
          Choose the plan that fits
        </h2>
        <p className="ui-muted">Start free, upgrade anytime. Every plan uses the latest AI models.</p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 16,
        }}
      >
        {PLANS.map((plan) => (
          <article
            key={plan.name}
            className="ui-card ui-card-hover"
            style={
              plan.popular
                ? { borderColor: "rgba(233, 189, 101, 0.55)", boxShadow: "0 20px 50px rgba(233, 181, 75, 0.12)" }
                : undefined
            }
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 className="ui-subtitle">{plan.name}</h3>
              {plan.popular && <span className="ui-badge ui-badge-gold">Popular</span>}
            </div>
            <div style={{ margin: "10px 0 6px" }}>
              <span style={{ font: "700 27px var(--font-space), sans-serif", color: "var(--ui-gold)" }}>
                {plan.price}
              </span>
              <span className="ui-muted" style={{ fontSize: 13 }}>
                {plan.period}
              </span>
            </div>
            <p className="ui-muted" style={{ fontSize: 13, margin: "0 0 4px" }}>
              {plan.credits}
            </p>
            <p className="ui-muted" style={{ fontSize: 12, margin: "0 0 18px" }}>
              {plan.duration}
            </p>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 22px", display: "grid", gap: 8 }}>
              {plan.features.map((feature) => (
                <li key={feature} style={{ display: "flex", gap: 8, fontSize: 13, color: "#c9cbd3" }}>
                  <span className="ui-gold">✓</span>
                  {feature}
                </li>
              ))}
            </ul>
            <Link
              href="/register"
              className={`ui-btn ui-btn-block ${plan.popular ? "ui-btn-gold" : "ui-btn-ghost"}`}
            >
              {plan.name === "Free" ? "Start free" : `Choose ${plan.name}`}
            </Link>
          </article>
        ))}
      </div>
    </div>
  )
}
