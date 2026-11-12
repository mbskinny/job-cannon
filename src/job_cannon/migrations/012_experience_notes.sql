-- Interview prep experience notes: raw notes about the user's work (jobs, projects,
-- stories, numbers) that Claude draws on when drafting answers and cover letters.
CREATE TABLE experience_notes (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
