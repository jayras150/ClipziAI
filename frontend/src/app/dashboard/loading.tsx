import { ClipzySpinner } from "@/components/ClipzySpinner"

/**
 * Loading state rute /dashboard.
 *
 * Next.js menampilkan ini otomatis saat chunk/komponen dashboard dimuat,
 * jadi pengguna selalu melihat indikator proses, bukan layar kosong.
 */
export default function DashboardLoading() {
  return (
    <div className="ui-container" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          marginBottom: 26,
          color: "var(--ui-gold, #f4c76b)",
        }}
      >
        <ClipzySpinner size="lg" />
        <div>
          <p style={{ margin: 0, fontWeight: 700, color: "#f4efe4" }}>Preparing your clip studio…</p>
          <p style={{ margin: 0, fontSize: 13, color: "var(--ui-muted)" }}>
            Loading your tasks, credits, and YouTube connection.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="ui-card"
            style={{
              minHeight: 118,
              background:
                "linear-gradient(100deg, rgba(255,255,255,0.03), rgba(255,255,255,0.08), rgba(255,255,255,0.03))",
              backgroundSize: "220% 100%",
              animation: "cz-shimmer 2.4s linear infinite",
            }}
          />
        ))}
      </div>
    </div>
  )
}
