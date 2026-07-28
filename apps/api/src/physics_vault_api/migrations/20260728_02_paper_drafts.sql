CREATE TABLE IF NOT EXISTS paper_drafts (
    draft_id            TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    subtitle            TEXT,
    source              TEXT NOT NULL DEFAULT 'compose',
    status              TEXT NOT NULL DEFAULT 'draft',
    question_count      INTEGER NOT NULL DEFAULT 0,
    item_count          INTEGER NOT NULL DEFAULT 0,
    total_score         REAL NOT NULL DEFAULT 0,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    quality_report_json TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paper_draft_items (
    item_id       TEXT NOT NULL,
    draft_id      TEXT NOT NULL,
    position      INTEGER NOT NULL,
    item_type     TEXT NOT NULL,
    question_id   TEXT,
    title         TEXT,
    section_title TEXT,
    score         REAL,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_id, item_id),
    FOREIGN KEY (draft_id) REFERENCES paper_drafts(draft_id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS paper_draft_exports (
    export_id    TEXT PRIMARY KEY,
    draft_id     TEXT NOT NULL,
    export_type  TEXT NOT NULL,
    file_path    TEXT,
    options_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (draft_id) REFERENCES paper_drafts(draft_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_paper_drafts_updated
ON paper_drafts(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_draft_items_draft_position
ON paper_draft_items(draft_id, position);

CREATE INDEX IF NOT EXISTS idx_paper_draft_items_question
ON paper_draft_items(question_id);
