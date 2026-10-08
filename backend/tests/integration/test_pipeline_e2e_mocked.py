import json
from pathlib import Path

import pytest

from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.db.connection import init_db
from reviewerfinder.models import EmailVerificationStatus, KeywordSet
from reviewerfinder.pipeline import run_search

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

OA_PAGE_URL = "https://example.edu/oa-landing-page"

# The mocked candidate-finder search always returns the same fixture works
# regardless of which keyword set's query text was actually sent (the fake
# is keyed on URL/params shape, not content), so each of the 5 keyword sets
# discovers the same 2 fixture authors.
FIXTURE_AUTHOR_COUNT = 2
KEYWORD_SET_COUNT = 5


def _fake_keyword_sets() -> list[KeywordSet]:
    return [
        KeywordSet(set_index=i, label=f"Angle {i}", keywords=[f"kw{i}a", f"kw{i}b", f"kw{i}c"])
        for i in range(1, KEYWORD_SET_COUNT + 1)
    ]


class JsonFakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ContentFakeResponse:
    def __init__(self, content: bytes, content_type: str = "text/html", status_code: int = 200):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def _make_fake_get(works_payload, author_payload, oa_html: bytes | None):
    def fake_get(url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/works"):
            if "filter" in params:
                # get_author_recent_works() -- used by email_hunter
                if oa_html is None:
                    return JsonFakeResponse({"results": []})
                return JsonFakeResponse(
                    {"results": [{"open_access": {"oa_url": OA_PAGE_URL}}]}
                )
            # candidate_finder's topical works search
            return JsonFakeResponse(works_payload)
        if url == OA_PAGE_URL:
            return ContentFakeResponse(oa_html, content_type="text/html")
        # any /authors/<id> lookup returns the same sample author for simplicity
        return JsonFakeResponse(author_payload)

    return fake_get


def test_run_search_end_to_end_mocked_discovers_email(mocker, db_path):
    mocker.patch("reviewerfinder.pipeline.generate_keyword_sets", return_value=_fake_keyword_sets())

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    oa_html = b"<html>Correspondence: jane.doe@mit.edu</html>"

    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(
        client.session, "get", side_effect=_make_fake_get(works_payload, author_payload, oa_html)
    )

    result = run_search(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        db_path=db_path,
        openalex_client=client,
        s2_client=None,
        max_openalex_pages=1,
    )

    assert result.paper.id is not None
    assert len(result.keyword_set_results) == KEYWORD_SET_COUNT
    # Every keyword set independently discovers the same 2 fixture authors.
    assert result.evaluated_count == FIXTURE_AUTHOR_COUNT * KEYWORD_SET_COUNT

    for set_result in result.keyword_set_results:
        assert len(set_result.passing_scholars) == FIXTURE_AUTHOR_COUNT
        for scholar, _score in set_result.passing_scholars:
            assert scholar.current_institution_country_code == "US"
            assert scholar.email == "jane.doe@mit.edu"
            assert scholar.email_verification_status == EmailVerificationStatus.UNVERIFIED
            assert scholar.email_source == f"openalex_oa:{OA_PAGE_URL}"

    # Flattened convenience property sums across every set.
    assert len(result.passing_scholars) == FIXTURE_AUTHOR_COUNT * KEYWORD_SET_COUNT


def test_run_search_end_to_end_mocked_excludes_scholars_with_no_discoverable_email(mocker, db_path):
    mocker.patch("reviewerfinder.pipeline.generate_keyword_sets", return_value=_fake_keyword_sets())

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())

    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(
        client.session, "get", side_effect=_make_fake_get(works_payload, author_payload, oa_html=None)
    )

    result = run_search(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        db_path=db_path,
        openalex_client=client,
        s2_client=None,
        max_openalex_pages=1,
    )

    # Core rules (zone/institution/pubs/h-index) still pass in every keyword
    # set, but with no OA works and no Semantic Scholar homepage, no email is
    # ever discovered -- so nobody makes any set's final ranked list.
    assert result.evaluated_count == FIXTURE_AUTHOR_COUNT * KEYWORD_SET_COUNT
    assert result.passing_scholars == []
    for set_result in result.keyword_set_results:
        assert set_result.passing_scholars == []


