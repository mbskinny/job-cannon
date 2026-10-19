-- Archived applications are hidden from the board, dashboard and list but kept
-- as a record (e.g. the posting closed before applying). NULL when active.
ALTER TABLE applications ADD COLUMN archived_at TEXT;
