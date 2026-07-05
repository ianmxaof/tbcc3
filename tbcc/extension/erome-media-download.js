/**
 * TBCC Erome album media download buttons (pink, X-enhancer style).
 * Surfaces one-tap download on album /a/ pages instead of raw source URLs.
 */
(function () {
  "use strict";
  if (window.__tbccEromeMediaDownload) return;
  window.__tbccEromeMediaDownload = true;

  var PINK = "#eb6395";
  var downloadIcon =
    '<path d="M11.99 16l-5.7-5.7L7.7 8.88l3.29 3.3V2.59h2v9.59l3.3-3.3 1.41 1.42-5.71 5.7zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z" fill="currentColor"/>';

  function injectStyles() {
    if (document.getElementById("tbcc-erome-media-dl-css")) return;
    var link = document.createElement("link");
    link.id = "tbcc-erome-media-dl-css";
    link.rel = "stylesheet";
    link.href = chrome.runtime.getURL("styles/erome-media-download.css");
    (document.head || document.documentElement).appendChild(link);
  }

  function isAlbumPage() {
    return /^\/a\/[^/]+/i.test(location.pathname || "");
  }

  function videoSources(video) {
    return Array.from(video.querySelectorAll("source")).filter(function (s) {
      return s.src;
    });
  }

  function pickBestSource(sources) {
    if (!sources.length) return null;
    if (sources.length === 1) return sources[0];
    var hd = sources.find(function (s) {
      return (s.getAttribute("label") || "").toUpperCase() === "HD";
    });
    if (hd) return hd;
    return sources[sources.length - 1];
  }

  function mediaUrlFromVideo(video) {
    var sources = videoSources(video);
    var picked = pickBestSource(sources);
    if (picked && picked.src) return picked.src;
    return video.currentSrc || video.src || "";
  }

  function mediaHostFor(video) {
    return (
      video.closest(".media-group, .album-media, .video-container, [class*='media']") ||
      video.parentElement
    );
  }

  function filenameFromUrl(url, fallback) {
    try {
      var base = new URL(url).pathname.split("/").pop() || fallback || "media";
      return "tbcc/erome/" + base.replace(/[^\w.\-]+/g, "_");
    } catch (_) {
      return "tbcc/erome/" + (fallback || "media.mp4");
    }
  }

  function setBtnState(btn, state) {
    btn.classList.remove("download", "loading", "completed", "failed");
    btn.classList.add(state);
    if (state === "loading") btn.disabled = true;
    else btn.disabled = false;
    if (state === "download") btn.title = "Download video";
    if (state === "loading") btn.title = "Downloading…";
    if (state === "completed") btn.title = "Download started";
    if (state === "failed") btn.title = "Download failed — try again";
  }

  function triggerDownload(url, btn, label) {
    if (!url || !/^https?:\/\//i.test(url)) {
      setBtnState(btn, "failed");
      return;
    }
    setBtnState(btn, "loading");
    chrome.runtime.sendMessage(
      {
        action: "tbcc-download-url-from-page-menu",
        url: url,
        refererPageUrl: location.href,
        filename: filenameFromUrl(url, label),
      },
      function (resp) {
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          setBtnState(btn, "failed");
          return;
        }
        setBtnState(btn, "completed");
        setTimeout(function () {
          setBtnState(btn, "download");
        }, 2500);
      }
    );
  }

  function makeButton(label, url) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tbcc-erome-dl download";
    btn.setAttribute("aria-label", "Download " + label);
    btn.title = "Download " + label;
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' + downloadIcon + "</svg>";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      triggerDownload(url, btn, label);
    });
    return btn;
  }

  function addButtonsToVideo(video) {
    if (video.dataset.tbccDlBound === "1") return;
    var host = mediaHostFor(video);
    if (!host) return;

    var sources = videoSources(video);
    var urls = [];
    if (sources.length) {
      sources.forEach(function (s) {
        var label = (s.getAttribute("label") || "").trim() || "video";
        if (s.src && !urls.some(function (u) { return u.url === s.src; })) {
          urls.push({ label: label, url: s.src });
        }
      });
    } else {
      var direct = mediaUrlFromVideo(video);
      if (direct) urls.push({ label: "video", url: direct });
    }
    if (!urls.length) return;

    video.dataset.tbccDlBound = "1";
    var wrap = host.querySelector(".tbcc-erome-dl-wrap");
    if (!wrap) {
      var pos = window.getComputedStyle(host).position;
      if (!pos || pos === "static") host.style.position = "relative";
      wrap = document.createElement("div");
      wrap.className = "tbcc-erome-dl-wrap";
      host.appendChild(wrap);
    }

    urls.forEach(function (item) {
      var key = item.url + "|" + item.label;
      if (wrap.querySelector('[data-dl-key="' + key + '"]')) return;
      var btn = makeButton(item.label, item.url);
      btn.dataset.dlKey = key;
      if (urls.length > 1 && item.label) {
        var tag = document.createElement("span");
        tag.className = "tbcc-erome-dl-label";
        tag.textContent = item.label.toUpperCase();
        btn.appendChild(tag);
      }
      wrap.appendChild(btn);
    });
  }

  function scan(root) {
    if (!isAlbumPage()) return;
    if (!root || root.nodeType !== 1) return;
    if (root.tagName === "VIDEO") addButtonsToVideo(root);
    root.querySelectorAll("video").forEach(addButtonsToVideo);
  }

  function init() {
    if (!isAlbumPage()) return;
    injectStyles();
    scan(document.body || document.documentElement);
    var mo = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType === 1) scan(node);
        });
      });
    });
    mo.observe(document.body || document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
