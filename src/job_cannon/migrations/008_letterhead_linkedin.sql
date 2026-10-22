-- LinkedIn gets its own field next to the website, so a letterhead can show
-- either or both. A LinkedIn address saved in the old combined field moves over.
ALTER TABLE letterhead ADD COLUMN linkedin TEXT NOT NULL DEFAULT '';
UPDATE letterhead SET linkedin = website, website = '' WHERE website LIKE '%linkedin.com%';
