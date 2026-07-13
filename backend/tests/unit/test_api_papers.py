import json
import time
from datetime import date
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from reviewerfinder.api.app import app
from reviewerfinder.api.deps import (
    check_ollama_reachable,
    get_db_path,
    get_keyword_set_repository,
    get_match_repository,
    get_openalex_client,
    get_paper_repository,
    get_scholar_repository,
    get_semantic_scholar_client,
)
from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.clients.semantic_scholar import SemanticScholarClient
from reviewerfinder.db.connection import init_db
from reviewerfinder.db.repository import (
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)
from reviewerfinder.models import InstitutionType, KeywordSet, Paper, Scholar, Zone

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
OA_PAGE_URL = "https://example.edu/oa-landing-page"
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


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def client(db_path, mocker):
    # get_db_path is overridden too (not just the repo getters) because
    # search_papers() takes db_path directly for pipeline.run_search() --
    # without this override it would silently write to the real database.
    app.dependency_overrides[get_db_path] = lambda: db_path
    app.dependency_overrides[get_paper_repository] = lambda: PaperRepository(db_path)
    app.dependency_overrides[get_keyword_set_repository] = lambda: KeywordSetRepository(db_path)
    app.dependency_overrides[get_scholar_repository] = lambda: ScholarRepository(db_path)
    app.dependency_overrides[get_match_repository] = lambda: MatchRepository(db_path)
    app.dependency_overrides[check_ollama_reachable] = lambda: None

    fake_openalex = OpenAlexClient(api_key="test-key")
    fake_s2 = SemanticScholarClient()
    app.dependency_overrides[get_openalex_client] = lambda: fake_openalex
    app.dependency_overrides[get_semantic_scholar_client] = lambda: fake_s2

    with TestClient(app) as test_client:
        test_client.fake_openalex = fake_openalex
        yield test_client

    app.dependency_overrides.clear()


def test_list_papers_empty(client):
    resp = client.get("/api/papers")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_papers_returns_passing_count(client, db_path):
    paper_repo = PaperRepository(db_path)
    scholar_repo = ScholarRepository(db_path)
    match_repo = MatchRepository(db_path)

    paper = paper_repo.create(Paper(title="Test Paper", run_date=date.today()))
    scholar_repo.upsert(make_scholar())
    match_repo.record_match(paper.id, "A1", 0.5, True, [], rank_position=1)

    resp = client.get("/api/papers")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Test Paper"
    assert body[0]["passing_count"] == 1


def test_get_paper_detail(client, db_path):
    paper_repo = PaperRepository(db_path)
    keyword_set_repo = KeywordSetRepository(db_path)
    scholar_repo = ScholarRepository(db_path)
    match_repo = MatchRepository(db_path)

    paper = paper_repo.create(Paper(title="Test Paper", run_date=date.today()))
    ks = keyword_set_repo.create(
        KeywordSet(paper_id=paper.id, set_index=1, label="Methodology", keywords=["a", "b", "c"])
    )
    scholar_repo.upsert(make_scholar())
    match_repo.record_match(paper.id, "A1", 0.5, True, [], rank_position=1, keyword_set_id=ks.id)

    resp = client.get(f"/api/papers/{paper.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper"]["title"] == "Test Paper"
    assert len(body["keyword_set_results"]) == 1
    set_result = body["keyword_set_results"][0]
    assert set_result["keyword_set"]["label"] == "Methodology"
    assert len(set_result["passing_scholars"]) == 1
    assert set_result["passing_scholars"][0]["scholar"]["display_name"] == "Jane Doe"


def test_get_paper_detail_404(client):
    resp = client.get("/api/papers/999999")
    assert resp.status_code == 404


