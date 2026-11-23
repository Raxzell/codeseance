/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Cinzel"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        void: "#07090e",
        crypt: "#0d111a",
        panel: "#111724",
        ectoplasm: "#2dd4bf",
        parchment: "#f59e0b",
        crimson: "#f43f5e",
      },
      boxShadow: {
        spectral: "0 0 32px -10px rgba(45, 212, 191, 0.25)",
        amberGlow: "0 0 28px -10px rgba(245, 158, 11, 0.28)",
      },
    },
  },
  plugins: [],
};
