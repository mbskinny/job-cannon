---
name: audit-concepts
description: Fact-check the user's interview prep concepts in their Job Cannon tracker (the short explanations they rehearse and say from memory, plus their notes), so they don't learn and repeat wrong, outdated or made-up information. Checks every claim, number and version detail against primary sources and proposes corrected wording. Use whenever the user asks to audit, check, verify, review or fact-check their concepts, explanations or prep notes, or worries an explanation is wrong, even if they don't name the skill or Job Cannon. For multiple-choice quiz questions, use audit-quiz-questions.
argument-hint: "[all | older-than DAYS | concept ID | tag NAME]"
---

# Audit concepts for accuracy

Arguments: `$ARGUMENTS`

A concept's **explanation** is the 30-second version the user rehearses (often with "Read to me" on repeat) and then says from memory in interviews. Its **notes** are the details they draw on for follow-up questions. An error in either gets memorised and repeated, so the job is to find errors, not to polish wording. Be rigorous, and don't invent problems: an explanation that's accurate but phrased differently from how you'd phrase it is fine.

## 1. Load what's due

Run `uv run job-cannon profiles --json` to get the active profile, and say which profile (`name`) you're auditing. If the user means someone else, pass `--profile <id>` to every command below.

```sh
uv run python .claude/skills/audit-concepts/scripts/concept_audit.py list
```

This is **read-only**. By default it lists the concepts **never checked**. A concept is marked checked when an audit passes or fixes it, and editing its name, explanation or notes in the app clears the mark (changing tags doesn't). Map the arguments to options:
- `all`: `--all`
- `older-than N`: `--older-than N`, which adds concepts last checked more than N days ago (90 suits a periodic recheck)
- `concept ID`: `--concept ID`
- `tag NAME`: `--tag NAME`, repeatable

It prints JSON with `due`, `total` and `concepts`. Each concept has:
- `name`, `explanation`, `notes`, `tags` and `checked_at`;
- `interview_questions`: the prompts it's linked to, showing how the user uses it;
- `quiz_questions`: id, prompt and answer, so you can keep them consistent with the explanation.

If nothing is due, say so with the total, suggest `older-than 90` or `all`, and stop. For more than about 15 concepts, work through them a tag at a time and keep notes as you go.

## 2. Check each concept

**The explanation.** Check every sentence:
1. **Is each claim true?** Check definitions, mechanisms, cause and effect, and comparisons ("X is faster than Y", "X prevents Y").
2. **Are the numbers right?** Check figures, defaults, limits and versions ("since Go 1.14", "about 100 ns", "4 threads by default").
3. **Is it current?** It may have been true once but changed in a newer version, default or standard.
4. **Is anything oversimplified to the point of being false?** An explanation has to be short, and leaving out detail is fine. What isn't fine is a simplification that states something untrue, or an "always/never" that has common exceptions. An interviewer who knows the topic would catch it.
5. **Is the terminology right?** Look for terms used for the wrong thing, or two ideas run together, such as concurrency and parallelism, or authentication and authorisation.

**The notes.** Apply the same checks. Notes are often terse bullet points, which is fine; only their accuracy matters.

**Quiz consistency.** If a quiz question's answer contradicts the explanation as it stands or as you'd correct it, mention it. The quiz question gets fixed through the audit-quiz-questions skill, not here.

**The user's own experience.** Some concepts, often tagged `past-work`, describe tools the user used or what they did with them. Check public facts about a product, such as features and how it works, against its documentation. Never "correct" what the user says they did, built or measured. If such a claim looks doubtful, ask about it rather than changing it.

**Verify, don't assume.** For anything version-specific, numeric, product-specific, or that you aren't certain of, check a primary source: official docs, release notes, the spec, or the source code. Use WebSearch or WebFetch, and keep the URL. Settled fundamentals can come from memory. If you can't confirm something, report it as **unverified** rather than wrong.

Classify each problem:
- **Wrong**: a false claim. Always fix.
- **Outdated**: true once, but changed since.
- **Misleading**: true words that leave a false impression, or a simplification that crosses into untrue.
- **Imprecise**: true, but likely to blur into a wrong idea.

Don't report style, length or tone. The one exception: if a fix would push the explanation well past about 75 words, say so and suggest moving the detail into the notes.

## 3. Report

Start with a one-line summary: how many checked, how many fine, and how many problems by class.

Then one entry per problem, most serious first:
- the concept's id and name;
- the field (explanation or notes) and the sentence at fault, quoted;
- what's wrong, in a sentence or two;
- the proposed fix. For the explanation, give the **whole new explanation**, since it's rehearsed as one piece, keeping the user's wording wherever it was correct and the length about the same. For notes, give the corrected lines;
- the source URL;
- any quiz questions affected, by id.

Then list the concepts that passed.

## 4. Apply, after the user agrees

Nothing changes until the user says so. They may accept all of the fixes, some, or ask for changes. Then:

- **Fix a concept:** write the changed fields to a JSON file in your scratchpad, e.g. `{"explanation": "..."}` or `{"notes": "..."}`, and run:
  ```sh
  uv run python .claude/skills/audit-concepts/scripts/concept_audit.py fix <ID> <file.json>
  ```
  It backs up the profile first, keeps the name and tags, and marks the concept checked. Notes replace the whole notes field, so send the complete corrected notes, not only the changed lines.
- **Mark the concepts that passed** as checked, in one call:
  ```sh
  uv run python .claude/skills/audit-concepts/scripts/concept_audit.py mark <ID> <ID> ...
  ```
  Only mark concepts you actually checked and found sound, or fixed. Leave unverified and declined ones unmarked, so the next audit picks them up again.

Finish by saying what changed, with the links the script printed, and how many concepts are still unchecked. If any quiz questions were affected, offer to run the audit-quiz-questions skill on those concepts next.
