// Profiles: tell the server which profile this page was rendered for, so a
// form left open in one tab can't post into another profile after a switch.
// htmx requests send it via hx-headers on <body>; plain forms get it here.
(function () {
  const profile = document.body.dataset.profile;
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!profile || form.method.toLowerCase() !== "post") return;
    const action = event.submitter && event.submitter.hasAttribute("formaction") ? event.submitter.formAction : form.action;
    const url = new URL(action, location.href);
    url.searchParams.set("_profile", profile);
    if (event.submitter && event.submitter.hasAttribute("formaction")) event.submitter.formAction = url.href;
    else form.action = url.href;
  });
  // htmx doesn't swap error responses, so show the server's explanation instead of failing silently.
  document.addEventListener("htmx:responseError", (event) => {
    const xhr = event.detail.xhr;
    if (xhr.status !== 409 || document.querySelector(".profile-stale")) return;
    const note = document.createElement("p");
    note.className = "profile-stale";
    note.setAttribute("role", "alert");
    note.textContent = xhr.responseText + " ";
    const reload = document.createElement("a");
    reload.href = location.href;
    reload.textContent = "Reload";
    note.append(reload);
    document.querySelector("main").prepend(note);
  });
})();
