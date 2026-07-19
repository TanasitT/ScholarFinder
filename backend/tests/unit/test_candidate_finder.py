from datetime import date

from reviewerfinder.discovery.candidate_finder import build_search_query
from reviewerfinder.models import Paper


def make_paper(**overrides) -> Paper:
    defaults = dict(
        title="FD-GhostFaceNet: Frequency-Decoupled Ghost Modules for Lightweight Face Recognition",
        abstract="Deploying accurate face recognition models on resource-constrained devices "
        "remains a significant challenge. Ghost modules mitigate feature-map redundancy by "
        "synthesizing half of each feature map through inexpen-\nsive linear transformations.",
        keywords=["ghost modules", "frequency decoupling", "face recognition"],
        run_date=date.today(),
    )
    defaults.update(overrides)
    return Paper(**defaults)


def test_build_search_query_excludes_abstract_and_title():
    """A live search against a real paper returned zero OpenAlex results in
    every one of the 5 keyword sets, tracing back to the full abstract
    (with a PDF hard-wrap hyphenation artifact, "inexpen-\\nsive") being
    folded into every set's search query. Each keyword-set angle must
    search on its own 3 keywords only, never the title or abstract.
    """
    query = build_search_query(make_paper())

    assert "resource-constrained" not in query
    assert "inexpen" not in query
    assert "FD-GhostFaceNet" not in query
    assert query == "ghost modules frequency decoupling face recognition"


def test_build_search_query_falls_back_to_title_when_no_keywords():
    query = build_search_query(make_paper(keywords=[]))

    assert query == "FD-GhostFaceNet: Frequency-Decoupled Ghost Modules for Lightweight Face Recognition"
