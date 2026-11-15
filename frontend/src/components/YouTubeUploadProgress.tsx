/**
 * Progress upload YouTube. Hanya menampilkan satu kalimat status sesuai
 * permintaan produk; detail byte/teknis tetap tersembunyi dari user.
 */
export default function YouTubeUploadProgress({ progress }: { progress: number }) {
  const value = Math.max(0, Math.min(100, Math.round(Number(progress) || 0)))
  return (
    <div className="yt-upload-progress" role="status" aria-live="polite">
      <p className="yt-upload-progress-text">Uploading Video To Youtube Please Wait..</p>
      <div
        className="yt-upload-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-label="Uploading video to YouTube"
      >
        <span className="yt-upload-progress-fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}
