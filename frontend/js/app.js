/* Entry point: landing page, the two login screens, and routing by role. */
(function () {
  const P = (window.PMA = window.PMA || {});
  const h = P.h;

  async function logout() {
    try { await P.api("POST", "/auth/logout"); } catch (e) { /* already signed out */ }
    landing();
  }

  function shell(title, subtitle, ...body) {
    return h("div", { class: "auth-wrap" }, h("div", { class: "auth-card" },
      h("h1", {}, title), subtitle ? h("p", { class: "muted" }, subtitle) : null, body));
  }

  function landing() {
    P.mount(h("div", { class: "auth-wrap" }, h("div", { class: "auth-card wide" },
      h("h1", {}, "PMA Teaching Assistant"),
      h("p", { class: "muted" }, "Probability Models and Applications. Answers grounded in your course material."),
      h("div", { class: "choices" },
        h("button", { class: "choice", type: "button", onclick: studentLogin },
          h("span", { class: "choice-title" }, "Student"), h("span", { class: "muted" }, "Ask questions and revisit your past chats")),
        h("button", { class: "choice", type: "button", onclick: adminLogin },
          h("span", { class: "choice-title" }, "Admin / Instructor"), h("span", { class: "muted" }, "Upload notes and manage material"))))));
  }

  function form(title, subtitle, fields, submitLabel, onSubmit) {
    const err = h("div", { class: "err", role: "alert" });
    const btn = h("button", { class: "btn primary block", type: "submit" }, submitLabel);
    const f = h("form", { novalidate: true }, fields.map((x) => x.label), err, btn,
      h("button", { class: "link", type: "button", onclick: landing }, "← Back"));
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault(); err.textContent = ""; btn.disabled = true;
      try { await onSubmit(); } catch (e) { err.textContent = e.message; btn.disabled = false; }
    });
    P.mount(shell(title, subtitle, f));
    fields[0].input.focus();
  }

  function field(label, attrs) {
    const input = h("input", attrs);
    return { input, label: h("label", {}, h("span", {}, label), input) };
  }

  function studentLogin() {
    const reg = field("Register number", { type: "text", autocomplete: "username", autocapitalize: "characters", maxlength: "25", required: true });
    form("Student sign in", "Enter your register number. Your chat history is saved under it.", [reg], "Continue",
      async () => { const me = await P.api("POST", "/auth/student/login", { reg_no: reg.input.value }); route(me); });
  }

  function adminLogin() {
    const u = field("Username", { type: "text", autocomplete: "username", required: true });
    const p = field("Password", { type: "password", autocomplete: "current-password", required: true });
    form("Admin sign in", null, [u, p], "Sign in",
      async () => { const me = await P.api("POST", "/auth/admin/login", { username: u.input.value, password: p.input.value }); route(me); });
  }

  function route(me) {
    P.onUnauthorized = () => { P.toast("Your session expired. Please sign in again.", "error"); landing(); };
    P.mount(me.role === "admin" ? P.adminView(me, logout) : P.studentView(me, logout));
  }

  async function start() {
    try { route(await P.api("GET", "/auth/me")); } catch (e) { landing(); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
