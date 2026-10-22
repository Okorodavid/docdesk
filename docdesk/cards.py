"""The MCP Apps card (ui://docdesk/card.html). A host that supports MCP Apps renders it in a
sandboxed iframe and sends it the tool result. It draws the answer's sources, open tickets,
"good news" updates, the doc gaps report, and guided walkthroughs: the brand's app screen with
a glowing highlight on the place to tap, one step at a time, while the host reads each step
aloud. Hosts without MCP Apps still get the complete spoken text."""

CARD_URI = "ui://docdesk/card.html"

CARD_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { --bg:#ffffff; --ink:#14212b; --muted:#5b6b78; --line:#dfe6eb; --accent:#0a7ea4;
          --good:#1f7a4d; --goodbg:#e8f5ee; --warn:#9a5b00; --warnbg:#fff4e0;
          --glow:#36c6f0; --phone:#0f1a22; --app:#f4f7f9; --tile:#ffffff; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16212a; --ink:#e7eef3; --muted:#9db0bf; --line:#2a3a46; --accent:#4cc3eb;
            --good:#6fd39e; --goodbg:#173326; --warn:#ffc46b; --warnbg:#3a2a10; --app:#1d2a34; --tile:#24343f; }
  }
  * { box-sizing:border-box; }
  html, body { overflow:hidden; }
  body { margin:0; font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }
  .card { padding:14px 16px; }
  .label { font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }
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

  /* ---------- guided walkthrough ---------- */
  .guide { display:grid; grid-template-columns:168px 1fr; gap:14px; margin:4px 0 10px; align-items:start; }
  .phone { background:var(--phone); border-radius:22px; padding:7px; box-shadow:0 6px 18px rgba(0,0,0,.18); }
  .screen { background:var(--app); border-radius:16px; height:252px; overflow:hidden; position:relative; }
  .status { display:flex; justify-content:space-between; font-size:9px; color:var(--muted); padding:6px 10px 2px; font-weight:600; }
  .apptitle { font-weight:700; font-size:14px; padding:4px 10px 8px; display:flex; align-items:center; gap:6px; }
  .apptitle .back { color:var(--accent); font-weight:400; }
  .els { padding:0 8px; display:flex; flex-direction:column; gap:6px; }
  .els.grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
  .els.launcher { display:grid; grid-template-columns:repeat(3,1fr); gap:12px 6px; padding:20px 8px 0; }
  .el { position:relative; background:var(--tile); border-radius:9px; font-size:11px; padding:8px 8px; border:1px solid var(--line); transition:transform .25s; }
  .el.tile { height:40px; display:flex; align-items:flex-end; font-weight:600; }
  .el.row::after { content:"\203A"; position:absolute; right:8px; top:6px; color:var(--muted); font-size:13px; }
  .el.button { background:var(--accent); color:#fff; text-align:center; font-weight:600; border-color:transparent; border-radius:99px; }
  .el.banner { grid-column:1 / -1; background:transparent; border-style:dashed; font-size:10px; color:var(--muted); }
  .el.toggle::after { content:""; position:absolute; right:8px; top:7px; width:22px; height:13px; border-radius:99px; background:var(--line); }
  .el.icon { background:none; border:0; padding:0; display:flex; flex-direction:column; align-items:center; gap:4px; font-size:9px; text-align:center; }
  .el.icon i { display:block; width:34px; height:34px; border-radius:9px; }
  .el.glow { z-index:2; transform:scale(1.04); border-color:var(--glow); animation:pulse 1.2s ease-in-out infinite; }
  .el.icon.glow { animation:none; }
  .el.icon.glow i { animation:pulse 1.2s ease-in-out infinite; }
  @keyframes pulse {
    0%, 100% { box-shadow:0 0 0 2px var(--glow), 0 0 8px 2px rgba(54,198,240,.55); }
    50% { box-shadow:0 0 0 3px var(--glow), 0 0 22px 8px rgba(54,198,240,.85); }
  }
  .tap { position:absolute; width:26px; height:26px; margin:-13px 0 0 -13px; border-radius:50%; border:2px solid var(--glow);
         pointer-events:none; z-index:3; animation:tap 1.2s ease-out infinite; transition:left .45s, top .45s; }
  @keyframes tap { 0% { transform:scale(.4); opacity:1; } 100% { transform:scale(1.6); opacity:0; } }
  @media (prefers-reduced-motion: reduce) {
    .el.glow, .el.icon.glow i { animation:none; box-shadow:0 0 0 3px var(--glow), 0 0 16px 5px rgba(54,198,240,.8); }
    .tap { animation:none; opacity:.8; }
  }
  .steps { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:4px; }
  .steps li { font-size:13px; padding:6px 8px; border-radius:8px; color:var(--muted); display:flex; gap:8px; align-items:baseline; }
  .steps li .num { font-variant-numeric:tabular-nums; font-weight:700; min-width:1.2em; }
  .steps li.now { color:var(--ink); background:rgba(54,198,240,.14); font-weight:600; }
  .steps li.past .num::after { content:" \2713"; color:var(--good); }
  .controls { display:flex; gap:6px; margin-top:10px; }
  .controls button { font:inherit; font-size:12px; padding:5px 10px; border-radius:8px; border:1px solid var(--line); background:var(--bg); color:var(--ink); cursor:pointer; }
  .controls button.primary { background:var(--accent); color:#fff; border-color:transparent; }
</style></head>
<body><div class="card" id="root"><p class="muted">Waiting for DocDesk...</p></div>
<script>
(function () {
  var root = document.getElementById("root");
  var nextId = 1, pending = {};
  function send(msg) { window.parent.postMessage(Object.assign({ jsonrpc: "2.0" }, msg), "*"); }
  function request(method, params, timeoutMs) {
    var id = nextId++;
    send({ id: id, method: method, params: params || {} });
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      if (timeoutMs) setTimeout(function () { if (pending[id]) { delete pending[id]; reject(new Error("timeout")); } }, timeoutMs);
    });
  }
  function notify(method, params) { send({ method: method, params: params || {} }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var lastHeight = 0;
  function size() {
    var h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (h !== lastHeight) { lastHeight = h; notify("ui/notifications/size-changed", { height: h }); }
  }
  if (window.ResizeObserver) new ResizeObserver(size).observe(document.documentElement);

  function sources(list) {
    if (!list || !list.length) return "";
    return '<p class="label">From the help centre</p>' + list.map(function (s) {
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

  // ---------------------------------------------------------------- guided walkthrough
  var guide = null, stepIndex = 0, playing = false, playToken = 0;

  function guideHtml(g) {
    return '<p class="label">Step by step in the ' + esc(g.app) + '</p><div class="guide">' +
      '<div class="phone"><div class="screen" id="screen"></div></div>' +
      '<div><ol class="steps" id="steps">' + g.steps.map(function (s, i) {
        return '<li data-i="' + i + '"><span class="num">' + s.n + "</span><span>" + esc(s.say) + "</span></li>";
      }).join("") + '</ol><div class="controls">' +
      '<button data-act="back" aria-label="Previous step">Back</button>' +
      '<button data-act="play" class="primary" id="playbtn">Play</button>' +
      '<button data-act="next" aria-label="Next step">Next</button></div>' +
      (g.after ? '<p class="muted" style="margin:10px 0 0">' + esc(g.after) + "</p>" : "") + "</div></div>";
  }

  function drawScreen(step) {
    var scr = guide.screens[step.screen];
    var el = document.getElementById("screen");
    if (!el || !scr) return;
    var layout = scr.layout === "launcher" ? "launcher" : (scr.elements.some(function (e) { return e.kind === "tile"; }) ? "grid" : "");
    var html = '<div class="status"><span>9:41</span><span>' + (layout === "launcher" ? "" : esc(guide.app)) + "</span></div>";
    if (scr.title) html += '<div class="apptitle">' + (step.screen !== "home" ? '<span class="back">‹</span>' : "") + esc(scr.title) + "</div>";
    html += '<div class="els ' + layout + '">' + scr.elements.map(function (e) {
      var cls = "el " + e.kind + (e.id === step.target ? " glow" : "");
      if (e.kind === "icon") return '<div class="' + cls + '" data-id="' + e.id + '"><i style="background:' + esc(e.color || "#888") + '"></i>' + esc(e.label.replace(/ app$/, "")) + "</div>";
      return '<div class="' + cls + '" data-id="' + e.id + '">' + esc(e.kind === "banner" ? (e.text || e.label) : e.label) + "</div>";
    }).join("") + '</div><div class="tap" id="tap"></div>';
    el.innerHTML = html;
    var target = el.querySelector(".glow");
    var tap = document.getElementById("tap");
    if (target) {
      var a = target.getBoundingClientRect(), b = el.getBoundingClientRect();
      var node = target.querySelector("i") || target;
      var c = node.getBoundingClientRect();
      tap.style.left = (c.left - b.left + c.width / 2) + "px";
      tap.style.top = (c.top - b.top + c.height / 2) + "px";
    } else { tap.style.display = "none"; }
  }

  function showStep(i) {
    if (!guide) return;
    stepIndex = Math.max(0, Math.min(i, guide.steps.length - 1));
    drawScreen(guide.steps[stepIndex]);
    document.querySelectorAll("#steps li").forEach(function (li) {
      var n = Number(li.getAttribute("data-i"));
      li.className = n === stepIndex ? "now" : (n < stepIndex ? "past" : "");
    });
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // Ask the host to read a step aloud; fall back to a timer if the host cannot speak.
  function speak(text) {
    return request("docdesk/speak", { text: text }, 30000).catch(function () { return wait(2400); });
  }

  async function play(from) {
    if (!guide) return;
    var token = ++playToken;
    playing = true;
    document.getElementById("playbtn").textContent = "Pause";
    for (var i = from; i < guide.steps.length; i++) {
      if (token !== playToken) return;
      showStep(i);
      await wait(250);
      await speak(guide.steps[i].say);
      if (token !== playToken) return;
      await wait(500);
    }
    if (guide.after && token === playToken) await speak(guide.after);
    playing = false;
    document.getElementById("playbtn").textContent = "Replay";
    notify("docdesk/notifications/guide-finished", { steps: guide.steps.length });
  }
  function stop() { playToken++; playing = false; var b = document.getElementById("playbtn"); if (b) b.textContent = "Play"; }

  // ---------------------------------------------------------------- render a tool result
  function render(sc, text) {
    var html = "";
    guide = null;
    if (!sc) { root.innerHTML = "<p>" + esc(text) + "</p>"; size(); return; }
    var ups = sc.updates || [];
    var mainGuide = sc.status === "answered" ? sc.guide : null;
    var upGuide = null;
    ups.forEach(function (u) {
      var who = u.resolved_by === "docs" ? "Answered by a new help article" : "The support team replied";
      html += '<div class="update"><p class="label">Good news: ticket ' + u.ticket_id + "</p><div><b>" + esc(u.question) + "</b></div>";
      if (u.guide && !mainGuide && !upGuide) { upGuide = u.guide; html += guideHtml(u.guide); }
      else html += "<div>" + esc(u.answer) + "</div>";
      html += '<div class="muted">' + who + "</div>" + sources(u.sources) + "</div>";
    });
    if (sc.status === "answered") {
      if (mainGuide) html += guideHtml(mainGuide);
      html += sources(sc.sources) || (mainGuide ? "" : '<p class="muted">Answered from the help centre.</p>');
    } else if (sc.status === "ticket_opened" || sc.status === "added_to_ticket") {
      html += '<p class="label">' + (sc.status === "ticket_opened" ? "Passed to the support team" : "Added to your ticket") +
        "</p>" + ticket(sc.ticket);
    } else if (sc.open) {
      html += sc.open.length ? '<p class="label">Your open tickets</p>' + sc.open.map(ticket).join("")
                             : (ups.length ? "" : '<p class="muted">No open tickets.</p>');
    } else if (sc.topics) {
      html += '<p class="label">Doc gaps, last ' + esc(sc.days) + " days</p><p>" + sc.answered + " of " + sc.questions +
        " questions answered from the docs. " + sc.open_tickets + " tickets open.</p>";
      html += sc.topics.length ? "<table>" + sc.topics.map(function (g) {
        return "<tr><td>" + esc(g.topic) + '<div class="muted">' + g.examples.map(esc).join("<br>") +
          '</div></td><td class="n">' + g.count + "</td></tr>"; }).join("") + "</table>" : "";
    } else if (!ups.length) {
      html += "<p>" + esc(sc.speech || text) + "</p>";
    }
    root.innerHTML = html;
    guide = mainGuide || upGuide;
    if (guide) showStep(0);
    size();
  }

  root.addEventListener("click", function (e) {
    var b = e.target.closest(".src");
    if (b) { request("ui/open-link", { url: b.getAttribute("data-url") }).catch(function () {}); return; }
    var c = e.target.closest("[data-act]");
    if (!c || !guide) return;
    var act = c.getAttribute("data-act");
    if (act === "play") { if (playing) stop(); else play(stepIndex >= guide.steps.length - 1 ? 0 : stepIndex); }
    if (act === "next") { stop(); showStep(stepIndex + 1); }
    if (act === "back") { stop(); showStep(stepIndex - 1); }
  });

  window.addEventListener("message", function (e) {
    var m = e.data || {};
    if (m.id !== undefined && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(new Error(m.error.message || "error")); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-result") {
      var params = m.params || {};
      var text = (params.content || []).filter(function (c) { return c.type === "text"; }).map(function (c) { return c.text; }).join(" ");
      render(params.structuredContent, text);
    } else if (m.method === "docdesk/notifications/guide-start" && guide) {
      play(0);
    }
  });
  request("ui/initialize", { appInfo: { name: "docdesk-card", version: "1.1.0" }, appCapabilities: {}, protocolVersion: "2026-01-26" }).catch(function () {});
  notify("ui/notifications/initialized", {});
})();
</script></body></html>
"""
