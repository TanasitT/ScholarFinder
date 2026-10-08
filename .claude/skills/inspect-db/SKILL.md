---
name: inspect-db
description: Quickly inspect ScholarFinder's local SQLite database (backend/data/reviewerfinder.db) — scholar counts by zone, stale-scholar count, recent papers — without hand-writing SQL each time. Use when the user wants to peek at stored data or debug why a search produced unexpected results.
---

Run a quick summary using the sqlite3 CLI against `backend/data/reviewerfinder.db`:

```
sqlite3 backend/data/reviewerfinder.db "SELECT zone, COUNT(*) FROM scholars GROUP BY zone;"
sqlite3 backend/data/reviewerfinder.db "SELECT COUNT(*) FROM papers;"
sqlite3 backend/data/reviewerfinder.db "SELECT title, run_date FROM papers ORDER BY id DESC LIMIT 5;"
sqlite3 backend/data/reviewerfinder.db "SELECT s.display_name, m.passed_hard_rules, m.fail_reasons_json FROM paper_scholar_matches m JOIN scholars s ON s.id = m.scholar_id ORDER BY m.paper_id DESC LIMIT 20;"
```

Adjust the query if the user asks a more specific question (e.g. "how many scholars are stale" → use the staleness window from `SCHOLAR_STALENESS_MONTHS` in `backend/.env`, default 6 months, against `last_checked_at`). If `sqlite3` isn't on PATH, fall back to a short Python one-liner using `sqlite3` from the stdlib against the same file.

If the db file doesn't exist yet, tell the user no search has been run yet rather than trying to create it here.
