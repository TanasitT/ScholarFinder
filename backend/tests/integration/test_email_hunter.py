import json

import pytest

from reviewerfinder.clients.openalex import OpenAlexClient
from reviewerfinder.discovery.email_hunter import (
    find_email_from_openalex_works,
    find_email_from_semantic_scholar_homepage,
    hunt_email,
)
from reviewerfinder.models import EmailVerificationStatus, Scholar


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200, content_type: str = "text/html"):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _make_pdf_bytes(text: str) -> bytes:
    """Hand-build a minimal single-page PDF with `text` drawn on it, so
    email_hunter's PDF-extraction path can be tested without checking in a
    binary fixture file.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 300 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream_content = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
    objects.append(b"<< /Length %d >>\nstream\n" % len(stream_content) + stream_content + b"\nendstream")

    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode()
    return pdf


def make_scholar(**overrides) -> Scholar:
    defaults = dict(
        id="A1",
        display_name="Jane Doe",
        openalex_id="A1",
    )
    defaults.update(overrides)
    return Scholar(**defaults)


def test_find_email_from_openalex_works_html_page(mocker):
    scholar = make_scholar()
    client = OpenAlexClient(api_key="test-key")
    works = [{"open_access": {"oa_url": "https://example.edu/paper1"}}]
    mocker.patch.object(client, "get_author_recent_works", return_value=works)

    session = mocker.Mock()
    session.get.return_value = FakeResponse(
        b"<html>Contact the corresponding author: jane.doe@example.edu</html>",
        content_type="text/html",
    )

    email, source = find_email_from_openalex_works(scholar, client, session)

    assert email == "jane.doe@example.edu"
    assert source == "openalex_oa:https://example.edu/paper1"


def test_find_email_from_openalex_works_pdf(mocker):
    scholar = make_scholar()
    client = OpenAlexClient(api_key="test-key")
    works = [{"open_access": {"oa_url": "https://example.edu/paper1.pdf"}}]
    mocker.patch.object(client, "get_author_recent_works", return_value=works)

    pdf_bytes = _make_pdf_bytes("Correspondence: jane.doe@example.edu")
    session = mocker.Mock()
    session.get.return_value = FakeResponse(pdf_bytes, content_type="application/pdf")

    email, source = find_email_from_openalex_works(scholar, client, session)

    assert email == "jane.doe@example.edu"
    assert source == "openalex_oa:https://example.edu/paper1.pdf"


def test_find_email_from_openalex_works_prefers_personal_over_generic(mocker):
    scholar = make_scholar()
    client = OpenAlexClient(api_key="test-key")
    works = [{"open_access": {"oa_url": "https://example.edu/paper1"}}]
    mocker.patch.object(client, "get_author_recent_works", return_value=works)

    session = mocker.Mock()
    session.get.return_value = FakeResponse(
        b"<html>info@example.edu is the department office; "
        b"jane.doe@example.edu is the corresponding author.</html>",
        content_type="text/html",
    )

    email, _source = find_email_from_openalex_works(scholar, client, session)

    assert email == "jane.doe@example.edu"


def test_find_email_from_openalex_works_never_attributes_a_coauthors_email(mocker):
    """Regression test: a scraped page listing multiple people's emails
    (e.g. co-authors) must never have a non-matching one attributed to this
    scholar -- that's a correctness bug (a wrong contact), not a lesser
    version of "best effort found something".
    """
    scholar = make_scholar(display_name="James S. Fraser")
    client = OpenAlexClient(api_key="test-key")
    works = [{"open_access": {"oa_url": "https://example.edu/paper1"}}]
    mocker.patch.object(client, "get_author_recent_works", return_value=works)

    session = mocker.Mock()
    session.get.return_value = FakeResponse(
        b"<html>For correspondence contact erik.andersen@gmail.com "
        b"(co-author). James Fraser did not list a direct email here.</html>",
        content_type="text/html",
    )

    email, source = find_email_from_openalex_works(scholar, client, session)

    assert email is None
    assert source is None


def test_find_email_from_openalex_works_no_oa_links_returns_none(mocker):
    scholar = make_scholar()
    client = OpenAlexClient(api_key="test-key")
    mocker.patch.object(client, "get_author_recent_works", return_value=[{"open_access": {}}])

    session = mocker.Mock()
    email, source = find_email_from_openalex_works(scholar, client, session)

    assert email is None
    assert source is None
    session.get.assert_not_called()


def test_find_email_from_semantic_scholar_homepage(mocker):
    scholar = make_scholar(raw_s2_json=json.dumps({"homepage": "https://janedoe.example.edu"}))

    session = mocker.Mock()
    session.get.return_value = FakeResponse(
        b"<html>Email me at jane@example.edu</html>", content_type="text/html"
    )

    email, source = find_email_from_semantic_scholar_homepage(scholar, session)

    assert email == "jane@example.edu"
    assert source == "semantic_scholar_homepage:https://janedoe.example.edu"


def test_homepage_from_raw_s2_missing_returns_none():
    from reviewerfinder.discovery.email_hunter import _homepage_from_raw_s2

    assert _homepage_from_raw_s2(None) is None
    assert _homepage_from_raw_s2("not json") is None
    assert _homepage_from_raw_s2(json.dumps({"name": "Jane Doe"})) is None


def test_hunt_email_falls_back_to_homepage_when_no_oa_email(mocker):
    scholar = make_scholar(raw_s2_json=json.dumps({"homepage": "https://janedoe.example.edu"}))
    client = OpenAlexClient(api_key="test-key")
    mocker.patch.object(client, "get_author_recent_works", return_value=[{"open_access": {}}])

    session = mocker.Mock()
    session.get.return_value = FakeResponse(
        b"<html>Email me at jane@example.edu</html>", content_type="text/html"
    )

    hunt_email(scholar, client, session)

    assert scholar.email == "jane@example.edu"
    assert scholar.email_verification_status == EmailVerificationStatus.UNVERIFIED
    assert scholar.email_checked_at is not None


def test_hunt_email_not_found_when_nothing_available(mocker):
    scholar = make_scholar(raw_s2_json=None)
    client = OpenAlexClient(api_key="test-key")
    mocker.patch.object(client, "get_author_recent_works", return_value=[])

    hunt_email(scholar, client)

    assert scholar.email is None
    assert scholar.email_verification_status == EmailVerificationStatus.NOT_FOUND
    assert scholar.email_checked_at is not None
