PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    abstract TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    run_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scholars (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    orcid TEXT UNIQUE,
    openalex_id TEXT UNIQUE,
    semantic_scholar_id TEXT UNIQUE,

    h_index INTEGER,
    h_index_source TEXT,
    works_count_total INTEGER,
    works_count_last_5y INTEGER,

    current_institution_name TEXT,
    current_institution_country_code TEXT,
    current_institution_type TEXT NOT NULL DEFAULT 'unknown',
    zone TEXT NOT NULL DEFAULT 'excluded',

    research_topics_json TEXT NOT NULL DEFAULT '[]',

    email TEXT,
    email_verification_status TEXT NOT NULL DEFAULT 'not_found',
    email_source TEXT,
    email_checked_at TEXT,

    gscholar_search_url TEXT,
    scopus_search_url TEXT,
    profile_confirmation_status TEXT NOT NULL DEFAULT 'needs_review',

    last_checked_at TEXT,
    raw_openalex_json TEXT,
    raw_s2_json TEXT,

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS affiliation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholar_id TEXT NOT NULL REFERENCES scholars(id) ON DELETE CASCADE,
    institution_name TEXT NOT NULL,
    country_code TEXT,
    institution_type TEXT NOT NULL DEFAULT 'unknown',
    year_start INTEGER,
    year_end INTEGER
);

-- One paper is decomposed into 5 distinct 3-keyword search angles by
-- discovery/keyword_summarizer.py (Claude) -- see keyword_sets below.
CREATE TABLE IF NOT EXISTS keyword_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    set_index INTEGER NOT NULL,
    label TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (paper_id, set_index)
);

CREATE TABLE IF NOT EXISTS paper_scholar_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    keyword_set_id INTEGER REFERENCES keyword_sets(id) ON DELETE CASCADE,
    scholar_id TEXT NOT NULL REFERENCES scholars(id) ON DELETE CASCADE,
    relevance_score REAL NOT NULL DEFAULT 0.0,
    passed_hard_rules INTEGER NOT NULL DEFAULT 0,
    fail_reasons_json TEXT NOT NULL DEFAULT '[]',
    rank_position INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- A scholar can legitimately surface under more than one keyword set
    -- for the same paper (each set is an independent search), so the
    -- uniqueness key includes keyword_set_id, not just (paper_id, scholar_id).
    UNIQUE (paper_id, keyword_set_id, scholar_id)
);

CREATE INDEX IF NOT EXISTS idx_scholars_zone ON scholars(zone);
CREATE INDEX IF NOT EXISTS idx_scholars_country ON scholars(current_institution_country_code);
CREATE INDEX IF NOT EXISTS idx_scholars_last_checked ON scholars(last_checked_at);
CREATE INDEX IF NOT EXISTS idx_matches_paper ON paper_scholar_matches(paper_id);
CREATE INDEX IF NOT EXISTS idx_matches_keyword_set ON paper_scholar_matches(keyword_set_id);
CREATE INDEX IF NOT EXISTS idx_affiliation_scholar ON affiliation_history(scholar_id);
CREATE INDEX IF NOT EXISTS idx_keyword_sets_paper ON keyword_sets(paper_id);
