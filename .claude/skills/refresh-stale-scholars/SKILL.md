---
name: refresh-stale-scholars
description: Bulk re-check scholars in the database whose data has exceeded the staleness window (default 6 months), re-fetching from OpenAlex and re-evaluating hard rules. Use when the user wants to refresh stored scholar data independent of running a new paper search.
---

Run (from the `backend/` directory):

```
backend/.venv/Scripts/python.exe -m reviewerfinder.cli refresh
```

Report back how many scholars were found stale and how many were successfully refreshed. If the count of stale scholars is 0, say so plainly — there's nothing to do. If `OPENALEX_API_KEY` is missing, point the user to `backend/.env.example`.
