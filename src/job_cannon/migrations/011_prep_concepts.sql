-- Interview prep concepts: short explanations of things (a tool, a method, a domain idea)
-- worth rehearsing because they come up across several questions.
CREATE TABLE prep_concepts (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    explanation  TEXT NOT NULL DEFAULT '',
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE prep_question_concepts (
    question_id  INTEGER NOT NULL REFERENCES prep_questions(id) ON DELETE CASCADE,
    concept_id   INTEGER NOT NULL REFERENCES prep_concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, concept_id)
);
CREATE INDEX idx_prep_question_concepts_concept ON prep_question_concepts(concept_id);
