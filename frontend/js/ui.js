/* Small DOM helpers. Text is always set with textContent / text nodes, never innerHTML. */
(function () {
  const P = (window.PMA = window.PMA || {});

  P.h = function (tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  };

  P.mount = function (node) {
    document.getElementById("app").replaceChildren(node);
  };

  P.toast = function (msg, kind) {
    const t = P.h("div", { class: "toast " + (kind || "") }, msg);
    document.getElementById("toasts").append(t);
    setTimeout(() => t.remove(), kind === "error" ? 6000 : 3000);
  };

  P.fmtDate = (ts) =>
    new Date(ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

  P.fmtSize = function (b) {
    if (b < 1024) return b + " B";
    if (b < 1048576) return (b / 1024).toFixed(0) + " KB";
    return (b / 1048576).toFixed(1) + " MB";
  };

  P.pages = function (s) {
    if (s.page_start === null || s.page_start === undefined) return "";
    return s.page_start === s.page_end ? "p. " + s.page_start : "pp. " + s.page_start + "-" + s.page_end;
  };
})();
