import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        bg:        '#ffffff',
        'bg-mut':  '#f8fafc',
        'bg-row':  '#fafbfc',
        text:      '#0f172a',
        'text-mut':'#64748b',
        'text-dim':'#94a3b8',
        border:    '#e2e8f0',
        'border-mut':'#eef2f6',
        accent:    '#2563eb',
        'accent-bg':'#eff6ff',
        success:   '#16a34a',
        warning:   '#ca8a04',
        danger:    '#dc2626',
        'danger-bg':'#fef2f2',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(15,23,42,0.04)',
        elev: '0 8px 24px rgba(15,23,42,0.08)',
      },
    },
  },
  plugins: [typography],
};
