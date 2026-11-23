-- Tags on interview prep concepts. They share prep_tags with questions, so one
-- vocabulary ("databases", "system-design") covers both.
CREATE TABLE prep_concept_tags (
    concept_id  INTEGER NOT NULL REFERENCES prep_concepts(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES prep_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (concept_id, tag_id)
);
CREATE INDEX idx_prep_concept_tags_tag ON prep_concept_tags(tag_id);
