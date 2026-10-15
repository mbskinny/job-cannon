CREATE TABLE cover_letter_templates (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    body        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- One working draft per application; the finished letter becomes an attachment.
CREATE TABLE cover_letters (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
    template_id     INTEGER REFERENCES cover_letter_templates(id) ON DELETE SET NULL,
    body            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
