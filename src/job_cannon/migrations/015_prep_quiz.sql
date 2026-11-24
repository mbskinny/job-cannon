-- Multiple-choice quiz questions on interview prep concepts. Each belongs to one
-- concept (and goes with it); its topics are that concept's tags. The results are
-- kept as counters on the row, which is all the "focus on what I miss" mode needs.
CREATE TABLE prep_quiz_questions (
    id                INTEGER PRIMARY KEY,
    concept_id        INTEGER NOT NULL REFERENCES prep_concepts(id) ON DELETE CASCADE,
    prompt            TEXT NOT NULL,
    code              TEXT NOT NULL DEFAULT '',
    answer            TEXT NOT NULL,
    wrong_1           TEXT NOT NULL,
    wrong_2           TEXT NOT NULL,
    wrong_3           TEXT NOT NULL,
    explanation       TEXT NOT NULL DEFAULT '',
    right_count       INTEGER NOT NULL DEFAULT 0,
    wrong_count       INTEGER NOT NULL DEFAULT 0,
    last_correct      INTEGER,
    last_answered_at  TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX idx_prep_quiz_questions_concept ON prep_quiz_questions(concept_id);
