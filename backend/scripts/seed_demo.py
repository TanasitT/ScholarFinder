"""Load a small, fully fictional demo dataset so the web UI can be browsed with
no API keys and no Ollama.

    cd backend
    python scripts/seed_demo.py            # writes to data/reviewerfinder.db
    python scripts/seed_demo.py --db /tmp/demo.db

Everything here is invented: the paper, the scholars, their metrics, and the
`@example.org` addresses. Eligibility is NOT hard-coded -- each scholar is run
through the real rule engine (`rules/filters.py`, `rules/zones.py`) and the
real ranking function, so the demo shows genuine pass/fail decisions and
their reasons.

The script is idempotent: if the demo paper already exists it exits without
touching the database.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
for extra in (BACKEND_DIR, BACKEND_DIR / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from config.settings import DB_PATH  # noqa: E402
from reviewerfinder.db.connection import init_db  # noqa: E402
from reviewerfinder.db.repository import (  # noqa: E402
    KeywordSetRepository,
    MatchRepository,
    PaperRepository,
    ScholarRepository,
)
from reviewerfinder.models import (  # noqa: E402
    EmailVerificationStatus,
    InstitutionType,
    KeywordSet,
    Paper,
    ProfileConfirmationStatus,
    ResearchTopic,
    Scholar,
)
from reviewerfinder.rules.filters import passes_all_hard_rules  # noqa: E402
from reviewerfinder.rules.ranking import relevance_score  # noqa: E402
from reviewerfinder.rules.zones import zone_of  # noqa: E402

DEMO_TITLE = "Graph neural networks for early detection of crop disease from satellite imagery"

DEMO_PAPER = Paper(
    title=DEMO_TITLE,
    abstract=(
        "We propose a graph neural network that models field parcels as nodes and "
        "spatial adjacency as edges to detect crop disease outbreaks weeks earlier "
        "than vegetation-index baselines, using multispectral satellite imagery."
    ),
    keywords=["graph neural network", "crop disease", "remote sensing"],
    run_date=date(2026, 9, 1),
    notes="Fictional demo paper created by scripts/seed_demo.py",
)

DEMO_KEYWORD_SETS = [
    ("Methodology", ["graph neural network", "message passing", "spatial graph"]),
    ("Application domain", ["crop disease", "precision agriculture", "plant pathology"]),
    ("Data source", ["remote sensing", "multispectral imagery", "satellite"]),
    ("Early detection", ["anomaly detection", "outbreak prediction", "time series"]),
    ("Baselines", ["vegetation index", "random forest", "convolutional network"]),
]

# (id, name, country, institution, inst_type, h_index, recent_papers, has_email, [(topic, share)], [set indices 1-5])
_E = InstitutionType.EDUCATION
_C = InstitutionType.COMPANY
DEMO_SCHOLARS = [
    ("DEMO-001", "Dr. Ada Example", "DE", "Example University of Technology", _E, 24, 19, True,
     [("graph neural network", 0.6), ("spatial graph", 0.3)], [1, 3]),
    ("DEMO-002", "Dr. Bo Sample", "NL", "Sample Agricultural University", _E, 31, 27, True,
     [("crop disease", 0.5), ("precision agriculture", 0.4)], [2, 3]),
    ("DEMO-003", "Dr. Chiara Placeholder", "IT", "Placeholder Institute of Remote Sensing", _E, 18, 12, True,
     [("remote sensing", 0.7), ("multispectral imagery", 0.2)], [3, 4]),
    ("DEMO-004", "Dr. Dmitri Mockson", "KR", "Mockson National University", _E, 9, 10, True,
     [("anomaly detection", 0.5), ("time series", 0.4)], [4]),
    ("DEMO-005", "Dr. Elena Testova", "SE", "Testova Plant Science Centre", _E, 15, 14, True,
     [("plant pathology", 0.6), ("crop disease", 0.3)], [2]),
    # Deliberate rejections, so the UI shows fail reasons:
    ("DEMO-006", "Dr. Farid Corporate", "US", "Corporate AI Labs Inc.", _C, 28, 22, True,
     [("graph neural network", 0.8)], [1]),
    ("DEMO-007", "Dr. Greta Newcomer", "FR", "Newcomer Institute", _E, 3, 9, True,
     [("random forest", 0.5), ("vegetation index", 0.4)], [5]),
    ("DEMO-008", "Dr. Hana Unlisted", "ZZ", "Unlisted Country University", _E, 22, 20, True,
     [("convolutional network", 0.6)], [5]),
    ("DEMO-009", "Dr. Ivo Noemail", "CH", "Noemail Federal Institute", _E, 20, 16, False,
     [("time series", 0.5), ("outbreak prediction", 0.4)], [4, 5]),
]


def _build_scholar(row: tuple) -> Scholar:
    sid, name, country, inst, inst_type, h_index, recent, has_email, topics, _sets = row
    now = datetime.now()
    return Scholar(
        id=sid,
        display_name=name,
        orcid=f"0000-0000-0000-{sid[-4:].zfill(4)}",
        h_index=h_index,
        h_index_source="manual",
        works_count_total=recent * 3,
        works_count_last_5y=recent,
        current_institution_name=inst,
        current_institution_country_code=country,
        current_institution_type=inst_type,
        zone=zone_of(country),
        research_topics=[ResearchTopic(topic=t, share=s) for t, s in topics],
        email=f"{name.split()[-1].lower()}@example.org" if has_email else None,
        email_verification_status=(
            EmailVerificationStatus.UNVERIFIED if has_email else EmailVerificationStatus.NOT_FOUND
        ),
        email_source="demo-data" if has_email else None,
        email_checked_at=now if has_email else None,
        profile_confirmation_status=ProfileConfirmationStatus.CONFIRMED_VIA_ORCID,
        last_checked_at=now,
    )


def seed(db_path: Path) -> bool:
    """Returns True if data was written, False if the demo paper already exists."""
    init_db(db_path)
    papers = PaperRepository(db_path)
    if papers.find_by_title(DEMO_TITLE) is not None:
        return False

    paper = papers.create(DEMO_PAPER.model_copy(deep=True))
    keyword_sets = KeywordSetRepository(db_path)
    scholars = ScholarRepository(db_path)
    matches = MatchRepository(db_path)

    saved_sets = {}
    for index, (label, keywords) in enumerate(DEMO_KEYWORD_SETS, start=1):
        saved_sets[index] = keyword_sets.create(
            KeywordSet(paper_id=paper.id, set_index=index, label=label, keywords=keywords)
        )

    built = {row[0]: (_build_scholar(row), row[-1]) for row in DEMO_SCHOLARS}
    for scholar, _ in built.values():
        scholars.upsert(scholar)

    for set_index, kset in saved_sets.items():
        members = [s for s, sets in built.values() if set_index in sets]
        evaluated = []
        for scholar in members:
            passed, reasons = passes_all_hard_rules(scholar, check_email=True)
            evaluated.append((scholar, passed, reasons, relevance_score(paper, scholar)))
        # Passers first (by relevance), then rejected ones, mirroring what the pipeline stores.
        evaluated.sort(key=lambda e: (not e[1], -e[3]))
        rank = 0
        for scholar, passed, reasons, score in evaluated:
            rank_position = None
            if passed:
                rank += 1
                rank_position = rank
            matches.record_match(
                paper_id=paper.id,
                scholar_id=scholar.id,
                relevance_score=score,
                passed_hard_rules=passed,
                fail_reasons=reasons,
                rank_position=rank_position,
                keyword_set_id=kset.id,
            )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite file (default: {DB_PATH})")
    args = parser.parse_args()

    if seed(args.db):
        print(f"Seeded demo data into {args.db}")
        print("Start the API and UI, then open the 'Past papers' page.")
    else:
        print(f"Demo paper already present in {args.db}; nothing changed.")


if __name__ == "__main__":
    main()
