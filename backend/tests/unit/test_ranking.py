from datetime import date

from reviewerfinder.models import Paper, ResearchTopic, Scholar
from reviewerfinder.rules.ranking import rank_scholars, relevance_score


def make_paper(**overrides) -> Paper:
    defaults = dict(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning", "transformers"],
        run_date=date.today(),
    )
    defaults.update(overrides)
    return Paper(**defaults)


def make_scholar(topics: list[str], **overrides) -> Scholar:
    defaults = dict(
        id="A1",
        display_name="Test Scholar",
        research_topics=[ResearchTopic(topic=t, share=1.0) for t in topics],
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def test_related_scholar_scores_higher_than_unrelated():
    paper = make_paper()
    related = make_scholar(["protein folding", "deep learning"])
    unrelated = make_scholar(["medieval poetry", "linguistics"])

    related_score = relevance_score(paper, related)
    unrelated_score = relevance_score(paper, unrelated)

    assert related_score > unrelated_score


def test_no_topics_scores_zero():
    paper = make_paper()
    scholar = make_scholar([])
    assert relevance_score(paper, scholar) == 0.0


def test_rank_scholars_orders_descending():
    paper = make_paper()
    related = make_scholar(["protein folding", "deep learning"], id="A1")
    unrelated = make_scholar(["medieval poetry"], id="A2")

    ranked = rank_scholars(paper, [unrelated, related])

    assert [s.id for s, _ in ranked] == ["A1", "A2"]
