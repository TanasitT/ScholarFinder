import pytest
from fastapi.testclient import TestClient

from reviewerfinder.api.app import app
from reviewerfinder.api.deps import get_scholar_repository
from reviewerfinder.db.connection import init_db
from reviewerfinder.db.repository import ScholarRepository
from reviewerfinder.models import InstitutionType, Scholar, Zone


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def client(db_path):
    app.dependency_overrides[get_scholar_repository] = lambda: ScholarRepository(db_path)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_scholar(**overrides) -> Scholar:
    defaults = dict(
        id="A1",
        display_name="Jane Doe",
        openalex_id="A1",
        h_index=7,
        current_institution_name="MIT",
        current_institution_country_code="US",
        current_institution_type=InstitutionType.EDUCATION,
        zone=Zone.ZONE_1,
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def test_get_scholar(client, db_path):
    ScholarRepository(db_path).upsert(make_scholar())

    resp = client.get("/api/scholars/A1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Jane Doe"
    assert body["current_institution_name"] == "MIT"


def test_get_scholar_404(client):
    resp = client.get("/api/scholars/nonexistent")
    assert resp.status_code == 404