def _poll_job(client, job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/papers/search/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_search_papers_runs_pipeline(client, mocker):
    mocker.patch("reviewerfinder.pipeline.generate_keyword_sets", return_value=_fake_keyword_sets())

    works_payload = json.loads((FIXTURES / "openalex_works_sample.json").read_text())
    author_payload = json.loads((FIXTURES / "openalex_author_sample.json").read_text())
    oa_html = b"<html>Correspondence: jane.doe@mit.edu</html>"

    def fake_get(url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/works"):
            if "filter" in params:
                return JsonFakeResponse({"results": [{"open_access": {"oa_url": OA_PAGE_URL}}]})
            return JsonFakeResponse(works_payload)
        if url == OA_PAGE_URL:
            return ContentFakeResponse(oa_html)
        return JsonFakeResponse(author_payload)

    client.fake_openalex.session.get = fake_get

    resp = client.post(
        "/api/papers/search",
        json={
            "title": "Deep Learning for Protein Structure Prediction",
            "abstract": "Transformer-based protein folding model.",
            "keywords": ["protein folding", "deep learning"],
            "max_pages": 1,
        },
    )

    # The endpoint returns immediately with a running job, not the result --
    # a real search can take minutes, so this can't be a single blocking call.
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "running"

    finished = _poll_job(client, job["job_id"])

    assert finished["status"] == "done"
    result = finished["result"]
    assert len(result["keyword_set_results"]) == KEYWORD_SET_COUNT
    assert result["evaluated_count"] == 2 * KEYWORD_SET_COUNT

    first_set = result["keyword_set_results"][0]
    assert len(first_set["passing_scholars"]) == 2
    assert first_set["passing_scholars"][0]["scholar"]["email"] == "jane.doe@mit.edu"


def test_search_job_unknown_id_returns_404(client):
    resp = client.get("/api/papers/search/nonexistent-job-id")
    assert resp.status_code == 404


def test_search_papers_without_openalex_key_returns_503(db_path):
    app.dependency_overrides[get_db_path] = lambda: db_path
    app.dependency_overrides[get_paper_repository] = lambda: PaperRepository(db_path)
    app.dependency_overrides[get_scholar_repository] = lambda: ScholarRepository(db_path)
    app.dependency_overrides[get_match_repository] = lambda: MatchRepository(db_path)
    app.dependency_overrides[check_ollama_reachable] = lambda: None
    app.dependency_overrides.pop(get_openalex_client, None)
    app.dependency_overrides.pop(get_semantic_scholar_client, None)

    with TestClient(app) as test_client:
        # Simulate a server with no OPENALEX_API_KEY configured directly,
        # rather than relying on the ambient environment/.env having no key --
        # api/app.py's lifespan sets this to None in exactly that situation.
        app.state.openalex_client = None

        resp = test_client.post(
            "/api/papers/search",
            json={"title": "Some paper", "keywords": []},
        )
        # get_openalex_client is a route dependency, resolved (and raising)
        # before start_search's body runs -- so this fails fast with 503
        # rather than creating a job that's doomed to error out.
        assert resp.status_code == 503

    app.dependency_overrides.clear()


def test_search_papers_with_ollama_unreachable_returns_503(db_path, mocker):
    # check_ollama_reachable makes a real HTTP call (there's no injectable
    # "client" for a local server the way there is for OpenAlex/S2), so
    # simulate it being down by making that GET raise a connection error.
    mocker.patch(
        "reviewerfinder.api.deps.requests.get",
        side_effect=requests.ConnectionError("connection refused"),
    )

    app.dependency_overrides[get_db_path] = lambda: db_path
    app.dependency_overrides[get_paper_repository] = lambda: PaperRepository(db_path)
    app.dependency_overrides[get_scholar_repository] = lambda: ScholarRepository(db_path)
    app.dependency_overrides[get_match_repository] = lambda: MatchRepository(db_path)
    app.dependency_overrides[get_openalex_client] = lambda: OpenAlexClient(api_key="test-key")
    app.dependency_overrides[get_semantic_scholar_client] = lambda: SemanticScholarClient()
    app.dependency_overrides.pop(check_ollama_reachable, None)

    with TestClient(app) as test_client:
        resp = test_client.post(
            "/api/papers/search",
            json={"title": "Some paper", "keywords": []},
        )
        assert resp.status_code == 503
        assert "Ollama" in resp.json()["detail"]

    app.dependency_overrides.clear()
