/** @type {import('tailwindcss').Config} */

/*
 * MediPaw Design System (shared guardian-web & vet-web).
 * Primary = Pine Teal #2F6F67 (hover #255E57). Neutral = gray
 * (Text #1F2937/#6B7280, Border #E5E7EB, Divider #F1F3F5, Surface #F8FAFC).
 * Semantic = standard scales: red(응급/취소), orange(준응급), green(일반/완료),
 * blue(예약확정). Override Tailwind hue scales so existing `blue-600`, `red-500`,
 * `slate-50`… classes adopt the system without rewriting component classes.
 */
const palette = {
  // Primary — Pine Teal (mapped onto the `blue` class names)
  blue: {
    50: "#eef5f4",
    100: "#d5e7e4",
    200: "#aecfc9",
    300: "#7fb1a8",
    400: "#4f9387",
    500: "#357b70",
    600: "#2f6f67",
    700: "#255e57",
    800: "#214c47",
    900: "#1e3f3b",
    950: "#0f211f",
  },
  // 예약 확정 / blue accent — standard blue (kept distinct from primary teal)
  sky: {
    50: "#eff6ff",
    100: "#dbeafe",
    200: "#bfdbfe",
    300: "#93c5fd",
    400: "#60a5fa",
    500: "#3b82f6",
    600: "#2563eb",
    700: "#1d4ed8",
    800: "#1e40af",
    900: "#1e3a8a",
    950: "#172554",
  },
  // Neutral — gray (Surface 50 / Divider 100 / Border 200 / Text 500,800)
  slate: {
    50: "#f8fafc",
    100: "#f1f3f5",
    200: "#e5e7eb",
    300: "#d1d5db",
    400: "#9ca3af",
    500: "#6b7280",
    600: "#4b5563",
    700: "#374151",
    800: "#1f2937",
    900: "#111827",
    950: "#030712",
  },
  // Danger — red (응급 / 예약 취소)
  red: {
    50: "#fef2f2",
    100: "#fee2e2",
    200: "#fecaca",
    300: "#fca5a5",
    400: "#f87171",
    500: "#ef4444",
    600: "#dc2626",
    700: "#b91c1c",
    800: "#991b1b",
    900: "#7f1d1d",
    950: "#450a0a",
  },
  rose: {
    50: "#fef2f2",
    100: "#fee2e2",
    200: "#fecaca",
    300: "#fca5a5",
    400: "#f87171",
    500: "#ef4444",
    600: "#dc2626",
    700: "#b91c1c",
    800: "#991b1b",
    900: "#7f1d1d",
    950: "#450a0a",
  },
  // 준응급 — orange
  orange: {
    50: "#fff7ed",
    100: "#ffedd5",
    200: "#fed7aa",
    300: "#fdba74",
    400: "#fb923c",
    500: "#f97316",
    600: "#ea580c",
    700: "#c2410c",
    800: "#9a3412",
    900: "#7c2d12",
    950: "#431407",
  },
  // Warning — amber
  amber: {
    50: "#fffbeb",
    100: "#fef3c7",
    200: "#fde68a",
    300: "#fcd34d",
    400: "#fbbf24",
    500: "#f59e0b",
    600: "#d97706",
    700: "#b45309",
    800: "#92400e",
    900: "#78350f",
    950: "#451a03",
  },
  yellow: {
    50: "#fffbeb",
    100: "#fef3c7",
    200: "#fde68a",
    300: "#fcd34d",
    400: "#fbbf24",
    500: "#f59e0b",
    600: "#d97706",
    700: "#b45309",
    800: "#92400e",
    900: "#78350f",
    950: "#451a03",
  },
  // 일반 / Success — green
  green: {
    50: "#f0fdf4",
    100: "#dcfce7",
    200: "#bbf7d0",
    300: "#86efac",
    400: "#4ade80",
    500: "#22c55e",
    600: "#16a34a",
    700: "#15803d",
    800: "#166534",
    900: "#14532d",
    950: "#052e16",
  },
  emerald: {
    50: "#f0fdf4",
    100: "#dcfce7",
    200: "#bbf7d0",
    300: "#86efac",
    400: "#4ade80",
    500: "#22c55e",
    600: "#16a34a",
    700: "#15803d",
    800: "#166534",
    900: "#14532d",
    950: "#052e16",
  },
};

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ...palette,
        brand: {
          600: "#2f6f67",
          700: "#255e57",
        },
        // Named design-system tokens
        primary: { DEFAULT: "#2f6f67", hover: "#255e57" },
        surface: "#f8fafc",
        divider: "#f1f3f5",
        cream: "#f8fafc",
      },
    },
  },
  plugins: [],
};
