/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Theme A — Dark Terminal
        terminal: {
          bg:       '#0a0a0f',
          surface:  '#111118',
          border:   '#1e1e2e',
          accent:   '#00ff88',
          accent2:  '#00d4ff',
          text:     '#e2e8f0',
          muted:    '#64748b',
          danger:   '#ff4d6d',
          warning:  '#fbbf24',
        },
        // Theme B — Dark Luxury
        luxury: {
          bg:       '#0d1117',
          surface:  '#161b22',
          border:   '#21262d',
          accent:   '#6366f1',
          accent2:  '#a78bfa',
          text:     '#f0f6fc',
          muted:    '#8b949e',
          danger:   '#f85149',
          warning:  '#d29922',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ticker':     'ticker 30s linear infinite',
        'blink':      'blink 1s step-end infinite',
      },
      keyframes: {
        ticker: {
          '0%':   { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        blink: {
          '0%, 100%': { opacity: 1 },
          '50%':      { opacity: 0 },
        },
      },
    },
  },
  plugins: [],
}
