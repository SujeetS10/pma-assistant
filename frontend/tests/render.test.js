// Run:  node --test frontend/tests/
const test = require("node:test");
const assert = require("node:assert");
const { renderMarkdown: md } = require("../js/render.js");

test("raw HTML and script tags are escaped", () => {
  const out = md('<script>alert(1)</script> <img src=x onerror=alert(1)>');
  assert.ok(!/<script|<img/i.test(out));
  assert.ok(out.includes("&lt;script&gt;"));
});

test("attribute-breaking quotes cannot create elements", () => {
  const out = md('"><svg onload=alert(1)> and \' onmouseover=\'x');
  assert.ok(!/<svg/i.test(out));
});

test("math is kept verbatim and escaped, not formatted", () => {
  const out = md("Mean is $E[X]=1/p$ and $$\\frac{a}{b}$$ with <b>x</b>");
  assert.ok(out.includes("$E[X]=1/p$"));
  assert.ok(out.includes("$$\\frac{a}{b}$$"));
  assert.ok(!out.includes("<b>x</b>"));
});

test("math content is not touched by markdown (underscores, asterisks)", () => {
  const out = md("$a_1 * b_2 * c_3$");
  assert.ok(out.includes("a_1 * b_2 * c_3"));
  assert.ok(!out.includes("<em>"));
});

test("dollar amounts are not mistaken for math", () => {
  const out = md("It costs $5 and then $6 more.");
  assert.ok(!out.includes("math"));
  assert.ok(out.includes("$5 and then $6"));
});

test("html inside math is escaped", () => {
  const out = md("$<img src=x onerror=alert(1)>$");
  assert.ok(!/<img/i.test(out));
});

test("valid citation becomes a button, unknown marker is dropped", () => {
  const out = md("Fact [S1] and bogus [S9].", [1]);
  assert.ok(out.includes('class="cite" data-n="1"'));
  assert.ok(!out.includes("S9"));
});

test("code fences are escaped", () => {
  const out = md("```\n<b>&</b>\n```");
  assert.ok(out.includes("<pre><code>&lt;b&gt;&amp;&lt;/b&gt;</code></pre>"));
});

test("lists, headings, bold, italics", () => {
  const out = md("# Title\n\n- a\n- b\n\n1. x\n2. y\n\n**bold** and *it*");
  assert.ok(out.includes("<h3>Title</h3>"));
  assert.ok(out.includes("<ul><li>a</li><li>b</li></ul>"));
  assert.ok(out.includes("<ol><li>x</li><li>y</li></ol>"));
  assert.ok(out.includes("<strong>bold</strong>") && out.includes("<em>it</em>"));
});

test("placeholder control characters in input cannot smuggle content", () => {
  const out = md("evil \uE0000\uE001 text $x$");
  assert.ok(!out.includes("\uE000"));
});

test("links and images are never produced", () => {
  const out = md("[click](javascript:alert(1)) ![i](http://x/y.png)");
  assert.ok(!/<a |<img/i.test(out));
});
