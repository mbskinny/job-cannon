---
name: answer-application-question
description: Help the user answer a question from a job application form ("Why do you want to work here?", "Describe a project you're proud of", "What are your salary expectations?", short free-text or yes/no screening questions), grounded in their résumé and, if given, one application from their Job Cannon tracker. Use whenever the user pastes an application-form question or asks for help answering one, even if they don't name the skill or Job Cannon.
argument-hint: "[application id] [question]"
---

# Answer an application-form question

Arguments: `$ARGUMENTS`

The arguments may start with a Job Cannon **application id** (a bare integer, or `#12`), and anything after it is the question. Both are optional. If there is no question in the arguments or the conversation, ask the user to paste it (with any character/word limit the form shows) and stop until they do.

## 1. Load the application (if there is one)

Run `uv run job-cannon profiles --json` to get the active Job Cannon profile. Several people can share the install, each with their own tracker and résumé, so say which profile (`name`) you're working in. If the user means someone else, pass `--profile <id>` to every script below, and to `profiles --json`.

If an id was given:

```sh
uv run python .claude/skills/answer-application-question/scripts/app_context.py <APP_ID>
```

This is **read-only**. It prints JSON with the application (company, role, posting URL, location, salary, notes), the company, linked contacts, the interaction log (recruiter calls, interview notes), the cover letter draft, attachments with their paths on disk, and status history.

If no id was given but the question or conversation names a company, find it with `uv run python .claude/skills/find-jobs/scripts/add_applications.py --list` and confirm the match with the user in one line before using it. If nothing matches, answer without application context; don't add the application unless the user asks.

## 2. Gather material

- **Résumé**: read the file at `job_search_file` (from `profiles --json`, step 1) for the résumé location and any notes. If it doesn't exist and the profile id is `default`, fall back to `.claude/job-search.local.md`. If neither exists, ask the user where their résumé is and offer to create `job_search_file` from `.claude/job-search.example.md`. Fetch the résumé with WebFetch for a URL, Read for a local file. The résumé, plus that file's notes, is the source of truth for facts about the user.
- **Posting**: only fetch `posting_url` when the question is about the role or company ("why us", "how does your experience match") and the application notes aren't enough. WebFetch, or for LinkedIn the user's Chrome (claude-in-chrome, new tab, `https://www.linkedin.com/jobs/view/<id>/`). **Read only**: never click Apply or anything that sends something.
- **Already-written material**: the cover letter draft and any `cover_letter` attachment (Read the PDF path). Keep the answer consistent with what the user has sent or will send, but don't copy whole paragraphs from the letter; forms often go to the same reader.
- **Interactions**: what a recruiter or interviewer said is often the best evidence for "why this role".

## 3. Write the answer

- Answer the question that was asked, first sentence first. No preamble ("Great question", "I am writing to...").
- **Respect the limit**. If the form gives a character or word limit, stay under it and state the count. If not, aim for what the question implies: one line for factual questions, 80-150 words for open ones.
- **Never invent** experience, numbers, employers, dates, or skills that aren't in the résumé or the profile notes. If the honest answer is weak or missing (e.g. "years of Kubernetes experience" with none on the résumé), say so to the user and suggest an honest framing rather than stretching the truth.
- Be specific to this company and role when there is application context: tie a concrete thing from the résumé to a concrete thing in the posting or notes.
- Write in the user's voice: first person, plain, confident, no buzzwords. Match the form's language (an Italian form gets an Italian answer) unless the user says otherwise.
- **Factual / eligibility questions** (work authorization, relocation, notice period, start date, salary expectations): answer from the profile notes and application data. If the answer isn't there, ask the user rather than guessing. For salary, use the user's stated floor or the posting's range if known, and mention which you used.
- If the question is ambiguous or could be answered from several angles, write the best one and offer one alternative angle in a single line.

## 4. Present

Show the answer in a block the user can copy, with its word/character count when there's a limit. Below it, in a few short bullets, list which résumé items or application facts each claim rests on, so the user can check them. State that nothing was saved or submitted.

If the user wants to keep the answer, offer to log it on the application as a `note` interaction in the app (http://127.0.0.1:8765/applications/<APP_ID>); don't write to the database yourself unless they ask.
