// Kanban drag-and-drop: after a drop, send each affected column's new order.
(function () {
  function save(list) {
    const body = new FormData();
    body.append("status", list.dataset.status);
    list.querySelectorAll(".card").forEach((card) => body.append("ids", card.dataset.id));
    return fetch("/board/reorder", { method: "POST", body }).then((res) => {
      if (!res.ok) throw new Error("Save failed: " + res.status);
    });
  }

  function updateCounts() {
    document.querySelectorAll(".column").forEach((col) => {
      col.querySelector(".col-count").textContent = col.querySelectorAll(".card").length;
    });
  }

  document.querySelectorAll(".cards").forEach((list) => {
    Sortable.create(list, {
      group: "board",
      animation: 150,
      ghostClass: "card-ghost",
      onEnd(evt) {
        const lists = evt.from === evt.to ? [evt.to] : [evt.from, evt.to];
        updateCounts();
        Promise.all(lists.map(save)).catch((err) => {
          alert(err.message + " — reloading the board.");
          location.reload();
        });
      },
    });
  });
})();
