# Job search profile

Read by the `find-jobs`, `tailor-cover-letter` and `answer-application-question`
skills. Each Job Cannon profile has its own copy: save it as `job-search.md` in the
profile's data folder (`uv run job-cannon profiles --json` prints the path) and fill
it in. The first profile may use `.claude/job-search.local.md` (gitignored) instead.

## Résumé

https://example.com/cv

A URL to fetch, or a path to a local file (PDF, Markdown, text). It is the
source of truth for facts about you.

## Notes

Anything the skills should know that the résumé doesn't say, for example
location preferences or commuting radius, citizenship or work permits, roles to
avoid, or a salary floor. Optional.

Conventions for the whole field (where to search, what makes a posting a fit,
how letters are written) belong in the sector guide, `.claude/sectors/<sector>.md`,
not here. Set the profile's sector on the Profiles page or with
`uv run job-cannon profiles sector <id> <sector>`. Use these notes for what is
personal, and for exceptions to the guide.
