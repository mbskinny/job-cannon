---
name: audit-quiz-questions
description: Fact-check the user's interview prep quiz questions (and the concept explanations they test) in their Job Cannon tracker, so they don't memorise wrong or made-up information. Checks that each marked answer is right, each wrong answer is really wrong, and explanations, numbers and version details are accurate, then proposes fixes. Use whenever the user asks to audit, check, verify, review or fact-check their quiz questions, concepts or prep material, or worries they're learning something false, even if they don't name the skill or Job Cannon.
argument-hint: "[all | older-than DAYS | concept ID | tag NAME]"
---

# Audit quiz questions for accuracy

Arguments: `$ARGUMENTS`

The user rehearses these questions until the answers stick, so a wrong "correct" answer or a false explanation does real harm: they'll repeat it in an interview. The job is to find errors, not to polish wording. Be rigorous, and don't invent problems either: a question that's correct but phrased differently from how you'd phrase it is fine.

## 1. Load what's due

Run `uv run job-cannon profiles --json` to get the active profile, and say which profile (`name`) you're auditing. If the user means someone else, pass `--profile <id>` to every command below.

```sh
uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py list
```

This is **read-only**. By default it lists the quiz questions **never checked**. Each question is marked checked when an audit passes or fixes it, and editing it in the app clears the mark. Map the arguments to options:
- `all`: `--all`, every question
- `older-than N`: `--older-than N`, which adds questions last checked more than N days ago (for a periodic recheck, 90 is sensible)
- `concept ID`: `--concept ID`
- `tag NAME`: `--tag NAME`, repeatable

It prints JSON with:
- `due` and `total`;
- `concepts`: each concept the listed questions test, with `explanation` and `notes`;
- `questions`: each with `id`, `concept`, `prompt`, `code`, `answer`, `wrong_answers`, `explanation` and `checked_at`.

If nothing is due, say so with the total, suggest `older-than 90` or `all`, and stop.

For more than about 30 questions, work through them concept by concept and keep notes as you go, rather than trying to hold everything at once.

## 2. Check each question

For every question, decide:

1. **Is the marked answer correct?** It must also be the best answer to the question as worded, not merely defensible.
2. **Is each wrong answer actually wrong?** A distractor that's also true, or true under a common reading, makes the question ambiguous. That's a defect even when the marked answer is right.
3. **Is the explanation accurate?** Check every factual claim: numbers, defaults, version numbers ("since Go 1.14", "since Node 15"), names, cause and effect.
4. **Is the prompt sound?** No hidden assumption the options depend on. No "always/never" that's false in practice. Code that does what the question says.
5. **Is it current?** Facts tied to versions or defaults may have changed. Flag the ones that have, with the version where they changed.

Also check each listed **concept's** `explanation` and `notes`. The user says these aloud from memory, so the same standard applies.

**Verify, don't assume.** For anything version-specific, numeric, or that you aren't certain of, check a primary source: official docs, release notes, the spec, or the source code. Use WebSearch or WebFetch, and keep the URL for the report. Your own memory is fine for settled fundamentals. Don't present a guess as a finding: if you can't confirm something, report it as **unverified** rather than wrong.

Classify each problem:
- **Wrong**: the marked answer or a stated fact is false. Always fix.
- **Ambiguous**: a wrong answer is also defensible, or the prompt allows two readings.
- **Outdated**: it was true, but a newer version or default changed it.
- **Imprecise**: true, but likely to plant a slightly wrong idea, such as an oversimplified number or a missing condition.

Don't report style preferences.

## 3. Report

Start with a one-line summary: how many checked, how many fine, and how many problems by class.

Then one entry per problem, most serious first:
- question `id`, its concept, and the prompt (shortened);
- what's wrong, in a sentence or two;
- the proposed fix, as the exact new text of the fields that change. A wrong answer stays a wrong answer: keep three, and keep them plausible;
- the source URL for anything you checked.

Concept problems get the same treatment, with the proposed new `explanation` or `notes`.

Then list the ids that passed. If a question can't be saved by rewording, say so and suggest the user deletes it from its edit page (`http://127.0.0.1:8765/prep/quiz/<id>/edit`). Never delete anything yourself.

## 4. Apply, after the user agrees

Nothing changes until the user says so. They may accept all of the fixes, some, or ask for changes. Then:

- **Fix a question:** write the changed fields to a JSON file in your scratchpad, e.g. `{"answer": "...", "explanation": "..."}`. Allowed fields are `prompt`, `answer`, `wrong_answers` (a list of exactly 3), `explanation`, `code` and `concept_id`. Then run:
  ```sh
  uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py fix <ID> <file.json>
  ```
  It backs up the profile first, keeps the user's right/wrong results, and marks the question checked.
- **Fix a concept:** a JSON file with `explanation` and/or `notes`, then:
  ```sh
  uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py fix-concept <ID> <file.json>
  ```
- **Mark the questions that passed** as checked, in one call:
  ```sh
  uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py mark <ID> <ID> ...
  ```
  Only mark questions you actually checked and found sound, or fixed. Leave unverified and declined ones unmarked, so the next audit picks them up again.

Finish by saying what changed, with the links the script printed, and how many questions are still unchecked.
