/**
 * Paginated archive/inbox list UI (100 rows per page). Shared by gallery + options.
 */
(function (global) {
  const Arch = () => global.TbccMasterArchive;

  function copyTextToClipboard(text) {
    const s = String(text || "");
    if (!s) return Promise.resolve(false);
    const clip = global.TbccClipboard;
    if (clip && clip.copyText) {
      return clip.copyText(s).then((ok) => !!ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(s).then(() => true).catch(() => false);
    }
    return Promise.resolve(false);
  }

  /**
   * @param {object} opts
   * @param {HTMLElement} opts.listEl
   * @param {HTMLElement} [opts.statusEl]
   * @param {HTMLElement} [opts.pagerEl]
   * @param {() => Promise<object[]>} opts.getEntries
   * @param {() => { q: string, kind: string }} opts.getFilters
   * @param {'master'|'readonly'} [opts.mode]
   * @param {(entry: object) => Promise<void>} [opts.onAddToInbox]
   */
  function createArchiveListController(opts) {
    const pageSize = (opts && opts.pageSize) || Arch().PAGE_SIZE || 100;
    let pageIndex = 0;
    /** @type {Set<string>} */
    let selectedKeys = new Set();

    function defaultSelectPage(slice) {
      selectedKeys = new Set();
      for (const e of slice) {
        if (e.kind === "url") selectedKeys.add(Arch().entryKey(e));
      }
    }

    function renderPager(pager, pag) {
      if (!pager) return;
      pager.innerHTML = "";
      if (pag.total <= pageSize) {
        pager.hidden = true;
        return;
      }
      pager.hidden = false;
      const prev = document.createElement("button");
      prev.type = "button";
      prev.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
      prev.textContent = "← Prev";
      prev.disabled = pag.page <= 0;
      prev.addEventListener("click", () => {
        pageIndex = Math.max(0, pag.page - 1);
        void refresh();
      });
      const label = document.createElement("span");
      label.className = "tbcc-archive-pager__label";
      label.textContent = `Page ${pag.page + 1} / ${pag.totalPages} (${pag.total} total)`;
      const next = document.createElement("button");
      next.type = "button";
      next.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
      next.textContent = "Next →";
      next.disabled = pag.page >= pag.totalPages - 1;
      next.addEventListener("click", () => {
        pageIndex = Math.min(pag.totalPages - 1, pag.page + 1);
        void refresh();
      });
      pager.appendChild(prev);
      pager.appendChild(label);
      pager.appendChild(next);
    }

    function renderRow(e, listEl) {
      const item = document.createElement("div");
      item.className = "master-archive-row saved-url-inbox-row";
      item.setAttribute("role", "listitem");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "saved-url-inbox-check tbcc-archive-row-check";
      cb.dataset.archiveKey = Arch().entryKey(e);
      if (e.kind === "url") {
        cb.checked = selectedKeys.has(Arch().entryKey(e));
        cb.addEventListener("change", () => {
          const k = Arch().entryKey(e);
          if (cb.checked) selectedKeys.add(k);
          else selectedKeys.delete(k);
        });
      } else {
        cb.disabled = true;
        cb.title = "Usernames copy as @handle from export";
      }

      const body = document.createElement("div");
      body.className = "saved-url-inbox-row__body";

      const head = document.createElement("div");
      head.className = "tbcc-archive-row-head";
      const kindEl = document.createElement("span");
      kindEl.className = "master-archive-row__kind";
      kindEl.textContent = e.url_class || e.kind;
      if (e.route_hint) kindEl.title = e.route_hint;
      head.appendChild(kindEl);

      const valWrap = document.createElement("div");
      valWrap.className = "master-archive-row__value";
      if (e.kind === "url") {
        const link = document.createElement("a");
        link.href = e.value;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.className = "saved-url-inbox-url";
        link.textContent = e.value;
        valWrap.appendChild(link);
      } else {
        valWrap.textContent = "@" + e.value;
      }
      head.appendChild(valWrap);
      body.appendChild(head);

      const summaryText =
        (e.description && String(e.description).trim()) ||
        (e.summary && String(e.summary).trim()) ||
        (e.kind === "url" && e.note && !String(e.note).startsWith("ref:") ? String(e.note).trim() : "");
      if (summaryText) {
        const sum = document.createElement("div");
        sum.className = "tbcc-archive-row-summary";
        sum.textContent = summaryText;
        body.appendChild(sum);
      } else if (e.route_hint) {
        const hint = document.createElement("div");
        hint.className = "tbcc-archive-row-summary";
        hint.textContent = e.route_hint;
        body.appendChild(hint);
      }
      const meta = document.createElement("div");
      meta.className = "saved-url-inbox-meta";
      meta.textContent = Arch().formatEntryMeta(e);
      body.appendChild(meta);

      if (opts.mode === "master" && e.kind === "url" && opts.onAddToInbox) {
        const rowAct = document.createElement("div");
        rowAct.className = "tbcc-archive-row-actions";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
        btn.textContent = "→ Inbox";
        btn.addEventListener("click", () => void opts.onAddToInbox(e));
        rowAct.appendChild(btn);
        body.appendChild(rowAct);
      }

      item.appendChild(cb);
      item.appendChild(body);
      listEl.appendChild(item);
    }

    async function refresh() {
      const listEl = opts.listEl;
      const statusEl = opts.statusEl;
      if (!listEl || !Arch()) return { pag: null, filtered: [] };
      const all = await opts.getEntries();
      const filters = opts.getFilters ? opts.getFilters() : { q: "", kind: "" };
      const filtered = Arch().filterEntries(all, filters);
      const pag = Arch().paginateEntries(filtered, pageIndex, pageSize);
      pageIndex = pag.page;

      listEl.innerHTML = "";
      if (!pag.slice.length) {
        const empty = document.createElement("p");
        empty.className = "saved-url-inbox-empty";
        empty.textContent = filters.q || filters.kind
          ? "No matching entries."
          : "Archive empty.";
        listEl.appendChild(empty);
        if (statusEl) {
          statusEl.textContent = pag.total
            ? `${pag.total} matching — none on this page.`
            : "";
        }
        renderPager(opts.pagerEl, pag);
        selectedKeys = new Set();
        return { pag, filtered };
      }

      defaultSelectPage(pag.slice);
      for (const e of pag.slice) renderRow(e, listEl);
      renderPager(opts.pagerEl, pag);

      const urlOnPage = pag.slice.filter((e) => e.kind === "url").length;
      if (statusEl) {
        let msg = `${pag.total} entr${pag.total === 1 ? "y" : "ies"}`;
        if (pag.totalPages > 1) {
          msg += ` · showing ${pag.slice.length} on page ${pag.page + 1}/${pag.totalPages}`;
        }
        msg += ` · ${urlOnPage} URL(s) on page (copy uses checked rows only)`;
        if (pag.total > pageSize) {
          msg += " · export for full list";
        }
        statusEl.textContent = msg;
      }
      return { pag, filtered };
    }

    function resetPage() {
      pageIndex = 0;
    }

    function selectAllOnPage() {
      const checks = opts.listEl
        ? opts.listEl.querySelectorAll(".tbcc-archive-row-check:not(:disabled)")
        : [];
      checks.forEach((cb) => {
        cb.checked = true;
        const k = cb.dataset.archiveKey;
        if (k) selectedKeys.add(k);
      });
    }

    function deselectAllOnPage() {
      const checks = opts.listEl
        ? opts.listEl.querySelectorAll(".tbcc-archive-row-check")
        : [];
      checks.forEach((cb) => {
        cb.checked = false;
      });
      selectedKeys = new Set();
    }

    async function copyCheckedUrlsOnPage() {
      const all = await opts.getEntries();
      const filters = opts.getFilters ? opts.getFilters() : { q: "", kind: "" };
      const filtered = Arch().filterEntries(all, filters);
      const pag = Arch().paginateEntries(filtered, pageIndex, pageSize);
      const lines = Arch().entriesToUrlLines(pag.slice, selectedKeys);
      if (!lines.length) {
        return { ok: false, error: "No URLs selected on this page." };
      }
      const ok = await copyTextToClipboard(lines.join("\n"));
      return ok
        ? { ok: true, count: lines.length }
        : { ok: false, error: "Clipboard failed." };
    }

    return {
      refresh,
      resetPage,
      selectAllOnPage,
      deselectAllOnPage,
      copyCheckedUrlsOnPage,
      getSelectedKeys: () => selectedKeys,
    };
  }

  global.TbccArchiveListUi = {
    PAGE_SIZE_DEFAULT: 100,
    createArchiveListController,
    copyTextToClipboard,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
