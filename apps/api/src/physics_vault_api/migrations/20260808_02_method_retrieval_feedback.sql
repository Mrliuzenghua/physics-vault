CREATE TABLE IF NOT EXISTS method_retrieval_feedback (
    feedback_id    TEXT PRIMARY KEY,
    question_id    TEXT NOT NULL,
    method_id      TEXT NOT NULL,
    branch         TEXT NOT NULL,
    verdict        TEXT NOT NULL CHECK(verdict IN ('correct', 'incorrect', 'missed')),
    reason         TEXT,
    operator       TEXT NOT NULL DEFAULT 'teacher',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_method_retrieval_feedback_latest
ON method_retrieval_feedback(question_id, method_id, branch, created_at DESC, feedback_id DESC);

DROP TRIGGER IF EXISTS trg_method_feedback_index_ai;
CREATE TRIGGER trg_method_feedback_index_ai
AFTER INSERT ON method_retrieval_feedback
BEGIN
    DELETE FROM question_method_features
    WHERE question_id = new.question_id
      AND method_id = new.method_id
      AND branch = new.branch;
    DELETE FROM question_method_index_state WHERE question_id = new.question_id;
END;
