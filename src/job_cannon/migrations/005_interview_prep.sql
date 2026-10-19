-- Interview prep: a tagged question bank and practice answers (typed, or recorded and transcribed).
CREATE TABLE prep_questions (
    id          INTEGER PRIMARY KEY,
    prompt      TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE prep_tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE prep_question_tags (
    question_id  INTEGER NOT NULL REFERENCES prep_questions(id) ON DELETE CASCADE,
    tag_id       INTEGER NOT NULL REFERENCES prep_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, tag_id)
);

-- Audio recordings live in files/ under audio_stored_name; body is the typed text or the transcript.
CREATE TABLE prep_answers (
    id                 INTEGER PRIMARY KEY,
    question_id        INTEGER NOT NULL REFERENCES prep_questions(id) ON DELETE CASCADE,
    application_id     INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    mode               TEXT NOT NULL DEFAULT 'text' CHECK (mode IN ('text','voice')),
    body               TEXT NOT NULL DEFAULT '',
    audio_stored_name  TEXT UNIQUE,
    audio_mime         TEXT,
    duration_seconds   REAL,
    transcript_status  TEXT NOT NULL DEFAULT 'none' CHECK (transcript_status IN ('none','pending','done','failed')),
    best               INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX idx_prep_answers_question ON prep_answers(question_id);
CREATE INDEX idx_prep_answers_application ON prep_answers(application_id);
