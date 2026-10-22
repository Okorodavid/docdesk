/*
 * A small MCP Apps host: renders a tool's ui:// resource in a sandboxed iframe and talks to
 * it over postMessage JSON-RPC (ui/initialize, tool-input, tool-result, size-changed,
 * open-link). MIT licensed.
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

  // Render a tool result into container using the tool's MCP App. Returns the iframe.
  async function renderApp(client, tool, args, result, container) {
    var uri = tool && tool._meta && tool._meta.ui && tool._meta.ui.resourceUri;
    if (!uri) return null;
    var html = await loadResource(client, uri);
    var frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts");
    frame.setAttribute("scrolling", "no");
    frame.setAttribute("title", (tool.title || tool.name) + " card");
    frame.className = "app-frame";
    frame.style.height = "80px";
    var delivered = false;

    function post(msg) { frame.contentWindow.postMessage(Object.assign({ jsonrpc: "2.0" }, msg), "*"); }
    function deliver() {
      if (delivered) return;
      delivered = true;
      post({ method: "ui/notifications/tool-input", params: { arguments: args } });
      post({ method: "ui/notifications/tool-result", params: result });
    }

    function onMessage(e) {
      if (e.source !== frame.contentWindow) return;
      var m = e.data || {};
      if (m.method === "ui/initialize") {
        post({ id: m.id, result: {
          protocolVersion: "2026-01-26",
          hostInfo: { name: "docdesk-alexa-simulator", version: "1.0.0" },
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
      } else if (m.id !== undefined && m.method) {
        post({ id: m.id, error: { code: -32601, message: "Method not supported by this host: " + m.method } });
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
