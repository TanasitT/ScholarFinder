---
name: add-data-source
description: Scaffold a new external data source client (API wrapper) for ReviewerFinder, following the project's existing client conventions. Use when the user wants to integrate a new academic data source, email-verification provider, or similar external API.
---

This is a scaffolding shortcut for adding a new client under `backend/src/reviewerfinder/clients/`.

1. Read the existing pattern in `backend/src/reviewerfinder/clients/openalex.py` and `clients/semantic_scholar.py` before writing anything — match their style (plain `requests`-based client class, `timeout=30`, 404→None, a free top-level `extract_*` helper).
2. If the task is more than a small, obvious addition (new provider with non-trivial response shape, or it needs to be wired into `pipeline.py`'s control flow), delegate the actual design work to the `data-source-integrator` subagent rather than improvising.
3. Always add: the client module, a sample fixture JSON under `backend/tests/fixtures/`, and a fixture-based test under `backend/tests/integration/` — then run `pytest` from `backend/` to confirm nothing broke.
