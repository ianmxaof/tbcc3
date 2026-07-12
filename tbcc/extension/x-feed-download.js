/**
 * X/Twitter per-post download buttons (XEnhancer-style, TBCC extension port).
 * Hooks timeline API responses for media URLs; injects blue download on each post.
 */
(function () {
  "use strict";

  var STYLE_ID = "tbcc-x-feed-download-css";
  var CSS =
    ".x-master-dl{margin-left:12px;order:99}.x-master-dl:hover>div>div>div>div{color:#1da1f2}" +
    ".x-master-dl:hover svg{color:#1da1f2}.x-master-dl.tmd-media{position:absolute;right:0;z-index:5}" +
    ".x-master-dl.tmd-media>div{border-radius:99px;display:flex;margin:2px;background:rgba(0,0,0,.45)}" +
    ".x-master-dl.tmd-media>div>div{color:#fff;display:flex;margin:6px}" +
    ".x-master-dl.tmd-img{position:absolute;top:0;right:0;z-index:10;margin:5px}" +
    ".x-master-dl g{display:none}.x-master-dl.completed g.completed,.x-master-dl.download g.download," +
    ".x-master-dl.failed g.failed,.x-master-dl.loading g.loading{display:inline}" +
    ".x-master-dl.loading svg{animation:tbcc-x-dl-spin 1s linear infinite}" +
    "@keyframes tbcc-x-dl-spin{to{transform:rotate(360deg)}}";

  var SVG =
    '<g class="download"><path d="M11.99 16l-5.7-5.7L7.7 8.88l3.29 3.3V2.59h2v9.59l3.3-3.3 1.41 1.42-5.71 5.7zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z"/></g>' +
    '<g class="completed"><path d="M3,14 v5 q0,2 2,2 h14 q2,0 2,-2 v-5 M7,10 l3,4 q1,1 2,0 l8,-11" fill="none" stroke="#1DA1F2" stroke-width="2" stroke-linecap="round"/></g>' +
    '<g class="loading"><circle cx="12" cy="12" r="10" fill="none" stroke="#1DA1F2" stroke-width="4" opacity="0.4"/><path d="M12,2 a10,10 0 0 1 10,10" fill="none" stroke="#1DA1F2" stroke-width="4" stroke-linecap="round"/></g>' +
    '<g class="failed"><circle cx="12" cy="12" r="11" fill="#f33" stroke="currentColor" stroke-width="2" opacity="0.8"/><path d="M14,5 a1,1 0 0 0 -4,0 l0.5,9.5 a1.5,1.5 0 0 0 3,0 z M12,17 a2,2 0 0 0 0,4 a2,2 0 0 0 0,-4" fill="#fff" stroke="none"/></g>';

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = CSS;
    (document.head || document.documentElement).appendChild(el);
  }

  function isSafeTwimgUrl(raw) {
    try {
      var u = new URL(String(raw || ""));
      if (u.protocol !== "https:") return false;
      var host = u.hostname.toLowerCase();
      return host === "pbs.twimg.com" || host === "video.twimg.com" || host.endsWith(".twimg.com");
    } catch (_) {
      return false;
    }
  }

  function noteGqlQueryId(reqUrl) {
    try {
      var m = String(reqUrl || "").match(/\/graphql\/([A-Za-z0-9_-]+)\/(HomeTimeline|HomeLatestTimeline|UserTweets|UserMedia)/i);
      if (!m) return;
      window.__tbccXGqlQueryIds = window.__tbccXGqlQueryIds || {};
      window.__tbccXGqlQueryIds[m[2]] = m[1];
    } catch (_) {}
  }

  function chromeDownload(url, filename) {
    return new Promise(function (resolve, reject) {
      try {
        chrome.runtime.sendMessage(
          {
            action: "tbcc-x-media-download",
            url: url,
            filename: filename,
            refererPageUrl: location.href.split("#")[0],
          },
          function (resp) {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            if (!resp || resp.ok === false) {
              reject(new Error((resp && resp.error) || "download failed"));
              return;
            }
            resolve(resp.downloadId);
          }
        );
      } catch (e) {
        reject(e);
      }
    });
  }

  function upgradeTwitterPhotoUrl(url) {
    try {
      var u = new URL(String(url || ""));
      if (u.hostname.toLowerCase().indexOf("twimg.com") < 0) return "";
      u.searchParams.set("name", "orig");
      return u.toString();
    } catch (_) {
      return "";
    }
  }

  function shouldCaptureApiUrl(url) {
    try {
      var u = new URL(String(url || ""), location.origin);
      var host = u.hostname.toLowerCase();
      if (!/(^|\.)x\.com$|(^|\.)twitter\.com$/.test(host)) return false;
      var pathQ = u.pathname + u.search;
      return /\/i\/api\/|graphql|HomeTimeline|HomeLatestTimeline|ForYou|SearchTimeline|UserTweets|UserMedia|TweetDetail/i.test(
        pathQ
      );
    } catch (_) {
      return false;
    }
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function getNetMp4sForTab(tabId) {
    return new Promise(function (resolve) {
      if (tabId == null) {
        resolve([]);
        return;
      }
      try {
        chrome.storage.session.get("tbcc_net_media_" + tabId, function (got) {
          var net = (got && got["tbcc_net_media_" + tabId]) || [];
          var mp4s = [];
          for (var i = 0; i < net.length; i++) {
            var raw = String(net[i] || "");
            if (!raw) continue;
            try {
              var p = new URL(raw);
              if (p.hostname.toLowerCase() !== "video.twimg.com") continue;
              if (/\.mp4(\?|$)/i.test(p.pathname)) mp4s.push(raw);
            } catch (_) {}
          }
          resolve(mp4s);
        });
      } catch (_) {
        resolve([]);
      }
    });
  }

  function getCurrentTabId() {
    return new Promise(function (resolve) {
      try {
        chrome.runtime.sendMessage({ action: "tbcc-get-sender-tab-id" }, function (resp) {
          var id = resp && Number.isFinite(Number(resp.tabId)) ? Number(resp.tabId) : null;
          resolve(id);
        });
      } catch (_) {
        resolve(null);
      }
    });
  }

  var XDownload = {
    mediaMap: new Map(),
    findParent: function (obj, targetKey) {
      var result = [];
      if (typeof obj === "object" && obj !== null) {
        for (var key in obj) {
          if (!Object.prototype.hasOwnProperty.call(obj, key)) continue;
          if (key === targetKey) result.push(obj);
          result = result.concat(this.findParent(obj[key], targetKey));
        }
      } else if (Array.isArray(obj)) {
        for (var i = 0; i < obj.length; i++) result = result.concat(this.findParent(obj[i], targetKey));
      }
      return result;
    },
    ingestLegacyTweet: function (legacy) {
      if (!legacy || !legacy.id_str) return;
      var entityId = String(legacy.id_str);
      var media =
        (legacy.extended_entities && legacy.extended_entities.media) ||
        (legacy.entities && legacy.entities.media) ||
        [];
      if (!media.length) return;
      var text = (legacy.full_text || "").split("https://t.co")[0];
      text = text ? String(text).trim().slice(0, 50) : entityId;
      for (var mi = 0; mi < media.length; mi++) {
        var m = media[mi];
        if (!m || ["video", "animated_gif", "photo"].indexOf(m.type) < 0) continue;
        var variants = (m.video_info && m.video_info.variants) || [];
        var bestVideo = variants
          .filter(function (v) {
            return v && v.content_type === "video/mp4" && v.url;
          })
          .sort(function (a, b) {
            return (b.bitrate || 0) - (a.bitrate || 0);
          })[0];
        var patch = { text: text };
        if (bestVideo && bestVideo.url) patch.video = bestVideo.url;
        if (m.media_url_https) patch.photo = m.media_url_https;
        this.upsertMediaEntry(entityId, patch);
      }
      if (this.mediaMap.size > 300) {
        var oldest = this.mediaMap.keys().next().value;
        if (oldest) this.mediaMap.delete(oldest);
      }
    },
    walkTweetGraph: function (node, depth, seen) {
      if (!node || depth > 28) return;
      if (typeof node !== "object") return;
      if (seen.has(node)) return;
      seen.add(node);
      if (Array.isArray(node)) {
        for (var i = 0; i < node.length; i++) this.walkTweetGraph(node[i], depth + 1, seen);
        return;
      }
      if (node.legacy && node.legacy.id_str) this.ingestLegacyTweet(node.legacy);
      if (node.tweet && node.tweet.legacy) this.ingestLegacyTweet(node.tweet.legacy);
      if (node.tweet_results && node.tweet_results.result) this.walkTweetGraph(node.tweet_results.result, depth + 1, seen);
      for (var k in node) {
        if (!Object.prototype.hasOwnProperty.call(node, k)) continue;
        if (k === "legacy" || k === "tweet" || k === "tweet_results") continue;
        this.walkTweetGraph(node[k], depth + 1, seen);
      }
    },
    extractMediaFromResponse: function (_url, responseText) {
      try {
        var data = JSON.parse(responseText);
        this.walkTweetGraph(data, 0, new WeakSet());
      } catch (_) {}
    },
    upsertMediaEntry: function (entityId, patch) {
      if (!entityId) return;
      var prev = this.mediaMap.get(entityId) || {
        entityId: entityId,
        video: null,
        photo: null,
        text: entityId,
      };
      if (patch.text) prev.text = patch.text;
      if (patch.video) prev.video = patch.video;
      if (patch.photo) prev.photo = patch.photo;
      this.mediaMap.set(entityId, prev);
    },
    hookFetch: function () {
      if (window.__tbccXFeedFetchHooked) return;
      window.__tbccXFeedFetchHooked = true;
      var self = this;
      var originalFetch = window.fetch.bind(window);
      window.fetch = function (input, init) {
        var reqUrl =
          typeof input === "string"
            ? input
            : input && typeof input.url === "string"
              ? input.url
              : "";
        noteGqlQueryId(reqUrl);
        return originalFetch(input, init).then(function (response) {
          if (shouldCaptureApiUrl(reqUrl)) {
            try {
              response
                .clone()
                .text()
                .then(function (text) {
                  self.extractMediaFromResponse(reqUrl, text);
                })
                .catch(function () {});
            } catch (_) {}
          }
          return response;
        });
      };
    },
    hookXHR: function () {
      if (XMLHttpRequest.prototype.__tbccXFeedDlHooked) return;
      XMLHttpRequest.prototype.__tbccXFeedDlHooked = true;
      var self = this;
      var originalOpen = XMLHttpRequest.prototype.open;
      var originalSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (method, url) {
        this._tbccUrl = url;
        noteGqlQueryId(url);
        return originalOpen.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function () {
        this.addEventListener("load", function () {
          var reqUrl = String(this._tbccUrl || "");
          if (!shouldCaptureApiUrl(reqUrl)) return;
          if (!this.response) return;
          try {
            if (this.responseType === "" || this.responseType === "text") {
              self.extractMediaFromResponse(reqUrl, this.responseText);
            }
          } catch (_) {}
        });
        return originalSend.apply(this, arguments);
      };
    },
  };

  var XDownloadUI = {
    extractStatusId: function (url) {
      if (!url) return null;
      var m = String(url).match(/\/status\/(\d+)/);
      return m ? m[1] : null;
    },
    extFromUrl: function (url) {
      try {
        var p = new URL(url).pathname.split(".").pop();
        return p && p.length <= 5 ? p : null;
      } catch (_) {
        return null;
      }
    },
    sanitizeFilename: function (name) {
      return String(name || "media").replace(/[\/\\\?\%\*\:\|\\"<>\r\n]/g, "_").slice(0, 80);
    },
    setStatus: function (btn, classes, title) {
      if (classes) {
        btn.classList.remove("download", "completed", "loading", "failed");
        for (var i = 0; i < classes.length; i++) btn.classList.add(classes[i]);
      }
      if (title) btn.title = title;
    },
    primaryStatusId: function (article, statusIds) {
      if (article) {
        var timeEl = article.querySelector('a[href*="/status/"] time');
        if (timeEl) {
          var link = timeEl.closest("a");
          if (link && link.href) {
            var id = this.extractStatusId(link.href);
            if (id) return id;
          }
        }
      }
      return statusIds && statusIds.length ? statusIds[0] : null;
    },
    extractMediaFromArticle: function (article, statusId) {
      if (!article) return null;
      var text = "";
      var textEl = article.querySelector('[data-testid="tweetText"]');
      if (textEl) text = String(textEl.textContent || "").trim().slice(0, 50);
      var photo = "";
      article.querySelectorAll('img[src*="pbs.twimg.com/media"]').forEach(function (img) {
        var up = upgradeTwitterPhotoUrl(img.currentSrc || img.src || "");
        if (up && (!photo || up.length > photo.length)) photo = up;
      });
      var video = "";
      article.querySelectorAll("video").forEach(function (v) {
        var src = String(v.currentSrc || v.src || "");
        if (src && !/^blob:/i.test(src) && isSafeTwimgUrl(src)) video = src;
      });
      if (!video) {
        article.querySelectorAll("video source[src]").forEach(function (s) {
          var src = String(s.src || "");
          if (src && isSafeTwimgUrl(src)) video = src;
        });
      }
      if (!photo && !video) return null;
      return {
        entityId: statusId,
        text: text || statusId,
        photo: photo || null,
        video: video || null,
      };
    },
    tryPlayVideoInArticle: function (article) {
      if (!article) return;
      var play =
        article.querySelector('button[data-testid="playButton"]') ||
        article.querySelector('div[data-testid="videoComponent"] button') ||
        article.querySelector("video");
      if (play && typeof play.click === "function") {
        try {
          play.click();
        } catch (_) {}
      }
    },
    resolveMediaForStatus: async function (article, statusId, tabId, netBefore) {
      var mapped = XDownload.mediaMap.get(statusId);
      if (mapped && (mapped.video || mapped.photo)) return mapped;
      var dom = this.extractMediaFromArticle(article, statusId);
      if (dom && (dom.video || dom.photo)) {
        XDownload.upsertMediaEntry(statusId, dom);
        return dom;
      }
      var isVideoPost = article && article.querySelector('div[data-testid="videoComponent"], video, button[data-testid="playButton"]');
      if (!isVideoPost) return dom || mapped || null;
      if (article) {
        try {
          article.scrollIntoView({ block: "center", behavior: "auto" });
        } catch (_) {
          try {
            article.scrollIntoView(true);
          } catch (_2) {}
        }
      }
      this.tryPlayVideoInArticle(article);
      var deadline = Date.now() + 2200;
      while (Date.now() < deadline) {
        await sleep(180);
        mapped = XDownload.mediaMap.get(statusId);
        if (mapped && mapped.video && isSafeTwimgUrl(mapped.video)) return mapped;
        var mp4s = await getNetMp4sForTab(tabId);
        if (mp4s.length > netBefore) {
          var fresh = mp4s.slice(netBefore);
          var best = fresh[fresh.length - 1];
          if (best && isSafeTwimgUrl(best)) {
            var merged = {
              entityId: statusId,
              text: (dom && dom.text) || (mapped && mapped.text) || statusId,
              photo: (dom && dom.photo) || (mapped && mapped.photo) || null,
              video: best,
            };
            XDownload.upsertMediaEntry(statusId, merged);
            return merged;
          }
        }
      }
      return XDownload.mediaMap.get(statusId) || dom || null;
    },
    clickDownload: async function (btn, statusIds, article) {
      var self = this;
      var primary = this.primaryStatusId(article, statusIds);
      if (!primary) {
        this.setStatus(btn, ["failed"], "No tweet id on this post");
        return;
      }
      this.setStatus(btn, ["loading"], "Preparing download…");
      var tabId = await getCurrentTabId();
      var netBefore = (await getNetMp4sForTab(tabId)).length;
      var media;
      try {
        media = await this.resolveMediaForStatus(article, primary, tabId, netBefore);
      } catch (_) {
        media = null;
      }
      if (!media) {
        this.setStatus(btn, ["failed"], "No media URL — scroll post into view, play video once, retry");
        return;
      }
      var filename = this.sanitizeFilename(media.text || media.entityId || primary);
      var url = media.video;
      if (!url && media.photo) url = upgradeTwitterPhotoUrl(media.photo) || media.photo;
      if (!url || !isSafeTwimgUrl(url)) {
        this.setStatus(
          btn,
          ["failed"],
          media.video === null && article && article.querySelector("video")
            ? "Play the video once so TBCC can capture the MP4, then retry"
            : "Download failed — scroll post into view and retry"
        );
        return;
      }
      var ext = this.extFromUrl(url) || (media.video ? "mp4" : "jpg");
      try {
        await chromeDownload(url, filename + "." + ext);
        this.setStatus(btn, ["completed"], "Download complete");
      } catch (e) {
        this.setStatus(btn, ["failed"], String((e && e.message) || "Download failed — retry after playing video"));
      }
    },
    addButtonToArticle: function (article) {
      if (!article || article.dataset.tbccXFeedDl) return;
      article.dataset.tbccXFeedDl = "1";
      var statusIds = [];
      article.querySelectorAll('a[href*="/status/"]').forEach(function (el) {
        var id = XDownloadUI.extractStatusId(el.href);
        if (id && statusIds.indexOf(id) < 0) statusIds.push(id);
      });
      if (!statusIds.length) return;
      var hasMedia = article.querySelector(
        'a[href*="/photo/"], div[data-testid="videoComponent"], button[data-testid="playButton"], video, img[src*="twimg"]'
      );
      if (!hasMedia) return;
      var btnGroup =
        article.querySelector('div[role="group"]') ||
        article.querySelector('[data-testid="tweet"] div[role="group"]') ||
        article.querySelector('div[aria-label][role="group"]');
      if (!btnGroup) return;
      var btnShare =
        article.querySelector('[data-testid="share"]') ||
        article.querySelector('button[aria-label*="Share" i]') ||
        btnGroup.querySelector(":scope > div:last-child");
      if (!btnShare) return;
      var btnDownload = btnShare.cloneNode(true);
      btnDownload.style.marginLeft = "10px";
      var innerBtn = btnDownload.querySelector("button");
      if (innerBtn) innerBtn.removeAttribute("disabled");
      var svg = btnDownload.querySelector("svg");
      if (svg) svg.innerHTML = SVG;
      this.setStatus(btnDownload, ["x-master-dl", "download"], "Download media");
      if (btnShare.parentElement === btnGroup) {
        btnGroup.insertBefore(btnDownload, btnShare.nextSibling);
      } else {
        btnGroup.appendChild(btnDownload);
      }
      btnDownload.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        void XDownloadUI.clickDownload(btnDownload, statusIds, article);
      });
    },
    detect: function (node) {
      if (!node || node.nodeType !== 1) return;
      if (node.tagName === "ARTICLE") this.addButtonToArticle(node);
      if (node.querySelectorAll) {
        node.querySelectorAll("article").forEach(function (a) {
          XDownloadUI.addButtonToArticle(a);
        });
      }
    },
    startObserver: function () {
      if (this._obs) return;
      var self = this;
      this._obs = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          var added = mutations[i].addedNodes;
          for (var j = 0; j < added.length; j++) {
            if (added[j].nodeType === 1) self.detect(added[j]);
          }
        }
      });
      var root = document.body || document.documentElement;
      if (root) {
        this._obs.observe(root, { childList: true, subtree: true });
        root.querySelectorAll("article").forEach(function (a) {
          self.addButtonToArticle(a);
        });
      }
    },
    stop: function () {
      if (this._obs) {
        this._obs.disconnect();
        this._obs = null;
      }
      document.querySelectorAll(".x-master-dl").forEach(function (el) {
        el.remove();
      });
      document.querySelectorAll("article[data-tbcc-x-feed-dl]").forEach(function (el) {
        delete el.dataset.tbccXFeedDl;
      });
    },
  };

  function bootUI() {
    injectStyles();
    XDownloadUI.startObserver();
  }

  XDownload.hookXHR();
  XDownload.hookFetch();

  if (typeof tbccWaitForModule === "function") {
    tbccWaitForModule("x_profile_gallery", bootUI);
    if (typeof tbccBindModuleDisableListener === "function") {
      tbccBindModuleDisableListener("x_profile_gallery", function () {
        XDownloadUI.stop();
      });
    }
  } else {
    bootUI();
  }
})();
