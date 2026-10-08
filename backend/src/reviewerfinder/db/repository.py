from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from reviewerfinder.db.connection import connect
from reviewerfinder.models import (
    AffiliationRecord,
    EmailVerificationStatus,
    InstitutionType,
    KeywordSet,
    Paper,
    ProfileConfirmationStatus,
    ResearchTopic,
    Scholar,
    Zone,
)

logger = logging.getLogger(__name__)


def _paper_from_row(row: dict) -> Paper:
    return Paper(
        id=row["id"],
        title=row["title"],
        abstract=row["abstract"],
        keywords=json.loads(row["keywords_json"] or "[]"),
        run_date=date.fromisoformat(row["run_date"]),
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
    )


def _scholar_from_row(row: dict) -> Scholar:
    return Scholar(
        id=row["id"],
        display_name=row["display_name"],
        orcid=row["orcid"],
        openalex_id=row["openalex_id"],
        semantic_scholar_id=row["semantic_scholar_id"],
        h_index=row["h_index"],
        h_index_source=row["h_index_source"],
        works_count_total=row["works_count_total"],
        works_count_last_5y=row["works_count_last_5y"],
        current_institution_name=row["current_institution_name"],
        current_institution_country_code=row["current_institution_country_code"],
        current_institution_type=InstitutionType(row["current_institution_type"]),
        zone=Zone(row["zone"]),
        research_topics=[ResearchTopic(**t) for t in json.loads(row["research_topics_json"] or "[]")],
        email=row["email"],
        email_verification_status=EmailVerificationStatus(row["email_verification_status"]),
        email_source=row["email_source"],
        email_checked_at=datetime.fromisoformat(row["email_checked_at"]) if row["email_checked_at"] else None,
        gscholar_search_url=row["gscholar_search_url"],
        scopus_search_url=row["scopus_search_url"],
        profile_confirmation_status=ProfileConfirmationStatus(row["profile_confirmation_status"]),
        last_checked_at=datetime.fromisoformat(row["last_checked_at"]) if row["last_checked_at"] else None,
        raw_openalex_json=row["raw_openalex_json"],
        raw_s2_json=row["raw_s2_json"],
    )


def _keyword_set_from_row(row: dict) -> KeywordSet:
    return KeywordSet(
        id=row["id"],
        paper_id=row["paper_id"],
        set_index=row["set_index"],
        label=row["label"],
        keywords=json.loads(row["keywords_json"]),
        source=row["source"],
    )


class PaperRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def create(self, paper: Paper) -> Paper:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO papers (title, abstract, keywords_json, run_date, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    paper.title,
                    paper.abstract,
                    json.dumps(paper.keywords),
                    paper.run_date.isoformat(),
                    paper.notes,
                ),
            )
            paper.id = cur.lastrowid
            return paper

    def get(self, paper_id: int) -> Paper | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            return _paper_from_row(row) if row else None

    def find_by_title(self, title: str) -> Paper | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM papers WHERE title = ? ORDER BY id DESC LIMIT 1", (title,)
            ).fetchone()
            return _paper_from_row(row) if row else None

    def list_all(self) -> list[Paper]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM papers ORDER BY id DESC").fetchall()
            return [_paper_from_row(r) for r in rows]


class KeywordSetRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def create(self, keyword_set: KeywordSet) -> KeywordSet:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO keyword_sets (paper_id, set_index, label, keywords_json, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    keyword_set.paper_id,
                    keyword_set.set_index,
                    keyword_set.label,
                    json.dumps(keyword_set.keywords),
                    keyword_set.source,
                ),
            )
            keyword_set.id = cur.lastrowid
            return keyword_set

    def list_for_paper(self, paper_id: int) -> list[KeywordSet]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM keyword_sets WHERE paper_id = ? ORDER BY set_index ASC", (paper_id,)
            ).fetchall()
            return [_keyword_set_from_row(r) for r in rows]

    def get(self, keyword_set_id: int) -> KeywordSet | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM keyword_sets WHERE id = ?", (keyword_set_id,)).fetchone()
            return _keyword_set_from_row(row) if row else None


