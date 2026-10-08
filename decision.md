# ScholarFinder — Decision Log

A chronological record of the major decisions made while planning and building ScholarFinder, and why. For current architecture/conventions see `CLAUDE.md`; for setup/usage see `README.md`.

## Initial architecture (project kickoff)

- **Data sources**: OpenAlex (primary, topical search + author metrics) + Semantic Scholar (secondary cross-check), instead of Google Scholar/Scopus as literally requested — Scholar blocks scraping, Scopus needs paid institutional access the user doesn't have. ORCID anchors identity instead; Google Scholar/Scopus get constructed search-URL convenience links, not live queries.
- **Email discovery**: best-effort scraping only — never construct/guess emails from name+domain patterns.
- **Email verification**: deferred entirely — no paid provider wired up initially; emails ship as `unverified` behind a swappable seam (`clients/email_verifier.py`).
- **Storage**: SQLite, not JSON files — filtering/staleness/join queries are inherently relational.
- **LangChain**: `langchain.agents.create_agent` (LangGraph-based), not the deprecated `AgentExecutor`. Claude as the chatbot LLM. Chat session memory (`SqliteSaver`) kept in a separate DB file from domain data.
- **Build order**: phased (Phase 1 → 2 → 3), reviewed after each slice, rather than building everything at once.
- **Hard rule**: all eligibility rules enforced by deterministic Python, never LLM judgment — every reject stores its reason for auditability.

## Phase 1 — core pipeline

- `src/` package layout (installable, importable from CLI/tests without path hacks).
- Country-zone data externalized to `data/seed/zones.yaml` (editable data), but enforcement — including the Egypt/Saudi Arabia hard exclusion — stays in `rules/zones.py` code, so editing the yaml alone can never bypass it.
- **Bug found & fixed**: YAML 1.1's boolean resolver silently turned Norway's `"NO"` code into Python `False` — fixed by quoting every country code in the yaml.
- **Bug found & fixed**: `passes_all_hard_rules()` initially always gated on email, which would fail every candidate since email discovery didn't exist yet — added a `check_email` flag, defaulted off until Phase 2.
- Every evaluated candidate (pass *and* fail) persisted with `fail_reasons`, not just successes — needed later for the chatbot to explain rejections.
- Topical ranking (`rules/ranking.py`) explicitly separated from filtering — used only for ordering, never for pass/fail.

## Zone list update (mid-project correction)

- User replaced the seed zone lists with a full, explicit country mapping.
- **Conflict surfaced and resolved by user decision**: the new list placed Egypt/Saudi Arabia under Zone 2, contradicting the absolute "never invite" rule — user confirmed the hardcoded exclusion stays authoritative regardless of the yaml.
- Changed the unmapped-country fallback from `EXCLUDED` to `ZONE_3` ("and the rest"), matching the user's list — same practical filtering outcome, but more accurate stored `zone`/`fail_reasons` for unlisted countries.

## Phase 2 — email discovery

- User scope decisions: **include PDF text extraction** (`pypdf`) for open-access papers that are PDF-only; **skip Unpaywall** — rely solely on OpenAlex's own `open_access.oa_url`.
- Email sources tried in order: OpenAlex open-access papers (HTML or PDF) → Semantic Scholar homepage fallback. Generic-localpart addresses (`info@`, `support@`, etc.) deprioritized in favor of personal-looking ones.
- Pipeline restructured into **two passes**: core rules (zone/institution/pubs/h-index) first — candidates that fail never get scraped — then email hunt only for core-rule passers, then a final pass that actually enforces the email requirement.
- **Bug found & fixed**: `enrichment.py` was overloading `email_source` to stash a homepage URL as a hack; fixed to store the full raw Semantic Scholar JSON properly.
- **Bug found & fixed**: the pipeline would have created an unmocked, throwaway `requests.Session()` for email scraping instead of reusing the OpenAlex client's session — fixed to pass the session through explicitly.
- Test fixture PDF built by hand (raw PDF bytes with a computed xref table) rather than checking in a binary fixture file.

## Backend/frontend reorganization

- User's ask for a "frontend" folder was ambiguous (no frontend code existed) — clarified via question: chosen interpretation was "reorganize for a future web UI," not "split CLI vs core logic" or "build a real web frontend now."
- All existing Python code moved into `backend/`; `frontend/` created as an empty placeholder with a README noting a backend HTTP API layer would be needed first.
- Old root `.venv` deleted and rebuilt fresh inside `backend/` rather than attempting to relocate it (Windows venvs embed absolute paths).
- Root-level `README.md`/`CLAUDE.md` rewritten as monorepo overviews; per-package docs moved/adapted; all `.claude/agents` and `.claude/skills` path references updated to the new nested layout.

