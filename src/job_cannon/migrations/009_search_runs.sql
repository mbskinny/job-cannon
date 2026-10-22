-- Job searches started from the app: the find-jobs skill run by headless Claude
-- Code. Steps are newline-separated progress lines; the applications a run added
-- are those with an id above max_app_id_before.
CREATE TABLE search_runs (
    id                INTEGER PRIMARY KEY,
    status            TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','failed','cancelled')),
    job_count         INTEGER NOT NULL,
    focus             TEXT NOT NULL DEFAULT '',
    steps             TEXT NOT NULL DEFAULT '',
    report            TEXT NOT NULL DEFAULT '',
    error             TEXT NOT NULL DEFAULT '',
    max_app_id_before INTEGER NOT NULL DEFAULT 0,
    started_at        TEXT NOT NULL,
    finished_at       TEXT
);
