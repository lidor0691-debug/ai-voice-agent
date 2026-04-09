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
          50: "#ede9fe",
          100: "#ddd6fe",
          200: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          900: "#4c1d95",
        },
        surface: {
          0: "#07070d",
          1: "#0d0d16",
          2: "#12121e",
          3: "#18182a",
          4: "#1e1e30",
        },
        border: {
          DEFAULT: "#1e1e30",
          subtle: "#16162a",
          strong: "#2a2a40",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        "card": "0 1px 3px 0 rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)",
        "glow": "0 0 20px rgba(124,58,237,0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