## Phase 3 — LangChain chatbot

- Verified exact current LangChain/LangGraph/rapidfuzz APIs by installing the real packages and inspecting them directly, rather than trusting training-data recall — the API surface has churned significantly.
- Five tools designed around the existing repository/rule layer rather than reimplementing logic: `lookup_scholar` (fuzzy name match via `rapidfuzz`), `lookup_paper`, `check_scholar_fit` (the core "is X fit for Y" tool — re-runs the same deterministic rule engine), `list_top_candidates`, `search_new_candidates`.
- System prompt enforces that the model reports `check_scholar_fit`'s verdict verbatim, never asserting eligibility from its own judgment.
- **Confirmation gating decision**: `search_new_candidates` (which spends OpenAlex budget) is gated via system-prompt instruction only, not a hard LangGraph `interrupt_before` — documented as a soft gate, upgradeable later.
- **Design note accepted**: `search_new_candidates` creates a *new* paper record on each call (consistent with how the schema already models repeated dated search runs) rather than mutating the original `paper_id`.
- **Bug found & fixed**: refreshing a stale scholar's core stats rebuilt a brand-new `Scholar` object that silently discarded any previously-discovered email — found via a failing test, fixed with a new `carry_over_email()` helper applied at all three refresh call sites (`pipeline.py`, `cli.py refresh`, `check_scholar_fit`).
- Only the tools are unit-tested (mocked, no live calls); the live agent loop itself is left to manual verification, consistent with how `search`/`refresh` were verified in earlier phases.

## Web frontend + backend API

- User decisions (confirmed via clarifying questions before planning): **scope** is search + browse only (new-search form, past papers, paper detail, scholar detail) — the chatbot stays CLI-only, a bigger separate scope; **stack** is React + Vite talking to a new FastAPI backend, not a static page; **spend gate** — running a new search from the web form requires an explicit confirm click first, mirroring the chatbot's existing soft-gate on `search_new_candidates`.
- New `api/` package is a thin wrapper only — `Paper`/`Scholar` from `models.py` are reused directly as FastAPI response models (no duplicate schemas), and `POST /api/papers/search` calls the exact same `pipeline.run_search()` the CLI's `search` command uses.
- **Design decision**: browsing (list/detail endpoints) works without `OPENALEX_API_KEY` configured — only `/api/papers/search` needs it, checked lazily per-request rather than failing the whole app at startup, so a missing key doesn't block read-only use of already-stored data.
- **Bug found & fixed**: `POST /api/papers/search` initially imported `config.settings.DB_PATH` directly instead of going through an overridable dependency — its own test then silently wrote fixture data into the real production database (`backend/data/reviewerfinder.db`), caught by a manual `curl` check showing unexpected data, not by the test itself. Fixed by adding `api/deps.py::get_db_path()` as a proper `Depends()`-injected function that every route and repository dependency goes through, and by overriding it in the test fixture. This is the same category of "test isolation via a wrong indirection layer" as earlier bugs in the project, just at the API layer instead of the pipeline.
- Frontend dev-mode wiring uses Vite's `/api` proxy to the backend rather than CORS middleware — keeps both dev and (eventual) prod simpler by keeping the browser on one origin.
- Explicitly deferred rather than built now: production static-file build/serving, authentication, and frontend automated tests (no test runner exists yet in `frontend/`) — called out in the plan rather than silently skipped.

## First real-data run — bugs found in production, not tests

Running the built system against real OpenAlex data (not mocked fixtures) surfaced three real bugs that 92 passing tests hadn't caught, because the fixtures happened not to exercise these exact shapes of real-world data:

