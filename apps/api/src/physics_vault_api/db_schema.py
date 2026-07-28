from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .database import connect_db
from .paths import default_backups_dir, default_db_path

SCHEMA_VERSION = "2026.07.v1"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS system_meta (
    meta_key     TEXT PRIMARY KEY,
    meta_value   TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_batches (
    import_batch_id   TEXT PRIMARY KEY,
    batch_name        TEXT,
    source_type       TEXT,
    source_path       TEXT,
    pipeline_mode     TEXT,
    status            TEXT NOT NULL DEFAULT 'created',
    total_files       INTEGER NOT NULL DEFAULT 0,
    total_questions   INTEGER NOT NULL DEFAULT 0,
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    year            INTEGER,
    exam_type       TEXT,
    region          TEXT,
    paper_name      TEXT NOT NULL,
    subject         TEXT NOT NULL DEFAULT 'PHY',
    source_path     TEXT,
    source_format   TEXT,
    status          TEXT NOT NULL DEFAULT 'structured',
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS questions (
    question_id          TEXT PRIMARY KEY,
    canonical_title      TEXT,
    vault_markdown_path  TEXT,
    module               TEXT,
    topic2               TEXT,
    topic3               TEXT,
    difficulty           INTEGER NOT NULL DEFAULT 0,
    question_type        TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT '待校对',
    review_status        TEXT NOT NULL DEFAULT 'parsed',
    review_comment       TEXT,
    has_media            INTEGER NOT NULL DEFAULT 0,
    primary_paper_id     TEXT,
    primary_question_no  INTEGER,
    import_batch_id      TEXT,
    origin_file          TEXT,
    origin_page          INTEGER,
    source               TEXT,
    model_type           TEXT,
    experiment_type      TEXT,
    content_hash         TEXT,
    schema_version       TEXT NOT NULL DEFAULT 'v2',
    is_mistake           INTEGER NOT NULL DEFAULT 0,
    mistake_marked_at    TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (primary_paper_id) REFERENCES papers(paper_id) ON DELETE SET NULL,
    FOREIGN KEY (import_batch_id) REFERENCES import_batches(import_batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_text_index (
    question_id              TEXT PRIMARY KEY,
    paper_id                 TEXT,
    source_id                TEXT,
    question_no              INTEGER,
    markdown_path            TEXT,
    title_text               TEXT,
    stem_text                TEXT NOT NULL DEFAULT '',
    stem_clean_text          TEXT,
    answer_text              TEXT,
    analysis_text            TEXT,
    tips_text                TEXT,
    options_json             TEXT NOT NULL DEFAULT '[]',
    sub_questions_json       TEXT NOT NULL DEFAULT '[]',
    figures_json             TEXT NOT NULL DEFAULT '[]',
    image_asset_ids_json     TEXT NOT NULL DEFAULT '[]',
    image_filenames_json     TEXT NOT NULL DEFAULT '[]',
    image_count              INTEGER NOT NULL DEFAULT 0,
    tags_json                TEXT NOT NULL DEFAULT '[]',
    source_text              TEXT,
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_sources (
    source_id         TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL,
    paper_id          TEXT,
    question_no       INTEGER,
    source_role       TEXT NOT NULL DEFAULT 'primary',
    source_label      TEXT,
    page_start        INTEGER,
    page_end          INTEGER,
    is_verified       INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS knowledge_points (
    topic3_id         TEXT PRIMARY KEY,
    topic3_name       TEXT NOT NULL,
    topic2_id         TEXT NOT NULL,
    topic2_name       TEXT NOT NULL,
    topic1_id         TEXT NOT NULL,
    topic1_name       TEXT NOT NULL,
    source_chapter    TEXT,
    status            TEXT NOT NULL DEFAULT 'active',
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS question_knowledge_points (
    link_id           TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL,
    topic3_id         TEXT NOT NULL,
    rank              INTEGER NOT NULL DEFAULT 1,
    source            TEXT NOT NULL DEFAULT 'manual',
    confidence        REAL NOT NULL DEFAULT 1.0,
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    FOREIGN KEY (topic3_id) REFERENCES knowledge_points(topic3_id) ON DELETE CASCADE,
    UNIQUE (question_id, rank),
    UNIQUE (question_id, topic3_id)
);

CREATE TABLE IF NOT EXISTS image_assets (
    asset_id             TEXT PRIMARY KEY,
    filename             TEXT NOT NULL,
    file_path            TEXT NOT NULL,
    paper_id             TEXT,
    question_id          TEXT,
    source_id            TEXT,
    mime_type            TEXT,
    width                INTEGER,
    height               INTEGER,
    file_size            INTEGER,
    sha256               TEXT,
    description          TEXT,
    extracted_text       TEXT,
    image_type           TEXT,
    binding_confidence   REAL,
    verified             INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE SET NULL,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_assets (
    link_id            TEXT PRIMARY KEY,
    question_id        TEXT NOT NULL,
    asset_id           TEXT NOT NULL,
    role               TEXT NOT NULL DEFAULT 'question_figure',
    sort_order         INTEGER NOT NULL DEFAULT 0,
    placeholder_key    TEXT,
    is_primary         INTEGER NOT NULL DEFAULT 0,
    is_verified        INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES image_assets(asset_id) ON DELETE CASCADE,
    UNIQUE (question_id, asset_id)
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_id         TEXT PRIMARY KEY,
    entity_type       TEXT NOT NULL DEFAULT 'question',
    entity_id         TEXT NOT NULL,
    queue_type        TEXT NOT NULL DEFAULT 'manual',
    status            TEXT NOT NULL DEFAULT 'pending',
    priority          INTEGER NOT NULL DEFAULT 0,
    reason            TEXT,
    payload_json      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS question_versions (
    version_id        TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL,
    version_number    INTEGER NOT NULL,
    snapshot_json     TEXT NOT NULL,
    change_summary    TEXT,
    modified_by       TEXT DEFAULT 'system',
    source            TEXT DEFAULT 'manual',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    UNIQUE (question_id, version_number)
);

CREATE TABLE IF NOT EXISTS question_annotations (
    annotation_id     TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL,
    annotation_type   TEXT NOT NULL DEFAULT 'text',
    content           TEXT NOT NULL DEFAULT '',
    anchor_start      INTEGER,
    anchor_end        INTEGER,
    anchor_text       TEXT,
    figure_uuid       TEXT,
    color             TEXT DEFAULT '#fbbf24',
    author            TEXT DEFAULT '教师',
    visibility        TEXT NOT NULL DEFAULT 'private',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS favorite_groups (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS favorite_items (
    question_id      TEXT PRIMARY KEY,
    group_id         TEXT,
    star_rating      INTEGER NOT NULL DEFAULT 0 CHECK(star_rating >= 0 AND star_rating <= 5),
    added_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES favorite_groups(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    parent_id        TEXT,
    type             TEXT NOT NULL DEFAULT 'directory',
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES collections(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS collection_questions (
    collection_id    TEXT NOT NULL,
    question_id      TEXT NOT NULL,
    added_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (collection_id, question_id),
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_cache (
    cache_key              TEXT PRIMARY KEY,
    knowledge_points_json  TEXT NOT NULL,
    style                  TEXT NOT NULL DEFAULT 'teacher_handout',
    length                 TEXT NOT NULL DEFAULT 'medium',
    title                  TEXT NOT NULL DEFAULT '',
    content                TEXT NOT NULL DEFAULT '',
    outline_json           TEXT NOT NULL DEFAULT '[]',
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processing_runs (
    run_id             TEXT PRIMARY KEY,
    pipeline_name      TEXT NOT NULL,
    pipeline_version   TEXT NOT NULL,
    paper_id           TEXT,
    question_id        TEXT,
    status             TEXT NOT NULL DEFAULT 'pending',
    started_at         TEXT,
    finished_at        TEXT,
    operator           TEXT,
    summary_json       TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE SET NULL,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id       TEXT PRIMARY KEY,
    owner_type         TEXT NOT NULL,
    owner_id           TEXT NOT NULL,
    vector_type        TEXT NOT NULL,
    model_name         TEXT NOT NULL,
    model_version      TEXT NOT NULL DEFAULT '',
    dimensions         INTEGER NOT NULL,
    content_hash       TEXT,
    vector_json        TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'ready',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_type, owner_id, vector_type, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_review_status ON questions(review_status);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_module ON questions(module);
CREATE INDEX IF NOT EXISTS idx_questions_topic2 ON questions(topic2);
CREATE INDEX IF NOT EXISTS idx_questions_topic3 ON questions(topic3);
CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(primary_paper_id);
CREATE INDEX IF NOT EXISTS idx_questions_batch ON questions(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_questions_mistake ON questions(is_mistake);

CREATE INDEX IF NOT EXISTS idx_qti_paper ON question_text_index(paper_id);
CREATE INDEX IF NOT EXISTS idx_qti_question_no ON question_text_index(question_no);
CREATE INDEX IF NOT EXISTS idx_qsources_question ON question_sources(question_id);
CREATE INDEX IF NOT EXISTS idx_qsources_paper ON question_sources(paper_id);
CREATE INDEX IF NOT EXISTS idx_kp_topic2 ON knowledge_points(topic2_id);
CREATE INDEX IF NOT EXISTS idx_kp_topic1 ON knowledge_points(topic1_id);
CREATE INDEX IF NOT EXISTS idx_qkp_question ON question_knowledge_points(question_id);
CREATE INDEX IF NOT EXISTS idx_qkp_topic3 ON question_knowledge_points(topic3_id);
CREATE INDEX IF NOT EXISTS idx_img_question ON image_assets(question_id);
CREATE INDEX IF NOT EXISTS idx_img_paper ON image_assets(paper_id);
CREATE INDEX IF NOT EXISTS idx_qassets_question ON question_assets(question_id);
CREATE INDEX IF NOT EXISTS idx_review_entity ON review_queue(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_qv_question_id ON question_versions(question_id);
CREATE INDEX IF NOT EXISTS idx_annotations_question ON question_annotations(question_id);
CREATE INDEX IF NOT EXISTS idx_collections_parent ON collections(parent_id);
CREATE INDEX IF NOT EXISTS idx_embedding_owner ON embeddings(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_processing_paper ON processing_runs(paper_id);
CREATE INDEX IF NOT EXISTS idx_processing_question ON processing_runs(question_id);

CREATE VIEW IF NOT EXISTS question_knowledge_points_view AS
SELECT
    qkp.link_id,
    qkp.question_id,
    qkp.rank,
    kp.topic1_id,
    kp.topic1_name,
    kp.topic2_id,
    kp.topic2_name,
    kp.topic3_id,
    kp.topic3_name,
    kp.source_chapter,
    qkp.source,
    qkp.confidence,
    qkp.note,
    qkp.created_at,
    qkp.updated_at
FROM question_knowledge_points qkp
INNER JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id;
"""


def ensure_database_parent(db_path: Path | None = None) -> Path:
    resolved = db_path or default_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def initialize_database(db_path: Path | str | None = None) -> Path:
    resolved = ensure_database_parent(Path(db_path) if db_path else None)
    with connect_db(resolved) as conn:
        conn.executescript(SCHEMA_SQL)
        apply_schema_migrations(conn)
        conn.execute(
            """
            INSERT INTO system_meta (meta_key, meta_value, updated_at)
            VALUES ('schema_version', ?, datetime('now'))
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value = excluded.meta_value,
                updated_at = excluded.updated_at
            """,
            (SCHEMA_VERSION,),
        )
        conn.commit()
    return resolved


def apply_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    if not MIGRATIONS_DIR.exists():
        return

    applied = {
        row["migration_id"]
        for row in conn.execute("SELECT migration_id FROM schema_migrations")
    }
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        migration_id = migration_file.stem
        if migration_id in applied:
            continue
        conn.executescript(migration_file.read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO schema_migrations (migration_id, applied_at)
            VALUES (?, datetime('now'))
            """,
            (migration_id,),
        )


def reset_database(
    db_path: Path | str | None = None,
    *,
    backup: bool = True,
    backup_dir: Path | str | None = None,
) -> tuple[Path, Path | None]:
    resolved = ensure_database_parent(Path(db_path) if db_path else None)
    backup_path: Path | None = None

    if resolved.exists():
        if backup:
            backups_root = Path(backup_dir) if backup_dir else default_backups_dir()
            backups_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = backups_root / f"{resolved.stem}-{timestamp}.sqlite3.bak"
            shutil.copy2(resolved, backup_path)
        resolved.unlink()

    initialize_database(resolved)
    return resolved, backup_path
