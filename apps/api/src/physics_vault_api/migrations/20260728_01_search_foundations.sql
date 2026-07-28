CREATE VIRTUAL TABLE IF NOT EXISTS question_search_fts USING fts5(
    question_id UNINDEXED,
    title,
    stem,
    answer,
    analysis,
    tags,
    source,
    tokenize = 'unicode61'
);

CREATE INDEX IF NOT EXISTS idx_questions_paper_no
ON questions(primary_paper_id, primary_question_no);

CREATE INDEX IF NOT EXISTS idx_questions_filter_combo
ON questions(status, question_type, difficulty);

CREATE INDEX IF NOT EXISTS idx_papers_filter_combo
ON papers(year, region, exam_type);

CREATE INDEX IF NOT EXISTS idx_review_queue_work
ON review_queue(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_favorite_items_browse
ON favorite_items(group_id, star_rating, added_at);

CREATE INDEX IF NOT EXISTS idx_qassets_question_order
ON question_assets(question_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_questions_mistake_recent
ON questions(is_mistake, updated_at)
WHERE is_mistake = 1;

DROP TRIGGER IF EXISTS trg_qti_fts_ai;
CREATE TRIGGER trg_qti_fts_ai
AFTER INSERT ON question_text_index
BEGIN
    DELETE FROM question_search_fts WHERE question_id = new.question_id;
    INSERT INTO question_search_fts(question_id, title, stem, answer, analysis, tags, source)
    SELECT
        new.question_id,
        COALESCE(new.title_text, q.canonical_title, ''),
        COALESCE(new.stem_clean_text, new.stem_text, ''),
        COALESCE(new.answer_text, ''),
        COALESCE(new.analysis_text, ''),
        COALESCE(new.tags_json, ''),
        COALESCE(new.source_text, q.source, q.primary_paper_id, '')
    FROM questions q
    WHERE q.question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qti_fts_au;
CREATE TRIGGER trg_qti_fts_au
AFTER UPDATE ON question_text_index
BEGIN
    DELETE FROM question_search_fts WHERE question_id = new.question_id;
    INSERT INTO question_search_fts(question_id, title, stem, answer, analysis, tags, source)
    SELECT
        new.question_id,
        COALESCE(new.title_text, q.canonical_title, ''),
        COALESCE(new.stem_clean_text, new.stem_text, ''),
        COALESCE(new.answer_text, ''),
        COALESCE(new.analysis_text, ''),
        COALESCE(new.tags_json, ''),
        COALESCE(new.source_text, q.source, q.primary_paper_id, '')
    FROM questions q
    WHERE q.question_id = new.question_id;
END;

DROP TRIGGER IF EXISTS trg_qti_fts_ad;
CREATE TRIGGER trg_qti_fts_ad
AFTER DELETE ON question_text_index
BEGIN
    DELETE FROM question_search_fts WHERE question_id = old.question_id;
END;

DROP TRIGGER IF EXISTS trg_questions_fts_au;
CREATE TRIGGER trg_questions_fts_au
AFTER UPDATE OF canonical_title, source, primary_paper_id ON questions
BEGIN
    DELETE FROM question_search_fts WHERE question_id = new.question_id;
    INSERT INTO question_search_fts(question_id, title, stem, answer, analysis, tags, source)
    SELECT
        q.question_id,
        COALESCE(qti.title_text, q.canonical_title, ''),
        COALESCE(qti.stem_clean_text, qti.stem_text, ''),
        COALESCE(qti.answer_text, ''),
        COALESCE(qti.analysis_text, ''),
        COALESCE(qti.tags_json, ''),
        COALESCE(qti.source_text, q.source, q.primary_paper_id, '')
    FROM questions q
    INNER JOIN question_text_index qti ON qti.question_id = q.question_id
    WHERE q.question_id = new.question_id;
END;

DELETE FROM question_search_fts;

INSERT INTO question_search_fts(question_id, title, stem, answer, analysis, tags, source)
SELECT
    q.question_id,
    COALESCE(qti.title_text, q.canonical_title, ''),
    COALESCE(qti.stem_clean_text, qti.stem_text, ''),
    COALESCE(qti.answer_text, ''),
    COALESCE(qti.analysis_text, ''),
    COALESCE(qti.tags_json, ''),
    COALESCE(qti.source_text, q.source, q.primary_paper_id, '')
FROM questions q
LEFT JOIN question_text_index qti ON qti.question_id = q.question_id;