class ScholarRepository:
    def __init__(self, db_path: Path, staleness_months: int = 6):
        self.db_path = db_path
        self.staleness_months = staleness_months

    def get(self, scholar_id: str) -> Scholar | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM scholars WHERE id = ?", (scholar_id,)).fetchone()
            return _scholar_from_row(row) if row else None

    def is_stale(self, scholar: Scholar) -> bool:
        if scholar.last_checked_at is None:
            return True
        cutoff = datetime.now() - timedelta(days=30 * self.staleness_months)
        return scholar.last_checked_at < cutoff

    def upsert(self, scholar: Scholar) -> Scholar:
        scholar.last_checked_at = scholar.last_checked_at or datetime.now()
        with connect(self.db_path) as conn:
            try:
                self._upsert_row(conn, scholar)
            except sqlite3.IntegrityError as e:
                if "semantic_scholar_id" in str(e) and scholar.semantic_scholar_id is not None:
                    # Semantic Scholar cross-check matches by fuzzy display-name
                    # search (enrichment.py::_best_name_match), so two distinct
                    # OpenAlex scholars can occasionally resolve to the same S2
                    # author id -- the UNIQUE constraint then rejects the second
                    # one. OpenAlex's id is our authoritative identity; drop the
                    # S2 cross-reference rather than losing the whole scholar
                    # (and, upstream, the whole search that was enriching them).
                    logger.warning(
                        "semantic_scholar_id %s already claimed by another scholar -- "
                        "saving %s (%s) without the S2 cross-reference",
                        scholar.semantic_scholar_id,
                        scholar.id,
                        scholar.display_name,
                    )
                    scholar.semantic_scholar_id = None
                    self._upsert_row(conn, scholar)
                else:
                    raise
        return scholar

    def _upsert_row(self, conn: sqlite3.Connection, scholar: Scholar) -> None:
        conn.execute(
            """
            INSERT INTO scholars (
                id, display_name, orcid, openalex_id, semantic_scholar_id,
                h_index, h_index_source, works_count_total, works_count_last_5y,
                current_institution_name, current_institution_country_code,
                current_institution_type, zone, research_topics_json,
                email, email_verification_status, email_source, email_checked_at,
                gscholar_search_url, scopus_search_url, profile_confirmation_status,
                last_checked_at, raw_openalex_json, raw_s2_json, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, datetime('now')
            )
            ON CONFLICT(id) DO UPDATE SET
                display_name=excluded.display_name,
                orcid=excluded.orcid,
                openalex_id=excluded.openalex_id,
                semantic_scholar_id=excluded.semantic_scholar_id,
                h_index=excluded.h_index,
                h_index_source=excluded.h_index_source,
                works_count_total=excluded.works_count_total,
                works_count_last_5y=excluded.works_count_last_5y,
                current_institution_name=excluded.current_institution_name,
                current_institution_country_code=excluded.current_institution_country_code,
                current_institution_type=excluded.current_institution_type,
                zone=excluded.zone,
                research_topics_json=excluded.research_topics_json,
                email=excluded.email,
                email_verification_status=excluded.email_verification_status,
                email_source=excluded.email_source,
                email_checked_at=excluded.email_checked_at,
                gscholar_search_url=excluded.gscholar_search_url,
                scopus_search_url=excluded.scopus_search_url,
                profile_confirmation_status=excluded.profile_confirmation_status,
                last_checked_at=excluded.last_checked_at,
                raw_openalex_json=excluded.raw_openalex_json,
                raw_s2_json=excluded.raw_s2_json,
                updated_at=datetime('now')
            """,
            (
                scholar.id,
                scholar.display_name,
                scholar.orcid,
                scholar.openalex_id,
                scholar.semantic_scholar_id,
                scholar.h_index,
                scholar.h_index_source,
                scholar.works_count_total,
                scholar.works_count_last_5y,
                scholar.current_institution_name,
                scholar.current_institution_country_code,
                scholar.current_institution_type.value,
                scholar.zone.value,
                json.dumps([t.model_dump() for t in scholar.research_topics]),
                scholar.email,
                scholar.email_verification_status.value,
                scholar.email_source,
                scholar.email_checked_at.isoformat() if scholar.email_checked_at else None,
                scholar.gscholar_search_url,
                scholar.scopus_search_url,
                scholar.profile_confirmation_status.value,
                scholar.last_checked_at.isoformat() if scholar.last_checked_at else None,
                scholar.raw_openalex_json,
                scholar.raw_s2_json,
            ),
        )
        return scholar

    def replace_affiliation_history(self, scholar_id: str, history: list[AffiliationRecord]) -> None:
        with connect(self.db_path) as conn:
            conn.execute("DELETE FROM affiliation_history WHERE scholar_id = ?", (scholar_id,))
            for rec in history:
                conn.execute(
                    """
                    INSERT INTO affiliation_history
                        (scholar_id, institution_name, country_code, institution_type, year_start, year_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scholar_id,
                        rec.institution_name,
                        rec.country_code,
                        rec.institution_type.value,
                        rec.year_start,
                        rec.year_end,
                    ),
                )

    def list_all(self) -> list[Scholar]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM scholars").fetchall()
            return [_scholar_from_row(r) for r in rows]

    def list_stale(self) -> list[Scholar]:
        cutoff = (datetime.now() - timedelta(days=30 * self.staleness_months)).isoformat()
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scholars WHERE last_checked_at IS NULL OR last_checked_at < ?",
                (cutoff,),
            ).fetchall()
            return [_scholar_from_row(r) for r in rows]

    def summary_counts(self) -> dict:
        with connect(self.db_path) as conn:
            by_zone = conn.execute(
                "SELECT zone, COUNT(*) as n FROM scholars GROUP BY zone"
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) as n FROM scholars").fetchone()
            stale_cutoff = (datetime.now() - timedelta(days=30 * self.staleness_months)).isoformat()
            stale = conn.execute(
                "SELECT COUNT(*) as n FROM scholars WHERE last_checked_at IS NULL OR last_checked_at < ?",
                (stale_cutoff,),
            ).fetchone()
            return {
                "total": total["n"],
                "by_zone": {r["zone"]: r["n"] for r in by_zone},
                "stale": stale["n"],
            }


class MatchRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def record_match(
        self,
        paper_id: int,
        scholar_id: str,
        relevance_score: float,
        passed_hard_rules: bool,
        fail_reasons: list[str],
        rank_position: int | None,
        keyword_set_id: int | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO paper_scholar_matches
                    (paper_id, keyword_set_id, scholar_id, relevance_score, passed_hard_rules, fail_reasons_json, rank_position)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, keyword_set_id, scholar_id) DO UPDATE SET
                    relevance_score=excluded.relevance_score,
                    passed_hard_rules=excluded.passed_hard_rules,
                    fail_reasons_json=excluded.fail_reasons_json,
                    rank_position=excluded.rank_position
                """,
                (
                    paper_id,
                    keyword_set_id,
                    scholar_id,
                    relevance_score,
                    1 if passed_hard_rules else 0,
                    json.dumps(fail_reasons),
                    rank_position,
                ),
            )

    def top_candidates(self, paper_id: int, limit: int = 10) -> list[dict]:
        """All passing matches for a paper across every keyword set,
        ordered by rank within each set's own ranking (not a cross-set
        ranking -- use top_candidates_for_keyword_set for a single set's
        ordered top N, which is what the grouped UI actually shows).
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT m.*, s.display_name, s.email, s.email_verification_status,
                       s.current_institution_name, s.current_institution_country_code,
                       s.h_index, s.zone, s.research_topics_json,
                       s.gscholar_search_url, s.scopus_search_url, s.profile_confirmation_status
                FROM paper_scholar_matches m
                JOIN scholars s ON s.id = m.scholar_id
                WHERE m.paper_id = ? AND m.passed_hard_rules = 1
                ORDER BY m.keyword_set_id ASC, m.rank_position ASC
                LIMIT ?
                """,
                (paper_id, limit),
            ).fetchall()
            return rows

    def top_candidates_for_keyword_set(self, keyword_set_id: int, limit: int = 5) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT m.*, s.display_name, s.email, s.email_verification_status,
                       s.current_institution_name, s.current_institution_country_code,
                       s.h_index, s.zone, s.research_topics_json,
                       s.gscholar_search_url, s.scopus_search_url, s.profile_confirmation_status
                FROM paper_scholar_matches m
                JOIN scholars s ON s.id = m.scholar_id
                WHERE m.keyword_set_id = ? AND m.passed_hard_rules = 1
                ORDER BY m.rank_position ASC
                LIMIT ?
                """,
                (keyword_set_id, limit),
            ).fetchall()
            return rows

    def passing_count(self, paper_id: int) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM paper_scholar_matches WHERE paper_id = ? AND passed_hard_rules = 1",
                (paper_id,),
            ).fetchone()
            return row["n"]
