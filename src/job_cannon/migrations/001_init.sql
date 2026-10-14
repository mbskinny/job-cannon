CREATE TABLE companies (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    website     TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE applications (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    role            TEXT NOT NULL,
    posting_url     TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    salary_range    TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'wishlist' CHECK (status IN
                        ('wishlist','applied','screening','interviewing','offer','rejected','withdrawn')),
    source          TEXT NOT NULL DEFAULT '',
    applied_on      TEXT,
    next_action     TEXT NOT NULL DEFAULT '',
    next_action_due TEXT,
    notes           TEXT NOT NULL DEFAULT '',
    position        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_applications_status ON applications(status, position);

CREATE TABLE contacts (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER REFERENCES companies(id),
    name        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    linkedin    TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE application_contacts (
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    contact_id     INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    role           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (application_id, contact_id)
);

CREATE TABLE interactions (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    contact_id      INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('email','call','interview','meeting','note')),
    occurred_at     TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    follow_up_due   TEXT,
    follow_up_done  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_interactions_followup ON interactions(follow_up_done, follow_up_due);

CREATE TABLE attachments (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'other' CHECK (kind IN ('resume','cover_letter','posting','other')),
    original_name   TEXT NOT NULL,
    stored_name     TEXT NOT NULL UNIQUE,
    mime            TEXT NOT NULL DEFAULT 'application/octet-stream',
    size            INTEGER NOT NULL DEFAULT 0,
    added_at        TEXT NOT NULL
);

CREATE TABLE status_history (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    changed_at      TEXT NOT NULL
);
