from __future__ import annotations

import re

from reviewerfinder.models import Paper, Scholar

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")

# Small stopword list; this is a lightweight keyword-overlap scorer, not
# meant to be a fully tuned IR ranking function. Good enough for ordering
# already-eligible candidates; upgrade to embeddings in Phase 4 if needed.
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "using",
    "based", "such", "which", "these", "those", "have", "has", "are", "was",
    "were", "can", "will", "not", "but", "our", "their", "its", "also",
}


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS}


def paper_keywords(paper: Paper) -> set[str]:
    tokens = _tokenize(paper.title) | _tokenize(paper.abstract)
    tokens |= {kw.lower() for kw in paper.keywords}
    return tokens


def relevance_score(paper: Paper, scholar: Scholar) -> float:
    """Topical relevance score used only for ordering passing candidates.

    Never used for pass/fail filtering (that's rules/filters.py). Jaccard
    overlap between the paper's keyword set and the scholar's research
    topics, weighted by each topic's `share`.
    """
    paper_tokens = paper_keywords(paper)
    if not paper_tokens or not scholar.research_topics:
        return 0.0

    score = 0.0
    for rt in scholar.research_topics:
        topic_tokens = _tokenize(rt.topic)
        if not topic_tokens:
            continue
        overlap = len(paper_tokens & topic_tokens) / len(paper_tokens | topic_tokens)
        score += overlap * (rt.share or 1.0)

    return score


def rank_scholars(paper: Paper, scholars: list[Scholar]) -> list[tuple[Scholar, float]]:
    """Sort scholars by descending relevance score to the paper."""
    scored = [(s, relevance_score(paper, s)) for s in scholars]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)
