(function () {
  "use strict";

  var APPS_EXT = "io.modelcontextprotocol/ui";
  var PROFILES = {
    ada: { label: "Ada", headers: { "X-DocDesk-Customer": "ada" } },
    tunde: { label: "Tunde", headers: { "X-DocDesk-Customer": "tunde" } },
    staff: { label: "Brightline team", headers: { "X-DocDesk-Customer": "brightline-staff", "X-DocDesk-Staff": window.DOCDESK.staffToken } },
  };
  var CHIPS = {
    ada: ["Alexa, ask Brightline how do I restart my router?", "What does a solid orange light mean?",
          "Can I pay my bill with mobile money?", "Any updates on my tickets?", "Is there a late fee?"],
    tunde: ["Alexa, ask Brightline how do I change my Wi-Fi password?", "Do I get a credit when there's an outage?",
            "Why is my bill higher this month?", "Any news on my tickets?"],
    staff: ["Alexa, ask Brightline what customers are asking that our docs don't cover",
            "Show me the doc gaps report for the last 7 days"],
  };

  var $ = function (id) { return document.getElementById(id); };
  var conversation = $("conversation"), steps = $("steps"), traffic = $("traffic");
  var current = "ada";
  var sessions = {};   // profile -> { client, tools, history: [nodes] }
  var busy = false;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function light(state) { $("lightbar").className = "lightbar" + (state ? " " + state : ""); }

  // ---------------------------------------------------------------- traffic log
  function logTraffic(t) {
    var m = t.message || {};
    var d = el("details", t.direction);
    var s = el("summary");
    s.appendChild(el("span", "dir", t.direction === "out" ? "→" : "←"));
    var label = m.method || (m.error ? "error" : "result");
    if (m.method === "tools/call") label += "  " + m.params.name;
    if (t.direction === "in" && m.result && m.result.protocolVersion) label += "  protocolVersion " + m.result.protocolVersion;
    s.appendChild(el("span", "", label + (m.id !== undefined ? "  #" + m.id : "")));
    s.appendChild(el("span", "meta", t.ms !== undefined ? t.ms + " ms" : PROFILES[current].label));
    d.appendChild(s);
    var body = JSON.stringify(m, function (k, v) {
      return typeof v === "string" && v.length > 600 ? v.slice(0, 600) + "... (" + v.length + " chars)" : v;
    }, 2);
    d.appendChild(el("pre", "", body));
    traffic.appendChild(d);
    traffic.scrollTop = traffic.scrollHeight;
    if (t.sessionId) $("session").textContent = "Mcp-Session-Id " + t.sessionId.slice(0, 8) + "...";
  }

  function step(html, ms) {
    var li = el("li");
    li.appendChild(el("span", "n", String(steps.children.length + 1)));
    var body = el("span");
    body.innerHTML = html;
    li.appendChild(body);
    if (ms !== undefined) li.appendChild(el("span", "ms", ms + " ms"));
    steps.appendChild(li);
  }
  function code(s) { return "<code>" + String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }) + "</code>"; }

  // ---------------------------------------------------------------- sessions
  async function session(profile) {
    if (sessions[profile] && sessions[profile].client) return sessions[profile];
    var s = sessions[profile] = sessions[profile] || { history: [] };
    var caps = { extensions: {} };
    caps.extensions[APPS_EXT] = { mimeTypes: [McpAppsHost.APP_MIME] };
    s.client = new McpClient("/mcp", {
      headers: PROFILES[profile].headers,
      clientInfo: { name: "docdesk-alexa-simulator", version: "1.0.0" },
      capabilities: caps,
      onTraffic: logTraffic,
    });
    var init = await s.client.connect();
    s.tools = await s.client.listTools();
    $("proto").textContent = "MCP " + init.protocolVersion + " · Streamable HTTP · " + s.tools.length + " tools";
    $("proto").className = "badge ok";
    step("Connected as " + PROFILES[profile].label + ": " + code("initialize") + " then " + code("tools/list") + " found " +
         s.tools.map(function (t) { return code(t.name); }).join(" "));
    return s;
  }

  // ---------------------------------------------------------------- conversation
  function showEmpty() {
    var e = el("div", "empty");
    e.appendChild(el("b", "", "Talk to " + PROFILES[current].label + "'s Alexa"));
    e.appendChild(el("span", "", current === "staff"
      ? "Staff can ask for the doc gaps report. Customers can't."
      : "Ask anything about Brightline Internet. Try a suggestion below."));
    conversation.appendChild(e);
  }

  function render() {
    conversation.innerHTML = "";
    var s = sessions[current];
    if (!s || !s.history.length) showEmpty();
    else s.history.forEach(function (n) { conversation.appendChild(n); });
    conversation.scrollTop = conversation.scrollHeight;
    var chips = $("chips");
    chips.innerHTML = "";
    CHIPS[current].forEach(function (text) {
      var b = el("button", "", text);
      b.type = "button";
      b.addEventListener("click", function () { say(text); });
      chips.appendChild(b);
    });
  }

  function addNode(node) {
    var s = sessions[current] = sessions[current] || { history: [] };
    if (!s.history.length) conversation.innerHTML = "";
    s.history.push(node);
    conversation.appendChild(node);
    conversation.scrollTop = conversation.scrollHeight;
  }

  function speak(text) {
    if (!$("speak").checked || !window.speechSynthesis) { light(""); return; }
    speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.rate = 1.03;
    u.onstart = function () { light("speaking"); };
    u.onend = u.onerror = function () { light(""); };
    speechSynthesis.speak(u);
  }

  async function say(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true;
    $("utterance").value = "";
    steps.innerHTML = "";
    var you = el("div", "bubble you");
    you.appendChild(el("div", "who", PROFILES[current].label));
    you.appendChild(el("div", "", text));
    addNode(you);
    light("thinking");
    try {
      var s = await session(current);
      var t0 = performance.now();
      var planRes = await fetch("/host/plan", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ utterance: text, tools: s.tools, planner: $("planner").value }) });
      var plan = await planRes.json();
      step("Host brain (" + plan.planner + ") chose " + code(plan.tool) + " with " + code(JSON.stringify(plan.arguments)),
           Math.round(performance.now() - t0));

      var t1 = performance.now();
      var result = await s.client.callTool(plan.tool, plan.arguments);
      var speech = (result.content || []).filter(function (c) { return c.type === "text"; })
        .map(function (c) { return c.text; }).join(" ");
      var sc = result.structuredContent || {};
      var what = sc.status === "answered" ? "answered from " + (sc.sources || []).length + " help-centre source(s)"
        : sc.status === "ticket_opened" ? "opened ticket " + sc.ticket.id
        : sc.status === "added_to_ticket" ? "added to ticket " + sc.ticket.id
        : sc.denied ? "refused: staff only" : "returned " + Object.keys(sc).filter(function (k) { return k !== "speech"; }).join(", ");
      step(code("tools/call " + plan.tool) + " " + what +
           (sc.updates && sc.updates.length ? ", plus " + sc.updates.length + " ticket update(s) delivered" : ""),
           Math.round(performance.now() - t1));

      var alexa = el("div", "bubble alexa");
      alexa.appendChild(el("div", "who", "Alexa · DocDesk"));
      alexa.appendChild(el("div", "said", speech));
      addNode(alexa);
      var tool = s.tools.filter(function (x) { return x.name === plan.tool; })[0];
      var frame = await McpAppsHost.renderApp(s.client, tool, plan.arguments, result, alexa);
      if (frame) step("Rendered the MCP App card " + code(tool._meta.ui.resourceUri) + " in a sandboxed iframe");
      setTimeout(function () { conversation.scrollTop = conversation.scrollHeight; }, 500);
      speak(speech);
    } catch (err) {
      var bad = el("div", "bubble alexa error");
      bad.appendChild(el("div", "who", "Error"));
      bad.appendChild(el("div", "said", String(err.message || err)));
      addNode(bad);
      light("");
    } finally {
      busy = false;
    }
  }

  // ---------------------------------------------------------------- wiring
  document.querySelectorAll(".profiles button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".profiles button").forEach(function (x) { x.classList.toggle("active", x === b); });
      current = b.getAttribute("data-profile");
      steps.innerHTML = "";
      render();
      session(current).catch(function (e) { step("Could not connect: " + e.message); });
    });
  });
  $("composer").addEventListener("submit", function (e) { e.preventDefault(); say($("utterance").value); });

  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) { $("mic").disabled = true; $("mic").title = "Speech input needs Chrome or Edge"; }
  $("mic").addEventListener("click", function () {
    if (!Rec || busy) return;
    var rec = new Rec();
    rec.lang = "en-US";
    rec.interimResults = true;
    $("mic").classList.add("on");
    light("listening");
    rec.onresult = function (e) {
      var text = Array.prototype.map.call(e.results, function (r) { return r[0].transcript; }).join("");
      $("utterance").value = text;
      if (e.results[e.results.length - 1].isFinal) say(text);
    };
    rec.onend = function () { $("mic").classList.remove("on"); if (!busy) light(""); };
    rec.onerror = rec.onend;
    rec.start();
  });

  fetch("/api/state").then(function (r) { return r.json(); }).then(function (st) {
    $("mode").textContent = "answers: " + st.answer_mode.split(" (")[0] + " · " + st.pages + " help pages";
    if (!st.claude_available) {
      var opt = $("planner").querySelector('option[value="claude"]');
      opt.disabled = true;
      opt.textContent = "Claude picks the tool (needs API key)";
    } else {
      $("planner").value = "claude";
    }
  });

  render();
  session(current).catch(function (e) { step("Could not connect: " + e.message); });
})();
