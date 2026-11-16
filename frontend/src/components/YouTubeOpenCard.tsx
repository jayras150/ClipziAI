"use client"

/** Kartu "Open Video on YouTube" (animasi border conic + shimmer). */
export default function YouTubeOpenCard({ href }: { href: string }) {
  return (
    <div className="yt-action-card">
      <div className="yt-action-inner">
        <div className="yt-card-shimmer" />
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="yt-open-btn"
        >
          <span className="yt-play-badge">
            <span className="yt-play-pulse" />
            <svg className="yt-play-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
            </svg>
          </span>
          <span className="yt-btn-text">Open Video on YouTube</span>
          <span className="yt-arrow-box">
            <svg
              className="yt-arrow-icon"
              viewBox="0 0 24 24"
              fill="none"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M7 17L17 7" />
              <path d="M8 7h9v9" />
            </svg>
          </span>
        </a>
      </div>
    </div>
  )
}
