-- Interview prep answers can be marked as AI-generated drafts (written by Claude,
-- e.g. by the answer-application-question skill), instead of noting it in the text.
ALTER TABLE prep_answers ADD COLUMN ai_draft INTEGER NOT NULL DEFAULT 0;
