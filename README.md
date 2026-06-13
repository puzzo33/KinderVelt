# KinderVelt

A general repo for Kinder Velt development stuff

## Site Redesign Demo

This repo includes a fast, mobile-friendly demo of a redesigned `kinderveltusa.org`
landing page (`index.html`) and donation page (`donate.html`), built as a reference
for improving the live Elementor site (see `feedback-for-masha.md` for the full
list of recommendations).

**Live demo (GitHub Pages):** `https://puzzo33.github.io/KinderVelt/`

### Highlights

- Pure static HTML + Tailwind CSS — no heavy images, loads instantly
- Sticky header with a persistent "Donate" button
- Impact stats visible immediately on page load
- Embedded live Transparency & Impact spreadsheet
- Clear donation flow with one-time/monthly toggle and suggested amounts
- Fully responsive, mobile-first layout

### Local development

```bash
npm install
npm run build   # compiles assets/css/style.css from assets/css/input.css
```

Then open `index.html` / `donate.html` directly in a browser, or serve the
folder with any static file server.
