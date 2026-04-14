/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Fira Sans', 'system-ui', 'sans-serif'],
        mono: ['Fira Code', 'JetBrains Mono', 'monospace'],
      },
      colors: {
        bg:      '#060a10',
        bg2:     '#0b1019',
        bg3:     '#111824',
        bg4:     '#18222f',
        border:  '#1e2e42',
        primary: '#7c3aed',
        'primary-bright': '#a78bfa',
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.2s ease both',
        'scale-in':   'scaleIn 0.2s ease both',
        'toast-in':   'toastIn 0.25s ease',
        'spin-fast':  'spin 0.7s linear infinite',
        'live-pulse': 'livePulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeInUp:  { from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        scaleIn:   { from: { opacity: 0, transform: 'scale(0.94)' }, to: { opacity: 1, transform: 'scale(1)' } },
        toastIn:   { from: { opacity: 0, transform: 'translateX(16px) scale(0.96)' }, to: { opacity: 1, transform: 'translateX(0) scale(1)' } },
        livePulse: { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.6 } },
      },
    },
  },
  plugins: [],
};
