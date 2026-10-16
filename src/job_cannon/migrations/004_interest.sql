-- Interest level per application: 1 (low) to 5 (high), NULL when unrated.
ALTER TABLE applications ADD COLUMN interest INTEGER CHECK (interest BETWEEN 1 AND 5);