- **Search progress**: the original synchronous `POST /api/papers/search` gave zero feedback for a call that can take minutes against real data (Semantic Scholar's free-tier rate limit alone added ~2.5 minutes to a 128-candidate search). Redesigned as an async job: the endpoint starts the search on a background thread and returns a job id immediately (`api/jobs.py`, in-memory store), `pipeline.run_search()` gained an optional `on_progress(stage, done, total)` callback, and the frontend polls `GET /api/papers/search/{job_id}` to drive a real progress bar (`SearchProgress.jsx`) instead of a generic spinner.
- **Crash bug**: a single `sqlite3.IntegrityError` (two distinct scholars' fuzzy Semantic Scholar name-matching resolving to the same S2 author id) crashed an entire ~130-candidate search with a bare, undebuggable 500 — caught directly by the user clicking "run search" in the browser. Root-caused via the server log (visible because client disconnects don't stop a running Python thread server-side — the 2.5-minute search had actually kept running after `curl --max-time 60` gave up, which is also why an earlier progress check of mine read a false "0 passed" mid-flight snapshot and had to be corrected). Fixed at two levels: `ScholarRepository.upsert()` retries without the colliding `semantic_scholar_id` rather than failing, and `pipeline.py`'s per-candidate loop got a broad `try/except` so any other single-candidate failure can't sink a whole batch either.
- **No error detail in API responses**: FastAPI's default unhandled-exception response has no JSON body at all, so the frontend's `{"detail": ...}`-parsing error handling fell back to a generic, unhelpful message — user feedback ("backend response does not include error detail") caught this directly. Added a global exception handler that returns the exception message as JSON and logs the full traceback server-side.
- **Wrong-person email attribution** — the most serious of the four: real results showed `morgan.lee@example.org` attributed to a scholar named "Taylor S. Sample." The email-picking logic took "the first non-generic-looking address found on the page," which silently attributes a co-author's or department staff's email to the wrong scholar when a page lists multiple people. This directly undermines the project's core "never guess, only extract what genuinely belongs to this person" principle stated since Phase 2, even though the address itself actually was scraped verbatim from somewhere. Fixed by requiring the scholar's own name to appear in the email's local-part before attributing it (`email_hunter.py::_pick_best_email()`); no match now correctly reports as not-found rather than as a wrong answer.

Takeaway kept for future work: mocked-fixture tests validate mechanics (does the pipeline run, does data flow through correctly) but can't catch data-shape or scale problems that only show up against real external data (rate limits, name collisions, multi-person pages) — a real-data smoke test remains valuable even with a thorough mocked suite in place.

## Keyword-set decomposition (search architecture change)

The user asked to change how *every* search works, not just run a one-off task: decompose a paper's title/abstract/keywords into 5 sets of 3 keywords and find 5 scholars per set. Three confirmed decisions before building:

- **Generation method**: LLM-based (Claude), not algorithmic/statistical extraction — chosen for more thematically distinct angles (methodology, application domain, technique, etc.) than TF-IDF-style extraction would produce. This makes `ANTHROPIC_API_KEY` a **base requirement for `search`** now, not just for `chat` — a new coupling accepted deliberately for output quality. Implemented with the plain `anthropic` SDK (not LangChain) specifically so the base `search` flow doesn't need to pull in the whole `chatbot` extra.
- **Integration scope**: replaces the existing single-query search entirely, across CLI/API/frontend/chatbot's `search_new_candidates` — there is no more "just search with the original keywords" mode.
- **Results structure**: one parent `Paper` row with 5 `keyword_sets` child rows, each holding its own ranked matches — not 5 independent unrelated paper records. Required a schema change: `paper_scholar_matches`'s uniqueness key became `(paper_id, keyword_set_id, scholar_id)` instead of `(paper_id, scholar_id)`, since the same scholar can legitimately surface under more than one angle.
- **"Verified scholars" clarified**: the user's phrase meant "passed all eligibility rules," not real email-deliverability verification (which still isn't implemented — see Phase 2). Confirmed via clarifying question before building, to avoid either overpromising or silently reinterpreting the ask.
- Eligibility rules stayed 100% deterministic throughout this change — Claude only ever shapes *what gets searched for* (the 5 keyword sets), never *who passes*. Malformed/wrong-shaped LLM output (`keyword_summarizer.py`) raises loudly rather than silently proceeding, unlike the best-effort posture used for enrichment/email-hunting elsewhere — there's nothing to search for without valid keyword sets, so failing loudly is the correct behavior here specifically.
- Progress reporting extended rather than redesigned: `on_progress(stage, done, total)` now emits `"generating_keywords"` once, then `"set_<N>_<phase>"` for N in 1..5, reusing the existing callback shape from the earlier async-job work instead of inventing a new one.
- No migration system exists (`CREATE TABLE IF NOT EXISTS` only) — the schema change required deleting and recreating the local dev database, same as every prior schema change in this project. Documented as an explicit, accepted limitation of a local single-user tool, not something to build a migration system for right now.

## Keyword-set generation: Claude → local Ollama

Shortly after shipping Claude-based keyword-set generation, the user tried to use their existing claude.ai Pro subscription instead of getting a separate Anthropic API key — a reasonable assumption, but wrong: **claude.ai Pro/Max and the Anthropic API are separate products with separate billing**; a Pro subscription grants no API access. Rather than push the user toward a new paid API account, offered genuinely free alternatives (Gemini free tier, Groq free tier, local Ollama, or dropping the LLM entirely) and let the user choose.

