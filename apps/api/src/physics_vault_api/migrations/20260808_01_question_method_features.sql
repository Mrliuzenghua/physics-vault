CREATE TABLE IF NOT EXISTS question_method_features (
    question_id     TEXT NOT NULL,
    method_id       TEXT NOT NULL,
    branch          TEXT NOT NULL,
    level           TEXT NOT NULL CHECK(level IN ('explicit', 'structural', 'related')),
    score           REAL NOT NULL,
    match_basis     TEXT NOT NULL,
    evidence_json   TEXT NOT NULL DEFAULT '[]',
    index_version   TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (question_id, method_id, branch),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS question_method_index_state (
    question_id     TEXT PRIMARY KEY,
    content_hash    TEXT NOT NULL,
    index_version   TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_question_method_features_lookup
ON question_method_features(method_id, branch, level, score DESC, question_id);

DROP TRIGGER IF EXISTS trg_qti_method_index_ai;
CREATE TRIGGER trg_qti_method_index_ai
AFTER INSERT ON question_text_index
BEGIN
    DELETE FROM question_method_features WHERE question_id = new.question_id;
    DELETE FROM question_method_index_state WHERE question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qti_method_index_au;
CREATE TRIGGER trg_qti_method_index_au
AFTER UPDATE OF title_text, stem_text, stem_clean_text, answer_text, analysis_text, tags_json
ON question_text_index
BEGIN
    DELETE FROM question_method_features WHERE question_id = new.question_id;
    DELETE FROM question_method_index_state WHERE question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qti_method_index_ad;
CREATE TRIGGER trg_qti_method_index_ad
AFTER DELETE ON question_text_index
BEGIN
    DELETE FROM question_method_features WHERE question_id = old.question_id;
    DELETE FROM question_method_index_state WHERE question_id = old.question_id;
END;

DROP TRIGGER IF EXISTS trg_questions_method_index_au;
CREATE TRIGGER trg_questions_method_index_au
AFTER UPDATE OF canonical_title, module, topic2, topic3 ON questions
BEGIN
    DELETE FROM question_method_features WHERE question_id = new.question_id;
    DELETE FROM question_method_index_state WHERE question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qkp_method_index_ai;
CREATE TRIGGER trg_qkp_method_index_ai
AFTER INSERT ON question_knowledge_points
BEGIN
    DELETE FROM question_method_features WHERE question_id = new.question_id;
    DELETE FROM question_method_index_state WHERE question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qkp_method_index_au;
CREATE TRIGGER trg_qkp_method_index_au
AFTER UPDATE ON question_knowledge_points
BEGIN
    DELETE FROM question_method_features WHERE question_id IN (old.question_id, new.question_id);
    DELETE FROM question_method_index_state WHERE question_id IN (old.question_id, new.question_id);
END;

DROP TRIGGER IF EXISTS trg_qkp_method_index_ad;
CREATE TRIGGER trg_qkp_method_index_ad
AFTER DELETE ON question_knowledge_points
BEGIN
    DELETE FROM question_method_features WHERE question_id = old.question_id;
    DELETE FROM question_method_index_state WHERE question_id = old.question_id;
END;
