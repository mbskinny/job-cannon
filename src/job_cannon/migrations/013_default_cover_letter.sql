-- One base letter can be the default: new drafts start from it and the
-- tailor-cover-letter skill uses it unless the user names another.
ALTER TABLE cover_letter_templates ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1));
CREATE UNIQUE INDEX cover_letter_templates_one_default ON cover_letter_templates (is_default) WHERE is_default = 1;
