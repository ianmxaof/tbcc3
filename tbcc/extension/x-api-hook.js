/**
 * TBCC X/Twitter API hook (PAGE WORLD).
 *
 * Same role as of-api-hook.js: monkey-patch the SPA's fetch / XHR so GraphQL
 * timeline + TweetDetail bodies populate media URLs. Isolated content scripts
 * never see those responses — that is why x-feed-download's in-world hooks
 * left mediaMap empty and Download media failed (loading → red !).
 *
 * Parity target: XEnhancer.user.js XDownload.extractMediaFromResponse + XHR hook.
 */
(function () {
  if (window.__tbccXApiHookInstalled) return;
  window.__tbccXApiHookInstalled = true;

  var MAX_BODY = 8 * 1024 * 1024;
  var API_RE = /\/i\/api\/|graphql|HomeTimeline|HomeLatestTimeline|ForYou|SearchTimeline|UserTweets|UserMedia|TweetDetail|TweetResultByRestId/i;

  function notifyEntries(entries) {
    if (!entries || !entries.length) return;
    try {
      window.postMessage({ tbccXApiHook: true, entries: entries }, "*");
    } catch (_) {}
  }

  function noteGqlQueryId(reqUrl) {
    try {
      var m = String(reqUrl || "").match(
        /\/graphql\/([A-Za-z0-9_-]+)\/(HomeTimeline|HomeLatestTimeline|UserTweets|UserMedia|TweetDetail|TweetResultByRestId)/i
      );
      if (!m) return;
      window.__tbccXGqlQueryIds = window.__tbccXGqlQueryIds || {};
      window.__tbccXGqlQueryIds[m[2]] = m[1];
      try {
        window.postMessage({ tbccXApiHook: true, gql: { op: m[2], id: m[1] } }, "*");
      } catch (_) {}
    } catch (_) {}
  }

  function findParent(obj, targetKey, depth, seen) {
    var result = [];
    if (!obj || depth > 40) return result;
    if (typeof obj !== "object") return result;
    if (seen) {
      if (seen.has(obj)) return result;
      seen.add(obj);
    }
    if (Array.isArray(obj)) {
      for (var i = 0; i < obj.length; i++) {
        result = result.concat(findParent(obj[i], targetKey, depth + 1, seen));
      }
      return result;
    }
    for (var key in obj) {
      if (!Object.prototype.hasOwnProperty.call(obj, key)) continue;
      if (key === targetKey) result.push(obj);
      result = result.concat(findParent(obj[key], targetKey, depth + 1, seen));
    }
    return result;
  }

  function extractEntries(responseText) {
    var out = [];
    if (!responseText || typeof responseText !== "string") return out;
    if (responseText.length > MAX_BODY) return out;
    var t = responseText.trim();
    if (!t || (t[0] !== "{" && t[0] !== "[")) return out;
    var data;
    try {
      data = JSON.parse(t);
    } catch (_) {
      return out;
    }
    var entities = findParent(data, "extended_entities", 0, typeof WeakSet !== "undefined" ? new WeakSet() : null);
    for (var ei = 0; ei < entities.length; ei++) {
      var entity = entities[ei];
      if (!entity || !entity.extended_entities) continue;
      var entityId = String(entity.id_str || entity.conversation_id_str || "");
      if (!entityId) continue;
      var text = (entity.full_text || "").split("https://t.co")[0];
      text = text ? String(text).trim().slice(0, 50) : entityId;
      var mediaList = entity.extended_entities.media || [];
      for (var mi = 0; mi < mediaList.length; mi++) {
        var m = mediaList[mi];
        if (!m || ["video", "animated_gif", "photo"].indexOf(m.type) < 0) continue;
        var variants = (m.video_info && m.video_info.variants) || [];
        var bestVideo = variants
          .filter(function (v) {
            return v && v.content_type === "video/mp4" && v.url;
          })
          .sort(function (a, b) {
            return (b.bitrate || 0) - (a.bitrate || 0);
          })[0];
        out.push({
          entityId: entityId,
          id: m.id_str || null,
          video: bestVideo && bestVideo.url ? bestVideo.url : null,
          photo: m.media_url_https || null,
          text: text,
        });
      }
    }
    return out;
  }

  function ingestResponseText(reqUrl, text) {
    noteGqlQueryId(reqUrl);
    try {
      notifyEntries(extractEntries(text));
    } catch (_) {}
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
        noteGqlQueryId(requestedUrl);
        var p = origFetch.apply(this, args);
        if (!API_RE.test(requestedUrl)) return p;
        return p.then(function (resp) {
          try {
            if (!resp || !resp.clone) return resp;
            resp
              .clone()
              .text()
              .then(function (text) {
                ingestResponseText(resp.url || requestedUrl, text);
              })
              .catch(function () {});
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
        this.__tbccXUrl = String(url || "");
      } catch (_) {}
      noteGqlQueryId(url);
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      try {
        xhr.addEventListener("load", function () {
          try {
            var reqUrl = String(xhr.__tbccXUrl || xhr.responseURL || "");
            var rt = xhr.responseType || "";
            if (rt === "" || rt === "text") {
              ingestResponseText(reqUrl, xhr.responseText);
            }
          } catch (_) {}
        });
      } catch (_) {}
      return origSend.apply(this, arguments);
    };
  } catch (_) {}
})();
