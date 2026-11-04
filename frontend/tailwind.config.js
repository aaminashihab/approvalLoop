/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Every text/background pairing used in the UI is at least 4.5:1 (checked with WCAG 2 contrast).
      colors: {
        paper: '#ECEEF1',
        sheet: '#FBFBFA',
        ink: { DEFAULT: '#17202E', soft: '#3C4758', mute: '#556070' },
        rule: '#D3D8DF',
        // Decision colors carry meaning only, and always appear next to a text label or icon.
        auto: { DEFAULT: '#14705E', wash: '#DDEFE9' },
        review: { DEFAULT: '#8A5100', wash: '#F7E8CC' },
        block: { DEFAULT: '#A52F2A', wash: '#F6DAD7' },
        focus: '#2B5FD9',
      },
      fontFamily: {
        sans: ['"Instrument Sans"', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        serif: ['Newsreader', 'Georgia', '"Times New Roman"', 'serif'],
      },
      maxWidth: { content: '960px' },
      minHeight: { touch: '44px' },
      minWidth: { touch: '44px' },
    },
  },
  plugins: [],
};
