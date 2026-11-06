// Tag pills under a comma-separated tags field: clicking one appends that tag
// to the field (once). Pills for tags already in the field are dimmed.
(function () {
  function tagsIn(input) {
    return input.value.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean);
  }

  document.querySelectorAll("[data-tag-picker]").forEach((picker) => {
    const input = document.querySelector(picker.dataset.tagPicker);
    if (!input) return;
    const pills = picker.querySelectorAll("[data-tag]");

    function mark() {
      const have = tagsIn(input);
      pills.forEach((p) => p.setAttribute("aria-pressed", have.includes(p.dataset.tag.toLowerCase()) ? "true" : "false"));
    }

    picker.addEventListener("click", (e) => {
      const pill = e.target.closest("[data-tag]");
      if (!pill) return;
      const tag = pill.dataset.tag;
      if (!tagsIn(input).includes(tag.toLowerCase())) {
        const current = input.value.replace(/[\s,]+$/, "");
        input.value = current ? current + ", " + tag : tag;
      }
      mark();
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    });

    input.addEventListener("input", mark);
    mark();
  });
})();
