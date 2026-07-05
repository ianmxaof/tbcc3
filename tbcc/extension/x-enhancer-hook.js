/**
 * TBCC X / Twitter media API hook (PAGE WORLD).
 *
 * Monkey-patches fetch + XMLHttpRequest so we can read extended_entities from
 * GraphQL timeline responses before the SPA discards them. Posts parsed media
 * to the isolated content script (x-enhancer.js) via window.postMessage.
 */
(function () {
  if (window.__tbccXEnhancerHookInstalled) return;
  window.__tbccXEnhancerHookInstalled = true;

  var MAX_BODY = 6 * 1024 * 1024;

  function notifyMedia(items) {
    if (!items || !items.length) return;
    try {
      window.postMessage({ tbccXEnhancer: true, type: "media", items: items }, "*");
    } catch (_) {}
  }

  function findParent(obj, targetKey, out) {
    out = out || [];
    if (typeof obj === "object" && obj !== null) {
      if (Array.isArray(obj)) {
        for (var i = 0; i < obj.length; i++) findParent(obj[i], targetKey, out);
      } else {
        for (var key in obj) {
          if (!Object.prototype.hasOwnProperty.call(obj, key)) continue;
          if (key === targetKey) out.push(obj);
          findParent(obj[key], targetKey, out);
        }
      }
    }
    return out;
  }

  function extractMediaFromJson(data) {
    var items = [];
    try {
      var entities = findParent(data, "extended_entities");
      for (var i = 0; i < entities.length; i++) {
        var entity = entities[i];
        if (!entity.extended_entities) continue;
        var entityId = entity.id_str || entity.conversation_id_str;
        if (!entityId) continue;
        var mediaList = entity.extended_entities.media || [];
        for (var j = 0; j < mediaList.length; j++) {
          var m = mediaList[j];
          if (["video", "animated_gif", "photo"].indexOf(m.type) < 0) continue;
          var variants = (m.video_info && m.video_info.variants) || [];
          var bestVideo = null;
          for (var k = 0; k < variants.length; k++) {
            var v = variants[k];
            if (v.content_type !== "video/mp4") continue;
            if (!bestVideo || (v.bitrate || 0) > (bestVideo.bitrate || 0)) bestVideo = v;
          }
          var text = (entity.full_text || "").split("https://t.co")[0];
          text = (text && text.trim().slice(0, 50)) || entityId;
          items.push({
            entityId: entityId,
            id: m.id_str,
            thumbnail: m.media_url_https ? m.media_url_https.split(".jpg")[0] : null,
            video: bestVideo ? bestVideo.url : null,
            photo: m.media_url_https || null,
            text: text,
          });
        }
      }
    } catch (_) {}
    return items;
  }

  function handleResponseText(text) {
    if (!text || typeof text !== "string" || text.length > MAX_BODY) return;
    var t = text.trim();
    if (!t || (t.charAt(0) !== "{" && t.charAt(0) !== "[")) return;
    try {
      var data = JSON.parse(text);
      var items = extractMediaFromJson(data);
      notifyMedia(items);
    } catch (_) {}
  }

  try {
    var origFetch = window.fetch;
    if (typeof origFetch === "function") {
      window.fetch = function () {
        var p = origFetch.apply(this, arguments);
        return p.then(function (resp) {
          try {
            if (!resp || !resp.clone) return resp;
            var ct = "";
            try {
              ct = (resp.headers && resp.headers.get && resp.headers.get("content-type")) || "";
            } catch (_) {}
            if (ct && ct.indexOf("json") < 0 && ct.indexOf("text") < 0) return resp;
            resp
              .clone()
              .text()
              .then(function (text) {
                handleResponseText(text);
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
      this._tbccXeUrl = String(url || "");
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      xhr.addEventListener("load", function () {
        try {
          var rt = xhr.responseType || "";
          if (rt === "json" && xhr.response) {
            var items = extractMediaFromJson(xhr.response);
            notifyMedia(items);
          } else if (rt === "" || rt === "text") {
            handleResponseText(xhr.responseText);
          }
        } catch (_) {}
      });
      return origSend.apply(this, arguments);
    };
  } catch (_) {}
})();
