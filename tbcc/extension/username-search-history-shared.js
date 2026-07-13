/**
 * Username search history helpers — source detection + badge labels.
 * Used by options page, background (via importScripts), and content overlay.
 */
(function (root) {
  const STORAGE_MODEL_SEARCH_HISTORY = "tbccModelSearchHistory";
  const HISTORY_CAP = 200;

  /** @type {Array<{ id: string, label: string, short: string, hosts: string[] }>} */
  const SOURCE_DEFS = [
    { id: "stripchat", label: "Stripchat", short: "SC", hosts: ["stripchat.com", "xhamsterlive.com", "instantfapcams.com"] },
    { id: "chaturbate", label: "Chaturbate", short: "CB", hosts: ["chaturbate.com"] },
    { id: "onlyfans", label: "OnlyFans", short: "OF", hosts: ["onlyfans.com"] },
    { id: "fansly", label: "Fansly", short: "FY", hosts: ["fansly.com"] },
    { id: "instagram", label: "Instagram", short: "IG", hosts: ["instagram.com"] },
    { id: "x", label: "X / Twitter", short: "X", hosts: ["x.com", "twitter.com"] },
    { id: "reddit", label: "Reddit", short: "RD", hosts: ["reddit.com"] },
    { id: "erome", label: "Erome", short: "ER", hosts: ["erome.com"] },
    { id: "cambb", label: "Cambb", short: "CM", hosts: ["cambb.xxx", "nudecams.xxx"] },
    { id: "model_search", label: "Model search", short: "MS", hosts: [] },
    { id: "macro", label: "Macro search", short: "MC", hosts: [] },
    { id: "overlay", label: "Overlay", short: "OV", hosts: [] },
    { id: "unknown", label: "Unknown", short: "?", hosts: [] },
  ];

  const BY_ID = Object.create(null);
  for (const d of SOURCE_DEFS) BY_ID[d.id] = d;

  function hostFromUrl(url) {
    try {
      return new URL(String(url || "")).hostname.toLowerCase().replace(/^www\./, "");
    } catch (_) {
      return "";
    }
  }

  function inferUsernameSearchSourceFromUrl(urlOrHost) {
    const raw = String(urlOrHost || "").trim().toLowerCase();
    if (!raw) return "unknown";
    if (BY_ID[raw]) return raw;
    const host = raw.includes("://") || raw.includes("/") ? hostFromUrl(raw) : raw.replace(/^www\./, "");
    if (!host) return "unknown";
    for (const d of SOURCE_DEFS) {
      for (const h of d.hosts) {
        if (host === h || host.endsWith("." + h)) return d.id;
      }
    }
    return "unknown";
  }

  function normalizeUsernameSearchSource(raw) {
    const s = String(raw || "").trim().toLowerCase();
    if (!s) return "unknown";
    if (BY_ID[s]) return s;
    return inferUsernameSearchSourceFromUrl(s);
  }

  function usernameSearchSourceMeta(id) {
    const n = normalizeUsernameSearchSource(id);
    return BY_ID[n] || BY_ID.unknown;
  }

  function appendUsernameSearchSourceBadge(parent, sourceId) {
    if (!parent) return null;
    const meta = usernameSearchSourceMeta(sourceId);
    const badge = document.createElement("span");
    badge.className = "tbcc-ush-source tbcc-ush-source--" + meta.id;
    badge.setAttribute("title", meta.label);
    badge.setAttribute("aria-label", meta.label);
    badge.textContent = meta.short;
    parent.appendChild(badge);
    return badge;
  }

  /**
   * Guess profile username from current page URL (cam / fan sites).
   */
  function guessUsernameFromLocation(href) {
    try {
      const u = new URL(String(href || (typeof location !== "undefined" ? location.href : "") || ""));
      const host = u.hostname.toLowerCase().replace(/^www\./, "");
      const segs = u.pathname
        .split("/")
        .map((x) => {
          try {
            return decodeURIComponent(x || "").trim();
          } catch (_) {
            return String(x || "").trim();
          }
        })
        .filter(Boolean);

      if (host === "chaturbate.com" || host.endsWith(".chaturbate.com")) {
        const skip = new Set(["p", "b", "followed", "tags", "accounts", "tipping", "private_shows", "discover"]);
        for (const seg of segs) {
          if (skip.has(seg.toLowerCase())) continue;
          if (/^[a-zA-Z0-9_-]{2,64}$/.test(seg)) return seg;
        }
      }
      if (
        host === "stripchat.com" ||
        host.endsWith(".stripchat.com") ||
        host === "xhamsterlive.com" ||
        host === "instantfapcams.com"
      ) {
        for (const seg of segs) {
          if (/^(tags|search|models|girls|couples|men|trans|categories)$/i.test(seg)) continue;
          if (/^[a-zA-Z0-9_.-]{2,64}$/.test(seg)) return seg;
        }
      }
      if (host === "onlyfans.com" || host.endsWith(".onlyfans.com") || host === "fansly.com") {
        for (const seg of segs) {
          if (/^(posts|media|videos|photos|chats|collections|settings|my)$/i.test(seg)) continue;
          if (/^[a-zA-Z0-9_.-]{2,64}$/.test(seg)) return seg;
        }
      }
      if (host === "instagram.com") {
        for (const seg of segs) {
          if (/^(p|reel|reels|stories|explore|accounts|direct)$/i.test(seg)) continue;
          if (/^[a-zA-Z0-9._]{2,64}$/.test(seg)) return seg;
        }
      }
      if (host === "x.com" || host === "twitter.com") {
        for (const seg of segs) {
          if (/^(home|explore|search|i|settings|messages|notifications|compose|intent)$/i.test(seg)) continue;
          if (/^[a-zA-Z0-9_]{1,15}$/.test(seg)) return seg;
        }
      }
      if (host.includes("cambb") || host.includes("nudecams")) {
        const idx = segs.findIndex((s) => /^(stripchat|chaturbate)$/i.test(s));
        if (idx >= 0 && segs[idx + 1]) return segs[idx + 1];
      }
    } catch (_) {}
    return "";
  }

  root.TbccUsernameSearchHistory = {
    STORAGE_KEY: STORAGE_MODEL_SEARCH_HISTORY,
    HISTORY_CAP,
    SOURCE_DEFS,
    inferUsernameSearchSourceFromUrl,
    normalizeUsernameSearchSource,
    usernameSearchSourceMeta,
    appendUsernameSearchSourceBadge,
    guessUsernameFromLocation,
  };
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
