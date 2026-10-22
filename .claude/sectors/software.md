# Sector guide: software engineering

Read by the Job Cannon skills for profiles whose sector is `software`. It holds
what is specific to software jobs; the person's own facts and preferences are in
their `job-search.md`, and those win over anything here.

## Profile cues

From the résumé, pull out: seniority and title, core stack (languages,
frameworks, databases, cloud), standout domains (e.g. data visualization,
observability), home location and citizenship, stated location preferences
(remote/regions), and languages spoken.

## Search

LinkedIn in the user's Chrome is the best source: it's logged in, results are
fresh, and postings show remote eligibility and pay. Web search is mostly stale
aggregators, so use it as a supplement (Hacker News "Who is hiring" for the
current month, company career pages) and expect many dead links.

- Search URL: `https://www.linkedin.com/jobs/search/?keywords=<terms>&location=European%20Union&geoId=91000000&f_WT=2&f_TPR=r1209600`
  (`f_WT=2` = remote, `f_TPR=r1209600` = past 2 weeks, `r2592000` = past month).
  Adjust keywords and geography to the person's preferences.
- Run 2-3 searches from different angles: core stack (e.g. "senior full stack
  TypeScript Go"), domain strength (e.g. "data visualization React"), and local
  roles near the person's home city.

## Fit checks

- **Stack mismatch**: only a keyword overlaps, or the core of the role is a
  stack the résumé doesn't show.
- **Seniority mismatch**: clearly junior, or a staff/principal scope the résumé
  doesn't support (flag rather than drop).
- **Remote terms**: "remote" limited to countries that don't include the
  person's, or working hours far outside their time zone (e.g. US Eastern hours
  from Europe).

## Record

- `role`: the title as posted, plus "(contract)" when it isn't employment.
- `location`: the remote terms, not just a city (e.g. "Remote (EU, UTC-1 to UTC+3)").
- `salary_range`: as printed, with currency.
- `notes`, 2-4 sentences: what the company does, the stack, why it fits, and caveats.

```json
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
```

## Writing

- Evidence is concrete work: systems built, the person's part in them, scale,
  and outcomes, tied to the posting's product and stack.
- Technical-depth questions ("years of Kubernetes") get an honest answer. If the
  résumé doesn't show it, say so to the user and suggest a framing based on
  adjacent experience.
- Plain, direct English unless the posting or form is in another language.
