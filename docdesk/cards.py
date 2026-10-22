"""The MCP Apps card (ui://docdesk/card.html). A host that supports MCP Apps renders it in a
sandboxed iframe and sends it the tool result; it then draws the answer, its sources, open
tickets, and "good news" updates. Hosts without MCP Apps still get the spoken text."""

CARD_URI = "ui://docdesk/card.html"

CARD_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { --bg:#ffffff; --ink:#14212b; --muted:#5b6b78; --line:#dfe6eb; --accent:#0a7ea4;
          --good:#1f7a4d; --goodbg:#e8f5ee; --warn:#9a5b00; --warnbg:#fff4e0; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16212a; --ink:#e7eef3; --muted:#9db0bf; --line:#2a3a46; --accent:#4cc3eb;
            --good:#6fd39e; --goodbg:#173326; --warn:#ffc46b; --warnbg:#3a2a10; }
  }
  * { box-sizing:border-box; }
  html, body { overflow:hidden; } body { margin:0; font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }
  .card { padding:14px 16px; }
  .label { font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }
  .answer { margin:0 0 10px; }
  .src { display:block; padding:8px 10px; border:1px solid var(--line); border-radius:8px; margin:6px 0;
         color:var(--accent); text-decoration:none; font-size:13px; cursor:pointer; background:none; width:100%; text-align:left; font-family:inherit; }
  .src:hover { border-color:var(--accent); }
  .ticket { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:8px 0; }
  .ticket b { font-variant-numeric:tabular-nums; }
  .pill { display:inline-block; font-size:11px; padding:2px 8px; border-radius:99px; margin-left:6px; vertical-align:1px; }
  .open { background:var(--warnbg); color:var(--warn); }
  .done { background:var(--goodbg); color:var(--good); }
  .update { background:var(--goodbg); border-radius:10px; padding:10px 12px; margin:0 0 12px; }
  .update .label { color:var(--good); }
  .muted { color:var(--muted); font-size:13px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  td { padding:6px 4px; border-top:1px solid var(--line); vertical-align:top; }
  td.n { text-align:right; font-variant-numeric:tabular-nums; width:3em; }
</style></head>
<body><div class="card" id="root"><p class="muted">Waiting for DocDesk...</p></div>
<script>
(function () {
  var root = document.getElementById("root");
  var nextId = 1;
  function send(msg) { window.parent.postMessage(Object.assign({ jsonrpc: "2.0" }, msg), "*"); }
  function request(method, params) { send({ id: nextId++, method: method, params: params || {} }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var lastHeight = 0;
  function size() {
    var h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (h !== lastHeight) { lastHeight = h; send({ method: "ui/notifications/size-changed", params: { height: h } }); }
  }
  if (window.ResizeObserver) new ResizeObserver(size).observe(document.documentElement);

  function sources(list) {
    if (!list || !list.length) return "";
    return '<p class="label">From the help centre</p>' + list.map(function (s, i) {
      return '<button class="src" data-url="' + esc(s.url) + '">' + esc(s.title) + "</button>";
    }).join("");
  }
  function ticket(t) {
    var open = t.status === "open";
    var pill = open ? '<span class="pill open">Open</span>' : '<span class="pill done">Answered</span>';
    var body = '<div class="ticket"><b>Ticket ' + t.id + "</b>" + pill + "<div>" + esc(t.question) + "</div>";
    if (t.details) body += '<div class="muted">Added: ' + esc(t.details) + "</div>";
    body += '<div class="muted">Opened ' + esc(t.opened) + "</div>";
    if (t.resolution) body += "<div>" + esc(t.resolution) + "</div>";
    return body + "</div>";
  }
  function updates(list) {
    return (list || []).map(function (u) {
      var who = u.resolved_by === "docs" ? "Answered by a new help article" : "The support team replied";
      return '<div class="update"><p class="label">Good news: ticket ' + u.ticket_id + "</p><div><b>" + esc(u.question) +
        "</b></div><div>" + esc(u.answer) + '</div><div class="muted">' + who + "</div>" + sources(u.sources) + "</div>";
    }).join("");
  }
  function render(sc, text) {
    var html = "";
    if (!sc) { root.innerHTML = "<p>" + esc(text) + "</p>"; size(); return; }
    html += updates(sc.updates);
    if (sc.status === "answered") {
      html += sources(sc.sources) || '<p class="muted">Answered from the help centre.</p>';
    } else if (sc.status === "ticket_opened" || sc.status === "added_to_ticket") {
      html += '<p class="label">' + (sc.status === "ticket_opened" ? "Passed to the support team" : "Added to your ticket") +
        "</p>" + ticket(sc.ticket);
    } else if (sc.open) {
      html += sc.open.length ? '<p class="label">Your open tickets</p>' + sc.open.map(ticket).join("")
                             : (sc.updates && sc.updates.length ? "" : '<p class="muted">No open tickets.</p>');
    } else if (sc.topics) {
      html += '<p class="label">Doc gaps, last ' + esc(sc.days) + " days</p><p>" + sc.answered + " of " + sc.questions +
        " questions answered from the docs. " + sc.open_tickets + " tickets open.</p>";
      html += sc.topics.length ? "<table>" + sc.topics.map(function (g) {
        return "<tr><td>" + esc(g.topic) + '<div class="muted">' + g.examples.map(esc).join("<br>") +
          '</div></td><td class="n">' + g.count + "</td></tr>"; }).join("") + "</table>" : "";
    } else {
      html += "<p>" + esc(sc.speech || text) + "</p>";
    }
    root.innerHTML = html;
    size();
  }

  root.addEventListener("click", function (e) {
    var b = e.target.closest(".src");
    if (b) request("ui/open-link", { url: b.getAttribute("data-url") });
  });
  window.addEventListener("message", function (e) {
    var m = e.data || {};
    if (m.method === "ui/notifications/tool-result") {
      var p = m.params || {};
      var text = (p.content || []).filter(function (c) { return c.type === "text"; }).map(function (c) { return c.text; }).join(" ");
      render(p.structuredContent, text);
    }
  });
  request("ui/initialize", { appInfo: { name: "docdesk-card", version: "1.0.0" }, appCapabilities: {}, protocolVersion: "2026-01-26" });
  send({ method: "ui/notifications/initialized", params: {} });
})();
</script></body></html>
"""
