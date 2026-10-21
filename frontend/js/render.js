/* Minimal, XSS-safe Markdown + LaTeX renderer for assistant answers.
 * Order matters: pull out code and math FIRST, escape everything else, THEN apply formatting.
 * Output contains only tags this file emits itself. No links, images or raw HTML are ever produced.
 */
(function () {
  const G = typeof window !== "undefined" ? window : globalThis;
  const P = (G.PMA = G.PMA || {});
  const OPEN = "\uE000", CLOSE = "\uE001";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function renderMarkdown(src, citeNumbers) {
    const cites = new Set(citeNumbers || []);
    const stash = [];
    const hold = (html) => { stash.push(html); return OPEN + (stash.length - 1) + CLOSE; };
    let t = String(src || "").replace(/\r\n?/g, "\n").split(OPEN).join("").split(CLOSE).join("");

    // 1. fenced code, 2. display math, 3. inline math (all kept verbatim, escaped on restore)
    t = t.replace(/```[^\n]*\n([\s\S]*?)```/g, (_, code) => hold("<pre><code>" + esc(code.replace(/\n$/, "")) + "</code></pre>"));
    t = t.replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => hold('<span class="math-display">' + esc("$$" + m + "$$") + "</span>"));
    t = t.replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => hold('<span class="math-display">' + esc("$$" + m + "$$") + "</span>"));
    t = t.replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => hold("<span>" + esc("$" + m + "$") + "</span>"));
    t = t.replace(/\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g, (_, m) => hold("<span>" + esc("$" + m + "$") + "</span>"));
    t = t.replace(/`([^`\n]+)`/g, (_, c) => hold("<code>" + esc(c) + "</code>"));

    function inline(line) {
      let s = esc(line);
      s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
      s = s.replace(/\[S(\d+)\]/g, (m, n) =>
        cites.has(Number(n)) ? '<button type="button" class="cite" data-n="' + n + '">' + n + "</button>" : "");
      return s;
    }

    const out = [];
    let list = null; // {tag, items}
    let para = [];
    const flushPara = () => { if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; } };
    const flushList = () => {
      if (list) { out.push("<" + list.tag + ">" + list.items.map((i) => "<li>" + inline(i) + "</li>").join("") + "</" + list.tag + ">"); list = null; }
    };

    for (const line of t.split("\n")) {
      let m;
      if (!line.trim()) { flushPara(); flushList(); }
      else if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) {
        flushPara(); flushList();
        const lvl = Math.min(m[1].length + 2, 6);
        out.push("<h" + lvl + ">" + inline(m[2]) + "</h" + lvl + ">");
      } else if ((m = /^\s*[-*]\s+(.*)$/.exec(line))) {
        flushPara();
        if (!list || list.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; }
        list.items.push(m[1]);
      } else if ((m = /^\s*\d+[.)]\s+(.*)$/.exec(line))) {
        flushPara();
        if (!list || list.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; }
        list.items.push(m[1]);
      } else if ((m = /^>\s?(.*)$/.exec(line))) {
        flushPara(); flushList();
        out.push("<blockquote>" + inline(m[1]) + "</blockquote>");
      } else { flushList(); para.push(line); }
    }
    flushPara(); flushList();

    const re = new RegExp(OPEN + "(\\d+)" + CLOSE, "g");
    let html = out.join("");
    // restore stashed pieces (nested stash entries cannot occur, one pass is enough)
    return html.replace(re, (_, i) => stash[Number(i)] || "");
  }

  P.renderMarkdown = renderMarkdown;
  P.escapeHtml = esc;

  /* Typeset math inside an element if KaTeX has loaded; otherwise leave the LaTeX visible. */
  P.typeset = function (el) {
    if (typeof G.renderMathInElement === "function") {
      try {
        G.renderMathInElement(el, {
          delimiters: [{ left: "$$", right: "$$", display: true }, { left: "$", right: "$", display: false }],
          throwOnError: false,
        });
      } catch (e) { /* leave raw LaTeX */ }
    }
  };

  if (typeof module !== "undefined" && module.exports) module.exports = { renderMarkdown, esc };
})();
