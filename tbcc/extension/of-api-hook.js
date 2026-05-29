/**
 * TBCC OnlyFans API hook (PAGE WORLD).
 *
 * Runs in the OnlyFans page's main JavaScript world (manifest_version 3 with
 * "world": "MAIN") so it can monkey-patch the same fetch / XMLHttpRequest the
 * SPA uses. We can't reach `window.fetch` from a content-script isolated
 * world; that's why this is a separate file.
 *
 * The full-resolution media URLs only ever appear in JSON bodies of
 * /api2/v2/... requests — the on-page <img> elements use the 300x300 preview
 * variant. So we clone every matching response and post the parsed JSON to
 * the content-script world via window.postMessage. capture.js receives it,
 * extracts media URLs, and feeds them to the sidebar gallery.
 */
(function () {
  if (window.__tbccOfHookInstalled) return;
  window.__tbccOfHookInstalled = true;

  var TARGET_RE = /\/api2\/v[12]\//;
  var MAX_BODY = 4 * 1024 * 1024;

  function notify(payload) {
    try {
      window.postMessage({ tbccOfHook: true, payload: payload }, "*");
    } catch (_) {}
  }

  function safeParseJson(text) {
    if (!text || typeof text !== "string") return null;
    if (text.length > MAX_BODY) return null;
    var t = text.trim();
    if (!t || (t[0] !== "{" && t[0] !== "[")) return null;
    try {
      return JSON.parse(t);
    } catch (_) {
      return null;
    }
  }

  try {
    var origFetch = window.fetch;
    if (typeof origFetch === "function") {
      window.fetch = function () {
        var args = arguments;
        var requestedUrl = "";
        try {
          var first = args[0];
          if (typeof first === "string") requestedUrl = first;
          else if (first && typeof first.url === "string") requestedUrl = first.url;
        } catch (_) {}

        var p = origFetch.apply(this, args);
        if (!TARGET_RE.test(requestedUrl)) return p;

        return p.then(function (resp) {
          try {
            if (!resp || !resp.clone || typeof resp.clone !== "function") return resp;
            var ct = "";
            try { ct = resp.headers && resp.headers.get && resp.headers.get("content-type") || ""; } catch (_) {}
            if (ct && ct.indexOf("json") < 0 && ct.indexOf("text") < 0) return resp;
            resp.clone().text().then(function (text) {
              var json = safeParseJson(text);
              if (json != null) {
                notify({ url: resp.url || requestedUrl, status: resp.status, json: json, via: "fetch" });
              }
            }).catch(function () {});
          } catch (_) {}
          return resp;
        });
      };
    }
  } catch (_) {}

  try {
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      try {
        this.__tbccOfUrl = String(url || "");
        this.__tbccOfTrack = TARGET_RE.test(this.__tbccOfUrl);
      } catch (_) {}
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      try {
        if (xhr.__tbccOfTrack) {
          xhr.addEventListener("load", function () {
            try {
              var rt = xhr.responseType || "";
              var json = null;
              if (rt === "json") {
                json = xhr.response;
              } else if (rt === "" || rt === "text") {
                json = safeParseJson(xhr.responseText);
              }
              if (json != null) {
                notify({
                  url: xhr.responseURL || xhr.__tbccOfUrl,
                  status: xhr.status,
                  json: json,
                  via: "xhr",
                });
              }
            } catch (_) {}
          });
        }
      } catch (_) {}
      return origSend.apply(this, arguments);
    };
  } catch (_) {}
})();