- **User's choice**: Ollama, fully local, no API key ever. Not installed on this machine — offered to install via `winget` or let the user install it themselves; user chose to install it themselves while the integration code was written in parallel.
- **Implementation**: `keyword_summarizer.py` now calls `POST {OLLAMA_BASE_URL}/api/chat` (default `http://localhost:11434`, model `llama3.1`) via plain `requests` — no new dependency, consistent with every other client in this codebase (OpenAlex, Semantic Scholar). The `anthropic` SDK was removed from base dependencies entirely (it was only ever there for this feature); `ANTHROPIC_API_KEY`/`langchain-anthropic` remain chatbot-only, unaffected.
- **Parsing note**: local models proved more prone than Claude to wrapping JSON in markdown fences or adding stray prose despite explicit instructions not to — `_extract_json_array()` gained a fallback regex extraction of the first `[...]` span, on top of the existing fence-stripping, to stay robust to that.
- **Fail-fast UX preserved**: `api/deps.py::check_ollama_reachable()` pings `/api/tags` before a search job is even created, mirroring the existing `get_openalex_client` pattern — a search with no reachable Ollama fails in under a second with an actionable message, rather than starting a job that dies partway through.
- Net effect: `search` now needs zero paid API accounts (`OPENALEX_API_KEY` is free-tier). Only `chat` still needs a paid Anthropic key, and that was true from Phase 3 onward regardless of this change.

## Chatbot: Claude → local Ollama too

Immediately after the search-side Ollama switch, the user asked whether the chatbot could also move off Claude — the goal being zero paid API keys anywhere in the project, not just for `search`. Confirmed via clarifying question: **fully replace**, not a configurable dual-provider setup — simpler code, matches the user's actual goal (a completely free/local project), and there was no stated need to keep Claude as an option.

- `chatbot/agent.py`'s `ChatAnthropic` → `langchain_ollama.ChatOllama`, using the exact same `settings.ollama_base_url`/`ollama_model` the search pipeline already uses — one Ollama server/model serves both features.
- `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` and `langchain-anthropic` removed from the project entirely (not just made optional) — `config/settings.py::require_anthropic_key()` deleted, `.env`/`.env.example` cleaned up.
- **Known tradeoff, called out rather than hidden**: local models are generally less reliable at consistent tool-calling than Claude was, which matters here because the chatbot's system prompt depends on it always calling `check_scholar_fit` for eligibility questions rather than answering from its own judgment. Flagged to the user before implementing, not discovered after the fact — if chatbot behavior seems inconsistent later, this is the first place to look, not a code bug.
- Verified the `langchain-ollama` package and `ChatOllama`'s actual constructor signature directly against the installed package before wiring it in, same verify-don't-assume approach used for the original LangChain integration in Phase 3.

## Documentation pass

- Root `README.md` rewritten as the primary explainer: project purpose, eligibility rules, full tech-stack table with rationale per choice, step-by-step pipeline mechanics, setup/usage commands, and a description of what every test file verifies.
- This decision log added (`decision.md`) to keep the *why* behind each choice discoverable separately from the *what* (README) and *how to work in this repo* (CLAUDE.md).

## Portfolio polish: naming, portability, demo data

- **Renamed the project to ScholarFinder** in everything a user or reader sees (READMEs, UI title and top bar, API docs title, chatbot system prompt, docs/, Claude Code agents and skills). The Python package, CLI module (`python -m reviewerfinder.cli`) and SQLite filename (`data/reviewerfinder.db`) deliberately keep the old working name: renaming them would touch every import and test and orphan existing local databases for no user-visible gain. The README says so explicitly.
- **Cross-platform launcher**: added `run.sh` next to `run.ps1`; the setup instructions no longer assume Windows virtualenv paths.
- **Demo data without API keys**: `backend/scripts/seed_demo.py` loads a fictional paper and nine fictional scholars through the real rule engine and ranking, so the UI can be explored with no OpenAlex key and no Ollama. It is idempotent and writes to the gitignored `data/*.db`.
- **Rules framed as an example policy**: the README now says the zone list, thresholds and the two unconditional country exclusions are one configurable reviewer-invitation policy, not a universal standard. Behaviour was not changed.
- **Third-party data removed**: the wrong-person-email example (here, in `CLAUDE.md` and in the regression test) used a real-looking name and Gmail address from an actual search. Replaced with invented values (`Taylor S. Sample`, `morgan.lee@example.org`); the test's logic is unchanged.
