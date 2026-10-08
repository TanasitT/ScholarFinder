# ScholarFinder — Backend

Given a paper's title, abstract, and keywords, decomposes the paper into 5 distinct keyword-set angles (via a local Ollama model — no API key needed) and finds up to 5 qualified peer-review candidate scholars per angle: name, research topics, affiliation, and a best-effort discovered email — filtered against strict eligibility rules.

All commands below assume your working directory is `backend/` (this folder).

## Eligibility rules (enforced deterministically, never by LLM judgment)

- 8+ papers published in the last 5 years
- Affiliation in a Zone 1 (high-trust) or Zone 2 (medium-trust) country — Zone 3 countries are never invited
- Egypt and Saudi Arabia are excluded unconditionally, regardless of zone
- Currently employed at a university/academic institution, not a company
- H-index ≥ 5 (Zone 1) or ≥ 10 (Zone 2)
- A discovered email address (best-effort, scraped — never guessed/constructed; ships as `unverified` until a paid verification provider is configured)
- Identity anchored via ORCID; Google Scholar/Scopus profile links provided as manual-check convenience (not auto-verified — see below)

## Setup

```
cd backend
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
python -m pip install -e ".[dev,chatbot,api]"
cp .env.example .env               # then fill in the keys below
```

(Omit `chatbot` and/or `api` from the extras if you don't need the LangChain chatbot or the web frontend's HTTP API.)

### Required keys (`.env`)

- `OPENALEX_API_KEY` — **required**. As of Feb 2026, OpenAlex requires a free API key and uses daily usage-based credits (~$1.00/day on the free tier). Get one from your OpenAlex account settings at openalex.org. Set `OPENALEX_MAILTO` to your email too (not billed, just identifies you to their "polite pool").
- **Ollama** (not an API key — a locally-running service) — **required for both `search`** (decomposes the paper into 5 keyword sets) **and `chat`** (the chatbot's model). Install from [ollama.com](https://ollama.com), leave it running, then `ollama pull llama3.1` (or whichever model you set `OLLAMA_MODEL` to). Free, no billing, no account — no paid API key is needed anywhere in this project. `search` fails with a clear error if it can't reach `OLLAMA_BASE_URL` (default `http://localhost:11434`).
- `SEMANTIC_SCHOLAR_API_KEY` — optional, raises Semantic Scholar's shared rate limit. Get one at semanticscholar.org/product/api.

No email-verification API key is configured yet — discovered emails ship as `unverified` by default; a provider like Hunter.io can be wired into `clients/email_verifier.py` later.

## Usage

```
python -m reviewerfinder.cli search --title "..." --abstract "..." --keywords "kw1,kw2,kw3"
python -m reviewerfinder.cli refresh   # re-check scholars whose data is stale (default: 6+ months old)
python -m reviewerfinder.cli chat      # interactive chatbot over stored papers/scholars
python -m reviewerfinder.cli serve     # HTTP API on :8000 -- see ../frontend/README.md to run the web UI against it
```

## Keyword-set decomposition

Every `search` first asks a local Ollama model to decompose the paper's title/abstract/keywords into exactly 5 distinct 3-keyword search angles (e.g. methodology, application domain, underlying technique) — see `discovery/keyword_summarizer.py`. Each angle is then searched completely independently (its own discovery → enrichment → filtering → email hunt → ranking), so the output is 5 labeled groups of up to 5 scholars each, not one flat list. This is the only place an LLM influences search behavior; eligibility itself stays 100% deterministic (see below).

## Chatbot

`chat` starts an interactive session (conversation history persists across runs via a SQLite checkpointer in `data/chat_sessions.db`, kept separate from the main `reviewerfinder.db`). It can look up stored scholars/papers, answer "is `<scholar>` fit to review `<paper>`?" (by calling the same deterministic rule engine the batch pipeline uses and reporting the verdict as-is, never its own judgment), list a paper's top-ranked candidates, and — after you explicitly confirm, since it spends OpenAlex budget (and needs Ollama running for keyword-set generation) — re-run discovery for a paper to find new candidates.

## Data sources and their limits

- **OpenAlex** (primary): topical search over works, author enrichment (h-index, recent-paper counts, institution country/type), and each author's recent open-access papers (scraped for a contact email — HTML landing pages and PDF-only papers alike).
- **Semantic Scholar** (secondary): cross-checks h-index/paper counts, and its `homepage` field is the fallback email-hunting source when no OA paper yields one. It has no institution country/type data of its own.
- **Google Scholar / Scopus**: not scraped or queried automatically — Scholar blocks automated scraping and Scopus requires paid institutional API access this project doesn't assume you have. Instead, ORCID (from OpenAlex/Semantic Scholar) anchors scholar identity, and a constructed Google Scholar / Scopus search URL is included per scholar as a manual-check convenience link.

## Email discovery

Emails are only ever *extracted* from content that's actually fetched (an open-access paper's landing page or PDF, or the scholar's homepage) — never constructed or guessed from a name+institution-domain pattern. If nothing turns up, the scholar shows as no-email and is excluded from the final ranked output rather than shown with a blank/guessed address. Discovered emails are not deliverability-checked yet (status `unverified`); wire a real provider into `clients/email_verifier.py` if you need that.

## HTTP API

`serve` runs a FastAPI app (`api/`) that's a thin layer over the same pipeline and repositories the CLI uses — no separate business logic. Browsing (`GET /api/papers`, `GET /api/papers/{id}`, `GET /api/scholars/{id}`) works with nothing configured; `POST /api/papers/search` needs `OPENALEX_API_KEY` and a reachable local Ollama. It's asynchronous — it returns a job id immediately and you poll `GET /api/papers/search/{job_id}` for progress and the eventual result, since a real search (5 keyword sets, each its own multi-step pipeline) can take several minutes. This is what `../frontend/` talks to.

## Project status

Phase 1 (core pipeline), Phase 2 (email discovery), Phase 3 (LangChain chatbot), a web frontend (search + browse), and keyword-set decomposition are all implemented and tested. See `../CLAUDE.md` for the phase breakdown.

## Testing

```
pytest
```

Unit tests (`tests/unit/`) are pure and offline. Integration tests (`tests/integration/`) mock HTTP calls against recorded fixtures in `tests/fixtures/` — no live API calls happen in the test suite, so running tests never consumes your OpenAlex daily credit.
