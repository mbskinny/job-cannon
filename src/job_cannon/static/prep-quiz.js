// Interview prep quiz: runs the deck the page carries as JSON (#quiz-data), one
// question at a time, with the answer options shuffled on every deal. Each result is
// posted to /prep/quiz/{id}/answer, so focus mode knows what was missed.
(function () {
  const KEYS = ["A", "B", "C", "D"];
  const profile = document.body.dataset.profile;

  // The topic and focus filters apply as soon as they change.
  const filters = document.querySelector("[data-quiz-filters]");
  if (filters) filters.addEventListener("change", () => filters.submit());

  const data = document.getElementById("quiz-data");
  const card = document.getElementById("quiz");
  if (!data || !card) return;
  const QUESTIONS = JSON.parse(data.textContent);
  const scoreEl = document.querySelector("[data-quiz-score]");
  const here = location.pathname + location.search;
  let state;

  function shuffle(list) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // Shuffle the questions and each one's options, remembering where the right answer landed.
  function deal(pool) {
    return shuffle(pool).map((q) => {
      const options = shuffle([q.answer, ...q.wrong]);
      return { ...q, options, right: options.indexOf(q.answer) };
    });
  }

  function start(pool) {
    state = { deck: deal(pool), i: 0, correct: 0, answered: 0, picked: null, missed: [] };
    render();
  }

  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }

  // `code` spans in question and answer text, built without innerHTML.
  function rich(text) {
    const frag = document.createDocumentFragment();
    for (const part of text.split(/(`[^`]+`)/)) {
      if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) frag.append(el("code", { text: part.slice(1, -1) }));
      else frag.append(part);
    }
    return frag;
  }

  function editLink(q) {
    return el("a", { href: `/prep/quiz/${q.id}/edit?next=${encodeURIComponent(here)}`, text: "Edit question" });
  }

  function conceptLink(q) {
    return el("a", { href: `/prep/concepts/${q.concept_id}`, text: q.concept });
  }

  function showStale(message) {
    if (document.querySelector(".profile-stale")) return;
    const note = el("p", { class: "profile-stale", role: "alert" }, message + " ", el("a", { href: location.href, text: "Reload" }));
    document.querySelector("main").prepend(note);
  }

  function record(q, correct) {
    const body = new URLSearchParams({ correct: correct ? "1" : "0" });
    fetch(`/prep/quiz/${q.id}/answer`, { method: "POST", body, headers: { "X-Job-Cannon-Profile": profile } })
      .then(async (res) => {
        if (res.status === 409 || res.status === 503) showStale(await res.text());
        else if (!res.ok) showStale(`Your answer couldn't be saved (error ${res.status}).`);
      })
      .catch(() => showStale("Your answer couldn't be saved: is Job Cannon still running?"));
  }

  function render() {
    if (scoreEl) scoreEl.textContent = `${state.correct} correct · ${state.answered} answered`;
    if (state.i >= state.deck.length) return renderResult();
    const q = state.deck[state.i];
    const done = state.picked !== null;

    const bar = el("div", { class: "quiz-bar" }, el("i"));
    bar.firstChild.style.width = `${(state.i / state.deck.length) * 100}%`;

    const options = el("div", { class: "quiz-options" }, ...q.options.map((text, i) => {
      let cls = "quiz-option";
      if (done) cls += i === q.right ? " right" : i === state.picked ? " wrong" : " dim";
      const b = el("button", { class: cls, type: "button", onclick: () => pick(i) },
        el("span", { class: "quiz-key", text: KEYS[i] }), el("span", {}, rich(text)));
      b.disabled = done;
      return b;
    }));

    const kids = [
      el("div", { class: "quiz-meta" }, conceptLink(q), el("span", { text: `Question ${state.i + 1} of ${state.deck.length}` })),
      bar,
      el("h2", { class: "quiz-prompt" }, rich(q.prompt)),
      q.code ? el("pre", { class: "quiz-code", text: q.code }) : null,
      options,
    ];
    if (done) {
      const ok = state.picked === q.right;
      kids.push(el("div", { class: "quiz-why" },
        el("strong", { class: ok ? "quiz-ok" : "quiz-no", text: ok ? "Correct." : `Not quite: the answer is ${KEYS[q.right]}.` }),
        q.explanation ? el("p", {}, rich(q.explanation)) : null,
        el("small", { class: "muted" }, "Concept: ", conceptLink(q), " · ", editLink(q))));
      kids.push(el("div", { class: "quiz-actions" },
        el("button", { type: "button", id: "quiz-next", onclick: next, text: state.i + 1 < state.deck.length ? "Next question" : "See results" }),
        el("small", { class: "muted quiz-hint", text: "Enter for next" })));
    } else {
      kids.push(el("small", { class: "muted quiz-hint", text: "Press 1–4 or A–D to answer" }));
    }
    card.replaceChildren(...kids.filter(Boolean));
    if (done) document.getElementById("quiz-next").focus();
  }

  function pick(i) {
    if (state.picked !== null) return;
    const q = state.deck[state.i];
    const correct = i === q.right;
    state.picked = i;
    state.answered++;
    if (correct) state.correct++;
    else state.missed.push(q);
    record(q, correct);
    render();
  }

  function next() {
    state.i++;
    state.picked = null;
    render();
    card.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function renderResult() {
    const total = state.deck.length;
    const pct = Math.round((state.correct / total) * 100);
    const concepts = new Map(state.missed.map((m) => [m.concept_id, m]));
    const rehearse = el("span");
    [...concepts.values()].forEach((m, i) => {
      if (i) rehearse.append(", ");
      rehearse.append(conceptLink(m));
    });
    const kids = [
      el("div", { class: "quiz-meta" }, el("span", { text: "Finished" })),
      el("h2", { class: "quiz-score", text: `${state.correct} / ${total}` }),
      el("p", {}, state.missed.length ? el("span", {}, `${pct}%. Concepts to rehearse: `, rehearse, ".") : `${pct}%. Nothing missed.`),
    ];
    if (state.missed.length) {
      // Each missed question's original, so a retry deals fresh option orders.
      kids.push(el("ul", { class: "quiz-missed" }, ...state.missed.map((m) => el("li", {},
        el("small", { class: "muted" }, conceptLink(m), " · ", editLink(m)),
        el("span", { class: "quiz-missed-q" }, rich(m.prompt)),
        el("span", { class: "quiz-ok" }, "Answer: ", rich(m.answer))))));
    }
    const missedPool = state.missed.map((m) => QUESTIONS.find((q) => q.id === m.id));
    kids.push(el("div", { class: "quiz-actions" },
      state.missed.length ? el("button", { type: "button", onclick: () => start(missedPool), text: `Retry the ${state.missed.length} missed` }) : null,
      el("button", { type: "button", class: state.missed.length ? "secondary outline" : "", onclick: () => start(QUESTIONS), text: "Start over" })));
    card.replaceChildren(...kids.filter(Boolean));
  }

  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || !state || state.i >= state.deck.length) return;
    if (e.target.closest("input, textarea, select")) return;
    const k = e.key.toUpperCase();
    const idx = k.length === 1 && "1234".includes(k) ? Number(k) - 1 : KEYS.indexOf(k);
    if (state.picked === null && idx >= 0) {
      e.preventDefault();
      pick(idx);
    } else if (state.picked !== null && e.key === "Enter" && document.activeElement?.id !== "quiz-next") {
      e.preventDefault();
      next();
    }
  });

  start(QUESTIONS);
})();
