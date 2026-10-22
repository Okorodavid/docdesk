/*
 * A small MCP Apps host: renders a tool's ui:// resource in a sandboxed iframe and talks to
 * it over postMessage JSON-RPC (ui/initialize, tool-input, tool-result, size-changed,
 * open-link). App-specific requests and notifications can be handled through hooks. MIT licensed.
 */
(function (global) {
  "use strict";

  var APP_MIME = "text/html;profile=mcp-app";
  var cache = {};

  async function loadResource(client, uri) {
    if (!cache[uri]) {
      cache[uri] = client.readResource(uri).then(function (r) {
        var c = (r.contents || [])[0];
        if (!c || c.mimeType !== APP_MIME) throw new Error("not an MCP App resource: " + uri);
        return c.text;
      });
    }
    return cache[uri];
  }

  /*
   * Render a tool result into container using the tool's MCP App. Returns the iframe, or null
   * when the tool has no UI. The iframe gets two helpers:
   *   frame.ready             a promise that settles once the app has the tool result
   *   frame.notify(m, params) send the app a notification
   * options.onRequest(method, params) may return a promise for app requests the host supports;
   * options.onNotification(method, params) receives app notifications.
   */
  async function renderApp(client, tool, args, result, container, options) {
    options = options || {};
    var uri = tool && tool._meta && tool._meta.ui && tool._meta.ui.resourceUri;
    if (!uri) return null;
    var html = await loadResource(client, uri);
    var frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts");
    frame.setAttribute("scrolling", "no");
    frame.setAttribute("title", (tool.title || tool.name) + " card");
    frame.className = "app-frame";
    frame.style.height = "80px";
    var delivered = false, markReady;
    frame.ready = new Promise(function (r) { markReady = r; });

    function post(msg) { if (frame.contentWindow) frame.contentWindow.postMessage(Object.assign({ jsonrpc: "2.0" }, msg), "*"); }
    frame.notify = function (method, params) { post({ method: method, params: params || {} }); };
    function deliver() {
      if (delivered) return;
      delivered = true;
      post({ method: "ui/notifications/tool-input", params: { arguments: args } });
      post({ method: "ui/notifications/tool-result", params: result });
      setTimeout(markReady, 50);
    }

    function onMessage(e) {
      if (e.source !== frame.contentWindow) return;
      var m = e.data || {};
      if (!m.method) return;
      if (m.method === "ui/initialize") {
        post({ id: m.id, result: {
          protocolVersion: "2026-01-26",
          hostInfo: { name: options.hostName || "mcp-apps-host", version: "1.1.0" },
          hostCapabilities: { openLinks: {} },
          hostContext: { theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light", displayMode: "inline" },
        } });
      } else if (m.method === "ui/notifications/initialized") {
        deliver();
      } else if (m.method === "ui/notifications/size-changed") {
        var h = Math.min(Math.max(Math.ceil(Number(m.params && m.params.height)) || 80, 40), 900);
        frame.style.height = h + "px";
        var screen = container.closest(".screen");
        if (screen && frame === screen.querySelector(".bubble:last-child .app-frame")) screen.scrollTop = screen.scrollHeight;
      } else if (m.method === "ui/open-link") {
        var url = m.params && m.params.url;
        if (/^https?:\/\//.test(url || "")) window.open(url, "_blank", "noopener");
        if (m.id !== undefined) post({ id: m.id, result: {} });
      } else if (m.id !== undefined) {
        var handled = options.onRequest && options.onRequest(m.method, m.params || {});
        if (handled && typeof handled.then === "function") {
          handled.then(function (r) { post({ id: m.id, result: r || {} }); },
                       function (err) { post({ id: m.id, error: { code: -32603, message: String(err && err.message || err) } }); });
        } else {
          post({ id: m.id, error: { code: -32601, message: "Method not supported by this host: " + m.method } });
        }
      } else if (options.onNotification) {
        options.onNotification(m.method, m.params || {});
      }
    }
    window.addEventListener("message", onMessage);
    frame.addEventListener("load", function () { setTimeout(deliver, 400); });
    frame.srcdoc = html;
    container.appendChild(frame);
    return frame;
  }

  global.McpAppsHost = { renderApp: renderApp, APP_MIME: APP_MIME };
})(window);
