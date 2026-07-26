/**
 * X/Twitter per-post download buttons (XEnhancer-style, TBCC extension port).
 *
 * Media URLs come from x-api-hook.js (MAIN world) via postMessage — same source
 * as Tampermonkey XEnhancer's page-context XHR hook. Isolated-world fetch hooks
 * cannot see X GraphQL and must not be relied on.
 */
(function () {
  "use strict";

  var STYLE_ID = "tbcc-x-feed-download-css";
  var CSS =
    ".x-master-dl{margin-left:12px;order:99}.x-master-dl:hover>div>div>div>div{color:#1da1f2}" +
    ".x-master-dl:hover>div>div>div>div>div{background-color:rgba(29,161,242,.1)}" +
    ".x-master-dl:active>div>div>div>div>div{background-color:rgba(29,161,242,.2)}" +
    ".x-master-dl:hover svg{color:#1da1f2}" +
    ".x-master-dl:hover div:first-child:not(:last-child){background-color:rgba(29,161,242,.1)}" +
    ".x-master-dl:active div:first-child:not(:last-child){background-color:rgba(29,161,242,.2)}" +
    ".x-master-dl.tmd-media{position:absolute;right:0;z-index:5}" +
    ".x-master-dl.tmd-media>div{border-radius:99px;display:flex;margin:2px;background:rgba(0,0,0,.45)}" +
    ".x-master-dl.tmd-media>div>div{color:#fff;display:flex;margin:6px}" +
    ".x-master-dl.tmd-media:hover>div{background-color:hsla(0,0%,100%,.6)}" +
    ".x-master-dl.tmd-media:hover>div>div{color:#1da1f2}" +
    ".x-master-dl.tmd-media:not(:hover)>div>div{filter:drop-shadow(0 0 1px #000)}" +
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

  function profileFromArticleOrUrl(article, fallbackUrl) {
    try {
      var href = "";
      if (article && article.querySelector) {
        var a = article.querySelector('a[href*="/status/"]');
        if (a) href = String(a.href || "");
      }
      if (!href) href = String(fallbackUrl || location.href || "");
      var m = href.match(/(?:twitter\.com|x\.com)\/([^/?#]+)\/status\//i);
      if (!m) return "";
      var h = String(m[1] || "").toLowerCase();
      if (["home", "search", "i", "intent", "share", "explore", "notifications", "messages"].indexOf(h) >= 0) {
        return "";
      }
      return h.replace(/^@+/, "").slice(0, 64);
    } catch (_) {
      return "";
    }
  }

  /** SW applies AOF naming + Downloads/{tbcc/inbox}/; watch organizer watermarks. */
  function chromeDownloadToInbox(url, opts) {
    opts = opts || {};
    return new Promise(function (resolve, reject) {
      try {
        chrome.runtime.sendMessage(
          {
            action: "tbcc-x-media-download",
            url: url,
            refererPageUrl: location.href.split("#")[0],
            profileHint: opts.profileHint || "",
            indexHint: opts.indexHint != null ? opts.indexHint : undefined,
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
    upsertMediaEntry: function (entityId, patch) {
      if (!entityId) return;
      var prev = this.mediaMap.get(String(entityId)) || {
        entityId: String(entityId),
        video: null,
        photo: null,
        text: String(entityId),
      };
      if (patch.text) prev.text = patch.text;
      if (patch.video) prev.video = patch.video;
      if (patch.photo) prev.photo = patch.photo;
      if (patch.id) prev.id = patch.id;
      this.mediaMap.set(String(entityId), prev);
      if (this.mediaMap.size > 400) {
        var oldest = this.mediaMap.keys().next().value;
        if (oldest) this.mediaMap.delete(oldest);
      }
    },
    ingestHookEntries: function (entries) {
      if (!entries || !entries.length) return;
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (!e || !e.entityId) continue;
        this.upsertMediaEntry(e.entityId, {
          text: e.text,
          video: e.video,
          photo: e.photo,
          id: e.id,
        });
      }
    },
    listenPageHook: function () {
      if (window.__tbccXFeedHookListener) return;
      window.__tbccXFeedHookListener = true;
      window.addEventListener("message", function (ev) {
        try {
          if (ev.source !== window) return;
          var d = ev.data;
          if (!d || d.tbccXApiHook !== true) return;
          if (d.gql && d.gql.op && d.gql.id) {
            window.__tbccXGqlQueryIds = window.__tbccXGqlQueryIds || {};
            window.__tbccXGqlQueryIds[d.gql.op] = d.gql.id;
          }
          if (d.entries && d.entries.length) XDownload.ingestHookEntries(d.entries);
        } catch (_) {}
      });
    },
  };

  var XDownloadUI = {
    showSensitive: true,
    extractStatusId: function (url) {
      if (!url) return null;
      var m = String(url).match(/\/status\/(\d+)/);
      return m ? m[1] : null;
    },
    uniqueArray: function (arr) {
      return Array.from(new Set(arr.filter(Boolean)));
    },
    extFromUrl: function (url) {
      try {
        var p = new URL(url).pathname.split(".").pop();
        return p && p.length <= 5 ? p : null;
      } catch (_) {
        return null;
      }
    },
    setStatus: function (btn, classes, title) {
      if (classes) {
        btn.classList.remove("download", "completed", "loading", "failed");
        for (var i = 0; i < classes.length; i++) btn.classList.add(classes[i]);
      }
      if (title) btn.title = title;
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
      var isVideoPost =
        article &&
        article.querySelector('div[data-testid="videoComponent"], video, button[data-testid="playButton"]');
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
    /** XEnhancer-parity primary path: mediaMap from GraphQL hook + chrome.downloads. */
    clickDownloadEvent: async function (btn, statusIds, article) {
      var self = this;
      var uniqueStatusIds = this.uniqueArray(statusIds);
      if (!uniqueStatusIds.length) {
        this.setStatus(btn, ["failed"], "No tweet id on this post");
        return;
      }
      this.setStatus(btn, ["loading"], "Preparing download…");

      var tabId = await getCurrentTabId();
      var netBefore = (await getNetMp4sForTab(tabId)).length;

      var profileHint = profileFromArticleOrUrl(article, location.href);
      var downloadPromises = uniqueStatusIds.map(async function (statusId, i) {
        var media = XDownload.mediaMap.get(statusId);
        if (!media || (!media.video && !media.photo)) {
          media = await self.resolveMediaForStatus(article, statusId, tabId, netBefore);
        }
        if (!media || (!media.video && !media.photo)) {
          throw new Error("Media data not found for status ID: " + statusId);
        }
        var url = media.video;
        if (!url && media.photo) {
          url = upgradeTwitterPhotoUrl(media.photo) || media.photo;
        }
        if (!url || !isSafeTwimgUrl(url)) {
          throw new Error("No safe media URL for " + statusId);
        }
        // Prefer last 5 of tweet id so repeated saves stay stable + uniquify-friendly.
        var indexHint = Number(String(statusId).slice(-5)) || i + 1;
        await chromeDownloadToInbox(url, { profileHint: profileHint, indexHint: indexHint });
      });

      try {
        var results = await Promise.allSettled(downloadPromises);
        var anySuccess = results.some(function (r) {
          return r.status === "fulfilled";
        });
        if (anySuccess) {
          this.setStatus(btn, ["completed"], "Saved to TBCC inbox (AOF name)");
        } else {
          var firstErr =
            (results[0] && results[0].reason && results[0].reason.message) ||
            "Media not found — scroll timeline so X loads the post API, then retry";
          this.setStatus(btn, ["failed"], String(firstErr).slice(0, 120));
        }
      } catch (e) {
        this.setStatus(btn, ["failed"], String((e && e.message) || "Download failed"));
      }
    },
    addButtonTo: function (article) {
      if (!article || article.dataset.tbccXFeedDl) return;
      article.dataset.tbccXFeedDl = "1";
      var statusIds = [];
      article.querySelectorAll('a[href*="/status/"]').forEach(function (el) {
        var id = XDownloadUI.extractStatusId(el.href);
        if (id && statusIds.indexOf(id) < 0) statusIds.push(id);
      });
      if (!statusIds.length) return;

      var mediaSelector = [
        'a[href*="/photo/"]',
        'div[role="progressbar"]',
        'button[data-testid="playButton"]',
        'div[data-testid="videoComponent"]',
        'a[href="/settings/content_you_see"]',
        "div.media-image-container",
        "div.media-preview-container",
        'div[aria-labelledby]>div:first-child>div[role="button"][tabindex="0"]',
        'img[src*="twimg"]',
        "video",
      ].join(",");
      var hasMedia = article.querySelector(mediaSelector);
      if (!hasMedia) return;

      var btnGroup = article.querySelector(
        'div[role="group"]:last-of-type, ul.tweet-actions, ul.tweet-detail-actions'
      );
      if (!btnGroup) {
        btnGroup =
          article.querySelector('div[role="group"]') ||
          article.querySelector('[data-testid="tweet"] div[role="group"]');
      }
      if (btnGroup) {
        var shareCandidates = btnGroup.querySelectorAll(
          ':scope > div > div, li.tweet-action-item > a, li.tweet-detail-action-item > a'
        );
        var btnShare = null;
        if (shareCandidates.length) {
          btnShare = shareCandidates[shareCandidates.length - 1].parentNode;
        } else {
          btnShare =
            article.querySelector('[data-testid="share"]') ||
            article.querySelector('button[aria-label*="Share" i]') ||
            btnGroup.querySelector(":scope > div:last-child");
        }
        if (btnShare) {
          var btnDownload = btnShare.cloneNode(true);
          btnDownload.style.marginLeft = "10px";
          var innerBtn = btnDownload.querySelector("button");
          if (innerBtn) innerBtn.removeAttribute("disabled");
          var svg = btnDownload.querySelector("svg");
          if (svg) svg.innerHTML = SVG;
          this.setStatus(
            btnDownload,
            ["x-master-dl", "download"],
            "Save to TBCC inbox (AOF rename → watch folder)"
          );
          if (btnShare.parentElement === btnGroup) {
            btnGroup.insertBefore(btnDownload, btnShare.nextSibling);
          } else {
            btnGroup.appendChild(btnDownload);
          }
          btnDownload.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            void XDownloadUI.clickDownloadEvent(btnDownload, statusIds, article);
          });
          if (this.showSensitive) {
            try {
              var sens = article.querySelector(
                'div[aria-labelledby] div[role="button"][tabindex="0"]:not([data-testid]) > div[dir] > span > span'
              );
              if (sens) sens.click();
            } catch (_) {}
          }
        }
      }

      var imgs = article.querySelectorAll('a[href*="/photo/"]');
      if (imgs.length > 1) {
        imgs.forEach(function (img) {
          var imgStatusId = XDownloadUI.extractStatusId(img.href);
          if (!imgStatusId || (img.parentNode && img.parentNode.querySelector(".x-master-dl.tmd-img"))) return;
          var btnImg = document.createElement("div");
          btnImg.style.cssText = "position: absolute; top: 0; right: 0; z-index: 10; margin: 5px;";
          btnImg.innerHTML =
            '<div><div><svg viewBox="0 0 20 20" width="15" height="15">' + SVG + "</svg></div></div>";
          XDownloadUI.setStatus(
            btnImg,
            ["x-master-dl", "tmd-img", "download"],
            "Save image to TBCC inbox (AOF name)"
          );
          if (img.parentNode) {
            var parent = img.parentNode;
            if (!parent.style.position || parent.style.position === "static") {
              parent.style.position = "relative";
            }
            parent.appendChild(btnImg);
          }
          btnImg.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            void XDownloadUI.clickDownloadEvent(btnImg, [imgStatusId], article);
          });
        });
      }
    },
    addButtonToMedia: function (listitems) {
      var self = this;
      listitems.forEach(function (li) {
        if (!li || li.dataset.tbccXFeedDl) return;
        li.dataset.tbccXFeedDl = "1";
        var statusElement = li.querySelector('a[href*="/status/"]');
        var statusId = statusElement ? self.extractStatusId(statusElement.href) : null;
        if (!statusId) return;
        var btnDownload = document.createElement("div");
        btnDownload.innerHTML =
          '<div><div><svg viewBox="0 0 20 20" width="15" height="15">' + SVG + "</svg></div></div>";
        self.setStatus(
          btnDownload,
          ["x-master-dl", "tmd-media", "download"],
          "Save to TBCC inbox (AOF rename → watch folder)"
        );
        li.appendChild(btnDownload);
        btnDownload.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          var article = li.closest("article") || document.querySelector("article");
          void self.clickDownloadEvent(btnDownload, [statusId], article);
        });
      });
    },
    detect: function (node) {
      if (!node || node.nodeType !== 1) return;
      var article =
        (node.tagName === "ARTICLE" && node) ||
        (node.tagName === "DIV" && (node.querySelector("article") || node.closest("article")));
      if (article) this.addButtonTo(article);

      var listitems = null;
      if (node.tagName === "LI" && node.getAttribute("role") === "listitem") {
        listitems = [node];
      } else if (node.querySelectorAll) {
        listitems = node.querySelectorAll('li[role="listitem"]');
      }
      if (listitems && listitems.length) this.addButtonToMedia(listitems);
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
          self.addButtonTo(a);
        });
        root.querySelectorAll('li[role="listitem"]').forEach(function (li) {
          self.addButtonToMedia([li]);
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
      document.querySelectorAll("[data-tbcc-x-feed-dl]").forEach(function (el) {
        delete el.dataset.tbccXFeedDl;
      });
    },
  };

  function bootUI() {
    injectStyles();
    XDownload.listenPageHook();
    XDownloadUI.startObserver();
  }

  XDownload.listenPageHook();

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
