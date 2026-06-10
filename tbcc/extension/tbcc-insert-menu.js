/**
 * Destination-panel Insert dropdown (promo links, captions, channel invites, ASCII, emoji).
 * Mirrors dashboard TbccInsertMenu for the extension gallery caption field.
 */
(function (global) {
  const API_BASE = "http://localhost:8000";

  function promoInsertUrl(r) {
    const s = String((r && r.short_url) || "").trim();
    return s || String((r && r.url) || "").trim();
  }

  function captionSnippetLabel(s) {
    const title = String((s && s.title) || "").trim();
    if (title) return title;
    const body = String((s && s.body) || "");
    const line = body.split(/\r?\n/).find((l) => l.trim());
    return line ? line.slice(0, 48) : "Untitled";
  }

  function emojiPresetLabel(p) {
    const t = String((p && p.title) || "").trim() || "Preset #" + (p && p.id);
    const n = String((p && p.html_fragment) || "").match(/<tg-emoji/gi);
    return n && n.length ? t + " (" + n.length + " emoji)" : t;
  }

  function ensureStyles() {
    if (document.getElementById("tbcc-insert-menu-styles")) return;
    const style = document.createElement("style");
    style.id = "tbcc-insert-menu-styles";
    style.textContent =
      ".tbcc-insert-menu{position:relative;display:inline-block}" +
      ".tbcc-insert-menu__btn{font-size:11px;background:var(--tbcc-bg-elevated,#313244);border:1px solid var(--tbcc-border,#45475a);" +
      "border-radius:6px;padding:4px 8px;color:var(--tbcc-accent,#89dceb);cursor:pointer;white-space:nowrap}" +
      ".tbcc-insert-menu__btn:hover{background:var(--tbcc-bg-muted,#45475a)}" +
      ".tbcc-insert-menu__btn:disabled{opacity:.4;cursor:not-allowed}" +
      ".tbcc-insert-menu__panel{position:absolute;right:0;top:calc(100% + 4px);z-index:130;width:min(100vw - 1.5rem,20rem);" +
      "max-height:min(70vh,22rem);overflow-y:auto;border-radius:8px;border:1px solid var(--tbcc-border,#45475a);" +
      "background:var(--tbcc-bg-base,#1e1e2e);box-shadow:0 8px 28px rgba(0,0,0,.45);padding:4px 0}" +
      ".tbcc-insert-menu__section{border-top:1px solid rgba(255,255,255,.08);margin-top:4px;padding-top:4px}" +
      ".tbcc-insert-menu__section:first-child{border-top:none;margin-top:0;padding-top:0}" +
      ".tbcc-insert-menu__head{padding:4px 8px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--tbcc-text-muted,#94a3b8)}" +
      ".tbcc-insert-menu__item{display:block;width:100%;text-align:left;padding:6px 8px;font-size:11px;color:var(--tbcc-text-primary,#cdd6f4);" +
      "background:transparent;border:none;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
      ".tbcc-insert-menu__item:hover{background:rgba(255,255,255,.08)}" +
      ".tbcc-insert-menu__empty{padding:8px;font-size:11px;color:var(--tbcc-text-muted,#94a3b8)}" +
      ".tbcc-insert-menu__promo-add{padding:6px 8px;display:flex;flex-direction:column;gap:4px}" +
      ".tbcc-insert-menu__promo-add input{font-size:11px;padding:4px 6px;border-radius:4px;border:1px solid var(--tbcc-border,#45475a);" +
      "background:var(--tbcc-bg-elevated,#313244);color:var(--tbcc-text-primary,#cdd6f4)}" +
      ".tbcc-insert-menu__promo-add button{font-size:11px;padding:4px 8px;border-radius:4px;border:none;background:var(--tbcc-accent-dim,#45475a);color:var(--tbcc-text-primary,#cdd6f4);cursor:pointer}";
    document.head.appendChild(style);
  }

  async function fetchJson(path) {
    try {
      const r = await fetch(API_BASE + path, { cache: "no-store" });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  async function fetchArchiveInsertItems(limit) {
    const cap = Math.min(Number(limit) || 200, 500);
    const primary = await fetchJson("/archive/entries/insert-menu?limit=" + cap);
    if (primary && Array.isArray(primary.items)) return primary.items;
    const items = [];
    for (let page = 1; page <= 5 && items.length < cap; page++) {
      const list = await fetchJson(
        "/archive/entries?kind=url&page=" + page + "&page_size=100&include_media=false"
      );
      if (!list || !Array.isArray(list.items)) break;
      for (const e of list.items) {
        if (e.kind !== "url") continue;
        if (e.status && e.status !== "approved") continue;
        const label = String(e.description || e.summary || e.value || "").trim();
        items.push({
          id: e.id,
          url: e.value,
          label: label.slice(0, 80),
          description: e.description || e.summary || "",
          tags: e.tags || "",
        });
        if (items.length >= cap) break;
      }
      if (page >= (list.total_pages || 1)) break;
    }
    return items;
  }

  function TbccInsertMenu(mountEl, opts) {
    if (!mountEl) return null;
    ensureStyles();
    const onInsert = (opts && opts.onInsert) || global.tbccInsertIntoCaption;
    const getChannels = (opts && opts.getChannels) || (() => []);
    const getPools = (opts && opts.getPools) || (() => []);

    const root = document.createElement("div");
    root.className = "tbcc-insert-menu";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tbcc-insert-menu__btn";
    btn.textContent = (opts && opts.buttonLabel) || "Insert…";
    btn.title = "Insert channel link, promo URL, archive link, caption, ASCII art, or emoji banner at cursor";
    btn.setAttribute("aria-haspopup", "listbox");
    root.appendChild(btn);
    mountEl.appendChild(root);

    let open = false;
    let panel = null;
    let cache = null;

    function close() {
      open = false;
      btn.setAttribute("aria-expanded", "false");
      if (panel) {
        panel.remove();
        panel = null;
      }
    }

    function pick(text) {
      const chunk = String(text || "").trim();
      if (!chunk) return;
      if (typeof onInsert === "function") onInsert(chunk);
      else if (global.tbccInsertIntoCaption) global.tbccInsertIntoCaption(chunk);
      close();
    }

    function section(title, bordered) {
      const sec = document.createElement("div");
      sec.className = "tbcc-insert-menu__section" + (bordered ? "" : "");
      const head = document.createElement("div");
      head.className = "tbcc-insert-menu__head";
      head.textContent = title;
      sec.appendChild(head);
      return sec;
    }

    function item(label, title, text) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tbcc-insert-menu__item";
      b.textContent = label;
      if (title) b.title = title;
      b.addEventListener("click", () => pick(text));
      return b;
    }

    async function loadData() {
      if (cache) return cache;
      const [promos, snippets, asciiWrap, presets, archiveItems, channels, pools] = await Promise.all([
        fetchJson("/promo-affiliate-links/?sort=priority_asc&active_only=true"),
        fetchJson("/caption-snippets/"),
        fetchJson("/listening-relay-settings/ascii-art"),
        fetchJson("/telegram-custom-emoji/presets"),
        fetchArchiveInsertItems(200),
        Promise.resolve(getChannels()),
        Promise.resolve(getPools()),
      ]);
      const channelIdsWithPools = new Set();
      (Array.isArray(pools) ? pools : []).forEach((p) => {
        const cid = Number(p.channel_id);
        if (Number.isFinite(cid) && cid > 0) channelIdsWithPools.add(cid);
      });
      const poolChannels = (Array.isArray(channels) ? channels : []).filter((c) => {
        const id = Number(c.id);
        const link = String(c.invite_link || "").trim();
        return link && channelIdsWithPools.has(id);
      });
      cache = {
        promos: Array.isArray(promos) ? promos : [],
        snippets: Array.isArray(snippets) ? snippets : [],
        ascii: asciiWrap && Array.isArray(asciiWrap.entries) ? asciiWrap.entries : [],
        presets: Array.isArray(presets) ? presets : [],
        archive: Array.isArray(archiveItems) ? archiveItems : [],
        poolChannels,
      };
      return cache;
    }

    function renderPromoAddForm(sec, onAdded) {
      const wrap = document.createElement("div");
      wrap.className = "tbcc-insert-menu__promo-add";
      const titleIn = document.createElement("input");
      titleIn.type = "text";
      titleIn.placeholder = "Promo title";
      titleIn.maxLength = 80;
      const urlIn = document.createElement("input");
      urlIn.type = "url";
      urlIn.placeholder = "https://…";
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.textContent = "Add promo link";
      addBtn.addEventListener("click", async () => {
        const label = titleIn.value.trim();
        const url = urlIn.value.trim();
        if (!label || !url) return;
        addBtn.disabled = true;
        try {
          const r = await fetch(API_BASE + "/promo-affiliate-links/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label, url, active: true }),
          });
          if (!r.ok) throw new Error(await r.text());
          cache = null;
          titleIn.value = "";
          urlIn.value = "";
          if (typeof onAdded === "function") onAdded();
          if (global.showToast) global.showToast("Promo link saved.", "success");
        } catch (e) {
          if (global.showToast) global.showToast("Could not save promo: " + (e.message || String(e)), "error");
        } finally {
          addBtn.disabled = false;
        }
      });
      wrap.appendChild(titleIn);
      wrap.appendChild(urlIn);
      wrap.appendChild(addBtn);
      sec.appendChild(wrap);
    }

    async function renderPanel() {
      close();
      open = true;
      btn.setAttribute("aria-expanded", "true");
      panel = document.createElement("div");
      panel.className = "tbcc-insert-menu__panel";
      panel.setAttribute("role", "listbox");
      root.appendChild(panel);

      const loading = document.createElement("p");
      loading.className = "tbcc-insert-menu__empty";
      loading.textContent = "Loading…";
      panel.appendChild(loading);

      const data = await loadData();
      panel.innerHTML = "";
      let bordered = false;

      if (data.poolChannels.length) {
        const sec = section("Channel invites", bordered);
        bordered = true;
        data.poolChannels.forEach((c) => {
          const link = String(c.invite_link || "").trim();
          const lab = String(c.name || c.identifier || "#" + c.id);
          sec.appendChild(item(lab, "Insert invite link for " + lab, link));
        });
        panel.appendChild(sec);
      }

      const promoSec = section("Promo links", bordered);
      bordered = true;
      renderPromoAddForm(promoSec, () => {
        cache = null;
        void renderPanel();
      });
      if (data.promos.length) {
        const listWrap = document.createElement("div");
        data.promos.forEach((r) => {
          listWrap.appendChild(item(r.label, promoInsertUrl(r), promoInsertUrl(r)));
        });
        promoSec.appendChild(listWrap);
      } else {
        const empty = document.createElement("p");
        empty.className = "tbcc-insert-menu__empty";
        empty.textContent = "No saved promo links yet.";
        promoSec.appendChild(empty);
      }
      panel.appendChild(promoSec);

      if (data.archive.length) {
        const sec = section("Archive links", bordered);
        bordered = true;
        data.archive.forEach((r) => {
          const label = String(r.label || r.description || "").trim() || String(r.url || "").slice(0, 56);
          const title = [r.description || r.label, r.tags ? "tags: " + r.tags : "", r.url].filter(Boolean).join(" · ");
          sec.appendChild(item(label, title, r.url));
        });
        panel.appendChild(sec);
      }

      if (data.snippets.length) {
        const sec = section("Captions", bordered);
        bordered = true;
        data.snippets.forEach((s) => {
          sec.appendChild(item(captionSnippetLabel(s), String(s.body || "").slice(0, 120), s.body));
        });
        panel.appendChild(sec);
      }

      if (data.ascii.length) {
        const sec = section("ASCII art", bordered);
        bordered = true;
        data.ascii.forEach((e) => {
          sec.appendChild(item(e.name || "Untitled", String(e.content || "").slice(0, 120), e.content));
        });
        panel.appendChild(sec);
      }

      if (data.presets.length) {
        const sec = section("Emoji banners", bordered);
        data.presets.forEach((p) => {
          sec.appendChild(item(emojiPresetLabel(p), "", String(p.html_fragment || "").trim()));
        });
        panel.appendChild(sec);
      }

      if (!bordered) {
        const empty = document.createElement("p");
        empty.className = "tbcc-insert-menu__empty";
        empty.textContent = "Nothing saved yet. Add a promo link above or use Dashboard → Misc libraries.";
        panel.appendChild(empty);
      }
    }

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (open) close();
      else void renderPanel();
    });

    document.addEventListener("mousedown", (e) => {
      if (!open) return;
      if (!root.contains(e.target)) close();
    });

    return { close, invalidateCache: () => { cache = null; } };
  }

  global.TbccInsertMenu = TbccInsertMenu;
})(typeof window !== "undefined" ? window : self);
