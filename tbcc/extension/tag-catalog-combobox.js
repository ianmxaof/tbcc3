/**
 * Searchable tag catalog combobox (vanilla). Used by gallery import settings.
 * Keyboard: Tab = accept ghost completion, ↑↓ = highlight, Enter = pick, Esc = close.
 */
(function (global) {
  function tagPickerLabel(t) {
    const name = t.name != null && String(t.name).trim() ? String(t.name).trim() : "";
    const slug = t.slug != null && String(t.slug).trim() ? String(t.slug).trim() : "";
    return name || slug;
  }

  function searchCatalogTags(rows, query, limit) {
    const cap = limit || 48;
    const q = String(query || "").trim().toLowerCase();
    if (!q) return { items: rows.slice(0, cap), prefixLabel: null };
    const scored = [];
    for (const row of rows) {
      const label = tagPickerLabel(row);
      if (!label) continue;
      const low = label.toLowerCase();
      const slugLow = (row.slug && String(row.slug).toLowerCase()) || "";
      let score = -1;
      if (low.startsWith(q)) score = 1000 - low.length;
      else if (slugLow.startsWith(q)) score = 900 - slugLow.length;
      else if (low.includes(q)) score = 500 - low.indexOf(q);
      else if (slugLow.includes(q)) score = 400 - slugLow.indexOf(q);
      if (score >= 0) scored.push({ row, score, label });
    }
    scored.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label, undefined, { sensitivity: "base" }));
    const top = scored[0];
    const prefixLabel = top && top.label.toLowerCase().startsWith(q) ? top.label : null;
    return { items: scored.slice(0, cap).map((s) => s.row), prefixLabel };
  }

  function autocompleteRemainder(query, fullLabel) {
    const q = String(query || "").trim();
    if (!q || !fullLabel) return "";
    if (!fullLabel.toLowerCase().startsWith(q.toLowerCase())) return "";
    return fullLabel.slice(q.length);
  }

  /**
   * @param {HTMLElement} mount
   * @param {{ placeholder?: string, onPick: (label: string, row: object) => void, className?: string }} opts
   */
  function createTagCatalogCombobox(mount, opts) {
    const onPick = opts.onPick;
    let rows = [];
    let query = "";
    let open = false;
    let highlight = 0;

    const root = document.createElement("div");
    root.className = "tag-catalog-combobox" + (opts.className ? " " + opts.className : "");

    const inputWrap = document.createElement("div");
    inputWrap.className = "tag-catalog-combobox__input-wrap";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "tag-catalog-combobox__input";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = opts.placeholder || "Search catalog…";
    input.title = "Type to search; Tab completes; ↑↓ highlight; Enter to add tag";

    const ghost = document.createElement("span");
    ghost.className = "tag-catalog-combobox__ghost";
    ghost.setAttribute("aria-hidden", "true");
    const ghostTyped = document.createElement("span");
    ghostTyped.className = "tag-catalog-combobox__ghost-typed";
    const ghostSuffix = document.createElement("span");
    ghostSuffix.className = "tag-catalog-combobox__ghost-suffix";
    ghost.appendChild(ghostTyped);
    ghost.appendChild(ghostSuffix);

    const list = document.createElement("ul");
    list.className = "tag-catalog-combobox__list";
    list.setAttribute("role", "listbox");
    list.hidden = true;

    inputWrap.appendChild(input);
    inputWrap.appendChild(ghost);
    root.appendChild(inputWrap);
    root.appendChild(list);
    mount.replaceChildren(root);

    function sortedRows() {
      return [...rows].sort((a, b) =>
        tagPickerLabel(a).localeCompare(tagPickerLabel(b), undefined, { sensitivity: "base" })
      );
    }

    function renderList() {
      const { items, prefixLabel } = searchCatalogTags(sortedRows(), open ? query : "", 48);
      const suffix = open && query.trim() && prefixLabel ? autocompleteRemainder(query, prefixLabel) : "";
      ghostTyped.textContent = input.value;
      ghostSuffix.textContent = suffix;
      ghost.hidden = !suffix;

      list.innerHTML = "";
      if (!open) {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        return;
      }
      list.hidden = items.length === 0 && !query.trim();
      input.setAttribute("aria-expanded", list.hidden ? "false" : "true");

      items.forEach((row, i) => {
        const label = tagPickerLabel(row);
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tag-catalog-combobox__option" + (i === highlight ? " is-active" : "");
        btn.textContent = label;
        if (row.slug && label.toLowerCase() !== String(row.slug).toLowerCase()) {
          const sub = document.createElement("span");
          sub.className = "tag-catalog-combobox__option-slug";
          sub.textContent = row.slug;
          btn.appendChild(sub);
        }
        btn.addEventListener("mousedown", (e) => e.preventDefault());
        btn.addEventListener("click", () => commit(row));
        btn.addEventListener("mouseenter", () => {
          highlight = i;
          renderList();
        });
        li.appendChild(btn);
        list.appendChild(li);
      });
      if (items.length === 0 && query.trim()) {
        const li = document.createElement("li");
        li.className = "tag-catalog-combobox__empty";
        li.textContent = "No matching tags";
        list.appendChild(li);
      }
    }

    function commit(row) {
      const label = tagPickerLabel(row);
      if (!label) return;
      onPick(label, row);
      query = "";
      input.value = "";
      open = false;
      highlight = 0;
      renderList();
      input.focus();
    }

    input.addEventListener("input", () => {
      query = input.value;
      open = true;
      highlight = 0;
      renderList();
    });

    input.addEventListener("focus", () => {
      open = true;
      renderList();
    });

    input.addEventListener("keydown", (e) => {
      const { items, prefixLabel } = searchCatalogTags(sortedRows(), query, 48);
      const suffix = prefixLabel ? autocompleteRemainder(query, prefixLabel) : "";
      if (e.key === "Tab" && open && suffix) {
        e.preventDefault();
        input.value = prefixLabel;
        query = prefixLabel;
        renderList();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        open = true;
        highlight = Math.min(highlight + 1, Math.max(0, items.length - 1));
        renderList();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        open = true;
        highlight = Math.max(highlight - 1, 0);
        renderList();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        if (items[highlight]) commit(items[highlight]);
        return;
      }
      if (e.key === "Escape") {
        open = false;
        query = "";
        input.value = "";
        renderList();
      }
    });

    document.addEventListener("mousedown", function onDoc(e) {
      if (!root.contains(e.target)) {
        open = false;
        renderList();
      }
    });

    return {
      setItems(next) {
        rows = Array.isArray(next) ? next : [];
        renderList();
      },
      clear() {
        query = "";
        input.value = "";
        open = false;
        highlight = 0;
        renderList();
      },
      focus() {
        input.focus();
      },
    };
  }

  global.createTagCatalogCombobox = createTagCatalogCombobox;
})(typeof globalThis !== "undefined" ? globalThis : window);
