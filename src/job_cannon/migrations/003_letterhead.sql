-- Single-row settings for cover letter PDFs: letterhead details and accent colour.
CREATE TABLE letterhead (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    name        TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    website     TEXT NOT NULL DEFAULT '',
    accent      TEXT NOT NULL DEFAULT '#184078',
    updated_at  TEXT NOT NULL
);
