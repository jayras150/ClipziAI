/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0F172A",
        card: "rgba(255,255,255,0.04)",
        primary: {
          400: "#3B82F6",
          500: "#3B82F6",
          600: "#2563EB",
        },
        accent: {
          purple: "#8B5CF6",
          pink: "#EC4899",
        },
        success: "#10B981",
        warning: "#F59E0B",
        error: "#EF4444",
      },
      animation: {
        "float": "float 6s ease-in-out infinite",
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-20px)" },
        },
      },
    },
  },
  plugins: [],
}