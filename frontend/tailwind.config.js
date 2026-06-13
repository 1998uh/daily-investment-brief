/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#111111',
          tertiary: '#1a1a1a',
          elevated: '#222222',
          hover: '#2a2a2a',
        },
        border: {
          primary: '#2a2a2a',
          secondary: '#333333',
        },
        text: {
          primary: '#e8e8e8',
          secondary: '#999999',
          muted: '#666666',
          accent: '#f0a500',
        },
        accent: {
          orange: '#f0a500',
          green: '#22c55e',
          red: '#ef4444',
          blue: '#3b82f6',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
