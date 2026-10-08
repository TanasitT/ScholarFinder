# ScholarFinder — Frontend

A React + Vite single-page app for searching and browsing ScholarFinder's stored papers and scholars. Talks to the FastAPI backend in `../backend` — it has no logic of its own beyond presentation; every eligibility decision still happens server-side in the same deterministic rule engine the CLI uses.

## Scope

- **New search** — submit a paper's title/abstract/keywords (or switch to **Enter manually** to type 1–5 keyword sets yourself, which skips Ollama), optionally limit or exclude countries, confirm before running (since it spends OpenAlex API budget), then see the ranked results.
- **Past papers** — every paper searched so far, with its passing-scholar count.
- **Paper detail** — one paper's ranked matches, grouped by keyword set. Here and on the search results, clickable country pills filter the cards in the browser (no new request).
- **Scholar detail** — full profile: institution, zone, h-index, email + verification status, research topics, Google Scholar/Scopus links.

Not in scope yet: the chatbot (still CLI-only), a production build/serving story (this is dev-mode only), and authentication.

## Setup

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`. The dev server proxies `/api/*` to `http://127.0.0.1:8000`, so start the backend first:

```bash
cd ../backend
python -m reviewerfinder.cli serve
```

Browsing works even without `OPENALEX_API_KEY` configured on the backend; running a new search will show a clear error if it's missing.

## Structure

```
src/
├── main.jsx                     React root + router
├── App.jsx                      Top bar/nav + route table
├── api.js                       fetch wrappers for the backend endpoints
├── countryNames.js              ISO alpha-2 code → country name, for display
├── index.css                    Design tokens (shared visual language with ../docs/overview.html)
├── components/
│   ├── ScholarCard.jsx          Shared scholar summary card (name, institution, h-index, email, topics)
│   ├── KeywordSetResults.jsx    Ranked scholars grouped by keyword set
│   ├── CountryFilterBar.jsx     Country pills that filter the result cards
│   └── SearchProgress.jsx       Per-keyword-set progress while a search job runs
└── pages/
    ├── SearchPage.jsx
    ├── PapersPage.jsx
    ├── PaperDetailPage.jsx
    └── ScholarDetailPage.jsx
```

## Build

```bash
npm run build   # outputs to dist/ -- not yet wired up to be served anywhere
```
