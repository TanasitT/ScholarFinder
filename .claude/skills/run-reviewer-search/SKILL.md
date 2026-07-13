---
name: run-reviewer-search
description: Run the ReviewerFinder search pipeline end-to-end against a title/abstract/keywords and print the ranked candidate scholars. Use for quick manual verification during development, or whenever the user wants to actually find reviewers for a paper.
---

Ask the user (if not already given in their message) for the paper's title, abstract, and comma-separated keywords.

Then run (from the `backend/` directory):

```
backend/.venv/Scripts/python.exe -m reviewerfinder.cli search --title "<title>" --abstract "<abstract>" --keywords "<kw1,kw2,kw3>"
```

(On first use in a fresh checkout, make sure dependencies are installed from inside `backend/`: `python -m pip install -e ".[dev]"`, and that `backend/.env` has `OPENALEX_API_KEY` set — copy from `backend/.env.example` and point the user to `backend/README.md` for obtaining a free OpenAlex key if it's missing.)

Report the console output back to the user directly — do not paraphrase the ranked list, since the exact scholar names/emails/scores matter. If fewer than 10 scholars pass, mention the pipeline's own suggestion (broaden keywords / raise `--max-pages`) rather than inventing your own workaround.
