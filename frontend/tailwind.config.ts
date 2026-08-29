import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#07080C",
        surface: "#111318",
        surface2: "#151920",
        line: "#252A36",
        line2: "#2E3545",
        amber: "#F0C040",
        orange: "#E05C30",
        success: "#3EC97A",
        danger: "#EF4444",
        info: "#5B9DF9",
        body: "#E8EAF0",
        muted: "#6B7280",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
