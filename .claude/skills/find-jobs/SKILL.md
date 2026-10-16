---
name: find-jobs
description: Find current job listings that match the user's résumé and add them to their Job Cannon tracker as wishlist applications. Use this whenever the user asks to find, search for, scout, or source jobs/roles/openings, wants "a few more listings", asks what's hiring that fits them, or asks to populate/fill their Job Cannon or board with real postings, even if they don't say "skill" or name a site.
---

# Find jobs and add them to Job Cannon

The goal is a short list (default 4-5, or whatever number the user asks for) of **open, verified** postings that genuinely fit the user, added to their real tracker with notes good enough to decide on without re-opening the posting.

## 1. Build the profile

Read `.claude/job-search.local.md` for the résumé location and any notes. If it doesn't exist, ask the user where their résumé is and offer to create the file from `.claude/job-search.example.md`. Fetch the résumé (WebFetch for a URL, Read for a local file). Pull out: seniority and title, core stack, standout domains (e.g. data visualization, observability), home location and citizenship, stated location preferences (remote/regions), and languages spoken. The résumé is the source of truth for facts about the user. The profile's notes can add preferences it doesn't state, and constraints in the request (salary floor, contract vs. employee, a specific domain) override both.

## 2. Check what's already tracked

```sh
uv run python .claude/skills/find-jobs/scripts/add_applications.py --list
```

Don't propose anything already on the board. Also skip companies the user has previously rejected or withdrawn from unless the role is clearly different.

## 3. Search

LinkedIn in the user's local Chrome is the best source: it's logged in, results are fresh, and postings show remote eligibility and pay. Web search is mostly stale aggregators, so it's useful as a supplement (Hacker News "Who is hiring" for the current month, company career pages) but expect many dead links.

LinkedIn tips (claude-in-chrome tools, in a new tab you close at the end):
- Search URL: `https://www.linkedin.com/jobs/search/?keywords=<terms>&location=European%20Union&geoId=91000000&f_WT=2&f_TPR=r1209600` (`f_WT=2` = remote, `f_TPR=r1209600` = past 2 weeks, `r2592000` = past month). Adjust keywords/geo to the profile.
- Pages render slowly. Wait ~3-4s before `get_page_text`, and retry once if it returns empty.
- Open a job directly with `https://www.linkedin.com/jobs/view/<id>/`. The id is `currentJobId` in the URL after clicking a card. Use this id-based URL as `posting_url`, never the tracking-laden search URL.
- Run 2-3 searches with different angles (core stack, e.g. "senior full stack TypeScript Go"; domain strength, e.g. "data visualization React"; local roles near the user's home city).
- **Read only.** Don't click Apply, Easy Apply, Save, Message, "I'm interested", or anything that sends something on the user's behalf.

## 4. Verify each candidate

Read the actual posting before including it. Reject or flag:
- **Closed** postings (aggregators often show closed roles).
- **Location mismatch**: "remote" that is limited to specific countries not including the user's, onsite/hybrid elsewhere, or working hours far outside their time zone (e.g. US Eastern hours from Europe).
- **Stack mismatch**: only a keyword overlap.
- **Contract/freelance**: fine to include, but say so in the role and notes.

If a role is strong but has one open question (e.g. Italy not in the listed countries), include it and make resolving that question the `next_action`.

## 5. Confirm, then insert

Present the shortlist as a table (company, role, why it fits, pay) plus a short "left out and why" list, so the user can pull any of those back in. If the user's request already said to add them, go straight to inserting.

Write a JSON file in the scratchpad and run the bundled script, which backs up the data folder first, skips duplicates by URL or company+role, and inserts via `repo.applications.create` (so status history is recorded):

```json
[
  {
    "company": "Toggl",
    "role": "Senior Full Stack Engineer",
    "posting_url": "https://www.linkedin.com/jobs/view/4460399469/",
    "location": "Remote (anywhere UTC-4 to UTC+4)",
    "salary_range": "€83,000",
    "source": "LinkedIn",
    "next_action": "Apply",
    "notes": "Manager Tribe for Toggl 2.0: dashboards and visualizations on dense data. React + TypeScript, Go backend, Postgres. Meetings 11:00-16:00 UTC."
  }
]
```

```sh
uv run python .claude/skills/find-jobs/scripts/add_applications.py <scratchpad>/jobs.json
```

Field guidance: omit `status` (defaults to wishlist). Omit `interest` (1-5) unless the user gave you a rating; they usually rate listings themselves after reviewing them. `location` should state the remote terms, not just a city. `salary_range` should be as printed, with currency. `notes` should cover what the company does, the stack, the fit, and any caveats in 2-4 sentences. Leave out fields you don't know rather than guessing.

To set interest levels later (e.g. "make Toggl a 5"), find the ids with `--list` (the third column is interest) and run `--rate ID=LEVEL ...` (blank level clears it). This doesn't back up first; it only touches the `interest` column.

## 6. Report

Summarize what was added (table), what was skipped and why, the backup path, and a Sources list of the posting URLs. State plainly that nothing was applied to or sent from LinkedIn.
