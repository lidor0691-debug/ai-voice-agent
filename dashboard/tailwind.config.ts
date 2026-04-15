import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#ede9fe",
          100: "#ddd6fe",
          200: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          900: "#4c1d95",
        },
        surface: {
          0: "#05050d",
          1: "#0c0c18",
          2: "#111122",
          3: "#18182a",
          4: "#1e1e30",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.06)",
          subtle:  "rgba(255,255,255,0.04)",
          strong:  "rgba(255,255,255,0.12)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        card:     "0 1px 3px 0 rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)",
        glow:     "0 0 20px rgba(139,92,246,0.2)",
        "glow-sm":"0 4px 12px rgba(139,92,246,0.3)",
      },
      animation: {
        pulse2: "pulse2 1.8s ease-in-out infinite",
      },
      keyframes: {
        pulse2: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%":      { opacity: "0.4", transform: "scale(0.85)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
