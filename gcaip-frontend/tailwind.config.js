/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // GCAIP design system — "Earth at night" command-center palette
        abyss: '#06090F',        // Deep space background
        panel: '#0D1420',        // Card / panel background
        'panel-light': '#141D2E',
        ink: '#E8ECF4',          // Primary text
        muted: '#7C8AA3',        // Secondary text
        signal: {
          critical: '#FF3B30',
          warning: '#FF9500',
          watch: '#FFCC00',
          info: '#34AADC',
          low: '#30D158',
        },
        sentinel: '#1E88E5',     // Brand accent — satellite blue
        terra: '#2DD4BF',        // Secondary accent — vegetation teal
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body: ['"Inter"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan': 'scan 2s linear infinite',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
      },
    },
  },
  plugins: [],
}
