/**
 * TBCC Motherless enhancer — chevron overlay (friends bulk), thumbnail social actions.
 * Domains: motherless.com / motherless.xxx
 *
 * Social (session cookies):
 *   POST /friends/request?member={user}&back=…  (+ page _token; never fetch /m/{user} HTML per friend)
 *   POST /favorites/add  { codename, group }
 *   POST /shouts         { codename, visibility, parent, content, send }
 *   /media/add  { codenames[], gallery_codename } → JSON { status: "ok" }  (site media.js)
 *   /media/groups?codenames[]=… then group pick (modal); /groups/rmedia for remove
 */
(function () {
  "use strict";

  const HOST_RE = /(^|\.)motherless\.(com|xxx)$/i;
  if (!HOST_RE.test(location.hostname || "")) return;

  const MODULE_ID = "motherless_enhancer";
  const OVERLAY_ID = "tbcc-ml-overlay";
  const OVERLAY_TOP_KEY = "tbcc_ml_overlay_top_v1";
  const OVERLAY_UI_KEY = "tbcc_ml_overlay_ui_v1";
  const SETTINGS_KEY = "tbcc_ml_settings_v1";
  const FRIEND_SENT_KEY = "tbcc_ml_friend_sent_v1";
  const INTEL_ROWS_KEY = "tbcc_ml_intel_rows_v1";
  const INTEL_META_KEY = "tbcc_ml_intel_meta_v1";
  const GALLERY_CACHE_KEY = "tbcc_ml_my_galleries_v5";
  const GROUP_CACHE_KEY = "tbcc_ml_my_groups_v5";
  const ML_USER_CACHE_KEY = "tbcc_ml_account_user_v1";

  const SKIP_USERS = new Set([
    "anonymous",
    "login",
    "register",
    "upload",
    "search",
    "members",
    "groups",
    "images",
    "videos",
    "galleries",
    "shouts",
    "categories",
    "store",
    "chat",
    "help",
    "faq",
    "about",
    "contact",
    "dmca",
    "privacy",
    "rules",
  ]);

  const defaultSettings = () => ({
    friendConcurrency: 2,
    friendDelayMs: 700,
    friendMessage: "",
    thumbActions: true,
    defaultShout: "",
    lastGalleryId: "",
    lastGroupSlug: "",
    infiniteScroll: true,
    infiniteMaxPages: 3,
    infiniteMaxCards: 48,
    infiniteCooldownMs: 2200,
    titleInclude: "",
    titleExclude: "",
    // Member list filters (group /gm/ + shouts feed)
    filterGender: ["female", "male", "couple", "trans", "unknown"],
    filterSexuality: ["straight", "bisexual", "gay", "lesbian", "unknown"],
    memberSort: "default", // default | join_desc
  });

  function loadSettings() {
    try {
      return { ...defaultSettings(), ...(JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}) };
    } catch (_) {
      return defaultSettings();
    }
  }

  function saveSettings(s) {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
    } catch (_) {}
  }

  let settings = loadSettings();
  let friendAbort = false;
  let friendMassActive = false;
  let infiniteEngine = null;
  let scrollLocked = false;
  let infiniteStatusText = "";

  function toast(msg) {
    let el = document.getElementById("tbcc-ml-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "tbcc-ml-toast";
      document.documentElement.appendChild(el);
    }
    el.textContent = String(msg || "");
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2800);
  }

  function normalizeUser(raw) {
    const s = String(raw || "")
      .trim()
      .replace(/^@+/, "")
      .split(/[/?#]/)[0];
    if (!s || SKIP_USERS.has(s.toLowerCase())) return "";
    if (/^[A-F0-9]{6,}$/i.test(s) && s.length <= 12) return ""; // media id
    return s;
  }

  function usernameFromHref(href) {
    try {
      const u = new URL(href, location.origin);
      if (!HOST_RE.test(u.hostname)) return "";
      const path = (u.pathname || "").replace(/\/+$/, "") || "/";
      const m = path.match(/^\/m\/([^/]+)/i);
      if (m) return normalizeUser(m[1]);
      const uu = path.match(/^\/u\/([^/]+)/i);
      if (uu) return normalizeUser(uu[1]);
      const f = /^\/friends\/request$/i.test(path);
      if (f) return normalizeUser(u.searchParams.get("member") || "");
      // Bare profile URLs: /handymanjaycan (common on /gm/ member grids)
      const bare = path.match(/^\/([A-Za-z][A-Za-z0-9_-]{2,32})$/);
      if (bare) {
        const name = bare[1];
        if (SKIP_USERS.has(name.toLowerCase())) return "";
        if (/^(g|gm|gi|gv|term|tags|porn|nude|sex|gay|teen|live|chat|store|help)$/i.test(name)) {
          return "";
        }
        return normalizeUser(name);
      }
    } catch (_) {}
    return "";
  }

  function isSubscriptionsPage() {
    return /^\/s\//i.test(location.pathname) || !!document.querySelector("#subscriptions, a[href^='/s/']");
  }

  function isGroupMembersPage() {
    const p = location.pathname || "";
    // Live site uses /gm/{slug}; older docs used /g/{slug}/members
    return /^\/gm\/[^/]+/i.test(p) || /^\/g\/[^/]+\/members\/?/i.test(p);
  }

  function isGroupShoutsPage() {
    const p = location.pathname || "";
    if (/^\/gs\/[^/]+/i.test(p)) return true;
    if (/^\/g\/[^/]+\/shouts\/?/i.test(p)) return true;
    if (/^\/gm\/[^/]+\/shouts\/?/i.test(p)) return true;
    // Group home with a shouts stream present
    if (/^\/g\/[^/]+\/?$/i.test(p) && document.querySelector(".shout, .shouts, #shouts, [class*='shout']")) {
      return true;
    }
    return false;
  }

  function isMemberListPage() {
    if (isGroupMembersPage() || isSubscriptionsPage()) return true;
    const p = location.pathname || "";
    if (/^\/members\/?/i.test(p)) return true;
    if (/[?&](?:tab|view)=members\b/i.test(location.search || "")) return true;
    return !!document.querySelector(
      ".thumb-member-minibio, #members, .member-list, [class*='member-grid'], [class*='members-list']"
    );
  }

  const GENDER_KEYS = ["female", "male", "couple", "trans", "unknown"];
  const SEX_KEYS = ["straight", "bisexual", "gay", "lesbian", "unknown"];

  function parseGenderFromText(text) {
    const t = String(text || "").toLowerCase();
    if (/\bcouple\b|\bm\/f\b|\bf\/m\b|\bffm\b|\bmfm\b/.test(t)) return "couple";
    if (/\btrans(?:sexual|gender)?\b|\bshemale\b|\bcd\b|\bcross.?dress/.test(t)) return "trans";
    if (/\bfemale\b|\bwoman\b|\bwomen\b|\bgirl\b|\blady\b/.test(t)) return "female";
    if (/\bmale\b|\bman\b|\bmen\b|\bguy\b|\bboi\b/.test(t)) return "male";
    // Compact tokens often shown under avatars: F / M / C / T
    if (/(?:^|[|\u2022·,\s])F(?:[|\u2022·,\s]|$)/.test(text || "")) return "female";
    if (/(?:^|[|\u2022·,\s])M(?:[|\u2022·,\s]|$)/.test(text || "")) return "male";
    if (/(?:^|[|\u2022·,\s])C(?:[|\u2022·,\s]|$)/.test(text || "")) return "couple";
    if (/(?:^|[|\u2022·,\s])T(?:[|\u2022·,\s]|$)/.test(text || "")) return "trans";
    return "unknown";
  }

  function parseSexualityFromText(text) {
    const t = String(text || "").toLowerCase();
    if (/\blesbian\b/.test(t)) return "lesbian";
    if (/\bgay\b|\bhomo\b/.test(t)) return "gay";
    if (/\bbi(?:sexual)?\b/.test(t)) return "bisexual";
    if (/\bstraight\b|\bhetero/.test(t)) return "straight";
    return "unknown";
  }

  function parseJoinMsFromText(text) {
    const raw = String(text || "");
    const iso = raw.match(/(\d{4}-\d{2}-\d{2})/);
    if (iso) {
      const ms = Date.parse(iso[1]);
      if (!Number.isNaN(ms)) return ms;
    }
    const abs = raw.match(
      /joined[^0-9]{0,12}(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\w+\s+\d{1,2},?\s*\d{4})/i
    );
    if (abs) {
      const ms = Date.parse(abs[1]);
      if (!Number.isNaN(ms)) return ms;
    }
    const rel = raw.match(
      /(?:joined|member\s+since|added)[^0-9]{0,16}(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago/i
    );
    if (rel) {
      const n = parseInt(rel[1], 10);
      const unit = rel[2].toLowerCase();
      const mult = {
        second: 1000,
        minute: 60_000,
        hour: 3_600_000,
        day: 86_400_000,
        week: 604_800_000,
        month: 2_592_000_000,
        year: 31_536_000_000,
      };
      return Date.now() - n * (mult[unit] || 86_400_000);
    }
    return null;
  }

  function memberCardRoots() {
    const root =
      document.querySelector("#content .content-inner") ||
      document.querySelector(".content-inner") ||
      document.querySelector("#content") ||
      document.querySelector("#main") ||
      document.body;
    if (!root) return [];
    const cards = new Set();
    root
      .querySelectorAll(
        ".thumb-member-minibio, [class*='member'], .media, .col-xs-6, .col-md-3, .col-sm-3, .col-lg-2, tr, li"
      )
      .forEach((el) => {
        if (el.closest(`#${OVERLAY_ID}`)) return;
        const hasUser =
          el.querySelector?.("a[href*='/m/'], a[href*='/u/']") ||
          [...(el.querySelectorAll?.("a[href]") || [])].some((a) =>
            usernameFromHref(a.getAttribute("href") || a.href)
          );
        if (hasUser) cards.add(el);
      });
    // Fallback: wrap each avatar link's nearest block
    if (!cards.size || isGroupMembersPage()) {
      root.querySelectorAll("a[href] img").forEach((img) => {
        const a = img.closest("a[href]");
        if (!a || a.closest(`#${OVERLAY_ID}`)) return;
        const href = a.getAttribute("href") || a.href || "";
        const user = usernameFromHref(href);
        const bare = (() => {
          try {
            const p = new URL(href, location.origin).pathname.replace(/\/+$/, "");
            return /^\/[A-Za-z][A-Za-z0-9_-]{2,32}$/.test(p);
          } catch (_) {
            return false;
          }
        })();
        if (!user && !bare) return;
        const block =
          a.closest(
            ".thumb-member-minibio, .media, [class*='member'], .col-xs-6, .col-md-3, .col-sm-3, li, tr, div"
          ) || a.parentElement;
        if (block && !block.closest(`#${OVERLAY_ID}`)) cards.add(block);
      });
    }
    return [...cards];
  }

  function shoutRowRoots() {
    const root =
      document.querySelector("#content .content-inner") ||
      document.querySelector(".content-inner") ||
      document.querySelector("#content") ||
      document.body;
    if (!root) return [];
    const rows = [
      ...root.querySelectorAll(
        ".shout, .shouts .media, .shout-row, [class*='shout']:not(script):not(style), .comment, .ml-shout"
      ),
    ].filter((el) => el && !el.closest(`#${OVERLAY_ID}`) && (el.textContent || "").trim().length > 8);
    return rows;
  }

  function analyzeMemberCard(el) {
    const text = String(el?.textContent || "").replace(/\s+/g, " ").trim();
    let user = "";
    el.querySelectorAll?.("a[href]").forEach((a) => {
      if (user) return;
      user = usernameFromHref(a.getAttribute("href") || a.href) || "";
    });
    return {
      el,
      user,
      gender: parseGenderFromText(text),
      sexuality: parseSexualityFromText(text),
      joinMs: parseJoinMsFromText(text),
      text,
    };
  }

  function memberPassesFilter(info) {
    const genders = Array.isArray(settings.filterGender) ? settings.filterGender : GENDER_KEYS;
    const sexes = Array.isArray(settings.filterSexuality) ? settings.filterSexuality : SEX_KEYS;
    // Unlabeled cards (typical /gm/ member grids): no ASL text → don't hide.
    // Only enforce a dimension when we parsed a concrete signal.
    if (info.gender !== "unknown" && !genders.includes(info.gender)) return false;
    if (info.sexuality !== "unknown" && !sexes.includes(info.sexuality)) return false;
    return true;
  }

  function applyMemberFiltersAndSort() {
    const onMembers = isMemberListPage();
    const onShouts = isGroupShoutsPage();
    if (!onMembers && !onShouts) return { shown: 0, hidden: 0 };

    const nodes = onMembers ? memberCardRoots() : shoutRowRoots();
    const analyzed = nodes.map(analyzeMemberCard);
    let shown = 0;
    let hidden = 0;
    analyzed.forEach((info) => {
      const pass = memberPassesFilter(info);
      info.el.style.display = pass ? "" : "none";
      info.el.setAttribute("data-tbcc-ml-filter-hidden", pass ? "0" : "1");
      if (pass) shown += 1;
      else hidden += 1;
    });

    if (settings.memberSort === "join_desc") {
      const parent = analyzed[0]?.el?.parentElement;
      if (parent) {
        const visible = analyzed
          .filter((a) => a.el.getAttribute("data-tbcc-ml-filter-hidden") !== "1")
          .slice()
          .sort((a, b) => (b.joinMs || 0) - (a.joinMs || 0));
        visible.forEach((a) => parent.appendChild(a.el));
      }
    }
    return { shown, hidden };
  }

  /** Members discovered while scrolling this visit (survives infinite-load). */
  const discoveredMembers = new Set();
  const discoveredMemberNames = new Map(); // lower -> display
  let memberScanTimer = null;
  let memberScanBound = false;
  let memberScanPath = "";

  function resetDiscoveredIfPathChanged() {
    const p = location.pathname || "";
    if (p !== memberScanPath) {
      memberScanPath = p;
      discoveredMembers.clear();
      discoveredMemberNames.clear();
    }
  }

  function collectVisibleUsernames(opts = {}) {
    const includeFiltered = !!opts.includeFiltered;
    const out = new Set();
    const add = (raw) => {
      const u = normalizeUser(raw);
      if (u) out.add(u);
    };
    const root =
      document.querySelector("#content .content-inner") ||
      document.querySelector(".content-inner") ||
      document.querySelector("#content") ||
      document.querySelector("#main") ||
      document.body ||
      document;

    const isHiddenFiltered = (el) => {
      if (includeFiltered) return false;
      return !!(el && el.closest && el.closest('[data-tbcc-ml-filter-hidden="1"]'));
    };

    root.querySelectorAll(".thumb-member-minibio[rel]").forEach((el) => {
      if (isHiddenFiltered(el)) return;
      add(el.getAttribute("rel"));
    });
    root
      .querySelectorAll(
        "[data-member], [data-username], [data-user], [data-codename][data-type='member']"
      )
      .forEach((el) => {
        if (isHiddenFiltered(el)) return;
        add(
          el.getAttribute("data-member") ||
            el.getAttribute("data-username") ||
            el.getAttribute("data-user") ||
            el.getAttribute("data-codename")
        );
      });

    root.querySelectorAll("a[href]").forEach((a) => {
      if (a.closest(`#${OVERLAY_ID}`)) return;
      if (isHiddenFiltered(a)) return;
      const href = a.getAttribute("href") || a.href || "";
      if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;
      const fromHref = usernameFromHref(href);
      if (!fromHref) return;
      const isProfilePath = /\/m\/|\/u\/|\/friends\/request/i.test(href);
      const looksLikeCard =
        !!a.querySelector("img") ||
        !!a.closest(
          ".thumb-member-minibio, .member, [class*='member'], [class*='avatar'], tr, .media, .col-xs-6, .col-md-3, .content-inner"
        );
      if (isProfilePath || isMemberListPage() || looksLikeCard) add(fromHref);
    });

    if (isGroupMembersPage()) {
      root.querySelectorAll("a[href] img").forEach((img) => {
        const a = img.closest("a[href]");
        if (!a || a.closest(`#${OVERLAY_ID}`)) return;
        if (isHiddenFiltered(a)) return;
        add(usernameFromHref(a.getAttribute("href") || a.href || ""));
        const label =
          a.getAttribute("title") ||
          a.getAttribute("aria-label") ||
          img.getAttribute("alt") ||
          "";
        if (label && !/\s/.test(label.trim()) && label.length < 40) add(label);
      });

      // Fallback: username as first text line on avatar cards (xxx DOM sometimes omits /m/ links)
      memberCardRoots().forEach((card) => {
        if (isHiddenFiltered(card)) return;
        let user = "";
        card.querySelectorAll?.("a[href]").forEach((a) => {
          if (user) return;
          user = usernameFromHref(a.getAttribute("href") || a.href) || "";
        });
        if (user) {
          add(user);
          return;
        }
        const raw = String(card.textContent || "")
          .replace(/\s+/g, " ")
          .trim();
        // "argiris Group General 0 Uploads" → first token
        const m = raw.match(/^([A-Za-z][A-Za-z0-9_-]{2,32})\b/);
        if (m) add(m[1]);
      });
    }

    return [...out];
  }

  function scanMembersIntoDiscovered() {
    resetDiscoveredIfPathChanged();
    let filterStats = { shown: 0, hidden: 0 };
    if (isMemberListPage() || isGroupShoutsPage()) {
      try {
        filterStats = applyMemberFiltersAndSort() || filterStats;
      } catch (_) {}
    }
    // Discover everyone (including filter-hidden) so "Friend scanned" still grows while scrolling
    const allFound = collectVisibleUsernames({ includeFiltered: true });
    const visibleFound = collectVisibleUsernames({ includeFiltered: false });
    let added = 0;
    allFound.forEach((u) => {
      const key = u.toLowerCase();
      if (!discoveredMembers.has(key)) {
        discoveredMembers.add(key);
        discoveredMemberNames.set(key, u);
        added += 1;
      }
    });
    updateFriendsCountUi(visibleFound.length, filterStats);
    return { visible: visibleFound.length, discovered: discoveredMembers.size, added };
  }

  function discoveredMemberList() {
    if (discoveredMemberNames.size) return [...discoveredMemberNames.values()];
    return [...discoveredMembers];
  }

  function updateFriendsCountUi(visibleCount, filterStats) {
    const el = document.querySelector(`#${OVERLAY_ID} [data-ml-friend-count]`);
    if (!el) return;
    const visible =
      typeof visibleCount === "number" ? visibleCount : collectVisibleUsernames().length;
    let extra = "";
    if (filterStats && filterStats.hidden > 0 && visible === 0 && filterStats.shown === 0) {
      extra =
        `<div style="color:#f88;font-size:11px;margin-top:4px">Filters hid all ${filterStats.hidden} card(s). ` +
        `Unlabeled /gm/ cards no longer need Unknown checked — tap Apply or loosen gender/sex.</div>`;
    } else if (filterStats && filterStats.hidden > 0) {
      extra = `<div style="color:#888;font-size:11px;margin-top:4px">Filters hiding ${filterStats.hidden}</div>`;
    }
    el.innerHTML =
      `Visible now: <b style="color:#fff">${visible}</b>` +
      ` · scanned while scrolling: <b style="color:#fff">${discoveredMembers.size}</b>` +
      ` · <code>${location.pathname}</code>` +
      extra;
  }

  function setupMemberListScan() {
    if (memberScanBound) return;
    memberScanBound = true;
    const schedule = () => {
      if (!isMemberListPage() && !isGroupShoutsPage()) return;
      clearTimeout(memberScanTimer);
      memberScanTimer = setTimeout(() => scanMembersIntoDiscovered(), 120);
    };
    window.addEventListener("scroll", schedule, { passive: true });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") schedule();
    });
    try {
      const mo = new MutationObserver(() => {
        if (!isMemberListPage() && !isGroupShoutsPage()) return;
        schedule();
      });
      mo.observe(document.documentElement, { childList: true, subtree: true });
    } catch (_) {}
    schedule();
  }

  function codenameFromEl(el) {
    if (!el) return "";
    const fromData =
      el.getAttribute("data-image-view-modal-codename") ||
      el.getAttribute("data-codename") ||
      el.getAttribute("rel") ||
      "";
    if (fromData && /^[A-Za-z0-9]{4,}$/.test(fromData) && !fromData.includes("/")) {
      // rel on member thumbs is a username — only accept media-ish ids
      if (/^[A-F0-9]{6,}$/i.test(fromData)) return fromData.toUpperCase();
    }
    const a =
      el.closest("a[href]") ||
      el.querySelector("a.img-container[href], a[href^='/'][href*='']");
    const href = (a && a.getAttribute("href")) || "";
    const m = href.match(/^\/([A-Fa-f0-9]{6,})(?:\?|$)/);
    if (m) return m[1].toUpperCase();
    const mag = el.querySelector("[data-image-view-modal-codename]");
    if (mag) return String(mag.getAttribute("data-image-view-modal-codename") || "").toUpperCase();
    return "";
  }

  /** Session CSRF — same token on every Motherless page (favorites/shouts already use this). */
  let cachedCsrfToken = "";

  function pageToken() {
    const el = document.querySelector('input[name="_token"]');
    const t = el ? String(el.value || "").trim() : "";
    if (t) cachedCsrfToken = t;
    return t || cachedCsrfToken;
  }

  /**
   * Read only a prefix of a response body so mass-friend never retains full HTML pages in RAM.
   * Old path fetched entire /m/{user} profiles per request — multi‑GB tabs on large batches.
   */
  async function readResponsePrefix(res, maxBytes) {
    const cap = Math.max(256, Math.min(Number(maxBytes) || 4096, 64_000));
    try {
      if (res && res.body && typeof res.body.getReader === "function") {
        const reader = res.body.getReader();
        const chunks = [];
        let total = 0;
        while (total < cap) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!value || !value.byteLength) continue;
          chunks.push(value);
          total += value.byteLength;
        }
        try {
          reader.cancel();
        } catch (_) {}
        const out = new Uint8Array(Math.min(total, cap));
        let off = 0;
        for (const c of chunks) {
          const n = Math.min(c.byteLength, out.length - off);
          out.set(c.subarray(0, n), off);
          off += n;
          if (off >= out.length) break;
        }
        return new TextDecoder("utf-8", { fatal: false }).decode(out);
      }
    } catch (_) {}
    try {
      const t = await res.text();
      return String(t || "").slice(0, cap);
    } catch (_) {
      return "";
    }
  }

  /**
   * Friend CSRF: reuse the members-page token. Never download /m/{user} HTML per target.
   * One optional homepage bootstrap only when the current document has no _token field.
   */
  async function resolveFriendToken() {
    const existing = pageToken();
    if (existing) return existing;
    if (cachedCsrfToken) return cachedCsrfToken;
    try {
      const res = await fetch("/", {
        credentials: "include",
        headers: { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) return "";
      const head = await readResponsePrefix(res, 48_000);
      const m = head.match(/name="_token"\s+value="([^"]+)"/i);
      if (m && m[1]) {
        cachedCsrfToken = m[1];
        return cachedCsrfToken;
      }
    } catch (_) {}
    return "";
  }

  async function sendFriendRequest(username) {
    const user = normalizeUser(username);
    if (!user) return { ok: false, error: "bad user" };
    const token = await resolveFriendToken();
    const back = location.href.split("#")[0];
    const body = new URLSearchParams();
    if (token) body.set("_token", token);
    const url = `/friends/request?member=${encodeURIComponent(user)}&back=${encodeURIComponent(back)}`;
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "text/html,application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
      },
      body,
      redirect: "follow",
    });
    const text = await readResponsePrefix(res, 2048);
    const login = /\/login|sign\s*in|not logged/i.test(text) || res.url.includes("/login");
    return { ok: res.ok && !login, status: res.status, login, text: text.slice(0, 200) };
  }

  async function addFavorite(codename) {
    const code = String(codename || "").trim();
    if (!code) return { ok: false, error: "no codename" };
    const body = new URLSearchParams({ codename: code, group: "" });
    const res = await fetch("/favorites/add", {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
      },
      body,
    });
    let data = {};
    try {
      data = await res.json();
    } catch (_) {}
    const login = res.status === 401 || /login/i.test(JSON.stringify(data));
    return { ok: res.ok && !login, status: res.status, data, login };
  }

  function loadJsonCache(key) {
    try {
      const raw = JSON.parse(localStorage.getItem(key) || "null");
      return Array.isArray(raw) ? raw : [];
    } catch (_) {
      return [];
    }
  }

  function saveJsonCache(key, rows) {
    try {
      localStorage.setItem(key, JSON.stringify(Array.isArray(rows) ? rows.slice(0, 80) : []));
    } catch (_) {}
  }

  /** Full Motherless gallery codename used by /media/add (e.g. G035DE2F, GV338999F). */
  function normalizeGalleryCodename(raw) {
    let s = String(raw || "")
      .trim()
      .toUpperCase()
      .replace(/^\/+/, "");
    if (/^G[VIG]?[A-F0-9]{6,12}$/.test(s)) return s;
    if (/^[A-F0-9]{6,12}$/.test(s)) return "G" + s;
    return "";
  }

  function galleryBareId(raw) {
    return String(normalizeGalleryCodename(raw) || "")
      .replace(/^G[VIG]?/i, "")
      .toUpperCase();
  }

  function isJunkGalleryTitle(raw) {
    const t = String(raw || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!t) return true;
    if (/^click\s+to\s+view(\s+gallery)?$/i.test(t)) return true;
    if (/^(view\s+gallery|open\s+gallery|gallery|untitled)$/i.test(t)) return true;
    if (/^(add|edit|delete|view|images?|videos?|group)$/i.test(t)) return true;
    if (/^G?[VIG]?[A-F0-9]{4,12}$/i.test(t)) return true;
    return false;
  }

  function cleanPickerTitle(raw, id) {
    let t = String(raw || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/\s*\|\s*MOTHERLESS.*$/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!t || isJunkGalleryTitle(t)) return "";
    const bare = galleryBareId(t);
    const idBare = galleryBareId(id);
    if (bare && idBare && bare === idBare) return "";
    return t.slice(0, 120);
  }

  function titleFromGalleryCard(card, linkEl) {
    if (!card && !linkEl) return "";
    const root = card || linkEl;
    const link = linkEl || root.querySelector?.("a[href*='/G']") || root;
    const pickAttr = (el, names) => {
      if (!el) return "";
      for (const n of names) {
        const v = el.getAttribute(n);
        if (v && !isJunkGalleryTitle(v)) return v;
      }
      return "";
    };
    const selectors = [
      ".caption.title",
      ".caption",
      ".filename",
      ".title.full",
      ".title",
      ".gallery-title",
      "h2",
      "h3",
      "h4",
      "strong",
    ];
    for (const sel of selectors) {
      const el = root.querySelector?.(sel);
      if (!el) continue;
      const t =
        pickAttr(el, ["origtitle", "title", "data-title", "aria-label"]) || el.textContent || "";
      const cleaned = cleanPickerTitle(t, "");
      if (cleaned) return cleaned;
    }
    const fromLink =
      pickAttr(link, ["origtitle", "data-title", "aria-label"]) ||
      (link && !isJunkGalleryTitle(link.getAttribute("title") || "")
        ? link.getAttribute("title")
        : "") ||
      "";
    const cleanedLink = cleanPickerTitle(fromLink, "");
    if (cleanedLink) return cleanedLink;
    // Never use img alt — Motherless sets alt="Click to view gallery" on every thumb
    return "";
  }

  async function enrichGalleryTitles(items) {
    const list = Array.isArray(items) ? items.slice() : [];
    const need = list.filter((it) => it && it.id && isJunkGalleryTitle(it.title));
    if (!need.length) return list;
    const byId = new Map(list.map((it) => [it.id, { ...it }]));
    await Promise.all(
      need.slice(0, 40).map(async (it) => {
        try {
          const res = await fetch(`/${encodeURIComponent(it.id)}`, {
            credentials: "include",
            headers: { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" },
            cache: "no-store",
          });
          if (!res.ok) return;
          const html = await res.text();
          const doc = new DOMParser().parseFromString(html, "text/html");
          const h =
            doc.querySelector(".media-meta-title h1, .media-meta-title, h1.title, h1, h2") ||
            null;
          let t =
            (h && h.textContent) ||
            doc.querySelector('meta[property="og:title"]')?.getAttribute("content") ||
            doc.title ||
            "";
          t = cleanPickerTitle(t, it.id);
          if (t) byId.set(it.id, { ...it, title: t });
        } catch (_) {}
      })
    );
    return [...byId.values()].sort((a, b) => String(a.title || a.id).localeCompare(String(b.title || b.id)));
  }

  function parseGalleryCodenameFromHref(href) {
    try {
      const u = new URL(href, location.origin);
      const path = (u.pathname || "").replace(/\/+$/, "");
      // Gallery root only: /G035DE2F or /GV338999F — not /G…/mediaId
      const m = path.match(/^\/(G[VIG]?)([A-F0-9]{6,12})$/i);
      if (!m) return "";
      return normalizeGalleryCodename(m[1] + m[2]);
    } catch (_) {
      return "";
    }
  }

  // Back-compat alias used by older helpers in this file
  function normalizeGalleryId(raw) {
    return galleryBareId(raw);
  }

  function parseGalleryIdFromHref(href) {
    return galleryBareId(parseGalleryCodenameFromHref(href));
  }

  function parseGalleryOptions(html) {
    const out = [];
    const seen = new Set();
    const push = (id, title) => {
      const gid = normalizeGalleryId(id);
      if (!gid || seen.has(gid)) return;
      const name = cleanPickerTitle(title, gid);
      // Prefer named galleries; allow id-only only as last resort later
      seen.add(gid);
      out.push({ id: gid, title: name || "" });
    };

    try {
      const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
      doc.querySelectorAll('a[href*="/G"]').forEach((a) => {
        const gid = parseGalleryIdFromHref(a.getAttribute("href") || a.href || "");
        if (!gid) return;
        const img = a.querySelector("img");
        const title =
          a.getAttribute("title") ||
          a.getAttribute("aria-label") ||
          (img && (img.getAttribute("alt") || img.getAttribute("title"))) ||
          a.textContent ||
          "";
        // Also check parent card for a heading
        const card = a.closest(".thumb-container, .media, .gallery, li, tr, .col-xs-6, .col-md-3, .row");
        const heading = card && card.querySelector(".title, .gallery-title, h2, h3, h4, .caption, strong");
        push(gid, (heading && heading.textContent) || title);
      });
      doc.querySelectorAll("option[value]").forEach((opt) => {
        const gid = normalizeGalleryId(opt.getAttribute("value") || "");
        if (!gid) return;
        push(gid, opt.textContent || "");
      });
      // data-gallery / data-codename attributes on add-to-gallery UI
      doc.querySelectorAll("[data-gallery], [data-gallery-id], [data-hash]").forEach((el) => {
        const gid = normalizeGalleryId(
          el.getAttribute("data-gallery") ||
            el.getAttribute("data-gallery-id") ||
            el.getAttribute("data-hash") ||
            ""
        );
        if (!gid) return;
        push(gid, el.getAttribute("title") || el.getAttribute("data-title") || el.textContent || "");
      });
    } catch (_) {
      // regex fallback
      const re = /href=["'](\/G[VIG]?[A-Fa-f0-9]{6,12})["'][^>]*>([\s\S]*?)<\/a>/gi;
      let m;
      while ((m = re.exec(html))) {
        push(parseGalleryIdFromHref(m[1]), m[2]);
      }
    }

    // Prefer rows with real names; keep unnamed only if nothing named exists
    const named = out.filter((r) => r.title);
    const final = named.length ? named : out.map((r) => ({ ...r, title: r.title || `Gallery ${r.id}` }));
    final.sort((a, b) => String(a.title).localeCompare(String(b.title)));
    return final;
  }

  function parseGroupOptions(html) {
    const out = [];
    const seen = new Set();
    const push = (slug, title) => {
      const s = String(slug || "")
        .trim()
        .toLowerCase()
        .replace(/^\/+/, "")
        .replace(/^g[vifm]?\//i, "");
      if (!s || !/^[a-z0-9][a-z0-9_-]{1,64}$/i.test(s) || seen.has(s)) return;
      if (/^(images|videos|galleries|members|upload|login|register|search)$/i.test(s)) return;
      const name = cleanPickerTitle(title, s) || "";
      seen.add(s);
      out.push({ id: s, title: name });
    };

    try {
      const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
      doc.querySelectorAll('a[href*="/g"]').forEach((a) => {
        const href = a.getAttribute("href") || a.href || "";
        let path = "";
        try {
          path = new URL(href, location.origin).pathname.replace(/\/+$/, "");
        } catch (_) {
          return;
        }
        const m = path.match(/^\/g[vifm]?\/([a-z0-9][a-z0-9_-]{1,64})$/i);
        if (!m) return;
        const img = a.querySelector("img");
        const title =
          a.getAttribute("title") ||
          (img && img.getAttribute("alt")) ||
          a.textContent ||
          "";
        const card = a.closest(".thumb-container, .media, .group, li, tr, .col-xs-6, .col-md-3");
        const heading = card && card.querySelector(".title, .group-title, h2, h3, h4, .caption, strong");
        push(m[1], (heading && heading.textContent) || title);
      });
      doc.querySelectorAll("option[value]").forEach((opt) => {
        const v = String(opt.getAttribute("value") || "").trim();
        if (!/^[a-z0-9][a-z0-9_-]{1,64}$/i.test(v)) return;
        push(v, opt.textContent || "");
      });
    } catch (_) {}

    const named = out.filter((r) => r.title);
    const final = named.length ? named : out.map((r) => ({ ...r, title: r.title || r.id }));
    final.sort((a, b) => String(a.title).localeCompare(String(b.title)));
    return final;
  }

  async function fetchHtmlPaths(paths) {
    for (const path of paths) {
      try {
        const res = await fetch(path, {
          credentials: "include",
          headers: { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" },
          cache: "no-store",
        });
        if (!res.ok) continue;
        const html = await res.text();
        if (/\/login|sign\s*in/i.test(html) && html.length < 8000) {
          return { login: true, html: "" };
        }
        return { login: false, html, path };
      } catch (_) {}
    }
    return { login: false, html: "", path: "" };
  }

  function detectLoggedInUserFromHtml(html) {
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    const pick = (root) => {
      if (!root) return "";
      // Prefer account chrome near logout / upload
      const logout =
        root.querySelector('a[href*="/logout"], a[href*="sign-out"], a[href*="signout"]') ||
        root.querySelector('a[href*="/account"], a[href*="/settings"]');
      const scope =
        (logout && (logout.closest("nav, header, #header, .header, .navbar, .top, ul, .menu") || root)) ||
        root.querySelector("nav, header, #header, .header, .navbar") ||
        root;
      const anchors = [...scope.querySelectorAll('a[href*="/m/"], a[href*="/u/"]')];
      for (const a of anchors) {
        const href = a.getAttribute("href") || "";
        const u = usernameFromHref(href);
        if (!u) continue;
        const label = String(a.textContent || "").trim().toLowerCase();
        if (/^(home|images|videos|galleries|groups|members|upload|search)$/i.test(u)) continue;
        // Profile / "my" style links
        if (
          /my\s*(profile|account|uploads|galleries|page)?/i.test(label) ||
          /\/(?:m|u)\/[^/]+\/?(?:galleries|uploads|images|videos)?$/i.test(href) ||
          label === u.toLowerCase()
        ) {
          return u;
        }
      }
      for (const a of anchors) {
        const u = usernameFromHref(a.getAttribute("href") || "");
        if (u && !/^(home|images|videos|galleries|groups|members)$/i.test(u)) return u;
      }
      return "";
    };
    let user = pick(doc);
    if (user) return user;
    const m =
      String(html || "").match(
        /(?:logged\s*in\s*as|welcome[,\s]+|@)\s*([A-Za-z0-9_-]{2,40})/i
      ) ||
      String(html || "").match(/\/(?:m|u)\/([A-Za-z0-9_-]{2,40})[^"'<]{0,40}(?:My\s+Profile|My\s+Uploads|Account)/i);
    return m ? normalizeUser(m[1]) : "";
  }

  function currentMotherlessUser() {
    try {
      const cached = String(localStorage.getItem(ML_USER_CACHE_KEY) || "").trim();
      if (cached && normalizeUser(cached)) return normalizeUser(cached);
    } catch (_) {}
    // Live DOM first
    const fromDom = detectLoggedInUserFromHtml(document.documentElement.outerHTML);
    if (fromDom) {
      try {
        localStorage.setItem(ML_USER_CACHE_KEY, fromDom);
      } catch (_) {}
      return fromDom;
    }
    return "";
  }

  function parseOwnedGalleries(html, ownerUser) {
    const owner = normalizeUser(ownerUser);
    const byId = new Map();
    const push = (id, title) => {
      const gcode = normalizeGalleryCodename(id);
      if (!gcode) return;
      const name = cleanPickerTitle(title, gcode);
      const prev = byId.get(gcode);
      if (!prev) {
        byId.set(gcode, { id: gcode, title: name || "" });
        return;
      }
      // Upgrade junk / empty titles when a real name appears later
      if (name && isJunkGalleryTitle(prev.title)) {
        byId.set(gcode, { id: gcode, title: name });
      }
    };

    try {
      const doc = new DOMParser().parseFromString(String(html || ""), "text/html");

      // 1) /media/add modal fragment + form controls (account galleries only)
      const formScope = [
        ...doc.querySelectorAll(
          'form[action*="galler"], form[action*="media/add"], form[id*="galler"], form[class*="galler"], #add-to-gallery, #add-gallery-modal, .add-to-gallery, [id*="AddToGallery"], [class*="add-to-gallery"]'
        ),
      ];
      const optionRoots = formScope.length
        ? formScope
        : [...doc.querySelectorAll("select[name*='galler' i], select[id*='galler' i], .modal-body")];
      optionRoots.forEach((root) => {
        root.querySelectorAll("option[value]").forEach((opt) => {
          push(opt.getAttribute("value") || "", opt.textContent || "");
        });
        root.querySelectorAll("input[type='checkbox'][value], input[type='radio'][value]").forEach((inp) => {
          const lab =
            (inp.id && doc.querySelector(`label[for="${inp.id}"]`)) ||
            inp.closest("label") ||
            inp.parentElement;
          push(inp.getAttribute("value") || "", (lab && lab.textContent) || "");
        });
        root.querySelectorAll("a[href*='/G'], [data-codename][href], .thumb-container, .desktop-thumb").forEach((el) => {
          const link =
            el.tagName === "A"
              ? el
              : el.querySelector?.("a[href*='/G']") || el;
          const gcode =
            normalizeGalleryCodename(
              el.getAttribute("data-codename") ||
                el.getAttribute("data-gallery-codename") ||
                el.getAttribute("rel") ||
                ""
            ) || parseGalleryCodenameFromHref((link && (link.getAttribute("href") || link.href)) || "");
          if (!gcode) return;
          const card =
            el.closest?.(".thumb-container, .media, .gallery, li, tr, .col-xs-6, .col-md-3, .desktop-thumb") ||
            el;
          push(gcode, titleFromGalleryCard(card, link));
        });
      });
      doc.querySelectorAll("select[name*='galler' i] option[value], select[id*='galler' i] option[value]").forEach(
        (opt) => {
          push(opt.getAttribute("value") || "", opt.textContent || "");
        }
      );

      // 2) Profile gallery grids — only cards owned by `owner`
      if (owner) {
        doc.querySelectorAll('a[href*="/G"]').forEach((a) => {
          const gcode = parseGalleryCodenameFromHref(a.getAttribute("href") || a.href || "");
          if (!gcode) return;
          const card =
            a.closest(".thumb-container, .media, .gallery, li, tr, .col-xs-6, .col-md-3, .col-sm-3, .row, .desktop-thumb") ||
            a.parentElement;
          if (!card) return;
          const ownerLinks = [...card.querySelectorAll('a[href*="/m/"], a[href*="/u/"]')]
            .map((x) => usernameFromHref(x.getAttribute("href") || ""))
            .filter(Boolean);
          const foreign = ownerLinks.some((u) => u.toLowerCase() !== owner.toLowerCase());
          if (foreign) return;
          if (ownerLinks.length && !ownerLinks.some((u) => u.toLowerCase() === owner.toLowerCase())) return;
          push(gcode, titleFromGalleryCard(card, a));
        });
      }
    } catch (_) {}

    return [...byId.values()]
      .map((r) => ({
        id: r.id,
        title: r.title || `Gallery ${galleryBareId(r.id)}`,
      }))
      .sort((a, b) => String(a.title).localeCompare(String(b.title)));
  }

  function parseOwnedGroups(html, ownerUser) {
    const owner = normalizeUser(ownerUser);
    const out = [];
    const seen = new Set();
    const push = (slug, title) => {
      const s = String(slug || "")
        .trim()
        .toLowerCase()
        .replace(/^\/+/, "")
        .replace(/^g[vifm]?\//i, "");
      if (!s || !/^[a-z0-9][a-z0-9_-]{1,64}$/i.test(s) || seen.has(s)) return;
      if (/^(images|videos|galleries|members|upload|login|register|search)$/i.test(s)) return;
      const name = cleanPickerTitle(title, s) || s;
      seen.add(s);
      out.push({ id: s, title: name });
    };

    try {
      const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
      const formScope = [
        ...doc.querySelectorAll(
          'form[action*="group"], form[id*="group"], #add-to-group, .add-to-group, select[name*="group" i]'
        ),
      ];
      formScope.forEach((root) => {
        root.querySelectorAll("option[value]").forEach((opt) => {
          const v = String(opt.getAttribute("value") || "").trim();
          if (!/^[a-z0-9][a-z0-9_-]{1,64}$/i.test(v)) return;
          push(v, opt.textContent || "");
        });
      });
      if (owner) {
        doc.querySelectorAll('a[href*="/g"]').forEach((a) => {
          let path = "";
          try {
            path = new URL(a.getAttribute("href") || a.href || "", location.origin).pathname.replace(
              /\/+$/,
              ""
            );
          } catch (_) {
            return;
          }
          const m = path.match(/^\/g[vifm]?\/([a-z0-9][a-z0-9_-]{1,64})$/i);
          if (!m) return;
          const card = a.closest(".thumb-container, .media, .group, li, tr, .col-xs-6, .col-md-3") || a.parentElement;
          if (!card) return;
          const ownerLinks = [...card.querySelectorAll('a[href*="/m/"], a[href*="/u/"]')]
            .map((x) => usernameFromHref(x.getAttribute("href") || ""))
            .filter(Boolean);
          if (ownerLinks.some((u) => u.toLowerCase() !== owner.toLowerCase())) return;
          const img = a.querySelector("img");
          const heading = card.querySelector(".title, .group-title, h2, h3, h4, .caption, strong");
          push(m[1], (heading && heading.textContent) || a.getAttribute("title") || (img && img.alt) || a.textContent);
        });
      }
    } catch (_) {}

    out.sort((a, b) => String(a.title).localeCompare(String(b.title)));
    return out;
  }

  async function resolveMotherlessAccountUser() {
    let user = currentMotherlessUser();
    if (user) return { user, login: false };
    // Homepage / account often exposes the profile link when session cookies are present
    for (const path of ["/", "/upload", "/account"]) {
      const r = await fetchHtmlPaths([path]);
      if (r.login) return { user: "", login: true };
      user = detectLoggedInUserFromHtml(r.html || "");
      if (user) {
        try {
          localStorage.setItem(ML_USER_CACHE_KEY, user);
        } catch (_) {}
        return { user, login: false };
      }
    }
    return { user: "", login: false };
  }

  async function listMyGalleries(force, codename) {
    if (!force) {
      const cached = loadJsonCache(GALLERY_CACHE_KEY);
      if (
        cached.length &&
        cached.every((r) => r && r.id && r.title && !isJunkGalleryTitle(r.title)) &&
        cached.some((r) => r.title && !/^Gallery /i.test(r.title) && !/^[A-F0-9]{4,12}$/i.test(r.title))
      ) {
        return { ok: true, items: cached };
      }
    }
    const acct = await resolveMotherlessAccountUser();
    if (acct.login) return { ok: false, login: true, items: [] };
    const owner = acct.user;
    if (!owner) {
      return {
        ok: false,
        login: false,
        items: [],
        error: "Could not detect your Motherless username — open your profile once, then ↻",
      };
    }

    const code = String(codename || "").trim().toUpperCase();
    // ONLY account-owned sources — never public /galleries browse.
    // Primary: site modal fragment GET /media/add?codenames[]=… (same as + ADD TO)
    const paths = [
      `/u/${encodeURIComponent(owner)}/galleries`,
      `/m/${encodeURIComponent(owner)}/galleries`,
    ];
    if (code) {
      paths.unshift(`/media/add?codenames[]=${encodeURIComponent(code)}`);
    }

    const merged = new Map();
    for (const path of paths) {
      const r = await fetchHtmlPaths([path]);
      if (r.login) return { ok: false, login: true, items: [] };
      // Skip full homepage HTML masquerading as the add fragment
      if (/^<!DOCTYPE|^<html[\s>]/i.test(String(r.html || "").trim())) continue;
      const isAdd = /\/media\/add/i.test(path);
      const isGalleriesTab = /\/galleries\/?$/i.test(path);
      const items = parseOwnedGalleries(r.html || "", owner);
      // For bare /u/user profile, require titles + ownership filter already applied;
      // skip if page looks like a public discover dump (too many foreign cards — parser already filters)
      if (!isAdd && !isGalleriesTab && !items.length) continue;
      items.forEach((it) => {
        const prev = merged.get(it.id);
        const nextTitle = it.title || "";
        const prevJunk = !prev || isJunkGalleryTitle(prev.title) || /^Gallery /i.test(prev.title || "");
        if (!prev || (nextTitle && !isJunkGalleryTitle(nextTitle) && prevJunk)) {
          merged.set(it.id, it);
        }
      });
      if (merged.size >= 1 && (isAdd || isGalleriesTab)) {
        if ([...merged.values()].some((x) => x.title && !isJunkGalleryTitle(x.title) && !/^Gallery /i.test(x.title))) {
          break;
        }
      }
    }

    let items = [...merged.values()];
    // Resolve real names from each gallery page when thumbs only had "Click to view gallery"
    if (items.some((it) => isJunkGalleryTitle(it.title) || /^Gallery /i.test(it.title || ""))) {
      items = await enrichGalleryTitles(items);
    }
    items.sort((a, b) => String(a.title || a.id).localeCompare(String(b.title || b.id)));
    if (items.length) saveJsonCache(GALLERY_CACHE_KEY, items);
    return {
      ok: items.length > 0,
      items,
      login: false,
      owner,
      error: items.length
        ? ""
        : `No galleries found for @${owner}. Create one on Motherless, open /u/${owner}/galleries, then ↻`,
    };
  }

  async function listMyGroups(force, codename) {
    if (!force) {
      const cached = loadJsonCache(GROUP_CACHE_KEY);
      if (cached.length && cached.some((r) => r && r.title && r.title !== r.id)) {
        return { ok: true, items: cached };
      }
    }
    const acct = await resolveMotherlessAccountUser();
    if (acct.login) return { ok: false, login: true, items: [] };
    const owner = acct.user;
    if (!owner) {
      return {
        ok: false,
        login: false,
        items: [],
        error: "Could not detect your Motherless username — open your profile once, then ↻",
      };
    }
    const code = String(codename || "").trim().toUpperCase();
    const paths = [
      `/u/${encodeURIComponent(owner)}/groups`,
      `/m/${encodeURIComponent(owner)}/groups`,
    ];
    if (code) {
      paths.unshift(`/media/groups?codenames[]=${encodeURIComponent(code)}`);
    }
    const merged = new Map();
    for (const path of paths) {
      const r = await fetchHtmlPaths([path]);
      if (r.login) return { ok: false, login: true, items: [] };
      parseOwnedGroups(r.html || "", owner).forEach((it) => {
        const prev = merged.get(it.id);
        if (!prev || (it.title && !prev.title)) merged.set(it.id, it);
      });
      if (merged.size >= 1) break;
    }
    const items = [...merged.values()].sort((a, b) =>
      String(a.title || a.id).localeCompare(String(b.title || b.id))
    );
    if (items.length) saveJsonCache(GROUP_CACHE_KEY, items);
    return {
      ok: items.length > 0,
      items,
      login: false,
      owner,
      error: items.length ? "" : `No groups found for @${owner}`,
    };
  }

  function parseMotherlessJsonStatus(text) {
    const raw = String(text || "").trim();
    if (!raw) return { ok: false, reason: "empty" };
    // Homepage HTML / modal HTML must never count as success
    if (/^<!DOCTYPE|^<html[\s>]/i.test(raw) || raw.length > 4000 && /<html[\s>]/i.test(raw)) {
      return { ok: false, reason: "html" };
    }
    try {
      const data = JSON.parse(raw);
      const status = data && data.status != null ? String(data.status).toLowerCase() : "";
      if (status === "ok" || status === "200" || data === true || data.ok === true) {
        return { ok: true, data };
      }
      if (status && status !== "ok") {
        return { ok: false, reason: status, data };
      }
      return { ok: false, reason: "no-status", data };
    } catch (_) {
      // Some endpoints return bare "ok"
      if (/^ok$/i.test(raw)) return { ok: true, data: { status: "ok" } };
      return { ok: false, reason: "not-json", data: { raw: raw.slice(0, 200) } };
    }
  }

  async function mediaAddToGallery(codename, galleryCodename) {
    const code = String(codename || "").trim().toUpperCase();
    const gallery = normalizeGalleryCodename(galleryCodename);
    if (!code || !gallery) return { ok: false, error: "missing gallery" };
    const token = pageToken();

    // Site media.js: $.ajax({ url:"/media/add", data:{ codenames:[…], gallery_codename } })
    // Require JSON status === "ok" (HTML 200 is a false positive).
    const payloads = [
      () => {
        const p = new URLSearchParams();
        p.append("codenames[]", code);
        p.set("gallery_codename", gallery);
        if (token) p.set("_token", token);
        return p;
      },
      () => {
        const p = new URLSearchParams();
        p.append("codenames", code);
        p.set("gallery_codename", gallery);
        if (token) p.set("_token", token);
        return p;
      },
      // Retry with bare hash if full G-prefix rejected
      () => {
        const p = new URLSearchParams();
        p.append("codenames[]", code);
        p.set("gallery_codename", galleryBareId(gallery));
        if (token) p.set("_token", token);
        return p;
      },
    ];

    let last = { ok: false, error: "add failed" };
    for (const method of ["POST", "GET"]) {
      for (const makeBody of payloads) {
        const body = makeBody();
        try {
          const url =
            method === "GET" ? `/media/add?${body.toString()}` : "/media/add";
          const res = await fetch(url, {
            method,
            credentials: "include",
            headers: {
              Accept: "application/json, text/javascript, */*; q=0.01",
              "X-Requested-With": "XMLHttpRequest",
              ...(method === "POST"
                ? { "Content-Type": "application/x-www-form-urlencoded" }
                : {}),
            },
            body: method === "POST" ? body : undefined,
            redirect: "follow",
          });
          const text = await res.text().catch(() => "");
          if (res.status === 401 || /\/login|sign\s*in/i.test(text.slice(0, 2000))) {
            return { ok: false, login: true, status: res.status };
          }
          const parsed = parseMotherlessJsonStatus(text);
          if (parsed.ok) {
            return { ok: true, status: res.status, data: parsed.data, url, method };
          }
          last = {
            ok: false,
            status: res.status,
            error: parsed.reason || "rejected",
            data: parsed.data,
            url,
            method,
          };
        } catch (e) {
          last = { ok: false, error: String(e && e.message ? e.message : e) };
        }
      }
    }
    return last;
  }

  async function addToGallery(codename, galleryId) {
    return mediaAddToGallery(codename, galleryId);
  }

  async function addToGroup(codename, groupSlug) {
    const code = String(codename || "").trim().toUpperCase();
    const slug = String(groupSlug || "")
      .trim()
      .replace(/^\/+/, "")
      .replace(/^g[vifm]?\//i, "");
    if (!code || !slug) return { ok: false, error: "missing group" };
    const token = pageToken();

    // Load the site's group picker fragment, then POST the matching group control if present.
    // Fallback: try common field shapes against /media/groups (same family as /media/add).
    try {
      const boot = await fetch(`/media/groups?codenames[]=${encodeURIComponent(code)}`, {
        credentials: "include",
        headers: {
          Accept: "text/html, */*; q=0.01",
          "X-Requested-With": "XMLHttpRequest",
        },
        cache: "no-store",
      });
      const bootHtml = await boot.text();
      if (/\/login|sign\s*in/i.test(bootHtml.slice(0, 2000)) && bootHtml.length < 8000) {
        return { ok: false, login: true };
      }
      if (bootHtml && !/^<!DOCTYPE|^<html[\s>]/i.test(bootHtml.trim())) {
        const doc = new DOMParser().parseFromString(bootHtml, "text/html");
        const hit =
          [...doc.querySelectorAll("a[href], button, input, [data-name], [data-group]")].find((el) => {
            const hay = [
              el.getAttribute("href"),
              el.getAttribute("data-name"),
              el.getAttribute("data-group"),
              el.getAttribute("value"),
              el.textContent,
            ]
              .filter(Boolean)
              .join(" ")
              .toLowerCase();
            return hay.includes(slug.toLowerCase());
          }) || null;
        if (hit) {
          const href = hit.getAttribute("href") || "";
          if (href && href !== "#" && !/^javascript:/i.test(href)) {
            const res = await fetch(href, {
              credentials: "include",
              headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json, text/html, */*" },
            });
            const text = await res.text();
            const parsed = parseMotherlessJsonStatus(text);
            if (parsed.ok) return { ok: true, data: parsed.data };
            // Non-JSON success pages sometimes just return a fragment
            if (res.ok && text.length < 2000 && !/error|fail|login/i.test(text)) {
              return { ok: true, data: { status: "ok", soft: true } };
            }
          }
        }
      }
    } catch (_) {}

    const attempts = [
      { url: "/media/groups", fields: { "codenames[]": code, group: slug, name: slug, query_safe_name: slug } },
      { url: "/media/groups", fields: { codenames: code, group: slug, name: slug } },
    ];
    let last = { ok: false, error: "add failed" };
    for (const attempt of attempts) {
      const body = new URLSearchParams(attempt.fields);
      if (token) body.set("_token", token);
      try {
        const res = await fetch(attempt.url, {
          method: "POST",
          credentials: "include",
          headers: {
            Accept: "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
          },
          body,
        });
        const text = await res.text();
        if (res.status === 401 || /\/login|sign\s*in/i.test(text.slice(0, 2000))) {
          return { ok: false, login: true };
        }
        const parsed = parseMotherlessJsonStatus(text);
        if (parsed.ok) return { ok: true, data: parsed.data };
        last = { ok: false, error: parsed.reason || "rejected", data: parsed.data };
      } catch (e) {
        last = { ok: false, error: String(e && e.message ? e.message : e) };
      }
    }
    return last;
  }

  async function postShout(codename, content) {
    const code = String(codename || "").trim();
    const text = String(content || "").trim();
    if (!code) return { ok: false, error: "no codename" };
    if (!text) return { ok: false, error: "empty shout" };
    const body = new URLSearchParams({
      codename: code,
      visibility: "public",
      parent: "0",
      content: text,
      send: "Send",
    });
    const token = pageToken();
    if (token) body.set("_token", token);
    const res = await fetch("/shouts", {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "text/html,application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
      },
      body,
      redirect: "follow",
    });
    const raw = await res.text().catch(() => "");
    const login = /\/login/i.test(res.url) || /please\s+log\s*in|sign\s*in/i.test(raw);
    return { ok: res.ok && !login, status: res.status, login };
  }

  let friendSentSaveTimer = null;

  function loadFriendSentSet() {
    try {
      const arr = JSON.parse(localStorage.getItem(FRIEND_SENT_KEY) || "[]");
      return new Set(Array.isArray(arr) ? arr.map(String) : []);
    } catch (_) {
      return new Set();
    }
  }

  function saveFriendSentSet(set) {
    try {
      localStorage.setItem(FRIEND_SENT_KEY, JSON.stringify([...set].slice(-4000)));
    } catch (_) {}
  }

  /** Batch localStorage writes during mass-friend (was rewriting 4k names on every request). */
  function scheduleFriendSentSave(set) {
    clearTimeout(friendSentSaveTimer);
    friendSentSaveTimer = setTimeout(() => {
      friendSentSaveTimer = null;
      saveFriendSentSet(set);
    }, 1500);
  }

  function flushFriendSentSave(set) {
    clearTimeout(friendSentSaveTimer);
    friendSentSaveTimer = null;
    saveFriendSentSet(set);
  }

  function isGalleryPage() {
    return /^\/G[A-Za-z0-9]{4,}(\/|$)/i.test(location.pathname || "") || /^\/gallery\//i.test(location.pathname || "");
  }

  function isMemberProfilePage() {
    return /^\/m\/[^/]+/i.test(location.pathname || "");
  }

  async function massFriendUsernames(users, onProgress) {
    friendAbort = false;
    friendMassActive = true;
    const concurrency = Math.max(1, Math.min(5, Number(settings.friendConcurrency) || 2));
    const delay = Math.max(200, Number(settings.friendDelayMs) || 700);
    const already = loadFriendSentSet();
    let sent = 0;
    let skipped = 0;
    let failed = 0;
    let deduped = 0;
    const queue = users.filter((u) => {
      const n = normalizeUser(u);
      if (!n) return false;
      if (already.has(n.toLowerCase())) {
        deduped += 1;
        return false;
      }
      return true;
    });
    const total = queue.length;
    // Warm CSRF once for the whole batch (no per-user profile HTML).
    await resolveFriendToken();

    async function worker() {
      while (queue.length && !friendAbort) {
        const user = queue.shift();
        if (!user) break;
        try {
          const r = await sendFriendRequest(user);
          if (r.login) {
            failed += 1;
            if (onProgress) onProgress({ sent, skipped, failed, deduped, total, user, login: true });
            friendAbort = true;
            break;
          }
          if (r.ok) {
            sent += 1;
            already.add(user.toLowerCase());
            scheduleFriendSentSave(already);
          } else {
            // treat "already friends" as skip
            skipped += 1;
            already.add(user.toLowerCase());
            scheduleFriendSentSave(already);
          }
        } catch (_) {
          failed += 1;
        }
        if (onProgress) onProgress({ sent, skipped, failed, deduped, total, user });
        if (delay) await new Promise((r) => setTimeout(r, delay));
      }
    }

    try {
      const workers = Array.from({ length: concurrency }, () => worker());
      await Promise.all(workers);
    } finally {
      flushFriendSentSave(already);
      friendMassActive = false;
    }
    return { sent, skipped, failed, deduped, aborted: friendAbort, total };
  }

  /* ---------- styles ---------- */
  function ensureStyle() {
    if (document.getElementById("tbcc-ml-style")) return;
    const s = document.createElement("style");
    s.id = "tbcc-ml-style";
    s.textContent = `
#tbcc-ml-overlay {
  position: fixed; right: 0; z-index: 2147483000; font: 12px/1.35 system-ui, sans-serif;
  color: #e8e8e8; display: flex; align-items: stretch; pointer-events: none;
}
#tbcc-ml-overlay .tbcc-chevron, #tbcc-ml-overlay .tbcc-panel { pointer-events: auto; }
#tbcc-ml-overlay .tbcc-chevron {
  writing-mode: vertical-rl; text-orientation: mixed;
  background: #1a1a1a; border: 1px solid #444; border-right: 0; color: #f2f2f2;
  padding: 10px 6px; cursor: grab; border-radius: 8px 0 0 8px;
  min-height: 110px; font-size: 11px; font-weight: 700; letter-spacing: .06em;
  touch-action: none; user-select: none;
}
#tbcc-ml-overlay .tbcc-chevron:active { cursor: grabbing; }
#tbcc-ml-overlay .tbcc-panel {
  display: flex; width: var(--tbcc-ml-panel-w, 260px); max-width: calc(100vw - 36px);
  max-height: min(72vh, 560px);
  background: #141414; border: 1px solid #3a3a3a; border-right: 0;
  border-radius: 10px 0 0 10px; box-shadow: -6px 0 24px rgba(0,0,0,.45);
  flex-direction: column; overflow: hidden;
}
#tbcc-ml-overlay.collapsed .tbcc-panel { display: none; }
#tbcc-ml-overlay.slim { --tbcc-ml-panel-w: 220px; }
#tbcc-ml-overlay.wide { --tbcc-ml-panel-w: 320px; }
#tbcc-ml-overlay .tbcc-head {
  display: flex; justify-content: space-between; align-items: center; gap: 6px;
  padding: 8px 10px; background: #0d0d0d; border-bottom: 1px solid #333; cursor: grab;
  touch-action: none; user-select: none;
}
#tbcc-ml-overlay .tbcc-head strong { flex: 1; pointer-events: none; min-width: 0; }
#tbcc-ml-overlay .tbcc-head .tbcc-intel-badge {
  cursor: pointer; touch-action: auto; user-select: none; flex-shrink: 0;
  display: inline-flex; align-items: center; gap: 4px;
  background: #1a2830; color: #7ec8e3; border: 1px solid #3a5560; border-radius: 6px;
  padding: 3px 8px; font-size: 12px; font-weight: 700; letter-spacing: .02em;
}
#tbcc-ml-overlay .tbcc-head .tbcc-intel-badge:hover { filter: brightness(1.12); border-color: #7ec8e3; }
#tbcc-ml-overlay .tbcc-head .tbcc-intel-badge.off { opacity: 0.45; }
#tbcc-ml-overlay .tbcc-head button {
  cursor: pointer; touch-action: auto; user-select: auto;
  background: #333; color: #eee; border: 1px solid #555; border-radius: 6px; padding: 4px 8px; font-size: 11px;
}
#tbcc-ml-overlay .tbcc-tabs { display: flex; gap: 4px; padding: 6px 8px; border-bottom: 1px solid #2a2a2a; overflow-x: auto; }
#tbcc-ml-overlay .tbcc-tabs button {
  flex: 0 0 auto; background: #222; color: #ccc; border: 1px solid #3a3a3a; border-radius: 6px;
  padding: 5px 8px; cursor: pointer; font-size: 11px;
}
#tbcc-ml-overlay .tbcc-tabs button.on { background: #c0392b; border-color: #e74c3c; color: #fff; }
#tbcc-ml-overlay .tbcc-body { padding: 10px; overflow: auto; flex: 1; }
#tbcc-ml-overlay .tbcc-body label { display: block; margin: 6px 0 3px; color: #aaa; font-size: 11px; }
#tbcc-ml-overlay .tbcc-body input, #tbcc-ml-overlay .tbcc-body textarea, #tbcc-ml-overlay .tbcc-body select {
  width: 100%; box-sizing: border-box; background: #1c1c1c; color: #eee;
  border: 1px solid #444; border-radius: 6px; padding: 6px 8px;
}
#tbcc-ml-overlay .tbcc-body textarea { min-height: 64px; resize: vertical; }
#tbcc-ml-overlay .tbcc-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
#tbcc-ml-overlay .tbcc-actions button {
  background: #c0392b; color: #fff; border: 0; border-radius: 6px; padding: 7px 10px; cursor: pointer;
}
#tbcc-ml-overlay .tbcc-actions button.secondary { background: #333; }
#tbcc-ml-overlay .tbcc-status { margin-top: 8px; color: #9ad; font-size: 11px; min-height: 1.2em; }
#tbcc-ml-overlay .tbcc-foot {
  display: flex; justify-content: space-between; align-items: center; gap: 6px;
  padding: 6px 10px; border-top: 1px solid #2a2a2a; background: #0d0d0d;
}
#tbcc-ml-overlay .tbcc-foot button {
  background: #333; color: #ddd; border: 1px solid #555; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 11px;
}
#tbcc-ml-overlay .tbcc-rss-item {
  display: block; padding: 8px 0; border-bottom: 1px solid #2a2a2a; color: #ddd; text-decoration: none;
}
#tbcc-ml-overlay .tbcc-rss-item:hover { color: #fff; }
#tbcc-ml-overlay .tbcc-rss-item .when { color: #888; font-size: 10px; margin-top: 2px; }
#tbcc-ml-overlay .tbcc-rss-item .ttl { font-weight: 600; font-size: 12px; word-break: break-word; }

.tbcc-ml-thumb-actions {
  position: absolute; top: 6px; right: 6px; z-index: 40;
  display: flex; flex-direction: column; gap: 4px; align-items: flex-end;
}
.tbcc-ml-thumb-actions .ml-act {
  border: 0; border-radius: 6px; padding: 5px 8px; cursor: pointer;
  background: rgba(20,20,20,.82); color: #fff; font-size: 12px; line-height: 1;
  backdrop-filter: blur(2px);
}
.tbcc-ml-thumb-actions .ml-act:hover { background: rgba(192,57,43,.95); }
.tbcc-ml-thumb-actions .ml-act.on { background: #c0392b; }
.tbcc-ml-thumb-actions .ml-act:disabled { opacity: .55; cursor: wait; }
.tbcc-ml-shout-pop {
  position: absolute; top: 34px; right: 0; width: 220px; z-index: 80;
  background: #151515; border: 1px solid #444; border-radius: 8px; padding: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,.5);
  pointer-events: auto;
  box-sizing: border-box;
}
/* Gallery/group picker — fixed to viewport so thumbs don't clip/overflow */
.tbcc-ml-shout-pop.tbcc-ml-pick-fixed {
  position: fixed;
  top: 0; left: 0;
  width: min(280px, calc(100vw - 16px));
  max-width: calc(100vw - 16px);
  max-height: min(360px, calc(100vh - 16px));
  z-index: 2147483000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tbcc-ml-shout-pop textarea {
  width: 100%; min-height: 56px; box-sizing: border-box; resize: vertical;
  background: #1c1c1c; color: #eee; border: 1px solid #444; border-radius: 5px; padding: 5px;
  font: 12px/1.3 system-ui, sans-serif;
}
.tbcc-ml-shout-pop .ml-pick-list {
  flex: 1 1 auto;
  min-height: 120px;
  max-height: 220px;
  overflow-x: hidden;
  overflow-y: auto;
  margin-top: 4px;
  border: 1px solid #444; border-radius: 5px; background: #111;
  -webkit-overflow-scrolling: touch;
}
.tbcc-ml-shout-pop .ml-pick-item {
  display: block; width: 100%; box-sizing: border-box;
  text-align: left; border: 0; border-bottom: 1px solid #2a2a2a;
  background: transparent; color: #eee; padding: 8px 10px; cursor: pointer;
  font: 12px/1.35 system-ui, sans-serif;
  white-space: normal; overflow-wrap: anywhere; word-break: break-word;
}
.tbcc-ml-shout-pop .ml-pick-item .ml-pick-name {
  display: block; font-weight: 600; color: #fff;
}
.tbcc-ml-shout-pop .ml-pick-item .ml-pick-id {
  display: block; margin-top: 2px; font-size: 10px; color: #888; font-weight: 400;
}
.tbcc-ml-shout-pop .ml-pick-item:last-child { border-bottom: 0; }
.tbcc-ml-shout-pop .ml-pick-item:hover { background: #2a2a2a; }
.tbcc-ml-shout-pop .ml-pick-item.on { background: #c0392b; }
.tbcc-ml-shout-pop .ml-pick-item.on .ml-pick-id { color: rgba(255,255,255,.75); }
.tbcc-ml-shout-pop .hint { color: #888; font-size: 10px; margin: 4px 0 0; flex: 0 0 auto; }
.tbcc-ml-shout-pop .ml-pick-title { color: #ddd; font-size: 12px; font-weight: 600; margin: 0; flex: 0 0 auto; }
.tbcc-ml-shout-pop .row { display: flex; gap: 6px; margin-top: 6px; flex: 0 0 auto; }
.tbcc-ml-shout-pop button {
  flex: 1; border: 0; border-radius: 5px; padding: 6px; cursor: pointer;
  background: #c0392b; color: #fff; font-size: 11px;
}
.tbcc-ml-shout-pop button.ghost { background: #333; }

#tbcc-ml-toast {
  position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(20px);
  background: rgba(20,20,20,.92); color: #fff; padding: 8px 14px; border-radius: 8px;
  border: 1px solid #444; z-index: 2147483646; opacity: 0; pointer-events: none;
  transition: opacity .2s, transform .2s; font: 12px/1.3 system-ui, sans-serif;
}
#tbcc-ml-toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

.tbcc-ml-page-sep {
  clear: both; text-align: center; margin: 16px 0 10px; color: #c0392b;
  font: 600 12px/1.2 system-ui, sans-serif; letter-spacing: .04em;
}
.tbcc-ml-infinite-page { clear: both; }
`;
    document.documentElement.appendChild(s);
  }

  /* ---------- thumbnail actions ---------- */
  function bindThumbActions(root) {
    if (!settings.thumbActions) return;
    const scope = root || document;
    const thumbs = scope.querySelectorAll(
      ".thumb-container, .desktop-thumb, .ml-image-modal-data, .thumb-container.image, .thumb-container.video"
    );
    thumbs.forEach((thumb) => {
      if (thumb.dataset.tbccMlActions === "1") return;
      const code = codenameFromEl(thumb);
      if (!code) return;
      thumb.dataset.tbccMlActions = "1";
      const host = thumb.classList.contains("thumb-container")
        ? thumb
        : thumb.closest(".thumb-container") || thumb;
      const posHost = host.querySelector(".img-container") || host;
      if (getComputedStyle(posHost).position === "static") posHost.style.position = "relative";

      const wrap = document.createElement("div");
      wrap.className = "tbcc-ml-thumb-actions";
      wrap.innerHTML = `
        <button type="button" class="ml-act ml-like" title="Favorite / Like">♥</button>
        <button type="button" class="ml-act ml-shout" title="Shout">📣</button>
        <button type="button" class="ml-act ml-gal" title="Add to gallery">🖼</button>
        <button type="button" class="ml-act ml-grp" title="Add to group">👥</button>
      `;
      const isFormControl = (el) =>
        !!el &&
        !!el.closest &&
        !!el.closest("select, option, textarea, input, .ml-pick-list, .ml-pick-item");
      const stop = (e) => {
        // Never preventDefault on form controls — that kills <select> / text focus.
        if (!isFormControl(e.target)) e.preventDefault();
        e.stopPropagation();
      };
      wrap.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!isFormControl(e.target) && e.target.closest("button, .ml-act")) e.preventDefault();
      });
      wrap.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        if (!isFormControl(e.target) && e.target.closest("button, .ml-act")) e.preventDefault();
      });

      const likeBtn = wrap.querySelector(".ml-like");
      const shoutBtn = wrap.querySelector(".ml-shout");
      const galBtn = wrap.querySelector(".ml-gal");
      const grpBtn = wrap.querySelector(".ml-grp");

      const closePops = () => {
        wrap.querySelectorAll(".tbcc-ml-shout-pop").forEach((p) => p.remove());
        document.querySelectorAll(".tbcc-ml-shout-pop.tbcc-ml-pick-fixed").forEach((p) => p.remove());
      };

      const placeFixedPop = (pop, anchorEl) => {
        if (!pop || !anchorEl) return;
        const pad = 8;
        const vw = window.innerWidth || document.documentElement.clientWidth || 360;
        const vh = window.innerHeight || document.documentElement.clientHeight || 640;
        const rect = anchorEl.getBoundingClientRect();
        const popW = Math.min(280, vw - pad * 2);
        let left = rect.right - popW;
        let top = rect.bottom + 6;
        if (left < pad) left = pad;
        if (left + popW > vw - pad) left = Math.max(pad, vw - pad - popW);
        pop.style.width = popW + "px";
        pop.style.left = left + "px";
        pop.style.top = top + "px";
        requestAnimationFrame(() => {
          const h = pop.getBoundingClientRect().height || 280;
          let t = top;
          if (t + h > vh - pad) t = Math.max(pad, rect.top - h - 6);
          if (t < pad) t = pad;
          pop.style.top = t + "px";
          pop.style.maxHeight = Math.min(360, vh - pad * 2) + "px";
        });
      };

      const openPicker = async ({ kind, title, listFn, addFn, lastKey, btn: anchorBtn }) => {
        closePops();
        document.querySelectorAll(".tbcc-ml-shout-pop.tbcc-ml-pick-fixed").forEach((p) => p.remove());
        const pop = document.createElement("div");
        pop.className = "tbcc-ml-shout-pop tbcc-ml-pick-fixed";
        pop.innerHTML = `
          <div class="ml-pick-title">${title}</div>
          <div class="ml-pick-list" role="listbox" aria-label="${title}"></div>
          <div class="row">
            <button type="button" class="ghost ml-refresh">↻</button>
            <button type="button" class="ghost ml-cancel">Cancel</button>
            <button type="button" class="ml-send">Add</button>
          </div>
          <div class="hint ml-pick-status"></div>
        `;
        document.documentElement.appendChild(pop);
        placeFixedPop(pop, anchorBtn);
        const onWin = () => placeFixedPop(pop, anchorBtn);
        window.addEventListener("resize", onWin);
        window.addEventListener("scroll", onWin, true);
        const onDoc = (ev) => {
          if (pop.contains(ev.target) || (anchorBtn && anchorBtn.contains(ev.target))) return;
          teardown();
        };
        const teardown = () => {
          window.removeEventListener("resize", onWin);
          window.removeEventListener("scroll", onWin, true);
          document.removeEventListener("mousedown", onDoc, true);
          pop.remove();
        };
        setTimeout(() => document.addEventListener("mousedown", onDoc, true), 0);

        const listEl = pop.querySelector(".ml-pick-list");
        const status = pop.querySelector(".ml-pick-status");
        let selectedId = String(settings[lastKey] || "");
        const setSelected = (id) => {
          selectedId = String(id || "");
          listEl.querySelectorAll(".ml-pick-item").forEach((el) => {
            el.classList.toggle("on", el.getAttribute("data-id") === selectedId);
          });
        };
        const fill = async (force) => {
          listEl.innerHTML = `<button type="button" class="ml-pick-item" disabled>Loading…</button>`;
          status.textContent = "";
          placeFixedPop(pop, anchorBtn);
          const r = await listFn(!!force, code);
          if (r.login) {
            listEl.innerHTML = `<button type="button" class="ml-pick-item" disabled>Log in required</button>`;
            status.textContent = "Log in to Motherless first";
            return;
          }
          const items = r.items || [];
          if (!items.length) {
            listEl.innerHTML = `<button type="button" class="ml-pick-item" disabled>No ${kind}s found</button>`;
            status.textContent =
              r.error ||
              (r.owner
                ? `No ${kind}s for @${r.owner} — create one, open your profile ${kind}s, then ↻`
                : "Open your Motherless profile once, then ↻");
            return;
          }
          if (!selectedId || !items.some((it) => String(it.id) === selectedId)) {
            selectedId = String(items[0].id || "");
          }
          listEl.innerHTML = items
            .map((it) => {
              const id = String(it.id || "").replace(/"/g, "");
              const name = String(it.title || "").trim() || `Untitled ${kind}`;
              const safeName = name.replace(/</g, "&lt;").replace(/>/g, "&gt;");
              const safeId = id.replace(/</g, "&lt;").replace(/>/g, "&gt;");
              const on = id && id === selectedId ? " on" : "";
              return `<button type="button" class="ml-pick-item${on}" data-id="${id}" role="option" title="${safeName}">
                <span class="ml-pick-name">${safeName}</span>
                <span class="ml-pick-id">${safeId}</span>
              </button>`;
            })
            .join("");
          listEl.querySelectorAll(".ml-pick-item").forEach((el) => {
            el.addEventListener("click", (ev) => {
              stop(ev);
              setSelected(el.getAttribute("data-id") || "");
            });
          });
          placeFixedPop(pop, anchorBtn);
          status.textContent =
            (r.owner ? `@${r.owner} · ` : "") + items.length + " of yours — scroll to choose";
        };
        pop.querySelector(".ml-cancel").addEventListener("click", (ev) => {
          stop(ev);
          teardown();
        });
        pop.querySelector(".ml-refresh").addEventListener("click", async (ev) => {
          stop(ev);
          await fill(true);
        });
        pop.querySelector(".ml-send").addEventListener("click", async (ev) => {
          stop(ev);
          const id = String(selectedId || "").trim();
          if (!id) {
            toast("Pick a " + kind);
            return;
          }
          const sendBtn = pop.querySelector(".ml-send");
          sendBtn.disabled = true;
          anchorBtn.disabled = true;
          try {
            const r = await addFn(code, id);
            if (r.login) {
              toast("Log in to Motherless");
              return;
            }
            if (!r.ok) {
              const why = r.error || r.data?.status || "rejected";
              toast("Add failed — not confirmed by Motherless");
              status.textContent = "Server said: " + String(why).slice(0, 80) + " — try ↻";
              return;
            }
            settings[lastKey] = id;
            saveSettings(settings);
            anchorBtn.classList.add("on");
            const pickedEl = [...listEl.querySelectorAll(".ml-pick-item")].find(
              (el) => el.getAttribute("data-id") === id
            );
            const picked = pickedEl && pickedEl.querySelector(".ml-pick-name")
              ? pickedEl.querySelector(".ml-pick-name").textContent
              : "";
            toast(picked ? `Added to ${picked}` : `Added to ${kind}`);
            teardown();
          } catch (_) {
            toast("Add failed — network error");
          } finally {
            sendBtn.disabled = false;
            anchorBtn.disabled = false;
          }
        });
        await fill(false);
      };

      likeBtn.addEventListener("click", async (e) => {
        stop(e);
        if (likeBtn.disabled) return;
        likeBtn.disabled = true;
        try {
          const r = await addFavorite(code);
          if (r.login) {
            toast("Log in to Motherless to favorite");
            return;
          }
          if (!r.ok) {
            toast("Favorite failed");
            return;
          }
          likeBtn.classList.add("on");
          toast("Favorited " + code);
        } catch (_) {
          toast("Favorite failed");
        } finally {
          likeBtn.disabled = false;
        }
      });

      shoutBtn.addEventListener("click", (e) => {
        stop(e);
        closePops();
        const pop = document.createElement("div");
        pop.className = "tbcc-ml-shout-pop";
        pop.innerHTML = `
          <textarea placeholder="Shout text…">${String(settings.defaultShout || "")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")}</textarea>
          <div class="row">
            <button type="button" class="ghost ml-cancel">Cancel</button>
            <button type="button" class="ml-send">Send</button>
          </div>
        `;
        wrap.appendChild(pop);
        pop.querySelector(".ml-cancel").addEventListener("click", (ev) => {
          stop(ev);
          pop.remove();
        });
        pop.querySelector(".ml-send").addEventListener("click", async (ev) => {
          stop(ev);
          const ta = pop.querySelector("textarea");
          const text = (ta && ta.value) || "";
          const btn = pop.querySelector(".ml-send");
          btn.disabled = true;
          try {
            const r = await postShout(code, text);
            if (r.login) {
              toast("Log in to Motherless to shout");
              return;
            }
            if (!r.ok) {
              toast("Shout failed");
              return;
            }
            toast("Shout sent");
            pop.remove();
          } catch (_) {
            toast("Shout failed");
          } finally {
            btn.disabled = false;
          }
        });
      });

      galBtn.addEventListener("click", (e) => {
        stop(e);
        openPicker({
          kind: "gallery",
          title: "Add to gallery",
          listFn: listMyGalleries,
          addFn: addToGallery,
          lastKey: "lastGalleryId",
          btn: galBtn,
        });
      });

      grpBtn.addEventListener("click", (e) => {
        stop(e);
        openPicker({
          kind: "group",
          title: "Add to group",
          listFn: listMyGroups,
          addFn: addToGroup,
          lastKey: "lastGroupSlug",
          btn: grpBtn,
        });
      });

      posHost.appendChild(wrap);
    });
  }

  /* ---------- overlay ---------- */
  const OVERLAY_PAGES = [
    { id: "friends", title: "Friends" },
    { id: "filters", title: "Filters" },
    { id: "gallery", title: "Gallery" },
    { id: "rss", title: "Intel" },
    { id: "thumbs", title: "Thumbs" },
  ];
  const JUMP_STACK_ID = "tbcc-ml-jump-stack";

  let overlayCollapsed = true;
  let overlayPageIndex = 0;
  let overlayWidthMode = "slim"; // slim | normal | wide
  let friendStatusText = "Ready — friend everyone currently visible on this page";
  let rssStatusText = "";
  let rssCache = { url: "", items: [], loadedAt: 0 };
  let lastIntelBadgeCount = 0;

  function intelHeaderCount() {
    try {
      if (intelRowsCache && Array.isArray(intelRowsCache)) return intelRowsCache.length;
    } catch (_) {}
    return loadIntelRows().length;
  }

  function updateIntelHeaderBadge(opts) {
    const o = opts || {};
    const el = document.querySelector(`#${OVERLAY_ID} [data-ml-intel-count]`);
    const btn = document.querySelector(`#${OVERLAY_ID} .tbcc-intel-badge`);
    if (!el) return;
    const count = intelHeaderCount();
    const recording = loadIntelMeta().recordIntel !== false;
    el.textContent = String(count);
    if (btn) {
      btn.classList.toggle("off", !recording);
      btn.title = recording
        ? `Browse intel: ${count} rows · click for Intel settings`
        : "Recording off — click to open Intel settings";
    }
    if (o.pulse && count > lastIntelBadgeCount) {
      el.style.transition = "color 0.2s ease, transform 0.2s ease";
      el.style.color = "#fff";
      el.style.transform = "scale(1.25)";
      setTimeout(() => {
        el.style.color = "";
        el.style.transform = "";
      }, 400);
    }
    lastIntelBadgeCount = count;
  }

  function openIntelSettingsPanel() {
    const idx = OVERLAY_PAGES.findIndex((p) => p.id === "rss");
    if (idx >= 0) overlayPageIndex = idx;
    setOverlayCollapsed(false);
    persistOverlayUi();
    renderOverlay();
    const root = document.getElementById(OVERLAY_ID);
    const body = root && root.querySelector(".tbcc-body");
    if (body) {
      body.scrollTop = 0;
      body.style.outline = "1px solid #7ec8e3";
      setTimeout(() => {
        body.style.outline = "";
      }, 900);
    }
  }

  function clampOverlayTop(px) {
    const max = Math.max(8, window.innerHeight - 140);
    return Math.min(max, Math.max(8, Math.round(Number(px) || 96)));
  }

  function loadOverlayTop() {
    try {
      return clampOverlayTop(JSON.parse(localStorage.getItem(OVERLAY_TOP_KEY) || "96"));
    } catch (_) {
      return 96;
    }
  }

  function saveOverlayTop(px) {
    try {
      localStorage.setItem(OVERLAY_TOP_KEY, JSON.stringify(clampOverlayTop(px)));
    } catch (_) {}
  }

  function loadOverlayUi() {
    try {
      const ui = JSON.parse(localStorage.getItem(OVERLAY_UI_KEY) || "{}");
      let idx = Number(ui.pageIndex);
      if (!Number.isFinite(idx) || idx < 0 || idx >= OVERLAY_PAGES.length) idx = 0;
      const w = String(ui.widthMode || "slim");
      return {
        collapsed: ui.collapsed !== false,
        pageIndex: idx,
        widthMode: w === "wide" || w === "normal" || w === "slim" ? w : "slim",
      };
    } catch (_) {
      return { collapsed: true, pageIndex: 0, widthMode: "slim" };
    }
  }

  function persistOverlayUi() {
    try {
      localStorage.setItem(
        OVERLAY_UI_KEY,
        JSON.stringify({
          collapsed: !!overlayCollapsed,
          pageIndex: overlayPageIndex,
          widthMode: overlayWidthMode,
        })
      );
    } catch (_) {}
  }

  function syncOverlayCollapsed(root) {
    if (!root) root = document.getElementById(OVERLAY_ID);
    if (!root) return;
    root.classList.toggle("collapsed", !!overlayCollapsed);
    root.classList.toggle("slim", overlayWidthMode === "slim");
    root.classList.toggle("wide", overlayWidthMode === "wide");
    const chevron = root.querySelector(".tbcc-chevron");
    if (chevron) chevron.textContent = overlayCollapsed ? "ML ▸" : "ML ◂";
    const Rail = window.TBCCSuiteRail;
    if (Rail) {
      Rail.syncJumpStack({
        stackId: JUMP_STACK_ID,
        overlayEl: root,
        visible: true,
        collapsed: overlayCollapsed,
      });
    }
  }

  function setOverlayCollapsed(next) {
    overlayCollapsed = !!next;
    syncOverlayCollapsed();
    persistOverlayUi();
  }

  function thumbTitleHaystack(el) {
    const bits = [
      el.getAttribute("title"),
      el.querySelector?.(".title")?.textContent,
      el.querySelector?.("a")?.getAttribute("title"),
      el.querySelector?.("a")?.textContent,
      el.querySelector?.("img")?.getAttribute("alt"),
      el.querySelector?.("img")?.getAttribute("title"),
    ];
    return bits
      .map((b) => String(b || "").trim())
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function applyThumbKeywordFilters() {
    const Rail = window.TBCCSuiteRail;
    const match = Rail
      ? (hay) => Rail.matchesKeywords(hay, settings.titleInclude, settings.titleExclude)
      : () => true;
    document
      .querySelectorAll(
        ".thumb-container, .desktop-thumb, .ml-image-modal-data, .thumb-member-minibio, .media-wrapper"
      )
      .forEach((el) => {
        if (el.closest(`#${OVERLAY_ID}`)) return;
        const ok = match(thumbTitleHaystack(el));
        el.classList.toggle("tbcc-suite-kw-filtered", !ok);
      });
  }

  function mountMotherlessKeywordBar() {
    const Rail = window.TBCCSuiteRail;
    if (!Rail) return;
    Rail.mountKeywordBar({
      barId: "tbcc-ml-kw-bar",
      hint: "Refines thumb titles on this grid (space/comma separated). Same Include/Exclude as Filters tab.",
      getInclude: () => settings.titleInclude || "",
      getExclude: () => settings.titleExclude || "",
      shouldMount: () => !/^\/[A-Fa-f0-9]{6,}\/?$/i.test(location.pathname || ""),
      onChange: (inc, exc) => {
        settings.titleInclude = inc;
        settings.titleExclude = exc;
        saveSettings(settings);
        applyThumbKeywordFilters();
      },
    });
  }

  function setFriendStatus(text) {
    friendStatusText = String(text || "");
    const el = document.querySelector(`#${OVERLAY_ID} .tbcc-status`);
    if (el) el.textContent = friendStatusText;
  }

  function discoverMotherlessRssFeeds() {
    const out = [];
    const seen = new Set();
    const push = (href, label) => {
      try {
        const u = new URL(href, location.origin);
        if (!/\/feeds\//i.test(u.pathname)) return;
        const key = u.pathname + u.search;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ href: u.toString(), label: label || u.pathname.split("/").slice(-2).join("/") });
      } catch (_) {}
    };
    document.querySelectorAll('a[href*="/feeds/"], link[type*="rss"], link[type*="atom"]').forEach((a) => {
      const href = a.getAttribute("href") || "";
      push(href, (a.getAttribute("title") || a.textContent || "").trim().slice(0, 48) || "RSS");
    });
    const path = location.pathname || "";
    const g = path.match(/^\/g\/([^/?#]+)/i);
    const gm = path.match(/^\/gm\/([^/?#]+)/i);
    if (g || gm) {
      const slug = (g || gm)[1];
      push(`/feeds/groups/${slug}/images?format=rss`, "Group images");
      push(`/feeds/groups/${slug}/videos?format=rss`, "Group videos");
    }
    const m = path.match(/^\/m\/([^/?#]+)/i);
    if (m) {
      push(`/feeds/members/${m[1]}/uploads?format=rss`, "Member uploads");
      push(`/feeds/members/${m[1]}/favorites?format=rss`, "Member favorites");
    }
    if (!out.length) {
      push("/feeds/images?format=rss", "Site images");
      push("/feeds/videos?format=rss", "Site videos");
    }
    return out;
  }

  function parseRssXml(xmlText) {
    const doc = new DOMParser().parseFromString(String(xmlText || ""), "text/xml");
    if (doc.querySelector("parsererror")) return [];
    const items = [...doc.querySelectorAll("item, entry")].slice(0, 80);
    return items.map((it) => {
      const title =
        (it.querySelector("title") && it.querySelector("title").textContent) ||
        "(untitled)";
      let link = "";
      const linkEl = it.querySelector("link");
      if (linkEl) {
        link = (linkEl.getAttribute("href") || linkEl.textContent || "").trim();
      }
      const guid = (it.querySelector("guid") && it.querySelector("guid").textContent) || "";
      if (!link) link = guid;
      const when =
        (it.querySelector("pubDate") && it.querySelector("pubDate").textContent) ||
        (it.querySelector("updated") && it.querySelector("updated").textContent) ||
        (it.querySelector("published") && it.querySelector("published").textContent) ||
        "";
      const desc =
        (it.querySelector("description") && it.querySelector("description").textContent) ||
        (it.querySelector("summary") && it.querySelector("summary").textContent) ||
        "";
      return {
        title: title.trim(),
        link: link.trim(),
        when: String(when).trim().slice(0, 80),
        desc: String(desc).trim().slice(0, 400),
      };
    }).filter((x) => x.link || x.title);
  }

  function loadIntelMeta() {
    try {
      return {
        recordIntel: true,
        // Lower default — 5k rows × per-thumb rewrite was blowing tab RAM on gallery/group browse.
        maxIntelRows: 1500,
        tbccApiUrl: "http://127.0.0.1:8000/analytics/erome-browse-intel",
        ...JSON.parse(localStorage.getItem(INTEL_META_KEY) || "{}"),
      };
    } catch (_) {
      return {
        recordIntel: true,
        maxIntelRows: 1500,
        tbccApiUrl: "http://127.0.0.1:8000/analytics/erome-browse-intel",
      };
    }
  }

  function saveIntelMeta(meta) {
    try {
      localStorage.setItem(INTEL_META_KEY, JSON.stringify(meta || {}));
    } catch (_) {}
  }

  /** In-memory intel cache — avoids parse/stringify of thousands of rows per thumb per scroll. */
  let intelRowsCache = null;
  let intelSeenDay = "";
  const intelSeenIds = new Set();

  function resetIntelMemoryCache() {
    intelRowsCache = null;
    intelSeenDay = "";
    intelSeenIds.clear();
  }

  function loadIntelRows() {
    try {
      const rows = JSON.parse(localStorage.getItem(INTEL_ROWS_KEY) || "[]");
      return Array.isArray(rows) ? rows : [];
    } catch (_) {
      return [];
    }
  }

  function ensureIntelMemoryCache() {
    const day = new Date().toISOString().slice(0, 10);
    if (intelRowsCache && intelSeenDay === day) return intelRowsCache;
    intelRowsCache = loadIntelRows();
    intelSeenDay = day;
    intelSeenIds.clear();
    for (const r of intelRowsCache) {
      const id = String(r.album_id || r.entity_id || "");
      if (!id) continue;
      if (String(r.captured_at || "").slice(0, 10) === day) intelSeenIds.add(id);
    }
    return intelRowsCache;
  }

  function saveIntelRows(rows, opts) {
    const o = opts || {};
    const meta = loadIntelMeta();
    const cap = Math.max(500, Math.min(5000, Number(meta.maxIntelRows) || 1500));
    const applyTrimmed = (stored) => {
      intelRowsCache = Array.isArray(stored) ? stored : [];
      try {
        localStorage.setItem(INTEL_ROWS_KEY, JSON.stringify(intelRowsCache));
      } catch (_) {}
    };
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.saveWithCapAndMaybePush === "function") {
      globalThis.tbccBrowseIntel.saveWithCapAndMaybePush({
        rows,
        meta: { ...meta, maxIntelRows: cap },
        skipAutoPush: !!o.skipAutoPush,
        applyTrimmed,
        toast: (msg) => {
          try {
            toast(msg);
          } catch (_) {}
        },
      });
      return;
    }
    applyTrimmed((rows || []).slice(-cap));
  }

  function motherlessEntityId(link) {
    try {
      const u = new URL(link, location.origin);
      const parts = u.pathname.split("/").filter(Boolean);
      if (!parts.length) return "";
      // /CODE or /G/hash or /u/user/…
      const last = parts[parts.length - 1];
      if (last && last.length >= 3 && !/^(images|videos|favorites|uploads)$/i.test(last)) {
        return last.toLowerCase();
      }
      return parts.join("_").toLowerCase().slice(0, 80);
    } catch (_) {
      return "";
    }
  }

  function ageDaysFromWhen(when) {
    const ms = Date.parse(String(when || ""));
    if (Number.isNaN(ms)) return null;
    return Math.max(0.04, (Date.now() - ms) / 86400000);
  }

  function feedContextTags(feedUrl) {
    const tags = [];
    try {
      const u = new URL(feedUrl, location.origin);
      const path = u.pathname || "";
      const g = path.match(/\/feeds\/groups\/([^/?#]+)/i);
      if (g) {
        tags.push("group:" + decodeURIComponent(g[1]).toLowerCase());
        tags.push(decodeURIComponent(g[1]).toLowerCase().replace(/[-_]+/g, " "));
      }
      const m = path.match(/\/feeds\/members\/([^/?#]+)/i);
      if (m) tags.push("member:" + decodeURIComponent(m[1]).toLowerCase());
      if (/\/videos/i.test(path)) tags.push("video");
      if (/\/images/i.test(path)) tags.push("image");
      if (/favorites/i.test(path)) tags.push("favorites");
      if (/uploads/i.test(path)) tags.push("uploads");
    } catch (_) {}
    return [...new Set(tags.filter(Boolean))].slice(0, 20);
  }

  function rssItemToIntelRow(item, feedUrl) {
    const link = String(item.link || "").trim();
    if (!link) return null;
    const id = motherlessEntityId(link);
    if (!id) return null;
    const age = ageDaysFromWhen(item.when);
    const feedTags = feedContextTags(feedUrl);
    const isVideo = feedTags.includes("video") || /\/videos?\b/i.test(link);
    const isImage = feedTags.includes("image") || (!isVideo && /\/images?\b/i.test(feedUrl));
    let uploader = null;
    const mem = String(feedUrl || "").match(/\/feeds\/members\/([^/?#]+)/i);
    if (mem) uploader = decodeURIComponent(mem[1]).slice(0, 80);
    return {
      platform: "motherless",
      captured_at: new Date().toISOString(),
      album_url: link.startsWith("http") ? link : new URL(link, location.origin).toString(),
      album_id: id,
      entity_id: id,
      entity_url: link.startsWith("http") ? link : new URL(link, location.origin).toString(),
      title: String(item.title || id).slice(0, 200),
      views: null,
      likes: null,
      videos: isVideo ? 1 : 0,
      images: isImage || !isVideo ? 1 : 0,
      tags: feedTags,
      format_bucket: isVideo ? "single_video" : "photo_album",
      uploaded_at_approx_days_ago: age,
      views_per_day_proxy: age ? Math.round((1 / age) * 10) / 10 : null,
      uploader,
      page_context: {
        path: location.pathname,
        feed_url: feedUrl,
        pub_date: item.when || null,
      },
      media_sequence: isVideo ? ["video"] : ["image"],
    };
  }

  function recordIntelRow(row) {
    return recordIntelRowsBatch([row]) > 0;
  }

  /** One load / one save for many thumbs — old path rewrote localStorage once per card. */
  function recordIntelRowsBatch(newRows) {
    const list = Array.isArray(newRows) ? newRows : [];
    if (!list.length) return 0;
    const meta = loadIntelMeta();
    if (meta.recordIntel === false) return 0;
    const rows = ensureIntelMemoryCache();
    const day = new Date().toISOString().slice(0, 10);
    let added = 0;
    let upgraded = 0;
    for (const row of list) {
      if (!row) continue;
      const id = String(row.album_id || row.entity_id || "");
      if (!id) continue;
      if (intelSeenIds.has(id)) {
        const idx = rows.findIndex((r) => {
          const rid = String(r.album_id || r.entity_id || "");
          const rday = String(r.captured_at || "").slice(0, 10);
          return rid === id && rday === day;
        });
        if (idx < 0) continue;
        const prev = rows[idx] || {};
        const nextViews = Number(row.views);
        const prevViews = Number(prev.views);
        const nextLikes = Number(row.likes);
        const prevLikes = Number(prev.likes);
        const needViews = !(prevViews > 0) && nextViews > 0;
        const needLikes = !(prevLikes > 0) && nextLikes >= 0 && row.likes != null;
        if (!needViews && !needLikes) continue;
        const merged = { ...prev, ...row };
        if (!needViews) merged.views = prev.views;
        if (!needLikes && prev.likes != null) merged.likes = prev.likes;
        if (merged.views && merged.likes) {
          merged.engagement_bps = Math.round((Number(merged.likes) / Number(merged.views)) * 100000);
        }
        rows[idx] = merged;
        upgraded += 1;
        continue;
      }
      intelSeenIds.add(id);
      rows.push(row);
      added += 1;
    }
    if (added || upgraded) {
      intelRowsCache = rows;
      saveIntelRows(rows);
      try {
        updateIntelHeaderBadge({ pulse: added > 0 });
      } catch (_) {}
    }
    return added + upgraded;
  }

  function parseAbbrevCount(raw) {
    const s = String(raw || "")
      .replace(/,/g, "")
      .trim();
    const m = s.match(/([\d.]+)\s*([kKmMbB])?/);
    if (!m) return null;
    let n = parseFloat(m[1]);
    if (!Number.isFinite(n)) return null;
    const u = (m[2] || "").toLowerCase();
    if (u === "k") n *= 1e3;
    else if (u === "m") n *= 1e6;
    else if (u === "b") n *= 1e9;
    return Math.round(n);
  }

  /**
   * Motherless thumbs show views as <i class="fa-eye"></i><span class="value">2.4K</span>
   * — not "2.4K views". Old regex required the word "views", so every row stored null and Pareto stayed empty.
   */
  function extractViewsFromThumb(el) {
    if (!el || !el.querySelector) return null;
    const eye =
      el.querySelector("i.fa-eye, i.far.fa-eye, i.fas.fa-eye, .fa-eye") ||
      el.querySelector('[class*="fa-eye"]');
    if (eye) {
      const host = eye.parentElement || eye;
      const val =
        host.querySelector(".value") ||
        (eye.nextElementSibling && /\d/.test(eye.nextElementSibling.textContent || "")
          ? eye.nextElementSibling
          : null);
      if (val) {
        const n = parseAbbrevCount(val.textContent);
        if (n != null && n > 0) return n;
      }
    }
    const dedicated = el.querySelector(
      ".views .value, .view-count, .thumb-views .value, [data-views], [data-view-count]"
    );
    if (dedicated) {
      const raw =
        dedicated.getAttribute("data-views") ||
        dedicated.getAttribute("data-view-count") ||
        dedicated.textContent;
      const n = parseAbbrevCount(raw);
      if (n != null && n > 0) return n;
    }
    const textBlob = String(el.textContent || "");
    let m = textBlob.match(/([\d.,]+\s*[kKmMbB]?)\s*views?\b/i);
    if (m) return parseAbbrevCount(m[1]);
    m = textBlob.match(/\bviews?\s*[:\-]?\s*([\d.,]+\s*[kKmMbB]?)/i);
    if (m) return parseAbbrevCount(m[1]);
    return null;
  }

  function extractLikesFromThumb(el) {
    if (!el || !el.querySelector) return null;
    const heart =
      el.querySelector("i.fa-heart, .fa-heart, [class*='fa-heart']") ||
      el.querySelector("i.fa-star, .fa-star");
    if (heart) {
      const host = heart.parentElement || heart;
      const val = host.querySelector(".value") || heart.nextElementSibling;
      if (val && /\d/.test(val.textContent || "")) {
        const n = parseAbbrevCount(val.textContent);
        if (n != null && n >= 0) return n;
      }
    }
    const textBlob = String(el.textContent || "");
    const m = textBlob.match(/([\d.,]+\s*[kKmMbB]?)\s*(?:favorites?|favs?|likes?)\b/i);
    return m ? parseAbbrevCount(m[1]) : null;
  }

  function extractUploaderFromThumb(el) {
    if (!el) return null;
    const fromData =
      el.getAttribute("data-username") ||
      el.querySelector("[data-username]")?.getAttribute("data-username") ||
      el.querySelector("[data-profile-link]")?.getAttribute("data-username");
    if (fromData) return String(fromData).slice(0, 80);
    const a = el.querySelector('a[href*="/m/"]');
    if (a) {
      const m = String(a.getAttribute("href") || "").match(/\/m\/([^/?#]+)/i);
      if (m) return decodeURIComponent(m[1]).slice(0, 80);
    }
    return null;
  }

  function thumbToIntelRow(el) {
    const code = codenameFromEl(el);
    if (!code) return null;
    const a =
      el.querySelector("a.img-container[href], a[href^='/']") ||
      el.closest("a[href]") ||
      el.querySelector("a[href]");
    let href = (a && (a.href || a.getAttribute("href"))) || `/${code}`;
    try {
      href = new URL(href, location.origin).toString();
    } catch (_) {}
    const titleEl = el.querySelector(
      ".caption, .captions, .title, .media-title, .desktop-thumb-info, [class*='title']"
    );
    let title = String((titleEl && titleEl.textContent) || "").replace(/\s+/g, " ").trim();
    // captions often include stats — keep first line / before view numbers when possible
    title = title.split(/\s{2,}|\n/)[0] || title;
    if (!title || /click to view/i.test(title)) {
      const alt = el.querySelector("img[alt]")?.getAttribute("alt");
      title = String(alt || code).replace(/\s+/g, " ").trim().slice(0, 200);
    }
    const views = extractViewsFromThumb(el);
    const likes = extractLikesFromThumb(el);
    const uploader = extractUploaderFromThumb(el);
    const isVideo =
      el.classList.contains("video") ||
      el.getAttribute("data-mediatype") === "video" ||
      !!el.querySelector(".video, .icon-video, [data-mediatype='video'], [class*='video']") ||
      /\/videos?\b/i.test(href);
    const tags = [];
    if (isVideo) tags.push("video");
    else tags.push("image");
    if (uploader) tags.push(uploader.toLowerCase());
    const pathTags = String(location.pathname || "")
      .split("/")
      .filter((p) => p && p.length > 1 && p.length < 40 && !/^(images|videos|u|m|G|gi|gv|gm|gti|g)$/i.test(p));
    pathTags.slice(0, 3).forEach((t) => {
      const clean = t.toLowerCase().replace(/[-_]+/g, " ");
      if (clean && clean !== code.toLowerCase()) tags.push(clean);
    });
    let engagement_bps = 0;
    if (views && likes) engagement_bps = Math.round((likes / views) * 100000);
    return {
      platform: "motherless",
      captured_at: new Date().toISOString(),
      album_url: href,
      album_id: code.toLowerCase(),
      entity_id: code.toLowerCase(),
      entity_url: href,
      title: title.slice(0, 200),
      views,
      likes,
      videos: isVideo ? 1 : 0,
      images: isVideo ? 0 : 1,
      tags: [...new Set(tags)].slice(0, 20),
      format_bucket: isVideo ? "single_video" : "image",
      engagement_bps,
      page_context: { path: location.pathname },
      uploader,
    };
  }

  function scanGridIntel() {
    const meta = loadIntelMeta();
    if (meta.recordIntel === false) return 0;
    ensureIntelMemoryCache();
    const pending = [];
    document
      .querySelectorAll(
        ".thumb-container, .desktop-thumb, .ml-image-modal-data, .thumb-container.image, .thumb-container.video"
      )
      .forEach((el) => {
        const row = thumbToIntelRow(el);
        if (!row) return;
        const already = el.dataset.tbccMlIntel === "1";
        el.dataset.tbccMlIntel = "1";
        // Re-pass cards that were stored without views so Pareto can fill in.
        if (already && !(Number(row.views) > 0) && !(Number(row.likes) > 0)) return;
        pending.push(row);
      });
    return recordIntelRowsBatch(pending);
  }

  function ingestRssItemsToIntel(items, feedUrl) {
    const pending = [];
    (items || []).forEach((it) => {
      const row = rssItemToIntelRow(it, feedUrl);
      if (row) pending.push(row);
    });
    return recordIntelRowsBatch(pending);
  }

  function exportIntelJsonl() {
    const rows = loadIntelRows();
    const name = `motherless-browse-intel-${new Date().toISOString().slice(0, 10)}.jsonl`;
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.exportJsonlSaveAs === "function") {
      void globalThis.tbccBrowseIntel.exportJsonlSaveAs(rows, name).then((r) => {
        toast(r && r.ok !== false ? `Save As · ${name}` : "Export failed");
      });
      return;
    }
    const blob = new Blob(
      [rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : "")],
      { type: "application/x-ndjson" }
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function pushIntelToTbcc() {
    const meta = loadIntelMeta();
    const rows = loadIntelRows();
    if (!rows.length) throw new Error("No intel rows");
    const url = String(meta.tbccApiUrl || "").trim();
    if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.postIntelRows === "function") {
      const resp = await globalThis.tbccBrowseIntel.postIntelRows(url, rows);
      const keep = Math.max(100, Math.floor(Math.max(500, meta.maxIntelRows || 1500) * 0.2));
      resetIntelMemoryCache();
      saveIntelRows(rows.slice(-keep), { skipAutoPush: true });
      return resp.appended != null ? resp.appended : rows.length;
    }
    if (!url) throw new Error("Set TBCC ingest URL");
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return rows.length;
  }

  async function loadRssFeed(url) {
    const r = await fetch(url, { credentials: "include", cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const text = await r.text();
    if (/<html[\s>]/i.test(text) && !/<rss[\s>]/i.test(text) && !/<feed[\s>]/i.test(text)) {
      throw new Error("Feed returned HTML (login or temp error)");
    }
    const items = parseRssXml(text);
    rssCache = { url, items, loadedAt: Date.now() };
    const meta = loadIntelMeta();
    if (meta.recordIntel !== false) {
      ingestRssItemsToIntel(items, url);
    }
    return items;
  }

  function renderOverlay() {
    const root = document.getElementById(OVERLAY_ID);
    if (!root) return;
    syncOverlayCollapsed(root);
    root.querySelectorAll(".tbcc-tabs button").forEach((b, i) => {
      b.classList.toggle("on", i === overlayPageIndex);
    });
    const body = root.querySelector(".tbcc-body");
    const page = OVERLAY_PAGES[overlayPageIndex] || OVERLAY_PAGES[0];
    const ind = root.querySelector(".page-ind");
    if (ind) ind.textContent = `${overlayPageIndex + 1}/${OVERLAY_PAGES.length}`;
    updateIntelHeaderBadge();

    if (page.id === "friends") {
      scanMembersIntoDiscovered();
      const visible = collectVisibleUsernames();
      const scanned = discoveredMembers.size;
      const genders = Array.isArray(settings.filterGender) ? settings.filterGender : GENDER_KEYS;
      const sexes = Array.isArray(settings.filterSexuality) ? settings.filterSexuality : SEX_KEYS;
      const genderChecks = GENDER_KEYS.map(
        (k) =>
          `<label style="display:inline-flex;gap:4px;align-items:center;margin:2px 8px 2px 0;font-size:11px"><input type="checkbox" data-fg="${k}" ${
            genders.includes(k) ? "checked" : ""
          }/>${k}</label>`
      ).join("");
      const sexChecks = SEX_KEYS.map(
        (k) =>
          `<label style="display:inline-flex;gap:4px;align-items:center;margin:2px 8px 2px 0;font-size:11px"><input type="checkbox" data-fs="${k}" ${
            sexes.includes(k) ? "checked" : ""
          }/>${k}</label>`
      ).join("");
      const onList = isMemberListPage() || isGroupShoutsPage();
      body.innerHTML = `
        <div data-ml-friend-count style="color:#bbb;font-size:11px;margin-bottom:6px">
          Visible now: <b style="color:#fff">${visible.length}</b>
          · scanned while scrolling: <b style="color:#fff">${scanned}</b>
          · <code>${location.pathname}</code>
        </div>
        <label>Friend how many at once <span style="color:#666">(1–5)</span></label>
        <input type="number" min="1" max="5" data-k="friendConcurrency" value="${Number(settings.friendConcurrency) || 2}" title="How many friend requests to send in parallel. Keep low to avoid being rate-limited." />
        <label>Wait between batches <span style="color:#666">(milliseconds)</span></label>
        <input type="number" min="200" max="5000" step="50" data-k="friendDelayMs" value="${Math.max(200, Number(settings.friendDelayMs) || 700)}" title="Pause after each friend request. Keep ≥700ms to avoid rate-limits. Values under 200 are ignored at send time." />
        ${
          onList
            ? `<div style="margin-top:10px;padding-top:8px;border-top:1px solid #333">
          <div style="color:#ddd;font-size:12px;margin-bottom:4px">Gender filter</div>
          <div data-filter-genders>${genderChecks}</div>
          <div style="color:#ddd;font-size:12px;margin:8px 0 4px">Sexuality filter</div>
          <div data-filter-sex>${sexChecks}</div>
          <label style="margin-top:8px">Sort</label>
          <select data-k="memberSort">
            <option value="default" ${settings.memberSort === "default" ? "selected" : ""}>Site order</option>
            <option value="join_desc" ${settings.memberSort === "join_desc" ? "selected" : ""}>Most recent group join</option>
          </select>
          <div class="tbcc-actions" style="margin-top:6px">
            <button type="button" class="secondary" data-act="filter-apply">Apply filter / sort</button>
          </div>
          <p style="color:#888;font-size:11px;margin-top:6px">Hides non-matching cards on Members (/gm) and group Shouts feeds. Join sort uses “joined … ago” text when present.</p>
        </div>`
            : ""
        }
        <div class="tbcc-actions">
          <button type="button" data-act="friend-visible">Friend visible</button>
          <button type="button" data-act="friend-scanned">Friend scanned</button>
          <button type="button" class="secondary" data-act="friend-abort">Stop</button>
          <button type="button" class="secondary" data-act="friend-clear">Forget who I friended</button>
        </div>
        <div class="tbcc-status">${friendStatusText}</div>
        <p style="color:#888;font-size:11px;margin-top:10px">
          On group <code>/gm/…</code> Members: scroll to load more — the counter updates as cards appear. <b>Friend visible</b> = on screen now. <b>Friend scanned</b> = everyone seen this visit.
          CSRF comes from this page (not each profile) so large batches stay light on RAM.
        </p>
      `;
      const persistFilters = () => {
        const fg = [...body.querySelectorAll("[data-fg]:checked")].map((el) => el.getAttribute("data-fg"));
        const fs = [...body.querySelectorAll("[data-fs]:checked")].map((el) => el.getAttribute("data-fs"));
        settings.filterGender = fg.length ? fg : ["unknown"];
        settings.filterSexuality = fs.length ? fs : ["unknown"];
        const sortEl = body.querySelector('[data-k="memberSort"]');
        if (sortEl) settings.memberSort = sortEl.value === "join_desc" ? "join_desc" : "default";
        saveSettings(settings);
      };
      body.querySelectorAll("[data-fg], [data-fs]").forEach((el) => {
        el.addEventListener("change", () => {
          persistFilters();
          const r = applyMemberFiltersAndSort();
          setFriendStatus(`Filter: showing ${r.shown}, hidden ${r.hidden}`);
          scanMembersIntoDiscovered();
        });
      });
    } else if (page.id === "filters") {
      const Rail = window.TBCCSuiteRail;
      body.innerHTML = `
        <p style="color:#bbb;font-size:11px;margin:0 0 8px">Title keywords for video/image thumbs (same as the sticky bar). Include = all must match; exclude = hide if any.</p>
        <label>Include (all must match)</label>
        <input type="text" data-kw-inc placeholder="e.g. milf blonde" value="${String(settings.titleInclude || "").replace(/"/g, "&quot;")}" autocomplete="off" />
        <label>Exclude (hide if any)</label>
        <input type="text" data-kw-exc placeholder="e.g. gay" value="${String(settings.titleExclude || "").replace(/"/g, "&quot;")}" autocomplete="off" />
        <div class="tbcc-actions">
          <button type="button" data-act="kw-apply">Apply</button>
          <button type="button" class="secondary" data-act="kw-clear">Clear</button>
        </div>
        <div class="tbcc-status">${friendStatusText}</div>
      `;
      const syncKw = () => {
        settings.titleInclude = String(body.querySelector("[data-kw-inc]")?.value || "").trim();
        settings.titleExclude = String(body.querySelector("[data-kw-exc]")?.value || "").trim();
        saveSettings(settings);
        applyThumbKeywordFilters();
        const bar = document.getElementById("tbcc-ml-kw-bar");
        if (bar) {
          const bi = bar.querySelector('[data-kw="inc"]');
          const be = bar.querySelector('[data-kw="exc"]');
          if (bi) bi.value = settings.titleInclude;
          if (be) be.value = settings.titleExclude;
        }
        setFriendStatus("Keywords applied");
      };
      body.querySelector("[data-act='kw-apply']")?.addEventListener("click", syncKw);
      body.querySelector("[data-act='kw-clear']")?.addEventListener("click", () => {
        const i = body.querySelector("[data-kw-inc]");
        const e = body.querySelector("[data-kw-exc]");
        if (i) i.value = "";
        if (e) e.value = "";
        syncKw();
      });
      body.querySelectorAll("[data-kw-inc], [data-kw-exc]").forEach((el) => {
        el.addEventListener("change", syncKw);
      });
      void Rail;
    } else if (page.id === "gallery") {
      const onGal = isGalleryPage();
      body.innerHTML = `
        <div style="color:#bbb;font-size:11px;margin-bottom:8px">
          ${onGal ? "You’re on a gallery — ZIP / download will grab the full-size media files." : "Open a gallery page first (URL usually starts with /G). List pages can still auto-load more thumbs."}
        </div>
        <label><input type="checkbox" data-k="infiniteScroll" ${settings.infiniteScroll !== false ? "checked" : ""}/> Keep loading more thumbs as I scroll</label>
        <label>Extra pages to load <span style="color:#666">(max 6)</span></label>
        <input type="number" min="1" max="6" data-k="infiniteMaxPages" value="${Number(settings.infiniteMaxPages) || 3}" />
        <label>Thumbs to keep on screen <span style="color:#666">(max 80)</span></label>
        <input type="number" min="20" max="80" data-k="infiniteMaxCards" value="${Number(settings.infiniteMaxCards) || 48}" />
        <div class="tbcc-actions">
          <button type="button" data-act="gal-zip" ${onGal ? "" : "disabled"}>ZIP this gallery</button>
          <button type="button" class="secondary" data-act="gal-dl" ${onGal ? "" : "disabled"}>Download files</button>
        </div>
        <div class="tbcc-status">${infiniteStatusText || friendStatusText}</div>
      `;
    } else if (page.id === "rss") {
      const feeds = discoverMotherlessRssFeeds();
      const intelMeta = loadIntelMeta();
      const intelRows = loadIntelRows();
      const intelCount = intelRows.length;
      const liveHtml =
        globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.renderParetoLiveHtml === "function"
          ? globalThis.tbccBrowseIntel.renderParetoLiveHtml(intelRows)
          : "";
      const opts = feeds
        .map((f) => `<option value="${f.href.replace(/"/g, "&quot;")}">${(f.label || f.href).replace(/</g, "")}</option>`)
        .join("");
      const listHtml =
        rssCache.items && rssCache.items.length
          ? rssCache.items
              .map(
                (it) =>
                  `<a class="tbcc-rss-item" href="${String(it.link || "#").replace(/"/g, "&quot;")}" target="_blank" rel="noopener">` +
                  `<div class="ttl">${String(it.title || "").replace(/</g, "&lt;")}</div>` +
                  (it.when ? `<div class="when">${String(it.when).replace(/</g, "&lt;")}</div>` : "") +
                  `</a>`
              )
              .join("")
          : `<p style="color:#888;font-size:11px"><b>Passive:</b> just browse thumbs — intel records automatically when Record is on. At max rows it auto-pushes to TBCC and keeps the last 20%. Scan / RSS are optional.</p>`;
      body.innerHTML = `
        <p style="color:#aaa;font-size:11px;margin:0 0 8px">Same idea as Erome: leave <b>Record</b> checked, scroll galleries/groups, ignore the Scan button unless you want a one-shot refresh.</p>
        <label><input type="checkbox" data-intel="record" ${intelMeta.recordIntel !== false ? "checked" : ""}/> Record browse intel (passive while browsing)</label>
        <label>Max local rows</label>
        <input type="number" min="500" max="5000" data-intel="max" value="${Number(intelMeta.maxIntelRows) || 1500}" />
        <label>TBCC ingest URL</label>
        <input type="text" data-intel="url" value="${String(intelMeta.tbccApiUrl || "").replace(/"/g, "&quot;")}" placeholder="http://127.0.0.1:8000/analytics/erome-browse-intel" />
        <div class="tbcc-actions">
          <button type="button" data-act="intel-scan">Scan visible now (optional)</button>
          <button type="button" class="secondary" data-act="intel-export">Export JSONL</button>
          <button type="button" class="secondary" data-act="intel-push">Push to TBCC</button>
          <button type="button" class="secondary" data-act="intel-clear">Clear intel</button>
        </div>
        <label style="margin-top:8px">RSS feed on this page</label>
        <select data-rss-select>${opts || `<option value="">No feeds found</option>`}</select>
        <div class="tbcc-actions">
          <button type="button" data-act="rss-load">Load RSS + record</button>
          <button type="button" class="secondary" data-act="rss-open">Open feed URL</button>
        </div>
        <div class="tbcc-status">${rssStatusText || (rssCache.url ? `${rssCache.items.length} item(s)` : "Ready")} · intel ${intelCount} row(s)</div>
        ${liveHtml}
        <div data-rss-list style="margin-top:8px">${listHtml}</div>
      `;
      const sel = body.querySelector("[data-rss-select]");
      if (sel && rssCache.url) {
        const match = [...sel.options].find((o) => o.value === rssCache.url);
        if (match) sel.value = rssCache.url;
      }
      const persistIntel = () => {
        saveIntelMeta({
          ...loadIntelMeta(),
          recordIntel: !!body.querySelector('[data-intel="record"]')?.checked,
          maxIntelRows: Math.max(500, Math.min(5000, Number(body.querySelector('[data-intel="max"]')?.value) || 1500)),
          tbccApiUrl: String(body.querySelector('[data-intel="url"]')?.value || "").trim(),
        });
      };
      body.querySelector('[data-intel="record"]')?.addEventListener("change", persistIntel);
      body.querySelector('[data-intel="max"]')?.addEventListener("change", persistIntel);
      body.querySelector('[data-intel="url"]')?.addEventListener("change", persistIntel);
    } else {
      body.innerHTML = `
        <label><input type="checkbox" data-k="thumbActions" ${settings.thumbActions ? "checked" : ""}/> Show ♥ 📣 🖼 👥 on thumbnails</label>
        <label>Default shout message</label>
        <textarea data-k="defaultShout" placeholder="Text used when you tap Shout on a thumb">${String(settings.defaultShout || "")}</textarea>
        <div class="tbcc-actions">
          <button type="button" data-act="thumbs-refresh">Refresh thumb buttons</button>
        </div>
        <div class="tbcc-status">♥ favorite · 📣 shout · 🖼 gallery · 👥 group (logged-in)</div>
      `;
    }

    body.querySelectorAll("[data-k]").forEach((el) => {
      const apply = () => {
        const k = el.getAttribute("data-k");
        if (el.type === "checkbox") settings[k] = !!el.checked;
        else if (el.type === "number") {
          let n = Number(el.value);
          if (k === "friendDelayMs") n = Math.max(200, Math.min(8000, n || 700));
          if (k === "friendConcurrency") n = Math.max(1, Math.min(5, n || 2));
          settings[k] = n;
          el.value = String(n);
        } else settings[k] = el.value;
        saveSettings(settings);
      };
      el.addEventListener("change", apply);
      el.addEventListener("input", apply);
    });

    body.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const act = btn.getAttribute("data-act");
        if (act === "friend-abort") {
          friendAbort = true;
          setFriendStatus("Stopping…");
          return;
        }
        if (act === "friend-clear") {
          localStorage.removeItem(FRIEND_SENT_KEY);
          setFriendStatus("Forgot prior friended names — they’ll be eligible again");
          return;
        }
        if (act === "thumbs-refresh") {
          document.querySelectorAll("[data-tbcc-ml-actions]").forEach((el) => {
            delete el.dataset.tbccMlActions;
            el.querySelectorAll(".tbcc-ml-thumb-actions").forEach((n) => n.remove());
          });
          bindThumbActions(document);
          toast("Thumb actions refreshed");
          return;
        }
        if (act === "intel-export") {
          exportIntelJsonl();
          toast("Exported motherless intel JSONL");
          return;
        }
        if (act === "intel-scan") {
          saveIntelMeta({
            ...loadIntelMeta(),
            recordIntel: !!body.querySelector('[data-intel="record"]')?.checked,
            maxIntelRows: Math.max(500, Math.min(5000, Number(body.querySelector('[data-intel="max"]')?.value) || 1500)),
            tbccApiUrl: String(body.querySelector('[data-intel="url"]')?.value || "").trim(),
          });
          const n = scanGridIntel();
          rssStatusText = `Grid scan · +${n} new`;
          toast(rssStatusText);
          renderOverlay();
          return;
        }
        if (act === "intel-clear") {
          if (!confirm("Clear Motherless intel rows?")) return;
          resetIntelMemoryCache();
          saveIntelRows([], { skipAutoPush: true });
          document.querySelectorAll("[data-tbcc-ml-intel]").forEach((el) => {
            delete el.dataset.tbccMlIntel;
          });
          rssStatusText = "Intel cleared";
          toast(rssStatusText);
          renderOverlay();
          return;
        }
        if (act === "intel-push") {
          try {
            const n = await pushIntelToTbcc();
            rssStatusText = `Pushed ${n} intel row(s)`;
            toast(rssStatusText);
          } catch (e) {
            rssStatusText = "Push failed: " + (e.message || e);
            toast(rssStatusText);
          }
          renderOverlay();
          return;
        }
        if (act === "rss-load" || act === "rss-open") {
          const sel = body.querySelector("[data-rss-select]");
          const url = sel && sel.value;
          if (!url) {
            rssStatusText = "No feed URL";
            renderOverlay();
            return;
          }
          if (act === "rss-open") {
            window.open(url, "_blank", "noopener");
            return;
          }
          saveIntelMeta({
            ...loadIntelMeta(),
            recordIntel: !!body.querySelector('[data-intel="record"]')?.checked,
            maxIntelRows: Math.max(500, Math.min(5000, Number(body.querySelector('[data-intel="max"]')?.value) || 1500)),
            tbccApiUrl: String(body.querySelector('[data-intel="url"]')?.value || "").trim(),
          });
          rssStatusText = "Loading…";
          renderOverlay();
          try {
            const before = loadIntelRows().length;
            const items = await loadRssFeed(url);
            const after = loadIntelRows().length;
            rssStatusText = `${items.length} item(s) · +${Math.max(0, after - before)} intel`;
          } catch (e) {
            rssStatusText = "Failed: " + (e.message || e);
            rssCache = { url: "", items: [], loadedAt: 0 };
          }
          renderOverlay();
          return;
        }
        if (act === "gal-zip" || act === "gal-dl") {
          setFriendStatus(act === "gal-zip" ? "Starting gallery ZIP…" : "Starting gallery download…");
          try {
            const r = await new Promise((resolve) => {
              chrome.runtime.sendMessage(
                { action: "tbcc-motherless-gallery-bulk", mode: act === "gal-zip" ? "zip" : "download" },
                (resp) => resolve(resp || { ok: false, error: chrome.runtime.lastError && chrome.runtime.lastError.message })
              );
            });
            if (!r || !r.ok) setFriendStatus("Failed: " + ((r && r.error) || "unknown"));
            else setFriendStatus(`Queued ${r.count || "?"} file(s) — see gallery panel`);
          } catch (e) {
            setFriendStatus("Failed: " + (e.message || e));
          }
          return;
        }
        if (act === "filter-apply") {
          const fg = [...body.querySelectorAll("[data-fg]:checked")].map((el) => el.getAttribute("data-fg"));
          const fs = [...body.querySelectorAll("[data-fs]:checked")].map((el) => el.getAttribute("data-fs"));
          settings.filterGender = fg.length ? fg : ["unknown"];
          settings.filterSexuality = fs.length ? fs : ["unknown"];
          const sortEl = body.querySelector('[data-k="memberSort"]');
          if (sortEl) settings.memberSort = sortEl.value === "join_desc" ? "join_desc" : "default";
          saveSettings(settings);
          const r = applyMemberFiltersAndSort();
          setFriendStatus(`Filter: showing ${r.shown}, hidden ${r.hidden}`);
          scanMembersIntoDiscovered();
          renderOverlay();
          return;
        }
        if (act === "friend-visible" || act === "friend-scanned") {
          scanMembersIntoDiscovered();
          const users =
            act === "friend-scanned" ? discoveredMemberList() : collectVisibleUsernames();
          if (!users.length) {
            setFriendStatus(
              isGroupMembersPage()
                ? "No members detected yet — scroll the Members grid; count updates live"
                : "Nobody visible yet — scroll the membership list"
            );
            return;
          }
          setFriendStatus(
            `Sending ${users.length} friend request(s)${act === "friend-scanned" ? " (scanned)" : " (visible)"}…`
          );
          const r = await massFriendUsernames(users, (p) => {
            setFriendStatus(
              `Friended ${p.sent} · already done ${p.skipped} · failed ${p.failed} · repeats skipped ${p.deduped}` +
                (p.login ? " · log in to Motherless first" : "") +
                (p.user ? ` · @${p.user}` : "")
            );
          });
          setFriendStatus(
            `Done: friended ${r.sent}, already done ${r.skipped}, failed ${r.failed}, repeats skipped ${r.deduped}` +
              (r.aborted ? " (stopped)" : "")
          );
        }
      });
    });
  }

  function bindVerticalDrag(root, handle, opts = {}) {
    let drag = null;
    const DRAG_THRESHOLD = 5;
    const suppressClick = opts.suppressClickAfterDrag !== false;
    handle.addEventListener("pointerdown", (e) => {
      if (e.button != null && e.button !== 0) return;
      if (opts.ignoreSelector && e.target && e.target.closest && e.target.closest(opts.ignoreSelector)) return;
      drag = {
        pointerId: e.pointerId,
        startY: e.clientY,
        startTop: root.getBoundingClientRect().top,
        moved: false,
      };
      try {
        handle.setPointerCapture(e.pointerId);
      } catch (_) {}
    });
    handle.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      const dy = e.clientY - drag.startY;
      if (!drag.moved && Math.abs(dy) < DRAG_THRESHOLD) return;
      drag.moved = true;
      root.style.top = `${clampOverlayTop(drag.startTop + dy)}px`;
    });
    const endDrag = (e) => {
      if (!drag || (e && e.pointerId !== drag.pointerId)) return;
      const wasDrag = drag.moved;
      if (wasDrag) saveOverlayTop(root.getBoundingClientRect().top);
      try {
        if (e) handle.releasePointerCapture(e.pointerId);
      } catch (_) {}
      drag = null;
      if (wasDrag && suppressClick) {
        handle.dataset.suppressClick = "1";
        setTimeout(() => {
          delete handle.dataset.suppressClick;
        }, 0);
      }
    };
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
  }

  function mountOverlay() {
    if (document.getElementById(OVERLAY_ID)) return;
    ensureStyle();
    const ui = loadOverlayUi();
    overlayCollapsed = ui.collapsed;
    overlayPageIndex = ui.pageIndex;
    overlayWidthMode = ui.widthMode || "slim";
    if (!localStorage.getItem(OVERLAY_UI_KEY)) {
      if (isGalleryPage()) {
        overlayPageIndex = OVERLAY_PAGES.findIndex((p) => p.id === "gallery");
        if (overlayPageIndex < 0) overlayPageIndex = 0;
      } else if (isSubscriptionsPage() || isGroupMembersPage() || isMemberProfilePage()) {
        overlayPageIndex = 0;
      }
    }

    const root = document.createElement("div");
    root.id = OVERLAY_ID;
    root.style.top = `${loadOverlayTop()}px`;
    root.innerHTML = `
      <button type="button" class="tbcc-chevron" title="TBCC Motherless · click to expand/collapse · drag">ML ▸</button>
      <div class="tbcc-panel">
        <div class="tbcc-head" title="Drag to reposition">
          <strong>TBCC Motherless</strong>
          <button type="button" class="tbcc-intel-badge" data-act="intel-open" title="Browse intel — click for settings">
            <span aria-hidden="true">▣</span><span data-ml-intel-count>0</span>
          </button>
          <button type="button" data-act="width" title="Cycle panel width">Width</button>
          <button type="button" data-act="collapse">Hide</button>
        </div>
        <div class="tbcc-tabs"></div>
        <div class="tbcc-body"></div>
        <div class="tbcc-foot">
          <button type="button" data-jump="top" title="Back to top">↑</button>
          <button type="button" data-act="prev">Prev</button>
          <span class="page-ind"></span>
          <button type="button" data-act="next">Next</button>
          <button type="button" data-jump="bottom" title="Back to bottom">↓</button>
        </div>
      </div>
    `;
    document.documentElement.appendChild(root);

    const tabs = root.querySelector(".tbcc-tabs");
    OVERLAY_PAGES.forEach((p, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = p.title;
      b.addEventListener("click", () => {
        overlayPageIndex = i;
        persistOverlayUi();
        renderOverlay();
      });
      tabs.appendChild(b);
    });

    const chevron = root.querySelector(".tbcc-chevron");
    bindVerticalDrag(root, chevron);
    bindVerticalDrag(root, root.querySelector(".tbcc-head"), {
      ignoreSelector: "button, a, input, select, textarea",
    });
    chevron.addEventListener("click", () => {
      if (chevron.dataset.suppressClick) return;
      setOverlayCollapsed(!overlayCollapsed);
    });
    root.querySelector('[data-act="collapse"]').addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setOverlayCollapsed(true);
    });
    root.querySelector('[data-act="width"]').addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      overlayWidthMode =
        overlayWidthMode === "slim" ? "normal" : overlayWidthMode === "normal" ? "wide" : "slim";
      syncOverlayCollapsed(root);
      persistOverlayUi();
    });
    root.querySelector('[data-act="intel-open"]')?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openIntelSettingsPanel();
    });
    root.querySelector('[data-act="prev"]').addEventListener("click", () => {
      overlayPageIndex = (overlayPageIndex + OVERLAY_PAGES.length - 1) % OVERLAY_PAGES.length;
      persistOverlayUi();
      renderOverlay();
    });
    root.querySelector('[data-act="next"]').addEventListener("click", () => {
      overlayPageIndex = (overlayPageIndex + 1) % OVERLAY_PAGES.length;
      persistOverlayUi();
      renderOverlay();
    });

    window.TBCCSuiteRail?.bindFootJumps(root);
    window.TBCCSuiteRail?.ensureStyles();
    syncOverlayCollapsed(root);
    renderOverlay();
  }

  function enforceDomCardBudget() {
    const api = typeof TbccMotherlessInfinite !== "undefined" ? TbccMotherlessInfinite : null;
    if (!api || !api.pruneOldestPages || !api.countThumbCards) return 0;
    const container =
      document.querySelector("#content .content-inner") ||
      document.querySelector(".content-inner") ||
      document.querySelector("#content");
    if (!container) return 0;
    const maxCards = api.resolveLimits(settings).maxCards;
    if (api.countThumbCards(container) <= maxCards) return 0;
    return api.pruneOldestPages(container, maxCards);
  }

  function observeDom() {
    let bindTimer = null;
    let intelTimer = null;
    const mo = new MutationObserver((mutations) => {
      // Ignore our own overlay / picker chrome — those fire constantly while the panel is open.
      if (
        mutations &&
        mutations.length &&
        mutations.every((m) => {
          const t = m.target;
          return (
            t &&
            (t.id === OVERLAY_ID ||
              t.id === "tbcc-ml-toast" ||
              t.closest?.(`#${OVERLAY_ID}`) ||
              t.closest?.(".tbcc-ml-shout-pop") ||
              t.closest?.(".tbcc-ml-thumb-actions"))
          );
        })
      ) {
        return;
      }
      clearTimeout(bindTimer);
      bindTimer = setTimeout(() => {
        bindThumbActions(document);
        try {
          enforceDomCardBudget();
        } catch (_) {}
      }, 600);
      if (loadIntelMeta().recordIntel === false) return;
      clearTimeout(intelTimer);
      intelTimer = setTimeout(() => {
        try {
          scanGridIntel();
        } catch (_) {}
      }, 2200);
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }

  function setupInfiniteScroll() {
    const api = typeof TbccMotherlessInfinite !== "undefined" ? TbccMotherlessInfinite : null;
    if (!api || !api.MotherlessInfiniteEngine) {
      console.warn("[TBCC ML] motherless-infinite-scroll.js missing");
      return;
    }
    if (!api.pageAllowsInfiniteScroll(location.pathname || "/")) return;

    infiniteEngine = new api.MotherlessInfiniteEngine({
      getSettings: () => settings,
      getHref: () => location.href,
      getPathname: () => location.pathname || "/",
      getContainer: () =>
        document.querySelector("#content .content-inner") ||
        document.querySelector(".content-inner") ||
        document.querySelector("#content"),
      isHidden: () => document.visibilityState === "hidden",
      onStatus: (text) => {
        infiniteStatusText = String(text || "");
        const el = document.querySelector(`#${OVERLAY_ID} .tbcc-status`);
        if (el) el.textContent = infiniteStatusText;
      },
      onPageAppended: () => {
        try {
          bindThumbActions(document);
          applyThumbKeywordFilters();
          enforceDomCardBudget();
          if (loadIntelMeta().recordIntel !== false) scanGridIntel();
        } catch (_) {}
      },
    });
    infiniteEngine.resetForSetup(api.currentPageFromUrl(location.href));

    window.addEventListener(
      "scroll",
      () => {
        // Mass-friend already hammers the network — don't also append infinite-scroll pages.
        if (friendMassActive) return;
        if (!settings.infiniteScroll || scrollLocked || !infiniteEngine) return;
        if (document.visibilityState === "hidden") return;
        if (window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 700) return;
        scrollLocked = true;
        const cooldown = api.resolveLimits(settings).cooldownMs;
        infiniteEngine
          .loadNextPage()
          .catch(() => {})
          .finally(() => setTimeout(() => (scrollLocked = false), cooldown));
      },
      { passive: true }
    );
  }

  function start() {
    ensureStyle();
    window.TBCCSuiteRail?.ensureStyles();
    // Heal pre-fix intel bloat (5k rows + per-thumb rewrite) left by earlier browse-intel update.
    try {
      const meta = loadIntelMeta();
      if (Number(meta.maxIntelRows) > 2500) {
        saveIntelMeta({ ...meta, maxIntelRows: 1500 });
      }
      const existing = loadIntelRows();
      if (existing.length > 1500) {
        resetIntelMemoryCache();
        saveIntelRows(existing.slice(-1500), { skipAutoPush: true });
      }
    } catch (_) {}
    mountOverlay();
    mountMotherlessKeywordBar();
    bindThumbActions(document);
    applyThumbKeywordFilters();
    observeDom();
    setupInfiniteScroll();
    setupMemberListScan();
    try {
      if (loadIntelMeta().recordIntel !== false) scanGridIntel();
    } catch (_) {}
    try {
      if (globalThis.tbccBrowseIntel && typeof globalThis.tbccBrowseIntel.flushIfAtCap === "function") {
        globalThis.tbccBrowseIntel.flushIfAtCap({
          rows: loadIntelRows(),
          meta: loadIntelMeta(),
          applyTrimmed: (stored) => {
            intelRowsCache = Array.isArray(stored) ? stored : [];
            try {
              localStorage.setItem(INTEL_ROWS_KEY, JSON.stringify(intelRowsCache));
            } catch (_) {}
          },
          toast: (msg) => {
            try {
              toast(msg);
            } catch (_) {}
          },
        });
      }
    } catch (_) {}
  }

  function teardown() {
    friendAbort = true;
    infiniteEngine = null;
    document.getElementById(OVERLAY_ID)?.remove();
    document.getElementById(JUMP_STACK_ID)?.remove();
    document.getElementById("tbcc-ml-kw-bar")?.remove();
    document.getElementById("tbcc-ml-style")?.remove();
    document.getElementById("tbcc-ml-toast")?.remove();
    document.querySelectorAll(".tbcc-ml-thumb-actions").forEach((n) => n.remove());
    document.querySelectorAll(".tbcc-ml-infinite-page, .tbcc-ml-page-sep").forEach((n) => n.remove());
    document.querySelectorAll(".tbcc-suite-kw-filtered").forEach((n) => n.classList.remove("tbcc-suite-kw-filtered"));
  }

  if (typeof tbccWaitForModule === "function") {
    tbccWaitForModule(MODULE_ID, start);
    if (typeof tbccBindModuleDisableListener === "function") {
      tbccBindModuleDisableListener(MODULE_ID, teardown);
    }
  } else {
    start();
  }
})();
