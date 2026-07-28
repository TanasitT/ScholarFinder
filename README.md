# ReviewerFinder

ReviewerFinder finds qualified peer reviewers for an academic paper. Give it a paper's title, abstract, and keywords; it first asks a local Ollama model to decompose the paper into 5 distinct 3-keyword search angles, then searches each independently and returns up to 5 candidate scholars per angle — name, institution, h-index, research topics, and a best-effort discovered email — who meet a strict set of eligibility rules. Results are stored locally so the same scholars don't need to be re-researched for the next paper. A CLI chatbot (also Ollama-powered) can answer follow-up questions like "is this scholar fit to review that paper?" against the stored data, and a web UI covers searching and browsing. No paid API key is needed anywhere in the project.

## Requirements

- **Python 3.11+** (backend — CLI, pipeline, API)
- **Node.js 18+** and npm (frontend — only needed if you want the web UI, not the CLI)
- **[Ollama](https://ollama.com)** installed and running locally, with a model pulled (default `llama3.1`, `ollama pull llama3.1`) — required for `search` (keyword-set decomposition) and `chat`
- **An [OpenAlex](https://openalex.org) API key** (free) — required for `search`/`refresh`. As of Feb 2026, OpenAlex requires a key and meters usage against a daily free credit (~$1.00/day)
- *Optional*: a **[Semantic Scholar](https://www.semanticscholar.org/product/api) API key** (free) — raises the shared rate limit for the secondary cross-check/email-hunting lookups; the app works without one, just with occasional `429`s logged and skipped
- No paid API key of any kind is required anywhere in this project — everything above is either free or fully local.

Browsing already-stored papers/scholars via `serve`/the web UI, and running the test suite, need none of the above except Python (and Node for the UI) — no Ollama, no API keys.

## Why it exists

Manually vetting reviewer candidates against rules like "8+ recent papers, academic employer only, h-index above a country-dependent threshold, never from an excluded country" is slow and error-prone, especially the exclusion rules. ReviewerFinder automates the research and applies the rules deterministically and auditably — every candidate's pass/fail decision, and the reasons for it, are stored, not just the ones who made the cut.

## Eligibility rules

Enforced entirely in Python (`rules/filters.py`, `rules/zones.py`) — **never** by LLM judgment, including inside the chatbot. (A local Ollama model does decompose the paper into keyword-set search angles up front — see "How it works" — but that only shapes what gets searched for, never who passes.)

- 8+ papers published in the last 5 years
- Affiliation in a Zone 1 (high-trust) or Zone 2 (medium-trust) country — Zone 3 countries and any country not on the explicit list are never invited
- Egypt and Saudi Arabia are excluded unconditionally, regardless of what zone they're listed under
- Currently employed at a university/academic institution, not a company
- H-index ≥ 5 (Zone 1) or ≥ 10 (Zone 2)
- A discovered email address (scraped, never guessed/constructed — see below)
- Identity anchored via ORCID, with Google Scholar/Scopus search links included as a manual-check convenience

## Layout

```
ReviewerFinder/
├── CLAUDE.md          Architecture/conventions notes for Claude Code
├── README.md          This file
├── decision.md        Chronological log of major project decisions and why
├── docs/               Generated HTML explainers (project overview, build plans)
├── backend/           CLI, pipeline, rule engine, chatbot, HTTP API
│   ├── src/reviewerfinder/
│   │   ├── cli.py             Entry point: `search`, `refresh`, `chat`, `serve` commands
│   │   ├── models.py          Pydantic models: Paper, Scholar, and their enums
│   │   ├── pipeline.py        Orchestrates the end-to-end search
│   │   ├── clients/           Thin API clients: OpenAlex, Semantic Scholar, email verifier (no-op)
│   │   ├── discovery/         Candidate discovery, profile enrichment, email hunting
│   │   ├── rules/             Deterministic eligibility rules, country-zone mapping, topical ranking
│   │   ├── db/                SQLite schema + repository classes
│   │   ├── chatbot/           LangChain agent, tools, and session persistence
│   │   └── api/                FastAPI layer the frontend talks to (thin wrapper, no new logic)
│   ├── config/settings.py     Env-driven settings (API keys, thresholds)
│   ├── data/seed/zones.yaml   Country → trust-zone mapping (editable data)
│   └── tests/                 Unit + integration tests (see below)
├── frontend/          React + Vite SPA: search form, past papers, paper/scholar detail views
└── .claude/           Claude Code project agents/skills for developing this repo
```

Backend commands run from `backend/`; frontend commands run from `frontend/` — noted per section below.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | |
| CLI | [Typer](https://typer.tiangolo.com/) | thin, typed CLI over `search`/`refresh`/`chat` |
| Data models | [Pydantic v2](https://docs.pydantic.dev/) | validation + easy JSON serialization for tool outputs |
| Config | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | typed `.env` loading, fails fast on missing keys |
| Storage | SQLite (stdlib `sqlite3`) | filtering/staleness/join queries are inherently relational; no extra service to run |
| HTTP | [requests](https://requests.readthedocs.io/) | plain clients for OpenAlex and Semantic Scholar |
| Country/zone data | [PyYAML](https://pyyaml.org/) | `data/seed/zones.yaml` |
| Fuzzy name matching | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | chatbot's `lookup_scholar` tool |
| PDF text extraction | [pypdf](https://pypdf.readthedocs.io/) | scraping emails out of PDF-only open-access papers |
| Chatbot | [LangChain](https://python.langchain.com/) `create_agent` + [LangGraph](https://langchain-ai.github.io/langgraph/) + [langchain-ollama](https://python.langchain.com/docs/integrations/chat/ollama/) | tool-calling agent over a local Ollama model — no paid API key anywhere in the project |
| Chat memory | `langgraph-checkpoint-sqlite` (`SqliteSaver`) | conversation history persists across CLI runs, in its own DB file |
| Keyword-set decomposition | [Ollama](https://ollama.com) (local, plain HTTP via `requests`) | a local model splits the paper into 5 search angles before every search — no API key/billing, same local Ollama server the chatbot uses |
| HTTP API | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | thin layer over the existing pipeline/repositories; `Paper`/`Scholar`/`KeywordSet` reused directly as response models since they're already Pydantic |
| Frontend | [React](https://react.dev/) + [Vite](https://vitejs.dev/) + [react-router-dom](https://reactrouter.com/) | SPA with routing/component state for search + browse; Vite's dev proxy avoids needing CORS |
| Tests | pytest + pytest-mock | all HTTP calls mocked against fixtures; no live network in the test suite |

External data sources: **[OpenAlex](https://openalex.org)** (primary — topical search, author metrics, open-access links; free but requires an API key and has daily usage credits) and **[Semantic Scholar](https://www.semanticscholar.org/product/api)** (secondary cross-check + homepage lead for email hunting). Google Scholar and Scopus are *not* queried automatically (Scholar blocks scraping, Scopus needs paid institutional access) — instead the tool generates a search-URL for each so you can check manually.

## How it works

`reviewerfinder search --title ... --abstract ... --keywords ...` runs this pipeline (`pipeline.py`):

0. **Keyword-set decomposition** (`discovery/keyword_summarizer.py`) — a local Ollama model reads the title/abstract/keywords and proposes exactly 5 distinct 3-keyword search angles (e.g. methodology, application domain, underlying technique), persisted as `keyword_sets` rows. Malformed output fails the whole search loudly rather than proceeding with something wrong.
1. **Discovery** (`discovery/candidate_finder.py`) — for each of the 5 sets independently: searches OpenAlex works matching that set's 3 keywords (plus the paper's title/abstract for context), collects the unique authors.
2. **Enrichment** (`discovery/enrichment.py`) — fetches each candidate's full OpenAlex author profile (h-index, recent-paper counts, institution, country) and cross-checks against Semantic Scholar.
3. **Core-rule filtering** (`rules/filters.py`, email not yet checked) — zone, institution type, recent-paper count, h-index. Candidates that fail here are recorded (with their specific failure reasons) and dropped before any scraping happens.
4. **Email hunt** (`discovery/email_hunter.py`) — for core-rule passers only: scrapes each scholar's recent open-access papers (HTML or PDF) for an email, falling back to their Semantic Scholar homepage. Never constructs or guesses an address.
5. **Final filtering** — the same rule check, now including "was an email found."
6. **Ranking** (`rules/ranking.py`) — orders each set's passers by topical relevance to that set's keywords (never used to filter, only to sort); the top 5 per set come back as the result.
7. **Persistence** — every evaluated candidate, pass or fail, is written to SQLite (keyed by paper + keyword set + scholar) with its reasons, so the chatbot can later explain a rejection and repeat searches can reuse already-vetted scholars instead of re-querying.

Steps 1–7 run once per keyword set — a search evaluates candidates from 5 independent angles, not one flat query.

The chatbot (`chatbot/`) is a LangChain agent with five tools over that same stored data and rule engine (`lookup_scholar`, `lookup_paper`, `check_scholar_fit`, `list_top_candidates`, `search_new_candidates`) — it answers questions and explains results, but for any eligibility verdict it calls `check_scholar_fit` and reports the rule engine's answer verbatim rather than deciding itself.

The web frontend talks to a FastAPI layer (`api/`) that's a thin wrapper over the *same* `pipeline.run_search()` and repositories — running a search from the browser goes through the identical pipeline above, just triggered over HTTP instead of the CLI (asynchronously, since 5 keyword sets' worth of work can take minutes — the UI polls a job and shows real per-set progress). Browsing already-stored papers/scholars works without anything configured; only triggering a new search needs `OPENALEX_API_KEY` and a reachable local Ollama, and the UI asks for explicit confirmation first since that spends OpenAlex budget.

## Usage

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate                          # .venv\Scripts\activate on Windows cmd
python -m pip install -e ".[dev,chatbot,api]"   # omit extras you don't need (chatbot needs LangChain, api needs FastAPI)
cp .env.example .env                             # then fill in OPENALEX_API_KEY (required for search); also install Ollama (ollama.com) + `ollama pull llama3.1`
```

```bash
# Find reviewers for a paper
python -m reviewerfinder.cli search --title "..." --abstract "..." --keywords "kw1,kw2,kw3"

# Re-check scholars whose stored data is stale (default: older than 6 months)
python -m reviewerfinder.cli refresh

# Interactive chatbot over everything stored so far
python -m reviewerfinder.cli chat

# HTTP API for the web frontend, on :8000
python -m reviewerfinder.cli serve
```

To run the web UI, with the API above already running: `cd frontend && npm install && npm run dev`, then open the printed `localhost:5173` URL.

**Windows shortcut**: once the backend venv (`backend/.venv`) and frontend (`frontend/node_modules`) are set up once as above, [`run.ps1`](run.ps1) at the repo root starts both the API (`:8000`) and the web UI (`:5173`) together in one command:

```powershell
powershell -File run.ps1
```

It prints both process IDs and stops both cleanly on Ctrl+C.

See [`backend/README.md`](backend/README.md) for full setup details, where to get each API key, and the OpenAlex daily-credit note.

## Tests

Run with `pytest` from `backend/`. Unit tests (`tests/unit/`) are pure and offline; integration tests (`tests/integration/`) mock every HTTP call against recorded fixtures in `tests/fixtures/` — the suite never makes a live network call or spends OpenAlex credit.

**`tests/unit/`**
- **`test_zones.py`** — country → trust-zone mapping. Covers Zone 1/2/3 lookups, the catch-all "unmapped country defaults to Zone 3" behavior, and — as an explicit regression guard — that Egypt and Saudi Arabia are excluded even if the yaml data file is edited to list them under an allowed zone.
- **`test_filters.py`** — the eligibility rule functions. Boundary cases for each rule (exactly 8 recent papers passes, 7 fails; h-index exactly at the Zone 1/Zone 2 threshold; academic vs. company institution), and that `passes_all_hard_rules` reports every failing reason at once rather than stopping at the first one.
- **`test_ranking.py`** — topical relevance scoring. Confirms a scholar whose research topics overlap the paper ranks above an unrelated one, and that scholars with no topic data score zero rather than erroring.
- **`test_repository.py`** — the SQLite repository layer (in a temp DB per test). Covers paper/scholar create-and-read, upsert idempotency (re-saving the same scholar updates rather than duplicates), staleness-flag computation, and that match records reflect the latest re-ranking.
- **`test_email_verifier.py`** — confirms the (currently no-op) verifier always returns `unverified`, documenting that no real deliverability check happens yet.
- **`test_enrichment.py`** — the `carry_over_email` helper, which prevents a scholar's core-data refresh (new h-index/institution from OpenAlex) from silently wiping a previously-discovered email.
- **`test_chatbot_tools.py`** — each chatbot tool in isolation (via `.invoke()`, no live LLM call): scholar/paper lookup by exact ID and fuzzy name, `check_scholar_fit` matching what calling the rule engine directly would return (including that it refreshes stale scholars, via a mocked OpenAlex client, without losing their email), ranked candidate listing, and that `search_new_candidates` calls the pipeline with the stored paper's own fields.
- **`test_keyword_summarizer.py`** — the Ollama-based keyword-set generator, with the HTTP call mocked: parses a valid 5-set response, strips a markdown code fence / surrounding prose the local model adds despite being told not to, raises a clear error when Ollama is unreachable, and raises on invalid JSON / wrong set count / wrong keyword count / missing fields rather than silently proceeding with something malformed.
- **`test_api_papers.py`** / **`test_api_scholars.py`** — the FastAPI routes via `TestClient`, with every repository/client dependency overridden to a temp DB and mocked HTTP (nothing ever touches the real database or network): listing papers with their passing counts, grouped paper/scholar detail 404s, running a real search through the async job HTTP layer end-to-end, and that search returns 503 rather than crashing when OpenAlex isn't configured or Ollama isn't reachable.

**`tests/integration/`**
- **`test_openalex_client.py`** — the OpenAlex API client against recorded fixture JSON: works-search extracts the right author IDs, author lookup parses h-index/institution/counts-by-year, and a 404 is handled as "not found" rather than an error.
- **`test_semantic_scholar_client.py`** — same idea for the Semantic Scholar client (author search, 404 handling).
- **`test_email_hunter.py`** — the scraping logic: extracting an email from a fixture HTML page, from a hand-built minimal PDF (to exercise the `pypdf` code path without checking in a binary fixture), preferring a personal address over a generic one (`info@...`) when both appear on a page, and falling back to the Semantic Scholar homepage when no open-access paper yields an email.
- **`test_pipeline_e2e_mocked.py`** — the full `search` pipeline end-to-end with keyword-set generation and every HTTP call mocked: confirms all 5 keyword sets run independently and scholars who pass core rules *and* have a discoverable email end up in each set's ranked output, and that scholars with no discoverable email anywhere are correctly excluded from every set rather than shown with a blank address.
