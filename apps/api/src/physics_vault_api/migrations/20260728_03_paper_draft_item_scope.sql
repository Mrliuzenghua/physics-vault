PRAGMA foreign_keys = OFF;

ALTER TABLE paper_draft_items RENAME TO paper_draft_items_old;

CREATE TABLE paper_draft_items (
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

INSERT OR IGNORE INTO paper_draft_items (
    item_id, draft_id, position, item_type, question_id, title,
    section_title, score, payload_json, created_at, updated_at
)
SELECT
    item_id, draft_id, position, item_type, question_id, title,
    section_title, score, payload_json, created_at, updated_at
FROM paper_draft_items_old;

DROP TABLE paper_draft_items_old;

CREATE INDEX IF NOT EXISTS idx_paper_draft_items_draft_position
ON paper_draft_items(draft_id, position);

CREATE INDEX IF NOT EXISTS idx_paper_draft_items_question
ON paper_draft_items(question_id);

PRAGMA foreign_keys = ON;

