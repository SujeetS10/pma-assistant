/* Student view: chat + saved history, all tied to the register number in the session. */
(function () {
  const P = (window.PMA = window.PMA || {});
  const h = P.h;

  P.studentView = function (me, onLogout) {
    const state = { convId: null, convs: [], sending: false };

    const convList = h("div", { class: "conv-list" });
    const messagesEl = h("div", { class: "messages", tabindex: "0" });
    const input = h("textarea", { rows: "1", placeholder: "Ask a question about the course…", maxlength: "2000",
      "aria-label": "Your question" });
    const sendBtn = h("button", { class: "btn primary", type: "button" }, "Send");
    const drawer = h("aside", { class: "drawer hidden", "aria-label": "Source details" });
    const sidebar = h("nav", { class: "sidebar", "aria-label": "Chat history" });

    // ---------- drawer (source viewer / library) ----------
    function openDrawer(title, bodyNodes) {
      drawer.replaceChildren(
        h("div", { class: "drawer-head" }, h("strong", {}, title),
          h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: () => drawer.classList.add("hidden") }, "×")),
        h("div", { class: "drawer-body" }, bodyNodes));
      drawer.classList.remove("hidden");
    }
    function showSource(s) {
      openDrawer("Source S" + s.n, [
        h("div", { class: "src-title" }, s.doc_title),
        h("div", { class: "muted" }, [P.pages(s), s.section].filter(Boolean).join(" · ") || "No page information"),
        h("pre", { class: "snippet" }, s.snippet + (s.snippet.length >= 500 ? "…" : "")),
        h("p", { class: "muted small" }, "This is the passage the assistant was shown. Check the original material for the full context."),
      ]);
    }
    async function showLibrary() {
      try {
        const docs = await P.api("GET", "/student/library");
        openDrawer("Course material available", docs.length
          ? h("ul", { class: "lib-list" }, docs.map((d) => h("li", {}, d.title, h("span", { class: "muted small" }, d.kind === "note" ? " · note" : d.pages ? " · " + d.pages + " pages" : ""))))
          : h("p", { class: "muted" }, "No material has been uploaded yet. Ask your instructor."));
      } catch (e) { P.toast(e.message, "error"); }
    }

    // ---------- messages ----------
    function messageEl(m) {
      const isUser = m.role === "user";
      const bubble = h("div", { class: "bubble" });
      const wrap = h("div", { class: "msg " + (isUser ? "user" : "assistant") + (m.abstained ? " abstained" : "") }, bubble);
      if (isUser) {
        bubble.textContent = m.content;
      } else {
        const srcs = m.sources || [];
        bubble.innerHTML = P.renderMarkdown(m.content, srcs.map((s) => s.n)); // renderer escapes everything it does not emit
        P.typeset(bubble);
        bubble.addEventListener("click", (ev) => {
          const b = ev.target.closest(".cite");
          const s = b && srcs.find((x) => x.n === Number(b.dataset.n));
          if (s) showSource(s);
        });
        if (srcs.length) {
          wrap.append(h("div", { class: "sources" }, h("span", { class: "muted small" }, "Sources:"),
            srcs.map((s) => h("button", { class: "chip", type: "button", onclick: () => showSource(s) },
              "S" + s.n + " · " + s.doc_title + (P.pages(s) ? " · " + P.pages(s) : "")))));
        } else if (m.abstained) {
          wrap.append(h("div", { class: "tag" }, "Not found in course material"));
        } else if (m.grounded === false) {
          wrap.append(h("div", { class: "tag warn" }, "No source cited. Verify before relying on this"));
        }
      }
      return wrap;
    }
    const scrollDown = () => { messagesEl.scrollTop = messagesEl.scrollHeight; };
    function emptyState() {
      messagesEl.replaceChildren(h("div", { class: "empty" },
        h("h2", {}, "Ask anything from your course"),
        h("p", { class: "muted" }, "Answers come only from the material your instructor uploaded, with sources you can open. If it isn't covered, the assistant will say so."),
        h("button", { class: "btn", type: "button", onclick: showLibrary }, "See what's covered")));
    }

    // ---------- history ----------
    function drawConvs() {
      convList.replaceChildren(...(state.convs.length ? state.convs.map((c) =>
        h("div", { class: "conv" + (c.id === state.convId ? " active" : "") },
          h("button", { class: "conv-open", type: "button", onclick: () => openConv(c.id), title: c.title },
            h("span", { class: "conv-title" }, c.title), h("span", { class: "muted small" }, P.fmtDate(c.updated_at))),
          h("button", { class: "icon-btn", type: "button", "aria-label": "Delete conversation", onclick: () => delConv(c) }, "🗑")))
        : [h("p", { class: "muted small pad" }, "Your past chats will appear here.")]));
    }
    async function loadConvs() {
      try { state.convs = await P.api("GET", "/student/conversations"); drawConvs(); }
      catch (e) { P.toast(e.message, "error"); }
    }
    async function openConv(id) {
      try {
        const data = await P.api("GET", "/student/conversations/" + id);
        state.convId = id;
        messagesEl.replaceChildren(...data.messages.map(messageEl));
        drawConvs(); scrollDown(); sidebar.classList.remove("open");
      } catch (e) { P.toast(e.message, "error"); }
    }
    async function delConv(c) {
      if (!confirm('Delete "' + c.title + '" from your history? This cannot be undone.')) return;
      try {
        await P.api("DELETE", "/student/conversations/" + c.id);
        if (state.convId === c.id) newChat();
        await loadConvs();
      } catch (e) { P.toast(e.message, "error"); }
    }
    function newChat() {
      state.convId = null; emptyState(); drawConvs(); input.focus(); sidebar.classList.remove("open");
    }

    // ---------- sending ----------
    async function send() {
      const text = input.value.trim();
      if (!text || state.sending) return;
      state.sending = true; sendBtn.disabled = true; input.value = ""; autosize();
      if (messagesEl.querySelector(".empty")) messagesEl.replaceChildren();
      messagesEl.append(messageEl({ role: "user", content: text }));
      const pending = h("div", { class: "msg assistant" }, h("div", { class: "bubble typing" }, "Searching the course material…"));
      messagesEl.append(pending); scrollDown();
      try {
        const r = await P.api("POST", "/student/chat", { conversation_id: state.convId, message: text });
        state.convId = r.conversation_id;
        pending.replaceWith(messageEl({ role: "assistant", content: r.answer, sources: r.sources, abstained: r.abstained, grounded: r.grounded }));
        await loadConvs();
      } catch (e) {
        pending.remove();
        input.value = text; autosize();
        P.toast(e.message, "error");
      } finally {
        state.sending = false; sendBtn.disabled = false; scrollDown(); input.focus();
      }
    }
    function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; }
    input.addEventListener("input", autosize);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
    sendBtn.addEventListener("click", send);

    sidebar.append(
      h("div", { class: "sidebar-top" }, h("button", { class: "btn primary block", type: "button", onclick: newChat }, "+ New chat")),
      h("div", { class: "sidebar-label muted small" }, "Your history"),
      convList,
      h("div", { class: "sidebar-foot" },
        h("button", { class: "btn block", type: "button", onclick: showLibrary }, "Course material"),
        h("div", { class: "who" }, h("span", { class: "muted small" }, "Signed in as"), h("strong", {}, me.subject)),
        h("button", { class: "btn block", type: "button", onclick: onLogout }, "Sign out")));

    const root = h("div", { class: "chat-layout" }, sidebar,
      h("main", { class: "chat-main" },
        h("header", { class: "chat-head" },
          h("button", { class: "icon-btn menu", type: "button", "aria-label": "Menu", onclick: () => sidebar.classList.toggle("open") }, "☰"),
          h("strong", {}, "PMA Teaching Assistant"), h("span", { class: "muted small" }, "Probability Models and Applications")),
        messagesEl,
        h("div", { class: "composer" }, input, sendBtn),
        h("div", { class: "disclaimer muted small" }, "AI can make mistakes. Check sources before relying on an answer.")),
      drawer);

    emptyState();
    loadConvs();
    return root;
  };
})();
