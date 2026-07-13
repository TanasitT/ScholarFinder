from datetime import date, datetime, timedelta

import pytest

from reviewerfinder.db.connection import init_db
from reviewerfinder.db.repository import (
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)
from reviewerfinder.models import InstitutionType, KeywordSet, Paper, Scholar, Zone


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def make_scholar(**overrides) -> Scholar:
    scholar_id = overrides.get("id", "A1")
    defaults = dict(
        id=scholar_id,
        display_name="Jane Doe",
        openalex_id=scholar_id,
        h_index=7,
        works_count_last_5y=10,
        current_institution_name="MIT",
        current_institution_country_code="US",
        current_institution_type=InstitutionType.EDUCATION,
        zone=Zone.ZONE_1,
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def test_paper_create_and_get(db_path):
    repo = PaperRepository(db_path)
    paper = repo.create(Paper(title="Test Paper", abstract="abc", keywords=["a", "b"], run_date=date.today()))
    assert paper.id is not None

    fetched = repo.get(paper.id)
    assert fetched.title == "Test Paper"
    assert fetched.keywords == ["a", "b"]


def test_keyword_set_create_and_list_for_paper(db_path):
    paper_repo = PaperRepository(db_path)
    keyword_set_repo = KeywordSetRepository(db_path)

    paper = paper_repo.create(Paper(title="P", run_date=date.today()))
    keyword_set_repo.create(KeywordSet(paper_id=paper.id, set_index=2, label="Second", keywords=["d", "e", "f"]))
    keyword_set_repo.create(KeywordSet(paper_id=paper.id, set_index=1, label="First", keywords=["a", "b", "c"]))

    sets = keyword_set_repo.list_for_paper(paper.id)

    assert [s.set_index for s in sets] == [1, 2]  # ordered by set_index, not insertion order
    assert sets[0].label == "First"
    assert sets[0].keywords == ["a", "b", "c"]


def test_keyword_set_get(db_path):
    paper_repo = PaperRepository(db_path)
    keyword_set_repo = KeywordSetRepository(db_path)
    paper = paper_repo.create(Paper(title="P", run_date=date.today()))

    created = keyword_set_repo.create(
        KeywordSet(paper_id=paper.id, set_index=1, label="Methodology", keywords=["a", "b", "c"])
    )

    fetched = keyword_set_repo.get(created.id)
    assert fetched.label == "Methodology"
    assert keyword_set_repo.get(999999) is None


def test_scholar_upsert_is_idempotent(db_path):
    repo = ScholarRepository(db_path)
    repo.upsert(make_scholar())
    repo.upsert(make_scholar(h_index=9))  # same id, updated field

    fetched = repo.get("A1")
    assert fetched.h_index == 9

    with repo.db_path.open("rb"):
        pass  # sanity: file exists

    import sqlite3

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM scholars").fetchone()[0]
    conn.close()
    assert count == 1


def test_scholar_upsert_survives_duplicate_semantic_scholar_id(db_path):
    """Regression test: Semantic Scholar cross-check matches by fuzzy name,
    so two distinct OpenAlex scholars can resolve to the same S2 author id.
    The UNIQUE constraint on semantic_scholar_id must not crash the whole
    search -- the second scholar should still save, just without the S2
    cross-reference.
    """
    repo = ScholarRepository(db_path)
    repo.upsert(make_scholar(id="A1", display_name="Wei Zhang", semantic_scholar_id="S2-123"))

    second = repo.upsert(make_scholar(id="A2", display_name="Wei Zhang", semantic_scholar_id="S2-123"))

    assert second.semantic_scholar_id is None
    first = repo.get("A1")
    assert first.semantic_scholar_id == "S2-123"  # untouched
    saved_second = repo.get("A2")
    assert saved_second is not None
    assert saved_second.semantic_scholar_id is None


def test_scholar_staleness(db_path):
    repo = ScholarRepository(db_path, staleness_months=6)

    fresh = make_scholar(id="A1", last_checked_at=datetime.now())
    stale = make_scholar(id="A2", last_checked_at=datetime.now() - timedelta(days=400))
    never_checked = make_scholar(id="A3", last_checked_at=None)

    assert repo.is_stale(fresh) is False
    assert repo.is_stale(stale) is True
    assert repo.is_stale(never_checked) is True


def test_list_stale(db_path):
    repo = ScholarRepository(db_path, staleness_months=6)
    repo.upsert(make_scholar(id="A1", last_checked_at=datetime.now()))
    repo.upsert(make_scholar(id="A2", last_checked_at=datetime.now() - timedelta(days=400)))

    stale = repo.list_stale()
    assert {s.id for s in stale} == {"A2"}


def test_match_repository_top_candidates_ordered(db_path):
    scholar_repo = ScholarRepository(db_path)
    paper_repo = PaperRepository(db_path)
    match_repo = MatchRepository(db_path)

    scholar_repo.upsert(make_scholar(id="A1", display_name="First"))
    scholar_repo.upsert(make_scholar(id="A2", display_name="Second"))
    paper = paper_repo.create(Paper(title="P", run_date=date.today()))

    match_repo.record_match(paper.id, "A2", relevance_score=0.9, passed_hard_rules=True, fail_reasons=[], rank_position=1)
    match_repo.record_match(paper.id, "A1", relevance_score=0.5, passed_hard_rules=True, fail_reasons=[], rank_position=2)

    top = match_repo.top_candidates(paper.id, limit=10)
    assert [row["scholar_id"] for row in top] == ["A2", "A1"]


def test_match_repository_upsert_updates_rank(db_path):
    scholar_repo = ScholarRepository(db_path)
    paper_repo = PaperRepository(db_path)
    keyword_set_repo = KeywordSetRepository(db_path)
    match_repo = MatchRepository(db_path)

    scholar_repo.upsert(make_scholar(id="A1"))
    paper = paper_repo.create(Paper(title="P", run_date=date.today()))
    # Real matches always belong to a keyword set -- the (paper_id,
    # keyword_set_id, scholar_id) unique constraint (not just paper_id,
    # scholar_id) is what upsert relies on here.
    ks = keyword_set_repo.create(
        KeywordSet(paper_id=paper.id, set_index=1, label="Test", keywords=["a", "b", "c"])
    )

    match_repo.record_match(paper.id, "A1", 0.1, True, [], rank_position=None, keyword_set_id=ks.id)
    match_repo.record_match(paper.id, "A1", 0.8, True, [], rank_position=1, keyword_set_id=ks.id)

    top = match_repo.top_candidates(paper.id, limit=10)
    assert len(top) == 1
    assert top[0]["relevance_score"] == 0.8


def test_match_repository_record_match_without_keyword_set_id_does_not_upsert(db_path):
    """Documents a real caveat: SQL UNIQUE treats NULL != NULL, so two
    record_match calls with no keyword_set_id are NOT deduplicated the way
    they would be with a real one. Not a bug to fix -- every real call site
    always supplies a keyword_set_id now; this just makes the caveat explicit
    rather than silently surprising someone later.
    """
    scholar_repo = ScholarRepository(db_path)
    paper_repo = PaperRepository(db_path)
    match_repo = MatchRepository(db_path)

    scholar_repo.upsert(make_scholar(id="A1"))
    paper = paper_repo.create(Paper(title="P", run_date=date.today()))

    match_repo.record_match(paper.id, "A1", 0.1, True, [], rank_position=None)
    match_repo.record_match(paper.id, "A1", 0.8, True, [], rank_position=1)

    top = match_repo.top_candidates(paper.id, limit=10)
    assert len(top) == 2
