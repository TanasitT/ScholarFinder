import json
from pathlib import Path

import pytest

from reviewerfinder.clients.semantic_scholar import SemanticScholarClient

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
def author_payload():
    return json.loads((FIXTURES / "s2_author_sample.json").read_text())


def test_search_author_by_name_parses_fields(mocker, author_payload):
    client = SemanticScholarClient()
    mocker.patch.object(
        client.session, "get", return_value=FakeResponse({"data": [author_payload]})
    )

    results = client.search_author_by_name("Jane Doe")

    assert results[0]["authorId"] == "2000000001"
    assert results[0]["hIndex"] == 21
    assert results[0]["homepage"] == "https://janedoe.example.edu"


def test_get_author_returns_none_on_404(mocker):
    client = SemanticScholarClient()
    mocker.patch.object(client.session, "get", return_value=FakeResponse({}, status_code=404))

    assert client.get_author("missing") is None
