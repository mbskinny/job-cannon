-- Contact details moved to the profile settings page; the Cover letters page
-- keeps the style: whether to print a letterhead at all, and the accent colour.
ALTER TABLE letterhead ADD COLUMN show_letterhead INTEGER NOT NULL DEFAULT 1 CHECK (show_letterhead IN (0, 1));
