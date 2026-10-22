---
name: find-jobs
description: Find current job listings that match the user's résumé and add them to their Job Cannon tracker as wishlist applications. Use this whenever the user asks to find, search for, scout, or source jobs/roles/openings, wants "a few more listings", asks what's hiring that fits them, or asks to populate/fill their Job Cannon or board with real postings, even if they don't say "skill" or name a site.
---

# Find jobs and add them to Job Cannon

The goal is a short list (default 4-5, or whatever number the user asks for) of **open, verified** postings that genuinely fit the user, added to their real tracker with notes good enough to decide on without re-opening the posting.

## 1. Build the profile

First run `uv run job-cannon profiles --json` to get the active Job Cannon profile. Several people can share the install, each with their own tracker and résumé, so say which profile (`name`) you're working in. If the user means someone else, pass `--profile <id>` to every script below, and to `profiles --json`. Read the file at `job_search_file` for the résumé location and any notes. If it doesn't exist and the profile id is `default`, fall back to `.claude/job-search.local.md`. If neither exists, or it has no résumé, ask the user to fill in Job search notes in their profile settings (`http://127.0.0.1:8765/profiles/<id>#notes`), where they can also upload a résumé file, and stop until they have. Get the résumé from `resume` in `profiles --json` (it resolves relative paths and uploads; for the `.claude/job-search.local.md` fallback, read the location from that file): WebFetch a URL, Read a PDF, and run `uv run job-cannon resume-text` (with the same `--profile`) for a .docx, .odt, .txt or .md file. Then read the profile's **sector guide**, `.claude/sectors/<sector>.md` (`general.md` if `sector` is empty), and pull out what its *Profile cues* section lists. The guide holds everything specific to the person's field; the steps below say when to use each section. If `sector` is empty and the résumé makes the field obvious, offer to set it (`uv run job-cannon profiles sector <id> <sector>`, with a sector that has a guide). The résumé is the source of truth for facts about the user. The profile's notes can add preferences it doesn't state, and constraints in the request (salary floor, contract vs. employee, a specific domain) override both.

## 2. Check what's already tracked

```sh
uv run python .claude/skills/find-jobs/scripts/add_applications.py --list
```

Don't propose anything already on the board. Also skip companies the user has previously rejected or withdrawn from unless the role is clearly different.

## 3. Search

Follow the sector guide's *Search* section for the sources and the queries, and adjust them to the person's notes (location, contract, subject or specialism). Run 2-3 searches from different angles.

Browser mechanics for any site (claude-in-chrome tools, in a new tab you close at the end):
- Pages often render slowly. Wait ~3-4s before `get_page_text`, and retry once if it returns empty.
- Use a stable URL for each posting as `posting_url`: for LinkedIn, `https://www.linkedin.com/jobs/view/<id>/` (the id is `currentJobId` in the URL after clicking a card), never the tracking-laden search URL; elsewhere, the posting's own page on the employer's or board's site, not a news article or aggregator about it.
- **Read only.** Don't click Apply, Easy Apply, Save, Message, "I'm interested", or anything that sends something on the user's behalf.

## 4. Verify each candidate

Read the actual posting before including it. Reject or flag:
- **Closed** postings, or ones whose application deadline has passed (aggregators often show closed roles).
- **Location mismatch** with the person's stated preferences.
- The sector guide's *Fit checks*.
- **Contract/freelance**: fine to include, but say so in the role and notes.

If a role is strong but has one open question (e.g. a qualification the posting may waive), include it and make resolving that question the `next_action`.

## 5. Confirm, then insert

Present the shortlist as a table (company, role, why it fits, pay or contract, and deadline when there is one) plus a short "left out and why" list, so the user can pull any of those back in. If the user's request already said to add them, go straight to inserting.

Write a JSON file in the scratchpad and run the bundled script, which backs up the data folder first, skips duplicates by URL or company+role, and inserts via `repo.applications.create` (so status history is recorded). The file is a list of objects with `company`, `role`, and any of `posting_url`, `location`, `salary_range`, `source`, `next_action`, `notes`; the sector guide's *Record* section says how to fill them for this field and has an example.

```sh
uv run python .claude/skills/find-jobs/scripts/add_applications.py <scratchpad>/jobs.json
```

Field guidance: omit `status` (defaults to wishlist). Omit `interest` (1-5) unless the user gave you a rating; they usually rate listings themselves after reviewing them. Leave out fields you don't know rather than guessing.

To set interest levels later (e.g. "make Acme a 5"), find the ids with `--list` (the third column is interest) and run `--rate ID=LEVEL ...` (blank level clears it). This doesn't back up first; it only touches the `interest` column.

## 6. Report

Summarize what was added (table), what was skipped and why, the backup path, and a Sources list of the posting URLs. State plainly that nothing was applied to or sent from any site.
