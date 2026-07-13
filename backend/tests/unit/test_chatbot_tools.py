import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from reviewerfinder.chatbot.tools import build_tools
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.db.connection import init_db
from reviewerfinder.db.repository import PaperRepository, ScholarRepository
from reviewerfinder.models import InstitutionType, Paper, Scholar, Zone
from reviewerfinder.rules.filters import passes_all_hard_rules

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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
        last_checked_at=datetime.now(),
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def make_paper(**overrides) -> Paper:
    defaults = dict(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        run_date=date.today(),
    )
    defaults.update(overrides)
    return Paper(**defaults)


def get_tool(tools, name):
    return next(t for t in tools if t.name == name)


def test_lookup_scholar_by_exact_id(db_path):
    ScholarRepository(db_path).upsert(make_scholar(id="A1", display_name="Jane Doe"))
    tools = build_tools(db_path, openalex_client=None)

    result = get_tool(tools, "lookup_scholar").invoke({"name_or_id": "A1"})

    assert result["display_name"] == "Jane Doe"


def test_lookup_scholar_by_fuzzy_name(db_path):
    ScholarRepository(db_path).upsert(make_scholar(id="A1", display_name="Jane Doe"))
    tools = build_tools(db_path, openalex_client=None)

    result = get_tool(tools, "lookup_scholar").invoke({"name_or_id": "jane doe"})

    assert result["id"] == "A1"


def test_lookup_scholar_no_match_returns_error(db_path):
    tools = build_tools(db_path, openalex_client=None)

    result = get_tool(tools, "lookup_scholar").invoke({"name_or_id": "nobody"})

    assert "error" in result


def test_lookup_paper_by_id_and_title(db_path):
    paper = PaperRepository(db_path).create(make_paper())
    tools = build_tools(db_path, openalex_client=None)
    lookup_paper = get_tool(tools, "lookup_paper")

    by_id = lookup_paper.invoke({"title_or_id": str(paper.id)})
    by_title = lookup_paper.invoke({"title_or_id": paper.title})

    assert by_id["title"] == paper.title
    assert by_title["id"] == paper.id


def test_lookup_paper_no_match_returns_error(db_path):
    tools = build_tools(db_path, openalex_client=None)

    result = get_tool(tools, "lookup_paper").invoke({"title_or_id": "nonexistent title"})

    assert "error" in result


def test_check_scholar_fit_matches_direct_rule_evaluation(db_path):
    scholar_repo = ScholarRepository(db_path)
    scholar = make_scholar()
    scholar_repo.upsert(scholar)
    paper = PaperRepository(db_path).create(make_paper())

    tools = build_tools(db_path, openalex_client=None)
    result = get_tool(tools, "check_scholar_fit").invoke(
        {"scholar_id": scholar.id, "paper_id": paper.id}
    )

    expected_passed, expected_reasons = passes_all_hard_rules(scholar, check_email=True)
    assert result["passed"] == expected_passed
    assert result["fail_reasons"] == expected_reasons


def test_check_scholar_fit_refreshes_stale_scholar_first(mocker, db_path):
    from reviewerfinder.models import EmailVerificationStatus

    # The fixture author's own embedded OpenAlex id is "A123456789" -- the
    # stored scholar must use that same id, since a real refresh always gets
    # back an object matching the id it was fetched by.
    scholar_repo = ScholarRepository(db_path, staleness_months=6)
    stale_scholar = make_scholar(
        id="A123456789",
        openalex_id="A123456789",
        h_index=1,  # will be overwritten by the refreshed fixture author (h_index=22)
        email="jane@mit.edu",  # previously discovered in Phase 2 -- must survive the refresh
        email_verification_status=EmailVerificationStatus.UNVERIFIED,
        last_checked_at=datetime.now() - timedelta(days=400),
    )
    scholar_repo.upsert(stale_scholar)
    paper = PaperRepository(db_path).create(make_paper())

    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    client = mocker.Mock(spec=OpenAlexClient)
    client.get_author.return_value = author_payload

    tools = build_tools(db_path, openalex_client=client, staleness_months=6)
    result = get_tool(tools, "check_scholar_fit").invoke(
        {"scholar_id": "A123456789", "paper_id": paper.id}
    )

    client.get_author.assert_called_once_with("A123456789")
    # h-index refreshed from 1 -> 22 (fixture) and the pre-existing email
    # carries over across the refresh, so every rule now passes.
    assert result["passed"] is True
    refreshed_scholar = scholar_repo.get("A123456789")
    assert refreshed_scholar.h_index == 22
    assert refreshed_scholar.email == "jane@mit.edu"


