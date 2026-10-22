/*
 * mcp-lite: a dependency-free MCP client for the browser over Streamable HTTP.
 * Speaks the 2025-11-25 handshake (initialize -> notifications/initialized), keeps the
 * Mcp-Session-Id, sends MCP-Protocol-Version on later requests, and reads both plain JSON
 * and text/event-stream (SSE) responses. MIT licensed.
 */
(function (global) {
  "use strict";

  var DEFAULT_PROTOCOL = "2025-11-25";

  function McpClient(url, options) {
    options = options || {};
    this.url = url;
    this.headers = options.headers || {};
    this.protocolVersion = options.protocolVersion || DEFAULT_PROTOCOL;
    this.clientInfo = options.clientInfo || { name: "mcp-lite", version: "1.0.0" };
    this.capabilities = options.capabilities || {};
    this.onTraffic = options.onTraffic || function () {};
    this.sessionId = null;
    this.negotiatedVersion = null;
    this.serverInfo = null;
    this.serverCapabilities = null;
    this.instructions = null;
    this._nextId = 1;
  }

  McpClient.prototype._headers = function () {
    var h = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
    for (var k in this.headers) h[k] = this.headers[k];
    if (this.sessionId) h["Mcp-Session-Id"] = this.sessionId;
    if (this.negotiatedVersion) h["MCP-Protocol-Version"] = this.negotiatedVersion;
    return h;
  };

  // Read an SSE body and return the JSON-RPC message whose id matches (or the last one).
  async function readSse(response, id) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    var last = null;
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop();
      for (var i = 0; i < events.length; i++) {
        var data = events[i].split(/\r?\n/).filter(function (l) { return l.indexOf("data:") === 0; })
          .map(function (l) { return l.slice(5).replace(/^ /, ""); }).join("\n");
        if (!data) continue;
        var msg = JSON.parse(data);
        last = msg;
        if (id !== undefined && msg.id === id && (msg.result !== undefined || msg.error !== undefined)) {
          reader.cancel().catch(function () {});
          return msg;
        }
      }
    }
    return last;
  }

  McpClient.prototype._post = async function (message) {
    var started = performance.now();
    this.onTraffic({ direction: "out", message: message });
    var response = await fetch(this.url, { method: "POST", headers: this._headers(), body: JSON.stringify(message) });
    var sid = response.headers.get("Mcp-Session-Id");
    if (sid) this.sessionId = sid;
    if (response.status === 202 || message.id === undefined) {
      return null; // notification accepted
    }
    if (!response.ok) {
      var text = await response.text();
      throw new Error("HTTP " + response.status + ": " + text.slice(0, 300));
    }
    var type = response.headers.get("Content-Type") || "";
    var reply = type.indexOf("text/event-stream") >= 0 ? await readSse(response, message.id) : await response.json();
    this.onTraffic({ direction: "in", message: reply, ms: Math.round(performance.now() - started), sessionId: this.sessionId });
    if (reply && reply.error) {
      var err = new Error(reply.error.message || "MCP error");
      err.code = reply.error.code;
      err.data = reply.error.data;
      throw err;
    }
    return reply ? reply.result : null;
  };

  McpClient.prototype.request = function (method, params) {
    return this._post({ jsonrpc: "2.0", id: this._nextId++, method: method, params: params || {} });
  };

  McpClient.prototype.notify = function (method, params) {
    return this._post({ jsonrpc: "2.0", method: method, params: params || {} });
  };

  McpClient.prototype.connect = async function () {
    var result = await this.request("initialize", {
      protocolVersion: this.protocolVersion,
      capabilities: this.capabilities,
      clientInfo: this.clientInfo,
    });
    this.negotiatedVersion = result.protocolVersion;
    this.serverInfo = result.serverInfo;
    this.serverCapabilities = result.capabilities;
    this.instructions = result.instructions || null;
    await this.notify("notifications/initialized");
    return result;
  };

  McpClient.prototype.listTools = async function () {
    var tools = [];
    var cursor;
    do {
      var page = await this.request("tools/list", cursor ? { cursor: cursor } : {});
      tools = tools.concat(page.tools || []);
      cursor = page.nextCursor;
    } while (cursor);
    return tools;
  };

  McpClient.prototype.callTool = function (name, args) {
    return this.request("tools/call", { name: name, arguments: args || {} });
  };

  McpClient.prototype.readResource = function (uri) {
    return this.request("resources/read", { uri: uri });
  };

  McpClient.prototype.close = async function () {
    if (!this.sessionId) return;
    try {
      await fetch(this.url, { method: "DELETE", headers: this._headers() });
    } catch (e) { /* server may already be gone */ }
    this.sessionId = null;
  };

  global.McpClient = McpClient;
})(typeof window !== "undefined" ? window : globalThis);
