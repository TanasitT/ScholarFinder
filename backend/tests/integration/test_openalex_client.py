import json
from pathlib import Path

import pytest

from reviewerfinder.clients.openalex import OpenAlexClient, extract_author_ids

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def works_payload():
    return json.loads((FIXTURES / "openalex_works_sample.json").read_text())


@pytest.fixture
def author_payload():
    return json.loads((FIXTURES / "openalex_author_sample.json").read_text())


def test_search_works_extracts_author_ids(mocker, works_payload):
    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mocker.patch.object(client.session, "get", return_value=FakeResponse(works_payload))

    works = client.search_works("protein folding deep learning", max_pages=1)
    author_ids = extract_author_ids(works)

    assert author_ids == {"A123456789", "A987654321"}


def test_search_works_semantic_extracts_author_ids(mocker, works_payload):
    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mock_get = mocker.patch.object(client.session, "get", return_value=FakeResponse(works_payload))

    works = client.search_works_semantic("protein folding deep learning", max_pages=2)
    author_ids = extract_author_ids(works)

    assert author_ids == {"A123456789", "A987654321"}
    # A short first page (fewer results than per_page) means there's nothing
    # more to fetch -- must not issue a second request.
    assert mock_get.call_count == 1
    sent_params = mock_get.call_args.kwargs["params"]
    assert sent_params["search.semantic"] == "protein folding deep learning"
    assert sent_params["page"] == 1
    assert "cursor" not in sent_params


def test_search_works_semantic_paginates_by_page_not_cursor(mocker):
    """OpenAlex's search.semantic has no cursor pagination (cursor=* returns
    a 400) -- confirmed live. A full page of results must trigger a second
    request using page=2, not a cursor.
    """
    full_page = {"results": [{"id": f"W{i}", "authorships": []} for i in range(50)]}
    short_page = {"results": [{"id": "W50", "authorships": []}]}
    client = OpenAlexClient(api_key="test-key", mailto="me@example.com")
    mock_get = mocker.patch.object(
        client.session, "get", side_effect=[FakeResponse(full_page), FakeResponse(short_page)]
    )

    works = client.search_works_semantic("deep learning", max_pages=2)

    assert len(works) == 51
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].kwargs["params"]["page"] == 1
    assert mock_get.call_args_list[1].kwargs["params"]["page"] == 2


def test_get_author_parses_fields(mocker, author_payload):
    client = OpenAlexClient(api_key="test-key")
    mocker.patch.object(client.session, "get", return_value=FakeResponse(author_payload))

    author = client.get_author("A123456789")

    assert author["display_name"] == "Jane Doe"
    assert author["summary_stats"]["h_index"] == 22
    assert author["last_known_institutions"][0]["country_code"] == "US"
    assert author["last_known_institutions"][0]["type"] == "education"


def test_get_author_returns_none_on_404(mocker):
    client = OpenAlexClient(api_key="test-key")
    mocker.patch.object(client.session, "get", return_value=FakeResponse({}, status_code=404))

    assert client.get_author("A_missing") is None
