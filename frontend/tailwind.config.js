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
          primary: '#0d1117',
          secondary: '#161b22',
          tertiary: '#21262d',
          elevated: '#2d333b',
          hover: '#30363d',
        },
        border: {
          primary: '#30363d',
          secondary: '#3d444d',
        },
        text: {
          primary: '#f0f6fc',
          secondary: '#c9d1d9',
          muted: '#8b949e',
          accent: '#58a6ff',
        },
        accent: {
          orange: '#58a6ff',
          green: '#3fb950',
          red: '#f85149',
          blue: '#58a6ff',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
