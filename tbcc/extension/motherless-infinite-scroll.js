/**
 * TBCC Motherless infinite scroll — n+1 HTML fetch with hard RAM caps.
 * Defaults are stricter than ThisVid (that path can blow multi‑GB tabs).
 *
 * Invariants:
 *  - pagesLoadedExtra <= maxPages <= HARD.MAX_EXTRA_PAGES
 *  - live thumb cards <= maxCards <= HARD.MAX_CARDS_IN_DOM (prune after each append)
 *  - at most one in-flight fetch
 *  - no loads when tab hidden / on media detail / account forms
 *  - response HTML byte-capped
 */
(function (root) {
  "use strict";

  const HARD = Object.freeze({
    MAX_EXTRA_PAGES: 6,
    MAX_CARDS_IN_DOM: 80,
    MAX_THUMBS_PER_PAGE: 48,
    MAX_HTML_BYTES: 1_200_000,
    DEFAULT_EXTRA_PAGES: 3,
    DEFAULT_CARDS: 48,
    DEFAULT_COOLDOWN_MS: 2200,
    MIN_COOLDOWN_MS: 1200,
    MAX_COOLDOWN_MS: 8000,
  });

  function clampInt(raw, min, max, fallback) {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function resolveLimits(settings) {
    const s = settings || {};
    return {
      maxPages: clampInt(s.infiniteMaxPages, 1, HARD.MAX_EXTRA_PAGES, HARD.DEFAULT_EXTRA_PAGES),
      maxCards: clampInt(s.infiniteMaxCards, 20, HARD.MAX_CARDS_IN_DOM, HARD.DEFAULT_CARDS),
      cooldownMs: clampInt(
        s.infiniteCooldownMs,
        HARD.MIN_COOLDOWN_MS,
        HARD.MAX_COOLDOWN_MS,
        HARD.DEFAULT_COOLDOWN_MS
      ),
    };
  }

  function pageAllowsInfiniteScroll(pathname) {
    const p = String(pathname || "");
    // Single media / forms — never scroll-append
    if (/^\/[A-Fa-f0-9]{6,}\/?$/i.test(p) && !/^\/G/i.test(p)) return false;
    if (/^\/(login|register|upload|mail|account|settings|help|search\/write)/i.test(p)) return false;
    if (/^\/friends\/request/i.test(p)) return false;
    return true;
  }

  function currentPageFromUrl(href) {
    try {
      const u = new URL(String(href || "https://motherless.xxx/"));
      const p = parseInt(u.searchParams.get("page") || "1", 10);
      return p > 0 ? p : 1;
    } catch (_) {
      return 1;
    }
  }

  function buildUrlForPage(href, page) {
    const u = new URL(String(href || "https://motherless.xxx/"));
    const n = Math.max(1, parseInt(page, 10) || 1);
    if (n <= 1) u.searchParams.delete("page");
    else u.searchParams.set("page", String(n));
    return u.toString();
  }

  function countThumbCards(root) {
    const el = root || document;
    return el.querySelectorAll(
      ".thumb-container, .desktop-thumb, .ml-image-modal-data, .thumb-member-minibio"
    ).length;
  }

  function detachThumbMedia(node) {
    if (!node || !node.querySelectorAll) return;
    node.querySelectorAll("img, video, source").forEach((m) => {
      try {
        m.removeAttribute("src");
        m.removeAttribute("srcset");
        if (m.tagName === "VIDEO") {
          try {
            m.pause();
          } catch (_) {}
          m.removeAttribute("poster");
        }
      } catch (_) {}
    });
  }

  /** Drop oldest appended page blocks until under card budget. */
  function pruneOldestPages(container, maxCards) {
    if (!container) return 0;
    let removed = 0;
    while (countThumbCards(container) > maxCards) {
      const block = container.querySelector(".tbcc-ml-infinite-page");
      if (!block) break;
      detachThumbMedia(block);
      const before = countThumbCards(container);
      block.remove();
      const after = countThumbCards(container);
      removed += Math.max(0, before - after);
      if (before === after) break;
    }
    // Hard fallthrough: strip oldest thumbs if no page wrappers
    while (countThumbCards(container) > maxCards) {
      const thumb = container.querySelector(
        ".thumb-container, .desktop-thumb, .ml-image-modal-data, .thumb-member-minibio"
      );
      if (!thumb) break;
      detachThumbMedia(thumb);
      thumb.remove();
      removed += 1;
    }
    return removed;
  }

  function extractMediaGrid(doc) {
    const candidates = [
      doc.querySelector("#content .content-inner"),
      doc.querySelector(".content-inner"),
      doc.querySelector("#content"),
      doc.querySelector("main"),
      doc.body,
    ].filter(Boolean);
    for (const root of candidates) {
      const thumbs = root.querySelectorAll(".thumb-container, .desktop-thumb");
      if (thumbs.length) return { root, thumbs };
    }
    return { root: null, thumbs: [] };
  }

  class MotherlessInfiniteEngine {
    constructor(host) {
      this.host = host || {};
      this.currentPage = 1;
      this.pagesLoadedExtra = 0;
      this.loadingPage = false;
      this.reachedEnd = false;
      this.stats = { fetches: 0, bytesFetched: 0, appended: 0, pruned: 0, blocked: 0, rejected: 0 };
    }

    limits() {
      return resolveLimits(this.host.getSettings ? this.host.getSettings() : {});
    }

    allowed() {
      const pathname = this.host.getPathname ? this.host.getPathname() : "/";
      return pageAllowsInfiniteScroll(pathname);
    }

    resetForSetup(startPage) {
      this.currentPage = Math.max(1, parseInt(startPage, 10) || 1);
      this.pagesLoadedExtra = 0;
      this.loadingPage = false;
      this.reachedEnd = false;
    }

    async loadNextPage() {
      const settings = this.host.getSettings ? this.host.getSettings() : {};
      if (settings.infiniteScroll === false || this.loadingPage || this.reachedEnd) {
        this.stats.blocked += 1;
        return 0;
      }
      if (!this.allowed()) {
        this.reachedEnd = true;
        this.stats.blocked += 1;
        return 0;
      }
      if (this.host.isHidden && this.host.isHidden()) {
        this.stats.blocked += 1;
        return 0;
      }

      const { maxPages, maxCards } = this.limits();
      if (this.pagesLoadedExtra >= maxPages) {
        this.reachedEnd = true;
        this.stats.blocked += 1;
        return 0;
      }

      const container =
        (this.host.getContainer && this.host.getContainer()) ||
        document.querySelector("#content .content-inner") ||
        document.querySelector(".content-inner") ||
        document.querySelector("#content");
      if (!container) {
        this.stats.blocked += 1;
        return 0;
      }

      if (countThumbCards(container) >= maxCards) {
        this.stats.pruned += pruneOldestPages(container, maxCards - 8);
        if (countThumbCards(container) >= maxCards) {
          this.reachedEnd = true;
          this.stats.blocked += 1;
          return 0;
        }
      }

      this.loadingPage = true;
      const nextPage = this.currentPage + 1;
      const href = this.host.getHref ? this.host.getHref() : location.href;
      const url = buildUrlForPage(href, nextPage);

      try {
        if (this.host.onStatus) this.host.onStatus(`Loading page ${nextPage}…`);
        const res = await fetch(url, {
          credentials: "include",
          headers: { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buf = await res.arrayBuffer();
        this.stats.fetches += 1;
        this.stats.bytesFetched += buf.byteLength;
        if (buf.byteLength > HARD.MAX_HTML_BYTES) {
          this.stats.rejected += 1;
          this.reachedEnd = true;
          if (this.host.onStatus) this.host.onStatus("Stopped — HTML too large (RAM guard)");
          return 0;
        }
        const html = new TextDecoder("utf-8", { fatal: false }).decode(buf);
        const doc = new DOMParser().parseFromString(html, "text/html");
        const { thumbs } = extractMediaGrid(doc);
        if (!thumbs.length) {
          this.reachedEnd = true;
          if (this.host.onStatus) this.host.onStatus(`No more results after page ${this.currentPage}`);
          return 0;
        }

        const wrap = document.createElement("div");
        wrap.className = "tbcc-ml-infinite-page";
        wrap.dataset.page = String(nextPage);

        const sep = document.createElement("div");
        sep.className = "tbcc-ml-page-sep";
        sep.textContent = `Page ${nextPage}`;
        wrap.appendChild(sep);

        let added = 0;
        const limit = Math.min(thumbs.length, HARD.MAX_THUMBS_PER_PAGE);
        for (let i = 0; i < limit; i++) {
          const node = document.importNode(thumbs[i], true);
          node.querySelectorAll("img").forEach((img) => {
            try {
              img.loading = "lazy";
              img.decoding = "async";
            } catch (_) {}
          });
          wrap.appendChild(node);
          added += 1;
        }
        // Drop parsed document ASAP so GC can reclaim the full HTML tree.
        try {
          doc.documentElement.innerHTML = "";
        } catch (_) {}
        container.appendChild(wrap);
        this.currentPage = nextPage;
        this.pagesLoadedExtra += 1;
        this.stats.appended += added;

        this.stats.pruned += pruneOldestPages(container, maxCards);

        if (this.host.onPageAppended) this.host.onPageAppended(nextPage, added);
        if (this.host.onStatus) {
          this.host.onStatus(
            `TBCC ∞ page ${nextPage} · +${added} · cards ${countThumbCards(container)}/${maxCards}` +
              (this.pagesLoadedExtra >= maxPages ? " · page cap" : "")
          );
        }
        if (this.pagesLoadedExtra >= maxPages) this.reachedEnd = true;
        return added;
      } catch (e) {
        this.stats.rejected += 1;
        if (this.host.onStatus) this.host.onStatus(`Scroll load failed: ${(e && e.message) || e}`);
        return 0;
      } finally {
        this.loadingPage = false;
      }
    }
  }

  const api = {
    HARD,
    resolveLimits,
    pageAllowsInfiniteScroll,
    currentPageFromUrl,
    buildUrlForPage,
    countThumbCards,
    pruneOldestPages,
    detachThumbMedia,
    MotherlessInfiniteEngine,
  };

  root.TbccMotherlessInfinite = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : globalThis);
