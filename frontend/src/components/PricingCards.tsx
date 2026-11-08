"use client"

export default function PricingCards() {
  const plans = [
    {
      name: "Gratis",
      price: "Gratis",
      credits: "5 kredit sekali jalan",
      duration: "Maks 5 menit",
      features: ["Smart Crop 9:16", "Auto Subtitle", "Watermark Clipzi"],
      popular: false,
      color: "border-gray-500",
    },
    {
      name: "Standar",
      price: "Rp 99.000",
      period: "/bulan",
      credits: "30 kredit/bulan",
      duration: "Maks 30 menit",
      features: ["Semua fitur Gratis", "Auto Zoom", "Blur Background", "YouTube Upload", "Tanpa watermark"],
      popular: false,
      color: "border-blue-500",
    },
    {
      name: "Pro",
      price: "Rp 249.000",
      period: "/bulan",
      credits: "100 kredit/bulan",
      duration: "Maks 60 menit",
      features: ["Semua fitur Standar", "Semua editing tools", "Viral Scoring AI", "AI Metadata", "Thumbnail AI", "Antrian prioritas"],
      popular: true,
      color: "border-purple-500",
    },
    {
      name: "Team",
      price: "Rp 499.000",
      period: "/bulan",
      credits: "300 kredit/bulan",
      duration: "Maks 120 menit",
      features: ["Semua fitur Pro", "5+ anggota tim", "Manajemen tim", "Kredit bersama"],
      popular: false,
      color: "border-pink-500",
    },
  ]

  return (
    <div className="max-w-7xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold mb-4">Pilih Paket yang Tepat</h2>
        <p className="text-gray-400">Mulai gratis, upgrade kapan saja</p>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
        {plans.map((plan) => (
          <div key={plan.name} className={`glass-card rounded-2xl p-8 ${plan.popular ? "border-blue-500/50 shadow-lg shadow-blue-500/20" : "border-white/10"}`}>
            <h3 className="text-xl font-bold mb-2">{plan.name}</h3>
            <div className="mb-6">
              <span className="text-3xl font-bold">{plan.price}</span>
              <span className="text-gray-400">{plan.period || ""}</span>
            </div>
            <p className="text-sm text-gray-400 mb-6">{plan.credits}</p>
            <p className="text-xs text-gray-500 mb-6">{plan.duration}</p>
            <ul className="space-y-3 mb-8">
              {plan.features.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                  <span className="text-green-400">✓</span> {f}
                </li>
              ))}
            </ul>
            <button className={`w-full py-3 rounded-lg font-semibold transition-all ${
              plan.popular
                ? "bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 text-white"
                : "bg-white/10 border border-white/20 text-white hover:bg-white/20"
            }`}>
              {plan.popular ? "Pilih Pro" : "Pilih " + plan.name}
            </button>
            {plan.popular && (
              <div className="mt-4 flex items-center justify-center gap-1 text-xs text-blue-400">
                <span className="bg-blue-500/20 px-2 py-1 rounded">Populer</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}