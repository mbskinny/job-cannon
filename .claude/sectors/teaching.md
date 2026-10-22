# Sector guide: teaching (Italy)

Read by the Job Cannon skills for profiles whose sector is `teaching`. It holds
what is specific to teaching jobs in Italy, in both Italian state schools and
private or international schools. The person's own facts and preferences are in
their `job-search.md`, and those win over anything here.

The rules for state-school supply teaching change almost every year, through a
new ministerial order or annual note. Treat the dates and rules below as
background. Check the current year's rules on the MIM site or the regional
school office (USR) site before telling the user about a deadline or whether
they're eligible, and say what you checked.

## Profile cues

From the résumé, pull out:
- **Subjects and levels**: infanzia, primaria, secondaria di I or II grado, and
  sostegno (special-needs support).
- **Classi di concorso** the person can teach (codes such as A022 or A-22),
  whether they hold an abilitazione or the sostegno specialisation, and any
  study credits (CFU) toward it.
- **Ranking lists**: whether they're in the GPS (provincial supply-teaching
  lists) or a school's own lists (graduatorie di istituto), and in which province.
- **Private and international schools**: curricula taught (IB, British,
  American, Montessori), and certifications such as PGCE, QTS or CELTA.
- **Languages** they can teach in, home town, and how far they will commute.

## Search

Postings come through very different channels. Search the ones that match the
person's notes, and say which you covered.

**Italian state schools**
- **Interpelli**: once a school has exhausted its graduatorie for a post, it
  publishes a supply-teaching notice (avviso di interpello). The notice goes on
  the school's website and online noticeboard (albo online), and is sent to the
  provincial school office (USP/UST). Many USR/USP sites collect them on one
  page.
  - Search "interpello" with the classe di concorso and the province, e.g.
    `interpello A022 provincia di Firenze`. Then open the school's or the
    USP's own page, not a news site.
  - Windows can be a few days, or even hours. Always record the deadline.
  - Interpelli peak from September through the school year.
- **GPS and the "150 preferenze"**: annual and until-30-June supply posts are
  assigned by the USP from the GPS, through an online application in late
  summer (on the MIM portal, Istanze online). The GPS lists themselves are
  renewed every two years. These are deadlines, not postings: if the person's
  notes say they're in the GPS, check the current year's dates and mention any
  that are coming up. Don't add them as applications.
- **MAD (messa a disposizione)**: a direct offer of availability to schools.
  It's still used where a school urgently needs teachers and its lists are
  exhausted, but recent orders give priority to interpelli. If the person wants
  this, list schools in their area and draft the letter; it isn't a posting.
- **Concorsi**: the state hiring competitions, announced by the MIM and applied
  for through the inPA portal. Note any open concorso for the person's classi
  di concorso.

**Private, paritarie and international schools**
- Paritarie (state-recognised private) schools hire directly. Search their own
  sites, plus LinkedIn, Indeed and InfoJobs, with the subject and town (e.g.
  `docente inglese scuola paritaria Firenze`).
- International schools: TES (`https://www.tes.com/jobs/browse/italy`), Teach
  Away, LinkedIn, and the careers pages of the international schools near the
  person.
  - Most hiring is from autumn to early spring, for a start the following
    August or September.
  - Check posting dates, because old listings linger on these boards.
- LinkedIn search: `https://www.linkedin.com/jobs/search/?keywords=<terms>&location=<city>&f_TPR=r2592000`
  (past month). Try both Italian and English keywords.

## Fit checks

- **Classe di concorso or level**: the post is for a code or level the person
  isn't qualified for. A sostegno post needs the specialisation, or comes after
  the specialised candidates.
- **Required qualification**: the notice requires an abilitazione the person
  doesn't have, or an international school requires a teaching licence
  (PGCE/QTS, a US state licence) or curriculum experience they lack. Flag it
  rather than drop it when the notice says unqualified candidates may be
  considered as a fallback.
- **Eligibility rules for interpelli**: for example, someone already on a
  fixed-term contract may be excluded. Read the notice itself.
- **Contract**:
  - Supplenza breve (short cover), until 30 June, or until 31 August.
  - A full cattedra (18 hours a week in secondaria) or a part-time block (spezzone).
  - Private schools: which national contract (CCNL) applies, and whether it's
    a fixed-term contract or a freelance arrangement (collaborazione).
- **Commute**: compare the school's town with the person's stated radius.
- **Deadline already passed**: drop it.

## Record

- `company`: the school's name as written, e.g. "IC Gandhi" or "Liceo Scientifico Castelnuovo".
- `role`: the post and contract, e.g. "Docente A022 - supplenza fino al 30/06 (interpello)" or "Primary Class Teacher (IB PYP)".
- `posting_url`: the notice on the school's or USP's own site, or the job-board page; never a news article about it.
- `location`: the town, plus the school's address if commuting matters.
- `salary_range`:
  - State schools are paid on the national scale, so leave it empty unless the notice says something specific.
  - Private and international schools: copy the amount as printed.
- `next_action`: how and when to apply, e.g. "Send application by PEC by 24/10 12:00" or "Apply on the school's form".
- `notes`, 2-4 sentences: the school type and level, the class or hours, the contract dates, the deadline, the required documents, and why it fits.

```json
{
  "company": "IC Gandhi",
  "role": "Docente A022 - supplenza fino al 30/06 (interpello)",
  "posting_url": "https://www.example-scuola.edu.it/albo-online/avviso-interpello-a022",
  "location": "Prato",
  "source": "School website (interpello)",
  "next_action": "Send application by PEC by 24/10 12:00",
  "notes": "Interpello for a full A022 cattedra (18 hours), two classes in scuola secondaria di I grado, until 30 June. Abilitati first, then candidates with the access degree only. Send a CV and the signed form to the school's PEC address."
}
```

When presenting a shortlist, sort it by deadline, soonest first.

## Writing

- **State and paritarie schools**: formal Italian.
  - Use "Gentile Dirigente Scolastico" or "Alla cortese attenzione del Dirigente Scolastico".
  - Lead with the classe di concorso, qualifications and availability.
  - Keep it short; these are read quickly.
- **MAD letters**: one page.
  - Full name, date and place of birth, codice fiscale and contacts.
  - Degree and qualifications, and the classi di concorso they apply to.
  - Immediate availability, and a statement that they are not in the GPS for that province, if true.
  - Ask the user for any personal data that isn't in their notes; never invent it.
- **International schools**: English (or the school's language), focused on the
  students.
  - Use the curriculum's vocabulary (IB learner profile, Key Stages) only when
    the résumé supports it.
- **Evidence comes from classroom practice**: what she taught, to whom, how she
  adapted it, and what changed for the students. It doesn't come from projects
  or technology. Never invent classes, results or qualifications.
- **Interview and form answers**: concrete classroom examples work best. Cover
  managing a class, inclusion (students with DSA or BES), assessment, and
  working with parents and colleagues.
