---
name: tailor-cover-letter
description: Tailor one of the user's base cover letters to a specific application in their Job Cannon tracker and save it as a draft for them to review and attach as a PDF. Use whenever the user asks to write, draft, tailor, adapt, or customize a cover letter for a job, company, or application, even if they don't name the skill or Job Cannon.
---

# Tailor a cover letter in Job Cannon

The user keeps **base letters** in Job Cannon (Cover letters page): their own prose with placeholders such as `{{why_company: 2-3 sentences on what draws me to this company}}`. Your job is to fill those placeholders for one application and save the result as that application's **draft**. The user edits it in the app and clicks **Attach as PDF** themselves.

## 1. Find the application

Run `uv run job-cannon profiles --json` to get the active Job Cannon profile. Several people can share the install, each with their own tracker and résumé, so say which profile (`name`) you're working in. If the user means someone else, pass `--profile <id>` to every script below, and to `profiles --json`. Then read the profile's **sector guide**, `.claude/sectors/<sector>.md` (`general.md` if `sector` is empty): its *Writing* section holds the conventions for this person's field (language and register, what counts as evidence), and the person's own notes override it.

```sh
uv run python .claude/skills/find-jobs/scripts/add_applications.py --list
uv run python .claude/skills/tailor-cover-letter/scripts/cover_letter.py context <APP_ID>
```

`context` prints the application (company, role, posting URL, notes), any existing draft, and every base letter with `{{company}}`, `{{role}}` and `{{date}}` already filled and the remaining placeholders listed with their instructions. If the application isn't tracked yet, offer to add it first (the find-jobs skill's script does this). If there are no base letters, tell the user to create one at http://127.0.0.1:8765/cover-letters/new and stop.

If a draft already exists, ask before replacing it, because the user may have edited it.

## 2. Gather material

- **Résumé**: read the file at `job_search_file` (from `profiles --json`, step 1) for the résumé location and any notes. If it doesn't exist and the profile id is `default`, fall back to `.claude/job-search.local.md`. If neither exists, ask the user where their résumé is and offer to create `job_search_file` from `.claude/job-search.example.md`. Fetch the résumé with WebFetch for a URL, Read for a local file. The résumé, plus that file's notes, is the only source of facts about the user.
- **Posting**: `posting_url`. Use WebFetch, or for LinkedIn the user's Chrome (claude-in-chrome, new tab, `https://www.linkedin.com/jobs/view/<id>/`). **Read only**: never click Apply, Save, Message, or anything that sends something. If the posting is closed or unreachable, say so and work from the application's notes.
- The application's `notes`, which often summarize the employer, the job and the fit.

## 3. Choose the base letter

Use the one the user named. Otherwise pick the one whose name and content best fit the role, and say which you chose and why in one line.

## 4. Fill the placeholders

- Replace **only** the `{{...}}` placeholders, following each one's instruction (length, focus). Leave the user's fixed text exactly as written, including line breaks and the sign-off.
- **Never invent** experience, numbers, employers, or skills that aren't in the résumé. Tie claims to specific things in the posting (what the employer does, the job's responsibilities, its requirements), not generic praise. Follow the sector guide's *Writing* section for what counts as evidence and for the register.
- Match the voice of the surrounding text: same language, formality and sentence length. If the posting is in Italian and the base letter is in English, keep English unless the user asks otherwise (the sector guide may say which language employers expect; mention it if it differs from the letter's).
- If a placeholder can't be filled honestly (e.g. `{{recipient}}` with no known name), use its instruction's fallback; if there is none, use a neutral choice ("Hiring Team") and mention it.
- No placeholders may remain. The app refuses to attach a letter that still contains `{{`.

## 5. Show, then save

Show the full letter in the terminal. Unless the user asked you to go straight to saving, wait for their OK or edits. Then write it to a file in the scratchpad and save it:

```sh
uv run python .claude/skills/tailor-cover-letter/scripts/cover_letter.py save-draft <APP_ID> --template <TEMPLATE_ID> <scratchpad>/letter.txt
```

The script backs up the data folder first and reports any placeholders still unfilled.

## 6. Report

Give the link `http://127.0.0.1:8765/applications/<APP_ID>#cover-letter` where the user can edit the draft and click **Attach as PDF**, list which placeholders you filled and from what evidence, and state plainly that nothing was sent or applied to.
