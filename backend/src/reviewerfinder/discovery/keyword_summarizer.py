from __future__ import annotations

import json
import logging
import re

import requests

from reviewerfinder.models import KeywordSet, Paper

logger = logging.getLogger(__name__)

EXPECTED_SET_COUNT = 5
KEYWORDS_PER_SET = 3
REQUEST_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = f"""You help find peer reviewers for academic papers by decomposing a \
paper's topic into distinct search angles.

Given a paper's title, abstract, and any author-supplied keywords, propose exactly \
{EXPECTED_SET_COUNT} sets of exactly {KEYWORDS_PER_SET} keywords each. Each set must \
represent a genuinely distinct angle on the paper (e.g. methodology, application \
domain, underlying technique, theoretical framework, problem being solved) so that \
searching an academic database with each set separately surfaces a different slice \
of relevant researchers, not near-duplicates of each other.

Respond with ONLY a JSON array of exactly {EXPECTED_SET_COUNT} objects, each shaped \
exactly like:
{{"label": "<short 2-4 word theme name>", "keywords": ["<kw1>", "<kw2>", "<kw3>"]}}

No prose, no markdown code fences, no explanation -- the raw JSON array only."""

KEYWORD_SETS_SCHEMA = {
    "type": "array",
    "minItems": EXPECTED_SET_COUNT,
    "maxItems": EXPECTED_SET_COUNT,
    "items": {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "keywords": {
                "type": "array",
                "minItems": KEYWORDS_PER_SET,
                "maxItems": KEYWORDS_PER_SET,
                "items": {"type": "string"},
            },
        },
        "required": ["label", "keywords"],
    },
}


def _build_user_prompt(paper: Paper) -> str:
    parts = [f"Title: {paper.title}"]
    if paper.abstract:
        parts.append(f"Abstract: {paper.abstract}")
    if paper.keywords:
        parts.append(f"Author-supplied keywords: {', '.join(paper.keywords)}")
    return "\n".join(parts)


def _extract_json_array(text: str) -> str:
    """Even with a schema-constrained `format`, local models occasionally
    wrap output in a markdown code fence or add a stray sentence -- strip a
    fence if present, and fall back to the first [...] span in the text as
    a last resort.
    """
    stripped = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    array_match = re.search(r"\[.*\]", stripped, re.DOTALL)
    return array_match.group(0) if array_match else stripped


def generate_keyword_sets(
    paper: Paper, *, base_url: str = "http://localhost:11434", model: str = "llama3.1"
) -> list[KeywordSet]:
    """Calls a local Ollama server to decompose a paper into 5 distinct
    3-keyword search angles. Raises RuntimeError on any connection or
    parsing/validation failure -- unlike email discovery or Semantic
    Scholar cross-checks, this is not a best-effort enrichment step; the
    whole search has nothing to search for without it, so failures must be
    loud rather than silently proceeding with fewer/malformed sets.
    """
    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(paper)},
                ],
                "stream": False,
                "format": KEYWORD_SETS_SCHEMA,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.ConnectionError as e:
        raise RuntimeError(
            f"Couldn't reach Ollama at {base_url} -- is it running? Start it (the Ollama "
            f"app, or `ollama serve`) and make sure the '{model}' model is pulled "
            f"(`ollama pull {model}`)."
        ) from e
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e

    raw_text = resp.json().get("message", {}).get("content", "")

    try:
        parsed = json.loads(_extract_json_array(raw_text))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ollama's keyword-set response wasn't valid JSON: {raw_text!r}") from e

    if not isinstance(parsed, list) or len(parsed) != EXPECTED_SET_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_SET_COUNT} keyword sets, got: {parsed!r}"
        )

    keyword_sets: list[KeywordSet] = []
    for i, item in enumerate(parsed, start=1):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("label"), str)
            or not isinstance(item.get("keywords"), list)
            or len(item["keywords"]) != KEYWORDS_PER_SET
            or not all(isinstance(k, str) for k in item["keywords"])
        ):
            raise RuntimeError(f"Malformed keyword set at position {i}: {item!r}")
        keyword_sets.append(KeywordSet(set_index=i, label=item["label"], keywords=item["keywords"]))

    return keyword_sets