def test_run_search_survives_a_transient_error_during_one_scholars_email_hunt(mocker, db_path):
    """A live search once died mid-run on a single OpenAlex 504 Gateway
    Timeout while hunting one candidate's email, losing every result
    already found across earlier keyword sets. The email-hunt loop must
    catch and skip a single candidate's failure, same as the enrichment
    loop already does, rather than letting it sink the whole search.
    """
    mocker.patch("reviewerfinder.pipeline.generate_keyword_sets", return_value=_fake_keyword_sets())

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    oa_html = b"<html>Correspondence: jane.doe@mit.edu</html>"

    base_fake_get = _make_fake_get(works_payload, author_payload, oa_html)
    call_count = {"recent_works": 0}

    def flaky_fake_get(url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/works") and "filter" in params:
            call_count["recent_works"] += 1
            if call_count["recent_works"] == 1:
                raise RuntimeError("HTTP 504")
        return base_fake_get(url, params=params, timeout=timeout)

    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(client.session, "get", side_effect=flaky_fake_get)

    result = run_search(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        db_path=db_path,
        openalex_client=client,
        s2_client=None,
        max_openalex_pages=1,
    )

    # The whole search completes across all 5 keyword sets despite the very
    # first email-hunt call blowing up with a transient network error.
    assert len(result.keyword_set_results) == KEYWORD_SET_COUNT
    assert result.evaluated_count == FIXTURE_AUTHOR_COUNT * KEYWORD_SET_COUNT
    assert call_count["recent_works"] > 1


def test_run_search_with_manual_keyword_sets_skips_ollama(mocker, db_path):
    generate_mock = mocker.patch("reviewerfinder.pipeline.generate_keyword_sets")

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    oa_html = b"<html>Correspondence: jane.doe@mit.edu</html>"

    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(
        client.session, "get", side_effect=_make_fake_get(works_payload, author_payload, oa_html)
    )

    result = run_search(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        db_path=db_path,
        openalex_client=client,
        s2_client=None,
        max_openalex_pages=1,
        manual_keyword_sets=[["kw1a", "kw1b"], ["kw2a", "kw2b", "kw2c"]],
    )

    generate_mock.assert_not_called()
    assert len(result.keyword_set_results) == 2
    for i, set_result in enumerate(result.keyword_set_results, start=1):
        assert set_result.keyword_set.source == "manual"
        assert set_result.keyword_set.label == f"Manual set {i}"
        assert len(set_result.passing_scholars) == FIXTURE_AUTHOR_COUNT


def test_run_search_rejects_invalid_manual_keyword_sets(db_path):
    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")

    with pytest.raises(ValueError):
        run_search(
            title="T",
            abstract=None,
            keywords=[],
            db_path=db_path,
            openalex_client=client,
            s2_client=None,
            manual_keyword_sets=[],
        )

    with pytest.raises(ValueError):
        run_search(
            title="T",
            abstract=None,
            keywords=[],
            db_path=db_path,
            openalex_client=client,
            s2_client=None,
            manual_keyword_sets=[["   ", ""]],
        )


def test_run_search_excludes_candidates_outside_allowed_countries(mocker, db_path):
    mocker.patch("reviewerfinder.pipeline.generate_keyword_sets", return_value=_fake_keyword_sets())

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    oa_html = b"<html>Correspondence: jane.doe@mit.edu</html>"

    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(
        client.session, "get", side_effect=_make_fake_get(works_payload, author_payload, oa_html)
    )

    # The fixture author's country is "US" (asserted elsewhere in this file) --
    # excluding it should drop every candidate from every keyword set.
    result = run_search(
        title="Deep learning for protein structure prediction",
        abstract="We propose a transformer-based model for predicting protein folding.",
        keywords=["protein folding", "deep learning"],
        db_path=db_path,
        openalex_client=client,
        s2_client=None,
        max_openalex_pages=1,
        excluded_countries=["US"],
    )

    assert result.passing_scholars == []
    for set_result in result.keyword_set_results:
        assert set_result.passing_scholars == []
