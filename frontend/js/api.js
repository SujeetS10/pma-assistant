/* Thin fetch wrapper. The session lives in an HttpOnly cookie; JavaScript never sees a token or the LLM API key. */
(function () {
  const P = (window.PMA = window.PMA || {});

  class ApiError extends Error {
    constructor(message, status) { super(message); this.status = status; }
  }
  P.ApiError = ApiError;

  P.api = async function (method, path, body, isForm) {
    const opt = { method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      if (isForm) opt.body = body;
      else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    }
    let res;
    try { res = await fetch("/api" + path, opt); }
    catch (e) { throw new ApiError("Cannot reach the server. Check your connection.", 0); }
    const text = await res.text();
    let data = null;
    if (text) { try { data = JSON.parse(text); } catch (e) { /* non-JSON error page */ } }
    if (!res.ok) {
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join("; ");
      if (!msg) msg = "Request failed (" + res.status + ").";
      if (res.status === 401 && P.onUnauthorized && !path.endsWith("/login")) P.onUnauthorized();
      throw new ApiError(msg, res.status);
    }
    return data;
  };
})();
