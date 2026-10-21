/* Admin view: upload files / notes, manage the shared knowledge base and student access. */
(function () {
  const P = (window.PMA = window.PMA || {});
  const h = P.h;

  P.adminView = function (me, onLogout) {
    let timer = null;
    const statsEl = h("div", { class: "stats" });
    const docsBody = h("tbody");
    const fileInput = h("input", { type: "file", accept: ".pdf,.docx,.txt,.md", id: "file" });
    const titleInput = h("input", { type: "text", placeholder: "Title (optional)", maxlength: "200" });
    const uploadBtn = h("button", { class: "btn primary", type: "button" }, "Upload");
    const noteTitle = h("input", { type: "text", placeholder: "Note title", maxlength: "200" });
    const noteText = h("textarea", { rows: "6", placeholder: "Paste lecture notes, formulas, FAQs… (LaTeX like $x^2$ is fine)" });
    const noteBtn = h("button", { class: "btn primary", type: "button" }, "Add note");
    const modeSel = h("select", {}, h("option", { value: "open" }, "Open: any valid register number can sign in"),
      h("option", { value: "roster" }, "Restricted: only register numbers on the list below"));
    const rosterText = h("textarea", { rows: "3", placeholder: "Paste register numbers separated by spaces, commas or new lines" });
    const rosterList = h("div", { class: "roster-list" });
    let rosterCount = 0;

    const badge = (s) => h("span", { class: "badge " + s }, s);

    async function loadAll() {
      try {
        const [stats, docs] = await Promise.all([P.api("GET", "/admin/stats"), P.api("GET", "/admin/documents")]);
        statsEl.replaceChildren(...[["Ready documents", stats.documents_ready], ["Students", stats.students],
          ["Chats", stats.conversations], ["Questions asked", stats.questions_asked]].map(([k, v]) =>
          h("div", { class: "stat" }, h("div", { class: "stat-n" }, v), h("div", { class: "muted small" }, k))));
        docsBody.replaceChildren(...(docs.length ? docs.map((d) =>
          h("tr", {},
            h("td", {}, h("div", { class: "doc-title" }, d.title), d.error ? h("div", { class: "err small" }, d.error) : null),
            h("td", {}, d.kind), h("td", {}, badge(d.status)),
            h("td", {}, d.status === "ready" ? d.chunks + " chunks" + (d.pages ? " · " + d.pages + " pp" : "") : "–"),
            h("td", {}, P.fmtSize(d.size_bytes)), h("td", {}, P.fmtDate(d.created_at)),
            h("td", {}, h("button", { class: "btn danger small", type: "button", onclick: () => del(d) }, "Delete"))))
          : [h("tr", {}, h("td", { colspan: "7", class: "muted pad" }, "Nothing uploaded yet."))]));
        const busy = docs.some((d) => d.status === "queued" || d.status === "processing");
        clearTimeout(timer);
        if (busy) timer = setTimeout(loadAll, 2500); // poll while indexing
      } catch (e) { P.toast(e.message, "error"); }
    }
    async function del(d) {
      if (!confirm('Delete "' + d.title + '"? Students will no longer get answers from it.')) return;
      try { await P.api("DELETE", "/admin/documents/" + d.id); P.toast("Deleted.", "ok"); loadAll(); }
      catch (e) { P.toast(e.message, "error"); }
    }
    async function upload() {
      const f = fileInput.files[0];
      if (!f) return P.toast("Choose a file first.", "error");
      const fd = new FormData(); fd.append("file", f); fd.append("title", titleInput.value);
      uploadBtn.disabled = true; uploadBtn.textContent = "Uploading…";
      try {
        await P.api("POST", "/admin/documents", fd, true);
        P.toast("Uploaded. Indexing in the background…", "ok");
        fileInput.value = ""; titleInput.value = ""; loadAll();
      } catch (e) { P.toast(e.message, "error"); }
      finally { uploadBtn.disabled = false; uploadBtn.textContent = "Upload"; }
    }
    async function addNote() {
      noteBtn.disabled = true;
      try {
        await P.api("POST", "/admin/notes", { title: noteTitle.value, text: noteText.value });
        P.toast("Note added. Indexing…", "ok"); noteTitle.value = ""; noteText.value = ""; loadAll();
      } catch (e) { P.toast(e.message, "error"); }
      finally { noteBtn.disabled = false; }
    }
    async function loadRoster() {
      try {
        const r = await P.api("GET", "/admin/roster");
        modeSel.value = r.mode; rosterCount = r.reg_nos.length;
        rosterList.replaceChildren(h("div", { class: "muted small" }, rosterCount + " register number(s) on the list"),
          h("div", { class: "chips" }, r.reg_nos.slice(0, 500).map((n) =>
            h("span", { class: "chip static" }, n, h("button", { class: "x", type: "button", "aria-label": "Remove " + n,
              onclick: async () => { await P.api("DELETE", "/admin/roster/" + encodeURIComponent(n)); loadRoster(); } }, "×")))));
      } catch (e) { P.toast(e.message, "error"); }
    }
    async function addRoster() {
      try {
        const r = await P.api("POST", "/admin/roster", { reg_nos: rosterText.value });
        P.toast("Added " + r.added + (r.invalid ? ", skipped " + r.invalid + " invalid" : "") + ".", "ok");
        rosterText.value = ""; loadRoster();
      } catch (e) { P.toast(e.message, "error"); }
    }
    modeSel.addEventListener("change", async () => {
      try { await P.api("PUT", "/admin/settings", { roster_mode: modeSel.value }); P.toast("Access mode saved.", "ok"); }
      catch (e) { P.toast(e.message, "error"); loadRoster(); }
    });
    uploadBtn.addEventListener("click", upload);
    noteBtn.addEventListener("click", addNote);

    const root = h("div", { class: "admin" },
      h("header", { class: "topbar" }, h("strong", {}, "PMA Teaching Assistant · Admin"),
        h("span", { class: "spacer" }), h("span", { class: "muted small" }, me.subject),
        h("button", { class: "btn small", type: "button", onclick: onLogout }, "Sign out")),
      h("main", { class: "admin-main" },
        statsEl,
        h("section", { class: "panel" }, h("h2", {}, "Add course material"),
          h("p", { class: "muted small" }, "PDF, DOCX, TXT or Markdown. Text-based PDFs only (scanned PDFs need OCR first). Everything you add becomes available to all students."),
          h("div", { class: "row" }, fileInput, titleInput, uploadBtn)),
        h("section", { class: "panel" }, h("h2", {}, "Add a note"), noteTitle, noteText, h("div", { class: "row end" }, noteBtn)),
        h("section", { class: "panel" }, h("h2", {}, "Knowledge base"),
          h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, ["Title", "Type", "Status", "Indexed", "Size", "Added", ""].map((c) => h("th", {}, c)))), docsBody))),
        h("section", { class: "panel" }, h("h2", {}, "Student access"),
          h("p", { class: "muted small" }, "Students sign in with a register number only. In open mode anyone who knows or guesses a number can read that student's history. Restrict access to a roster if that matters."),
          modeSel, rosterText, h("div", { class: "row end" }, h("button", { class: "btn", type: "button", onclick: addRoster }, "Add to list")), rosterList)));

    loadAll(); loadRoster();
    return root;
  };
})();
