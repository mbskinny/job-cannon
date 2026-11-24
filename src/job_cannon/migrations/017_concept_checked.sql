-- When a prep concept's explanation and notes were last checked for accuracy (the
-- audit-concepts skill). NULL = never checked; editing the name, explanation or
-- notes clears it, since the checked text is gone. Tag changes keep it.
ALTER TABLE prep_concepts ADD COLUMN checked_at TEXT;
