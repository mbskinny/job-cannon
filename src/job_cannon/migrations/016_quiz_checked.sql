-- When a quiz question was last checked for accuracy (the audit-quiz-questions
-- skill). NULL = never checked; editing a question clears it, since the checked
-- wording is gone.
ALTER TABLE prep_quiz_questions ADD COLUMN checked_at TEXT;
