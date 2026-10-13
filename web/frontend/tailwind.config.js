/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#F1F4FA',
        surface: '#FFFFFF',
        surfaceSoft: '#E5EAF4',
        ink: '#202B3E',
        muted: '#59677D',
        primary: '#243B5A',
        primaryHover: '#1B2D46',
        accent: '#AE432F',
        accentSoft: '#FBE9E2',
        divider: '#D9E0EB',
        controlLine: '#78869C',
        success: '#266854',
        error: '#B42335',
      },
      fontFamily: {
        sans: ['Golos Text', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 8px 28px rgba(32,43,62,.07)',
      },
    },
  },
  plugins: [],
}
