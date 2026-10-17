// Small helpers so the website behaves like the desktop app. Every page also works without it.
// 1. Click a table heading to sort (click again to reverse), like the desktop tables.
// 2. Click (or press Enter on) a row to open it, like double-clicking a row in the app.
// 3. Ask before a destructive button (delete) is sent.
document.querySelectorAll("table.data").forEach(function (table) {
  table.querySelectorAll("th button[data-sort]").forEach(function (button) {
    button.addEventListener("click", function () {
      var col = Number(button.dataset.sort);
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows).filter(function (r) { return !r.classList.contains("empty"); });
      var reverse = button.dataset.dir === "asc";
      table.querySelectorAll("th button").forEach(function (b) { b.dataset.dir = ""; b.textContent = b.textContent.replace(/ [▲▼]$/, ""); });
      button.dataset.dir = reverse ? "desc" : "asc";
      button.textContent += reverse ? " ▼" : " ▲";
      function key(row) {
        var cell = row.cells[col];
        if (cell.dataset.v !== undefined) return Number(cell.dataset.v);
        var text = cell.textContent.trim();
        return text === "—" ? null : text;
      }
      rows.sort(function (a, b) {
        var x = key(a), y = key(b);
        if (x === null) return 1;            // missing values always last
        if (y === null) return -1;
        var order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
        return reverse ? -order : order;
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
  table.querySelectorAll("tr[data-href]").forEach(function (row) {
    row.addEventListener("click", function (e) { if (!e.target.closest("a")) location.href = row.dataset.href; });
    row.addEventListener("keydown", function (e) { if (e.key === "Enter") location.href = row.dataset.href; });
  });
});
document.querySelectorAll("button[data-confirm]").forEach(function (button) {
  button.addEventListener("click", function (e) { if (!confirm(button.dataset.confirm)) e.preventDefault(); });
});
