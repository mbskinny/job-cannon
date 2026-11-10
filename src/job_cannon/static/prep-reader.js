// Interview prep: "Read to me" reads a written answer (or a concept's
// explanation) aloud with the browser's speech synthesis, optionally on repeat
// until stopped. "Your turn" makes it pause every N reads: it says so, then
// waits as long as the text takes to say (at 150 words per minute) while you
// say it yourself. Everything happens in the browser; the settings are
// remembered in localStorage.
(function () {
  const synth = window.speechSynthesis;
  if (!synth || !window.SpeechSynthesisUtterance) return; // controls stay hidden

  const PAUSE_MS = 1500; // breath between repeats
  const WORDS_PER_MINUTE = 150; // the speaking-time estimate the pages show
  const YOUR_TURN = "I'll wait for you to rehearse now.";
  const settings = document.querySelector("[data-read-settings]");
  const voiceSelect = settings && settings.querySelector("[data-voice]");
  const rateSelect = settings && settings.querySelector("[data-rate]");
  const rehearseSelect = settings && settings.querySelector("[data-rehearse]");

  function load(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private window etc. */ }
  }

  // --- settings row -------------------------------------------------------
  function fillVoices() {
    if (!voiceSelect) return;
    const voices = synth.getVoices();
    if (!voices.length) return;
    const wanted = load("jc-tts-voice") || voiceSelect.value;
    voiceSelect.length = 1; // keep "Browser default"
    const lang = (navigator.language || "en").toLowerCase();
    const sorted = voices.slice().sort((a, b) => {
      // the user's language first, then by name
      const am = a.lang.toLowerCase().startsWith(lang.slice(0, 2)) ? 0 : 1;
      const bm = b.lang.toLowerCase().startsWith(lang.slice(0, 2)) ? 0 : 1;
      return am - bm || a.name.localeCompare(b.name);
    });
    for (const v of sorted) voiceSelect.add(new Option(v.name + " (" + v.lang + ")", v.voiceURI));
    voiceSelect.value = voices.some((v) => v.voiceURI === wanted) ? wanted : "";
  }

  if (settings) {
    settings.hidden = false;
    const rate = load("jc-tts-rate");
    if (rate && [...rateSelect.options].some((o) => o.value === rate)) rateSelect.value = rate;
    rateSelect.addEventListener("change", () => save("jc-tts-rate", rateSelect.value));
    voiceSelect.addEventListener("change", () => save("jc-tts-voice", voiceSelect.value));
    if (rehearseSelect) {
      const every = load("jc-tts-rehearse");
      if (every && [...rehearseSelect.options].some((o) => o.value === every)) rehearseSelect.value = every;
      rehearseSelect.addEventListener("change", () => save("jc-tts-rehearse", rehearseSelect.value));
    }
    fillVoices();
    synth.addEventListener("voiceschanged", fillVoices); // Chrome loads voices late
  }

  function currentVoice() {
    const uri = voiceSelect && voiceSelect.value;
    return (uri && synth.getVoices().find((v) => v.voiceURI === uri)) || null;
  }

  // --- reading ------------------------------------------------------------
  function sentences(text) {
    // One utterance per sentence: Chrome cuts long utterances off after ~15 s.
    const parts = text.replace(/\s+/g, " ").trim().match(/[^.!?…]+[.!?…]*["'”’)\]]*\s*/g);
    return (parts || [text]).map((s) => s.trim()).filter(Boolean);
  }

  let current = null; // { box, timer, tick, token, pass }
  let tokens = 0;

  function reset(box) {
    const button = box.querySelector("[data-speak]");
    button.textContent = "▶ Read to me";
    button.setAttribute("aria-pressed", "false");
    box.querySelector("[data-pass]").textContent = "";
    const item = box.closest("li");
    if (item) item.classList.remove("reading");
  }

  function stop() {
    if (!current) return;
    clearTimeout(current.timer);
    clearInterval(current.tick);
    current.token = -1; // ignore the cancelled utterances' end events
    const box = current.box;
    current = null;
    synth.cancel();
    reset(box);
  }

  function bodyText(run) {
    const body = run.box.parentElement.querySelector(".answer-body");
    return body ? body.textContent : "";
  }

  function utterance(run, text) {
    const u = new SpeechSynthesisUtterance(text);
    const voice = currentVoice();
    if (voice) { u.voice = voice; u.lang = voice.lang; }
    u.rate = parseFloat(rateSelect ? rateSelect.value : "1") || 1;
    const token = run.token;
    u.onerror = (e) => {
      if (current === run && run.token === token && e.error !== "interrupted" && e.error !== "canceled") stop();
    };
    return u;
  }

  // Calls fn when the utterance finishes, unless the run was stopped meanwhile.
  function onEnd(run, u, fn) {
    const token = run.token;
    u.onend = () => current === run && run.token === token && fn();
  }

  function setStatus(run, text) {
    run.box.querySelector("[data-pass]").textContent = text;
  }

  // After each read: the user's turn every N reads, then another read if repeating.
  function afterPass(run) {
    const every = parseInt(rehearseSelect ? rehearseSelect.value : "0", 10) || 0;
    if (every && run.pass % every === 0) yourTurn(run);
    else next(run);
  }

  function next(run) {
    if (run.box.querySelector("[data-repeat]").checked) {
      run.timer = setTimeout(() => current === run && speakPass(run), PAUSE_MS);
    } else {
      stop();
    }
  }

  function clock(seconds) {
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }

  // Say so, then stay quiet for as long as the text takes to say, counting down.
  function yourTurn(run) {
    const words = bodyText(run).split(/\s+/).filter(Boolean).length;
    let left = Math.max(5, Math.round((words * 60) / WORDS_PER_MINUTE));
    const u = utterance(run, YOUR_TURN);
    onEnd(run, u, () => {
      setStatus(run, "your turn · " + clock(left));
      run.tick = setInterval(() => {
        left -= 1;
        if (left > 0) return setStatus(run, "your turn · " + clock(left));
        clearInterval(run.tick);
        setStatus(run, "");
        if (current === run) next(run);
      }, 1000);
    });
    synth.speak(u);
  }

  function speakPass(run) {
    const chunks = sentences(bodyText(run));
    if (!chunks.length) return stop();
    run.pass += 1;
    setStatus(run, run.pass > 1 ? "pass " + run.pass : "");
    chunks.forEach((text, i) => {
      const u = utterance(run, text);
      if (i === chunks.length - 1) onEnd(run, u, () => afterPass(run));
      synth.speak(u);
    });
  }

  function start(box) {
    stop();
    synth.cancel(); // anything else speaking on this page
    const run = { box, timer: null, tick: null, token: ++tokens, pass: 0 };
    current = run;
    const button = box.querySelector("[data-speak]");
    button.textContent = "■ Stop";
    button.setAttribute("aria-pressed", "true");
    const item = box.closest("li");
    if (item) item.classList.add("reading");
    speakPass(run);
  }

  document.addEventListener("click", (e) => {
    const button = e.target.closest("[data-speak]");
    if (!button) return;
    const box = button.closest("[data-read-aloud]");
    if (current && current.box === box) stop();
    else start(box);
  });

  // Show the controls, including on answers added later (a new recording,
  // or a finished transcript swapped in by htmx).
  function reveal(root) {
    root.querySelectorAll("[data-read-aloud]").forEach((el) => (el.hidden = false));
  }
  reveal(document);
  new MutationObserver(() => reveal(document)).observe(document.body, { childList: true, subtree: true });

  // Stop if the answer being read is replaced, and when leaving the page.
  document.body.addEventListener("htmx:beforeSwap", (e) => {
    if (current && e.detail.target && e.detail.target.contains(current.box)) stop();
  });
  window.addEventListener("pagehide", () => synth.cancel());
})();