def test_check_scholar_fit_unknown_scholar_or_paper_returns_error(db_path):
    paper = PaperRepository(db_path).create(make_paper())
    tools = build_tools(db_path, openalex_client=None)
    check_scholar_fit = get_tool(tools, "check_scholar_fit")

    assert "error" in check_scholar_fit.invoke({"scholar_id": "missing", "paper_id": paper.id})
    assert "error" in check_scholar_fit.invoke({"scholar_id": "A1", "paper_id": 999999})


def test_list_top_candidates_returns_rank_order(db_path):
    scholar_repo = ScholarRepository(db_path)
    scholar_repo.upsert(make_scholar(id="A1", display_name="First"))
    scholar_repo.upsert(make_scholar(id="A2", display_name="Second"))
    paper = PaperRepository(db_path).create(make_paper())

    from reviewerfinder.db.repository import MatchRepository

    match_repo = MatchRepository(db_path)
    match_repo.record_match(paper.id, "A2", 0.9, True, [], rank_position=1)
    match_repo.record_match(paper.id, "A1", 0.5, True, [], rank_position=2)

    tools = build_tools(db_path, openalex_client=None)
    result = get_tool(tools, "list_top_candidates").invoke({"paper_id": paper.id, "limit": 10})

    assert [row["scholar_id"] for row in result] == ["A2", "A1"]


def test_search_new_candidates_calls_pipeline_with_stored_paper_fields(mocker, db_path):
    from reviewerfinder.models import KeywordSet

    paper = PaperRepository(db_path).create(make_paper())

    fake_set_result = mocker.Mock()
    fake_set_result.keyword_set = KeywordSet(
        id=1, paper_id=999, set_index=1, label="Methodology", keywords=["a", "b", "c"]
    )
    fake_set_result.passing_scholars = [(make_scholar(id="A1"), 0.8)]

    fake_result = mocker.Mock()
    fake_result.paper.id = 999
    fake_result.evaluated_count = 5
    fake_result.passing_scholars = [(make_scholar(id="A1"), 0.8)]
    fake_result.keyword_set_results = [fake_set_result]
    run_search_mock = mocker.patch(
        "reviewerfinder.chatbot.tools.run_search", return_value=fake_result
    )

    client = mocker.Mock(spec=OpenAlexClient)
    tools = build_tools(db_path, openalex_client=client, staleness_months=6)
    result = get_tool(tools, "search_new_candidates").invoke({"paper_id": paper.id})

    run_search_mock.assert_called_once()
    call_kwargs = run_search_mock.call_args.kwargs
    assert call_kwargs["title"] == paper.title
    assert call_kwargs["abstract"] == paper.abstract
    assert call_kwargs["keywords"] == paper.keywords
    assert "ollama_base_url" in call_kwargs
    assert "ollama_model" in call_kwargs
    assert result == {
        "new_paper_id": 999,
        "evaluated_count": 5,
        "passing_count": 1,
        "keyword_sets": [
            {"label": "Methodology", "keywords": ["a", "b", "c"], "scholar_ids": ["A1"]}
        ],
    }


def test_search_new_candidates_unknown_paper_returns_error(db_path):
    tools = build_tools(db_path, openalex_client=None)

    result = get_tool(tools, "search_new_candidates").invoke({"paper_id": 999999})

    assert "error" in result
