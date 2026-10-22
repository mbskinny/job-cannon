// Interview prep: record an answer with the microphone, then upload it.
// The server stores the audio and transcribes it locally; the returned answer
// partial is added to the list and polls (htmx) until its transcript is ready.
(function () {
  const TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"];

  function fmt(seconds) {
    const s = Math.floor(seconds);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }

  document.querySelectorAll("[data-recorder]").forEach((root) => {
    const button = root.querySelector("[data-record]");
    const label = root.querySelector("[data-label]");
    const timer = root.querySelector("[data-timer]");
    const status = root.querySelector("[data-status]");
    const list = document.querySelector(root.dataset.target);
    const appSelect = document.querySelector(root.dataset.application);

    if (!navigator.mediaDevices || !window.MediaRecorder) {
      button.disabled = true;
      status.textContent = "This browser can't record audio here. Type your answer instead.";
      return;
    }

    let recorder = null, chunks = [], started = 0, tick = null;

    function setRecording(on) {
      root.classList.toggle("recording", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
      label.textContent = on ? "Stop" : "Record answer";
    }

    async function start() {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        status.textContent = "Couldn't use the microphone (" + err.name + "). Check the browser's permission for this site.";
        return;
      }
      const mimeType = TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      chunks = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        upload(new Blob(chunks, { type: recorder.mimeType || mimeType }), (Date.now() - started) / 1000);
      };
      recorder.start(1000);
      started = Date.now();
      timer.textContent = "0:00";
      tick = setInterval(() => (timer.textContent = fmt((Date.now() - started) / 1000)), 250);
      setRecording(true);
      status.textContent = "Recording…";
    }

    function stop() {
      clearInterval(tick);
      setRecording(false);
      button.disabled = true;
      status.textContent = "Saving…";
      recorder.stop();
    }

    async function upload(blob, duration) {
      const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
      const body = new FormData();
      body.append("audio", blob, "answer." + ext);
      body.append("duration", duration.toFixed(1));
      if (appSelect) body.append("application_id", appSelect.value);
      try {
        const res = await fetch(root.dataset.action, {
          method: "POST", body, headers: { "X-Job-Cannon-Profile": document.body.dataset.profile },
        });
        if (!res.ok) {
          const detail = res.status === 409 ? await res.text() : await res.json().then((j) => j.detail, () => "");
          throw new Error(detail || "HTTP " + res.status);
        }
        list.insertAdjacentHTML("afterbegin", await res.text());
        const item = list.firstElementChild;
        if (window.htmx) htmx.process(item);
        document.querySelectorAll("[data-empty]").forEach((el) => el.remove());
        status.textContent = "Saved.";
        item.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (err) {
        status.textContent = "Saving the recording failed: " + err.message;
      } finally {
        button.disabled = false;
      }
    }

    button.addEventListener("click", () => (recorder && recorder.state === "recording" ? stop() : start()));
  });
})();
