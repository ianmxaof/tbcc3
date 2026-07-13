/**
 * TBCC username search overlay — FAB + modal.
 * Probe-first (macro-style): never fan-out live tabs from the modal.
 * Open one site on demand; optional lazy blanks only via background helpers.
 */
(function () {
  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("username_search_overlay", function () {
    if (window.__tbccUsernameSearchOverlayLoaded) return;
    window.__tbccUsernameSearchOverlayLoaded = true;

    var ROOT_ID = "tbcc-ush-root";
    var FAB_ID = "tbcc-ush-fab";
    var STYLE_ID = "tbcc-ush-styles";
    var STORAGE_HISTORY = "tbccModelSearchHistory";
    var STORAGE_CUSTOM = "tbccModelSearchCustomSites";
    var STORAGE_ENABLED = "tbccModelSearchEnabledSites";
    var STORAGE_APPROVED = "tbccUsernameSearchApprovedHosts";
    var STORAGE_FAB_DENIED = "tbccUsernameSearchFabDeniedHosts";
    var PAGE_SIZE = 8;

    var lastSummary = null;
    var sourcesCache = [];
    var resultsPage = 0;
    var sourcesPage = 0;
    var activePane = "results";
    var fabHasResults = false;

    function isAlive() {
      try {
        return !!(chrome && chrome.runtime && chrome.runtime.id);
      } catch (_) {
        return false;
      }
    }

    function helpers() {
      return window.TbccUsernameSearchHistory || null;
    }

    function faviconForUrl(url) {
      try {
        var host = new URL(String(url || "")).hostname.replace(/^www\./, "");
        if (!host) return "";
        // DuckDuckGo icon CDN — real site favicons, no local assets required
        return "https://icons.duckduckgo.com/ip3/" + host + ".ico";
      } catch (_) {
        return "";
      }
    }

    function appendFavicon(parent, url) {
      var src = faviconForUrl(url);
      if (!src || !parent) return;
      var img = document.createElement("img");
      img.className = "tbcc-ush-favicon";
      img.alt = "";
      img.width = 16;
      img.height = 16;
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.src = src;
      img.addEventListener("error", function () {
        img.style.visibility = "hidden";
      });
      parent.insertBefore(img, parent.firstChild);
    }

    function setFabDot(on) {
      fabHasResults = !!on;
      var fab = document.getElementById(FAB_ID);
      if (!fab) return;
      fab.classList.toggle("tbcc-ush-fab--dot", fabHasResults);
      fab.title = fabHasResults ? "TBCC username search — new results" : "TBCC username search";
    }

    function pageSource() {
      var h = helpers();
      var s = h ? h.inferUsernameSearchSourceFromUrl(location.href) : "unknown";
      return s === "unknown" ? "overlay" : s;
    }

    function guessUser() {
      var h = helpers();
      return h ? h.guessUsernameFromLocation(location.href) : "";
    }

    function ensureStyles() {
      if (document.getElementById(STYLE_ID)) return;
      var s = document.createElement("style");
      s.id = STYLE_ID;
      s.textContent =
        "#" +
        FAB_ID +
        "{position:fixed;right:18px;bottom:88px;z-index:2147483640;width:48px;height:48px;border-radius:50%;" +
        "border:2px solid rgba(137,180,250,.9);background:rgba(17,17,27,.92);color:#cdd6f4;font-size:20px;cursor:pointer;" +
        "box-shadow:0 4px 18px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}" +
        "#" +
        FAB_ID +
        ":hover{border-color:#89b4fa;background:rgba(30,30,46,.96)}" +
        "#" +
        FAB_ID +
        ".tbcc-ush-fab--dot::after{content:'';position:absolute;top:2px;right:2px;width:11px;height:11px;" +
        "border-radius:50%;background:#f38ba8;border:2px solid #11111b;box-shadow:0 0 0 1px rgba(243,139,168,.5)}" +
        "#" +
        FAB_ID +
        "{position:fixed}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-favicon{width:16px;height:16px;border-radius:3px;flex-shrink:0;object-fit:contain;background:#11111b}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-main{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-title{display:flex;align-items:center;gap:8px;min-width:0}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-title strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        "#" +
        ROOT_ID +
        "{position:fixed;inset:0;z-index:2147483642;background:rgba(0,0,0,.55);display:flex;align-items:flex-start;" +
        "justify-content:center;padding:40px 16px 24px;font-family:system-ui,-apple-system,Segoe UI,sans-serif}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-panel{width:min(480px,100%);max-height:min(86vh,760px);overflow:auto;background:#1e1e2e;color:#cdd6f4;" +
        "border:1px solid #45475a;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.5);padding:14px 16px 18px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-head h2{margin:0;font-size:16px;font-weight:650}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-close{border:none;background:transparent;color:#a6adc8;font-size:22px;cursor:pointer;line-height:1}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-tabs{display:flex;gap:0;margin:0 0 10px;border:1px solid #45475a;border-radius:8px;overflow:hidden}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-tab{flex:1;padding:9px 6px;border:none;border-right:1px solid #45475a;border-bottom:2px solid transparent;" +
        "background:#11111b;color:#6c7086;font-size:12px;font-weight:600;cursor:pointer;text-align:center}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-tab:last-child{border-right:none}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-tab:hover{color:#cdd6f4;background:#181825}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-tab.active{color:#cdd6f4;background:#243039;border-bottom-color:#7ec8e3}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-step{font-size:11px;color:#89b4fa;margin:0 0 8px;font-weight:600;letter-spacing:.02em;text-transform:uppercase}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-card{border:1px solid #313244;border-radius:10px;padding:10px;margin:0 0 10px;background:#181825}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-host{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#a6e3a1;word-break:break-all}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-badge{display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:700;margin-left:6px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-badge.on{background:#a6e3a1;color:#11111b}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-badge.off{background:#45475a;color:#cdd6f4}" +
        "#" +
        ROOT_ID +
        " label{display:block;font-size:11px;color:#a6adc8;margin:8px 0 4px}" +
        "#" +
        ROOT_ID +
        " input,#" +
        ROOT_ID +
        " select{width:100%;box-sizing:border-box;border-radius:8px;border:1px solid #45475a;background:#11111b;" +
        "color:#cdd6f4;padding:8px 10px;font-size:13px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;align-items:center}" +
        "#" +
        ROOT_ID +
        " button.tbcc-ush-btn{border:1px solid #45475a;background:#313244;color:#cdd6f4;border-radius:8px;" +
        "padding:7px 12px;font-size:12px;cursor:pointer}" +
        "#" +
        ROOT_ID +
        " button.tbcc-ush-btn.primary{background:#89b4fa;border-color:#89b4fa;color:#11111b;font-weight:600}" +
        "#" +
        ROOT_ID +
        " button.tbcc-ush-btn:disabled{opacity:.5;cursor:not-allowed}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-status{min-height:1.2em;font-size:12px;color:#a6adc8;margin-top:8px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-status.err{color:#f38ba8}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-pane{display:none}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-pane.active{display:block}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-list{margin-top:8px;border:1px solid #313244;border-radius:10px;max-height:280px;overflow:auto}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid #313244}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item:hover{background:#313244}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-main{flex:1;min-width:0}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-main strong{display:block;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-item-main span{font-size:11px;color:#a6adc8}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-rank{font-size:11px;color:#a6e3a1;white-space:nowrap}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-pager{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:8px;font-size:12px;color:#a6adc8}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-hist-row{display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid #313244;cursor:pointer}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-hist-main{flex:1;min-width:0;display:flex;align-items:center;justify-content:space-between;gap:8px}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-hist-main code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-meta{display:flex;align-items:center;gap:6px;flex-shrink:0;font-size:11px;color:#a6adc8}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:18px;" +
        "padding:0 5px;border-radius:4px;font-size:10px;font-weight:700;color:#11111b}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--stripchat{background:#e91e63}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--chaturbate{background:#f7931e}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--onlyfans{background:#00aff0}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--fansly{background:#1d9bf0}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--instagram{background:linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);color:#fff}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--x{background:#e7e9ea}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-source--model_search,#" +
        ROOT_ID +
        " .tbcc-ush-source--macro,#" +
        ROOT_ID +
        " .tbcc-ush-source--overlay,#" +
        ROOT_ID +
        " .tbcc-ush-source--unknown{background:#6c7086;color:#cdd6f4}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-rm{border:none;background:transparent;color:#6c7086;font-size:16px;cursor:pointer;padding:0 4px}" +
        "#" +
        ROOT_ID +
        " details.tbcc-ush-add{margin-top:10px;border:1px solid #313244;border-radius:10px;padding:8px 10px}" +
        "#" +
        ROOT_ID +
        " details.tbcc-ush-add summary{cursor:pointer;font-size:12px;color:#89b4fa}" +
        "#" +
        ROOT_ID +
        " .tbcc-ush-hint{font-size:11px;color:#6c7086;margin:6px 0 0;line-height:1.35}";
      document.documentElement.appendChild(s);
    }

    function setStatus(el, msg, isErr) {
      if (!el) return;
      el.textContent = msg || "";
      el.className = "tbcc-ush-status" + (isErr ? " err" : "");
    }

    function formatTime(ts) {
      if (!ts || !Number.isFinite(ts)) return "";
      try {
        return new Date(ts).toLocaleString();
      } catch (_) {
        return "";
      }
    }

    function formatRate(site) {
      if (!site || site.hitRate == null) return "no data";
      var pct = Math.round(Number(site.hitRate) * 100);
      return pct + "% · " + site.hits + " hit / " + site.misses + " miss";
    }

    function validateCustomUrl(url) {
      var u = String(url || "").trim();
      if (!/^https?:\/\//i.test(u)) return "URL must start with http:// or https://";
      if (!u.includes("{username}")) return "URL must include {username}.";
      try {
        new URL(u.split("{username}").join("probe"));
      } catch (_) {
        return "Invalid URL.";
      }
      return null;
    }

    function normalizeHost(hostname) {
      return String(hostname || "")
        .toLowerCase()
        .replace(/^www\./, "")
        .trim();
    }

    function currentHost() {
      try {
        return normalizeHost(location.hostname);
      } catch (_) {
        return "";
      }
    }

    /** Turn the current page URL into a {username} search template. */
    function suggestTemplateFromPage() {
      var guessed = guessUser();
      var href = String(location.href || "").split("#")[0];
      try {
        var url = new URL(href);
        var keys = ["q", "query", "search", "username", "user", "model", "name", "keyword", "keywords", "s"];
        var hitKey = null;
        keys.forEach(function (k) {
          if (hitKey) return;
          if (url.searchParams.has(k) && String(url.searchParams.get(k) || "").trim()) hitKey = k;
        });
        if (hitKey) {
          url.searchParams.set(hitKey, "{username}");
          return url.toString();
        }
        if (guessed) {
          var enc = encodeURIComponent(guessed);
          var path = url.pathname;
          if (path.indexOf("/" + guessed) !== -1) {
            url.pathname = path.split("/" + guessed).join("/{username}");
            return url.toString();
          }
          if (path.indexOf("/" + enc) !== -1) {
            url.pathname = path.split("/" + enc).join("/{username}");
            return url.toString();
          }
          var full = url.toString();
          if (full.indexOf(enc) !== -1) return full.split(enc).join("{username}");
          if (full.indexOf(guessed) !== -1) return full.split(guessed).join("{username}");
        }
        url.searchParams.set("q", "{username}");
        return url.toString();
      } catch (_) {
        if (guessed && href.indexOf(guessed) !== -1) return href.split(guessed).join("{username}");
        return href + (href.indexOf("?") >= 0 ? "&" : "?") + "q={username}";
      }
    }

    function closeModal() {
      var root = document.getElementById(ROOT_ID);
      if (root) root.remove();
    }

    function sendMsg(payload) {
      return new Promise(function (resolve) {
        try {
          chrome.runtime.sendMessage(payload, function (resp) {
            if (chrome.runtime.lastError) {
              resolve({ ok: false, error: chrome.runtime.lastError.message });
              return;
            }
            resolve(resp || { ok: false, error: "no_response" });
          });
        } catch (e) {
          resolve({ ok: false, error: String(e && e.message ? e.message : e) });
        }
      });
    }

    async function copyUsername(username) {
      try {
        await navigator.clipboard.writeText(username);
        return true;
      } catch (_) {
        return false;
      }
    }

    function openSiteUrl(url, username, siteId, statusEl) {
      setStatus(statusEl, "Opening…");
      return sendMsg({
        action: "tbcc-open-model-search-url",
        url: url || "",
        username: username || "",
        siteId: siteId || "",
        lazy: false,
        active: true,
      }).then(function (r) {
        if (!r || !r.ok) {
          setStatus(statusEl, (r && r.error) || "Could not open", true);
          return;
        }
        setStatus(statusEl, "Opened in a new tab.");
      });
    }

    function pageSlice(arr, page) {
      var start = page * PAGE_SIZE;
      return {
        items: arr.slice(start, start + PAGE_SIZE),
        total: arr.length,
        page: page,
        pages: Math.max(1, Math.ceil(arr.length / PAGE_SIZE) || 1),
      };
    }

    function renderResults(panel) {
      var list = panel.querySelector("#tbcc-ush-results");
      var pager = panel.querySelector("#tbcc-ush-results-pager");
      if (!list || !pager) return;
      list.innerHTML = "";
      var hits = lastSummary && Array.isArray(lastSummary.hits) ? lastSummary.hits : [];
      if (!lastSummary) {
        list.innerHTML = '<div class="tbcc-ush-item"><div class="tbcc-ush-item-main"><span>Run Search to probe macro sources (no mass tab open).</span></div></div>';
        pager.textContent = "";
        return;
      }
      if (lastSummary.status === "running") {
        list.innerHTML =
          '<div class="tbcc-ush-item"><div class="tbcc-ush-item-main"><span>Searching… ' +
          (lastSummary.scanned || 0) +
          " / " +
          (lastSummary.totalSites || "?") +
          "</span></div></div>";
        pager.textContent = "";
        return;
      }
      if (!hits.length) {
        list.innerHTML =
          '<div class="tbcc-ush-item"><div class="tbcc-ush-item-main"><span>No hits for @' +
          String(lastSummary.query || "") +
          ". Check Sources ranking or add templates.</span></div></div>";
        pager.textContent = "";
        return;
      }
      var maxPage = Math.max(0, Math.ceil(hits.length / PAGE_SIZE) - 1);
      if (resultsPage > maxPage) resultsPage = maxPage;
      var slice = pageSlice(hits, resultsPage);
      var user = String(lastSummary.query || "");
      slice.items.forEach(function (h) {
        var row = document.createElement("div");
        row.className = "tbcc-ush-item";
        var main = document.createElement("div");
        main.className = "tbcc-ush-item-main";
        var titleRow = document.createElement("div");
        titleRow.className = "tbcc-ush-item-title";
        appendFavicon(titleRow, h.url);
        var title = document.createElement("strong");
        title.textContent = h.name || h.siteId || "Source";
        titleRow.appendChild(title);
        var sub = document.createElement("span");
        sub.textContent = "~" + (h.count || 0) + " result(s)" + (h.family ? " · " + h.family : "");
        main.appendChild(titleRow);
        main.appendChild(sub);
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tbcc-ush-btn primary";
        btn.textContent = "Open";
        btn.addEventListener("click", function () {
          var statusEl = panel.querySelector("#tbcc-ush-status");
          void openSiteUrl(h.url, user, h.siteId, statusEl);
        });
        row.appendChild(main);
        row.appendChild(btn);
        list.appendChild(row);
      });
      pager.innerHTML = "";
      var prev = document.createElement("button");
      prev.type = "button";
      prev.className = "tbcc-ush-btn";
      prev.textContent = "Prev";
      prev.disabled = resultsPage <= 0;
      prev.addEventListener("click", function () {
        resultsPage = Math.max(0, resultsPage - 1);
        renderResults(panel);
      });
      var info = document.createElement("span");
      info.textContent = "Hits " + (slice.page + 1) + " / " + slice.pages + " · " + slice.total + " site(s)";
      var next = document.createElement("button");
      next.type = "button";
      next.className = "tbcc-ush-btn";
      next.textContent = "Next";
      next.disabled = resultsPage >= slice.pages - 1;
      next.addEventListener("click", function () {
        resultsPage = Math.min(slice.pages - 1, resultsPage + 1);
        renderResults(panel);
      });
      pager.appendChild(prev);
      pager.appendChild(info);
      pager.appendChild(next);
    }

    function renderSources(panel) {
      var list = panel.querySelector("#tbcc-ush-sources");
      var pager = panel.querySelector("#tbcc-ush-sources-pager");
      var userInput = panel.querySelector("#tbcc-ush-user");
      var statusEl = panel.querySelector("#tbcc-ush-status");
      if (!list || !pager) return;
      list.innerHTML = "";
      if (!sourcesCache.length) {
        list.innerHTML =
          '<div class="tbcc-ush-item"><div class="tbcc-ush-item-main"><span>No macro sources enabled. Add some under Options or below.</span></div></div>';
        pager.textContent = "";
        return;
      }
      var maxPage = Math.max(0, Math.ceil(sourcesCache.length / PAGE_SIZE) - 1);
      if (sourcesPage > maxPage) sourcesPage = maxPage;
      var slice = pageSlice(sourcesCache, sourcesPage);
      slice.items.forEach(function (site, idx) {
        var rank = sourcesPage * PAGE_SIZE + idx + 1;
        var row = document.createElement("div");
        row.className = "tbcc-ush-item";
        var main = document.createElement("div");
        main.className = "tbcc-ush-item-main";
        var titleRow = document.createElement("div");
        titleRow.className = "tbcc-ush-item-title";
        var hostUrl = String(site.url || "").replace("{username}", "x");
        appendFavicon(titleRow, hostUrl);
        var title = document.createElement("strong");
        title.textContent = "#" + rank + "  " + (site.name || site.id);
        titleRow.appendChild(title);
        var sub = document.createElement("span");
        sub.textContent = formatRate(site);
        main.appendChild(titleRow);
        main.appendChild(sub);
        var rankEl = document.createElement("span");
        rankEl.className = "tbcc-ush-rank";
        rankEl.textContent = site.hitRate == null ? "—" : Math.round(site.hitRate * 100) + "%";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tbcc-ush-btn";
        btn.textContent = "Open";
        btn.title = "Open this source for the username above (one tab)";
        btn.addEventListener("click", function () {
          var u = String((userInput && userInput.value) || "").trim().replace(/^@+/, "");
          if (!u) {
            setStatus(statusEl, "Enter a username first.", true);
            return;
          }
          void openSiteUrl("", u, site.id, statusEl);
        });
        row.appendChild(main);
        row.appendChild(rankEl);
        row.appendChild(btn);
        list.appendChild(row);
      });
      pager.innerHTML = "";
      var prev = document.createElement("button");
      prev.type = "button";
      prev.className = "tbcc-ush-btn";
      prev.textContent = "Prev";
      prev.disabled = sourcesPage <= 0;
      prev.addEventListener("click", function () {
        sourcesPage = Math.max(0, sourcesPage - 1);
        renderSources(panel);
      });
      var info = document.createElement("span");
      info.textContent = "Sources " + (slice.page + 1) + " / " + slice.pages + " · ranked by hit rate";
      var next = document.createElement("button");
      next.type = "button";
      next.className = "tbcc-ush-btn";
      next.textContent = "Next";
      next.disabled = sourcesPage >= slice.pages - 1;
      next.addEventListener("click", function () {
        sourcesPage = Math.min(slice.pages - 1, sourcesPage + 1);
        renderSources(panel);
      });
      pager.appendChild(prev);
      pager.appendChild(info);
      pager.appendChild(next);
    }

    async function loadSources(panel) {
      var r = await sendMsg({ action: "tbcc-list-macro-sources" });
      sourcesCache = r && r.ok && Array.isArray(r.sites) ? r.sites : [];
      renderSources(panel);
    }

    async function renderHistory(listEl, statusEl, userInput) {
      if (!listEl) return;
      var data = await chrome.storage.local.get([STORAGE_HISTORY]);
      var rows = Array.isArray(data[STORAGE_HISTORY]) ? data[STORAGE_HISTORY] : [];
      listEl.innerHTML = "";
      if (!rows.length) {
        listEl.textContent = "No usernames searched yet.";
        return;
      }
      var h = helpers();
      rows.slice(0, 40).forEach(function (r) {
        var username = String((r && r.username) || "").trim();
        if (!username) return;
        var ts = Number((r && r.ts) || 0);
        var source = String((r && r.source) || "unknown");
        var row = document.createElement("div");
        row.className = "tbcc-ush-hist-row";
        row.title = "Click to copy · double-click to search";

        var rm = document.createElement("button");
        rm.type = "button";
        rm.className = "tbcc-ush-rm";
        rm.textContent = "×";
        rm.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          if (!window.confirm('Remove "' + username + '" from username search history?')) return;
          chrome.storage.local.get([STORAGE_HISTORY], function (latest) {
            var arr = Array.isArray(latest[STORAGE_HISTORY]) ? latest[STORAGE_HISTORY] : [];
            var filtered = arr.filter(function (x) {
              return !(
                String((x && x.username) || "").trim() === username && Number((x && x.ts) || 0) === ts
              );
            });
            chrome.storage.local.set({ [STORAGE_HISTORY]: filtered }, function () {
              void renderHistory(listEl, statusEl, userInput);
            });
          });
        });

        var mid = document.createElement("div");
        mid.className = "tbcc-ush-hist-main";
        var code = document.createElement("code");
        code.textContent = username;
        var meta = document.createElement("span");
        meta.className = "tbcc-ush-meta";
        if (h && h.appendUsernameSearchSourceBadge) h.appendUsernameSearchSourceBadge(meta, source);
        var time = document.createElement("span");
        time.textContent = formatTime(ts);
        meta.appendChild(time);
        mid.appendChild(code);
        mid.appendChild(meta);
        row.appendChild(rm);
        row.appendChild(mid);
        row.addEventListener("click", function (e) {
          if (e.target === rm || rm.contains(e.target)) return;
          void copyUsername(username).then(function (ok) {
            setStatus(statusEl, ok ? "Copied @" + username : "Copy failed", !ok);
            if (userInput) userInput.value = username;
          });
        });
        row.addEventListener("dblclick", function (e) {
          e.preventDefault();
          if (userInput) userInput.value = username;
          void runProbe(username, statusEl, panelFrom(listEl));
        });
        listEl.appendChild(row);
      });
    }

    function panelFrom(el) {
      return el && el.closest ? el.closest(".tbcc-ush-panel") : null;
    }

    function setPane(panel, name) {
      activePane = name;
      panel.querySelectorAll(".tbcc-ush-tab").forEach(function (t) {
        t.classList.toggle("active", t.getAttribute("data-pane") === name);
      });
      panel.querySelectorAll(".tbcc-ush-pane").forEach(function (p) {
        p.classList.toggle("active", p.id === "tbcc-ush-pane-" + name);
      });
    }

    function runProbe(username, statusEl, panel) {
      var u = String(username || "").trim().replace(/^@+/, "");
      if (!u) {
        setStatus(statusEl, "Enter a username.", true);
        return Promise.resolve();
      }
      setStatus(statusEl, "Probing macro sources (no tabs)…");
      lastSummary = {
        query: u,
        status: "running",
        scanned: 0,
        totalSites: "?",
        hits: [],
      };
      resultsPage = 0;
      if (panel) {
        setPane(panel, "results");
        renderResults(panel);
      }
      return sendMsg({
        action: "tbcc-macro-model-search",
        username: u,
        source: pageSource(),
      }).then(function (resp) {
        if (!resp || resp.ok === false) {
          setStatus(statusEl, (resp && resp.error) || "Search failed", true);
          lastSummary = null;
          if (panel) renderResults(panel);
          return;
        }
        lastSummary = resp.summary || null;
        var hits = lastSummary && Array.isArray(lastSummary.hits) ? lastSummary.hits.length : 0;
        var scanned = lastSummary && lastSummary.scanned != null ? lastSummary.scanned : 0;
        var src = lastSummary && lastSummary.source ? lastSummary.source : "";
        setFabDot(hits > 0);
        setStatus(
          statusEl,
          hits
            ? "Found " + hits + " real hit(s) of " + scanned + (src ? " · prioritized for " + src : "") + "."
            : "No real hits on " + scanned + " source(s)" + (src ? " for " + src : "") + ". Sites with only search-box echoes are hidden."
        );
        if (panel) {
          renderResults(panel);
          void loadSources(panel);
          var histEl = panel.querySelector("#tbcc-ush-hist");
          void renderHistory(histEl, statusEl, panel.querySelector("#tbcc-ush-user"));
        }
      });
    }

    async function addSource(name, url, category, statusEl, panel) {
      var err = validateCustomUrl(url);
      if (!String(name || "").trim()) {
        setStatus(statusEl, "Enter a display name.", true);
        return;
      }
      if (err) {
        setStatus(statusEl, err, true);
        return;
      }
      var id = "custom_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
      var site = {
        id: id,
        name: String(name).trim(),
        url: String(url).trim(),
        category: String(category || "macro").trim().toLowerCase() || "macro",
      };
      var data = await chrome.storage.local.get([STORAGE_CUSTOM, STORAGE_ENABLED]);
      var arr = Array.isArray(data[STORAGE_CUSTOM]) ? data[STORAGE_CUSTOM].slice() : [];
      arr.push(site);
      var enabled =
        data[STORAGE_ENABLED] && typeof data[STORAGE_ENABLED] === "object"
          ? Object.assign({}, data[STORAGE_ENABLED])
          : {};
      enabled[id] = true;
      await chrome.storage.local.set({ [STORAGE_CUSTOM]: arr, [STORAGE_ENABLED]: enabled });
      setStatus(statusEl, "Source added.");
      if (panel) void loadSources(panel);
    }

    function openModal() {
      if (!isAlive()) return;
      closeModal();
      ensureStyles();
      var root = document.createElement("div");
      root.id = ROOT_ID;
      root.setAttribute("role", "dialog");
      root.setAttribute("aria-label", "TBCC macrosearch");

      var panel = document.createElement("div");
      panel.className = "tbcc-ush-panel";
      panel.innerHTML =
        '<div class="tbcc-ush-head"><h2>Macrosearch</h2><button type="button" class="tbcc-ush-close" aria-label="Close">×</button></div>' +
        '<div class="tbcc-ush-tabs" role="tablist">' +
        '<button type="button" class="tbcc-ush-tab" data-pane="setup" role="tab">Setup</button>' +
        '<button type="button" class="tbcc-ush-tab active" data-pane="results" role="tab">Search</button>' +
        '<button type="button" class="tbcc-ush-tab" data-pane="sources" role="tab">Sources</button>' +
        '<button type="button" class="tbcc-ush-tab" data-pane="history" role="tab">History</button>' +
        "</div>" +
        '<div class="tbcc-ush-status" id="tbcc-ush-status"></div>' +
        '<div class="tbcc-ush-pane" id="tbcc-ush-pane-setup">' +
        '<p class="tbcc-ush-step">Step 1 — site + source</p>' +
        '<div class="tbcc-ush-card">' +
        '<div>This host: <span class="tbcc-ush-host" id="tbcc-ush-host"></span> <span class="tbcc-ush-badge off" id="tbcc-ush-host-badge">…</span></div>' +
        '<p class="tbcc-ush-hint">Approve this site so the ⌕ FAB stays active here after reload. Builtin cam/OF/X hosts are already allowed.</p>' +
        '<div class="tbcc-ush-row">' +
        '<button type="button" class="tbcc-ush-btn primary" id="tbcc-ush-approve">Approve this site</button>' +
        '<button type="button" class="tbcc-ush-btn" id="tbcc-ush-revoke">Disable FAB here</button>' +
        "</div></div>" +
        '<div class="tbcc-ush-card">' +
        '<div style="font-size:12px;font-weight:600;margin-bottom:4px">Add source (template helper)</div>' +
        '<p class="tbcc-ush-hint">Paste a real search URL after you search manually, then put <code>{username}</code> where the query goes — or tap <strong>From this page</strong>.</p>' +
        '<label for="tbcc-ush-src-name">Name</label><input id="tbcc-ush-src-name" type="text" placeholder="My forum" />' +
        '<label for="tbcc-ush-src-url">URL template</label><input id="tbcc-ush-src-url" type="url" placeholder="https://example.com/search?q={username}" />' +
        '<label for="tbcc-ush-src-cat">Category</label>' +
        '<select id="tbcc-ush-src-cat"><option value="macro">Macro search</option>' +
        '<option value="onlyfans">OnlyFans search</option><option value="livecams">Live cam search</option>' +
        '<option value="videos">Video search</option></select>' +
        '<div class="tbcc-ush-row">' +
        '<button type="button" class="tbcc-ush-btn" id="tbcc-ush-src-from-page">From this page</button>' +
        '<button type="button" class="tbcc-ush-btn primary" id="tbcc-ush-src-add">Add source</button>' +
        "</div></div></div>" +
        '<div class="tbcc-ush-pane active" id="tbcc-ush-pane-results">' +
        '<p class="tbcc-ush-step">Step 2 — search + open</p>' +
        '<label for="tbcc-ush-user">Username</label>' +
        '<input id="tbcc-ush-user" type="text" autocomplete="off" spellcheck="false" placeholder="model_name" />' +
        '<div class="tbcc-ush-row">' +
        '<button type="button" class="tbcc-ush-btn primary" id="tbcc-ush-search">Search</button>' +
        "</div>" +
        '<p class="tbcc-ush-hint">Probes macro sources in the background — does <strong>not</strong> open dozens of tabs. Open a hit below, or use the Sources tab mini-menu.</p>' +
        '<div class="tbcc-ush-list" id="tbcc-ush-results"></div>' +
        '<div class="tbcc-ush-pager" id="tbcc-ush-results-pager"></div>' +
        "</div>" +
        '<div class="tbcc-ush-pane" id="tbcc-ush-pane-sources">' +
        '<p class="tbcc-ush-step">Visit a source</p>' +
        '<p class="tbcc-ush-hint">Paginated mini-menu — ranked by historical hit rate. Opens one tab for the username on Search.</p>' +
        '<div class="tbcc-ush-list" id="tbcc-ush-sources"></div>' +
        '<div class="tbcc-ush-pager" id="tbcc-ush-sources-pager"></div>' +
        "</div>" +
        '<div class="tbcc-ush-pane" id="tbcc-ush-pane-history">' +
        '<div class="tbcc-ush-list" id="tbcc-ush-hist"></div>' +
        "</div>";

      root.appendChild(panel);
      document.documentElement.appendChild(root);

      var userInput = panel.querySelector("#tbcc-ush-user");
      var statusEl = panel.querySelector("#tbcc-ush-status");
      var histEl = panel.querySelector("#tbcc-ush-hist");
      var hostEl = panel.querySelector("#tbcc-ush-host");
      var badgeEl = panel.querySelector("#tbcc-ush-host-badge");
      var guessed = guessUser();
      if (guessed && userInput) userInput.value = guessed;
      if (hostEl) hostEl.textContent = currentHost() || "(unknown)";

      function refreshHostStatus() {
        return sendMsg({ action: "tbcc-username-search-host-status", url: location.href }).then(function (r) {
          if (!badgeEl) return;
          if (!r || !r.ok) {
            badgeEl.textContent = "unknown";
            badgeEl.className = "tbcc-ush-badge off";
            return;
          }
          var on = r.allowed && !r.fabDenied;
          badgeEl.textContent = r.fabDenied
            ? "FAB off"
            : r.builtin
              ? "builtin"
              : r.approved
                ? "approved"
                : "not approved";
          badgeEl.className = "tbcc-ush-badge " + (on ? "on" : "off");
        });
      }
      void refreshHostStatus();

      panel.querySelector(".tbcc-ush-close").addEventListener("click", closeModal);
      root.addEventListener("click", function (e) {
        if (e.target === root) closeModal();
      });
      panel.addEventListener("click", function (e) {
        e.stopPropagation();
      });

      panel.querySelectorAll(".tbcc-ush-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
          setPane(panel, tab.getAttribute("data-pane"));
          if (tab.getAttribute("data-pane") === "sources") void loadSources(panel);
          if (tab.getAttribute("data-pane") === "history") void renderHistory(histEl, statusEl, userInput);
          if (tab.getAttribute("data-pane") === "setup") void refreshHostStatus();
        });
      });

      panel.querySelector("#tbcc-ush-approve").addEventListener("click", function () {
        void sendMsg({ action: "tbcc-approve-username-search-host", host: currentHost() }).then(function (r) {
          if (!r || !r.ok) {
            setStatus(statusEl, (r && r.error) || "Approve failed", true);
            return;
          }
          setStatus(statusEl, "Approved " + (r.host || currentHost()) + " — FAB will load on this host.");
          void refreshHostStatus();
          ensureFab();
        });
      });
      panel.querySelector("#tbcc-ush-revoke").addEventListener("click", function () {
        void sendMsg({ action: "tbcc-revoke-username-search-host", host: currentHost() }).then(function (r) {
          if (!r || !r.ok) {
            setStatus(statusEl, (r && r.error) || "Disable failed", true);
            return;
          }
          setStatus(statusEl, "FAB disabled for " + (r.host || currentHost()) + ".");
          void refreshHostStatus();
          var fab = document.getElementById(FAB_ID);
          if (fab) fab.remove();
        });
      });

      panel.querySelector("#tbcc-ush-search").addEventListener("click", function () {
        void runProbe(userInput && userInput.value, statusEl, panel);
      });
      userInput &&
        userInput.addEventListener("keydown", function (e) {
          if (e.key === "Enter") {
            e.preventDefault();
            void runProbe(userInput.value, statusEl, panel);
          }
          if (e.key === "Escape") closeModal();
        });

      panel.querySelector("#tbcc-ush-src-from-page").addEventListener("click", function () {
        var tpl = suggestTemplateFromPage();
        var urlInput = panel.querySelector("#tbcc-ush-src-url");
        var nameInput = panel.querySelector("#tbcc-ush-src-name");
        if (urlInput) urlInput.value = tpl;
        if (nameInput && !String(nameInput.value || "").trim()) {
          nameInput.value = currentHost() || "Custom source";
        }
        setStatus(statusEl, "Template filled from this page — edit if needed, then Add source.");
        setPane(panel, "setup");
      });

      panel.querySelector("#tbcc-ush-src-add").addEventListener("click", function () {
        void addSource(
          panel.querySelector("#tbcc-ush-src-name").value,
          panel.querySelector("#tbcc-ush-src-url").value,
          panel.querySelector("#tbcc-ush-src-cat").value,
          statusEl,
          panel
        ).then(function () {
          panel.querySelector("#tbcc-ush-src-name").value = "";
          panel.querySelector("#tbcc-ush-src-url").value = "";
        });
      });

      renderResults(panel);
      void loadSources(panel);
      void renderHistory(histEl, statusEl, userInput);
      if (userInput) userInput.focus();
    }

    async function fabAllowedHere() {
      try {
        var host = currentHost();
        var data = await chrome.storage.local.get([STORAGE_APPROVED, STORAGE_FAB_DENIED]);
        var denied = (Array.isArray(data[STORAGE_FAB_DENIED]) ? data[STORAGE_FAB_DENIED] : []).map(normalizeHost);
        if (denied.indexOf(host) !== -1) return false;
        return true;
      } catch (_) {
        return true;
      }
    }

    function ensureFab() {
      if (!isAlive()) return;
      void fabAllowedHere().then(function (ok) {
        if (!ok) {
          var old = document.getElementById(FAB_ID);
          if (old) old.remove();
          return;
        }
        if (document.getElementById(FAB_ID)) return;
        ensureStyles();
        var fab = document.createElement("button");
        fab.id = FAB_ID;
        fab.type = "button";
        fab.title = "TBCC macrosearch";
        fab.setAttribute("aria-label", "TBCC macrosearch");
        fab.textContent = "⌕";
        fab.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          setFabDot(false);
          openModal();
        });
        if (fabHasResults) fab.classList.add("tbcc-ush-fab--dot");
        document.documentElement.appendChild(fab);
      });
    }

    function teardown() {
      closeModal();
      var fab = document.getElementById(FAB_ID);
      if (fab) fab.remove();
      var st = document.getElementById(STYLE_ID);
      if (st) st.remove();
    }

    if (typeof tbccBindModuleDisableListener === "function") {
      tbccBindModuleDisableListener("username_search_overlay", teardown);
    }

    ensureFab();
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) ensureFab();
    });
  });
})();
