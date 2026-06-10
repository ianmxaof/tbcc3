/* global chrome, TbccCollected */
const API_BASE = "http://localhost:8000";

let items = [];
let selected = new Set();
let filterCollectionId = "";

const gridEl = document.getElementById("grid");
const emptyEl = document.getElementById("empty");
const countEl = document.getElementById("count");
const selectAllCb = document.getElementById("selectAll");
const poolSelect = document.getElementById("poolSelect");
const destModeEl = document.getElementById("destMode");
const tagsInput = document.getElementById("tagsInput");
const noteInput = document.getElementById("noteInput");
const batchLabel = document.getElementById("batchLabel");
const captionInput = document.getElementById("captionInput");
const btnApplyMeta = document.getElementById("btnApplyMeta");
const btnStageDest = document.getElementById("btnStageDest");
const btnStageAndSend = document.getElementById("btnStageAndSend");
const btnRemove = document.getElementById("btnRemove");
const btnClearAll = document.getElementById("btnClearAll");
const statusLine = document.getElementById("statusLine");
const batchPills = document.getElementById("batchPills");

function setStatus(text) {
  if (statusLine) statusLine.textContent = text || "";
}

function visibleItems() {
  if (!filterCollectionId) return items;
  return items.filter((it) => it.collectionId === filterCollectionId);
}

function updateToolbar() {
  const n = selected.size;
  countEl.textContent = String(n);
  const disabled = n === 0;
  btnApplyMeta.disabled = disabled;
  btnStageDest.disabled = disabled;
  btnStageAndSend.disabled = disabled;
  btnRemove.disabled = disabled;
  const vis = visibleItems();
  selectAllCb.checked = vis.length > 0 && vis.every((it) => selected.has(TbccCollected.collectedItemKey(it)));
}

function renderBatchPills() {
  if (!batchPills) return;
  const batches = TbccCollected.listCollectionLabels(items);
  if (!batches.length) {
    batchPills.hidden = true;
    batchPills.innerHTML = "";
    return;
  }
  batchPills.hidden = false;
  batchPills.innerHTML = "";
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "batch-pill" + (!filterCollectionId ? " active" : "");
  allBtn.textContent = "All (" + items.length + ")";
  allBtn.addEventListener("click", () => {
    filterCollectionId = "";
    selected.clear();
    render();
  });
  batchPills.appendChild(allBtn);
  for (const b of batches) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "batch-pill" + (filterCollectionId === b.id ? " active" : "");
    btn.textContent = (b.label || b.id) + " (" + b.count + ")";
    btn.addEventListener("click", () => {
      filterCollectionId = b.id;
      selected.clear();
      render();
    });
    batchPills.appendChild(btn);
  }
}

function render() {
  const vis = visibleItems();
  gridEl.innerHTML = "";
  if (!items.length) {
    emptyEl.style.display = "block";
    updateToolbar();
    renderBatchPills();
    return;
  }
  emptyEl.style.display = vis.length ? "none" : "block";
  vis.forEach((item) => {
    const key = TbccCollected.collectedItemKey(item);
    const div = document.createElement("div");
    div.className = "cell" + (selected.has(key) ? " selected" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selected.has(key);
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      if (cb.checked) selected.add(key);
      else selected.delete(key);
      div.classList.toggle("selected", cb.checked);
      updateToolbar();
    });
    div.appendChild(cb);
    if (item.collectionLabel || item.collectionId) {
      const badge = document.createElement("div");
      badge.className = "cell-badge";
      badge.textContent = (item.collectionLabel || "batch").slice(0, 12);
      div.appendChild(badge);
    }
    const thumb = item.thumbUrl && /^https?:\/\//i.test(item.thumbUrl) ? item.thumbUrl : item.url;
    if (item.mediaType === "video" && /^https?:\/\//i.test(thumb)) {
      const v = document.createElement("video");
      v.src = thumb;
      v.muted = true;
      v.playsInline = true;
      v.preload = "metadata";
      div.appendChild(v);
    } else {
      const img = document.createElement("img");
      img.alt = "";
      img.referrerPolicy = "no-referrer";
      img.src = thumb;
      img.onerror = () => {
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = item.sourceHost || "media";
        div.appendChild(ph);
        img.remove();
      };
      div.appendChild(img);
    }
    const meta = document.createElement("div");
    meta.className = "cell-meta";
    const fname = (() => {
      try {
        return decodeURIComponent(new URL(item.url).pathname.split("/").pop() || "media");
      } catch (_) {
        return "media";
      }
    })();
    const tagBit = (item.tags && item.tags.length ? item.tags.slice(0, 3).join(", ") : "") || "";
    meta.textContent = [fname.slice(0, 28), item.sourceHost, tagBit].filter(Boolean).join(" · ");
    div.appendChild(meta);
    div.addEventListener("click", (e) => {
      if (e.target === cb) return;
      cb.checked = !cb.checked;
      if (cb.checked) selected.add(key);
      else selected.delete(key);
      div.classList.toggle("selected", cb.checked);
      updateToolbar();
    });
    gridEl.appendChild(div);
  });
  updateToolbar();
  renderBatchPills();
}

async function loadCollected() {
  items = await TbccCollected.getItems();
  selected.clear();
  render();
  setStatus(items.length ? items.length + " item(s) in collection." : "");
}

async function loadPools() {
  try {
    const r = await fetch(API_BASE + "/pools");
    const pools = await r.json();
    poolSelect.innerHTML = "";
    (pools || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = String(p.id);
      o.textContent = p.name || "Pool " + p.id;
      poolSelect.appendChild(o);
    });
    const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
    if (tbccPoolId != null) poolSelect.value = String(tbccPoolId);
  } catch (_) {}
}

function getSelectedItems() {
  return visibleItems().filter((it) => selected.has(TbccCollected.collectedItemKey(it)));
}

async function applyMetaToSelected() {
  const picked = getSelectedItems();
  if (!picked.length) return;
  const tags = TbccCollected.parseTagsCsv(tagsInput && tagsInput.value);
  const note = noteInput && noteInput.value ? noteInput.value.trim() : "";
  const label = batchLabel && batchLabel.value ? batchLabel.value.trim() : "";
  const batchId = label ? "batch_" + label.replace(/\s+/g, "-").slice(0, 40) : "";
  const keys = new Set(picked.map((it) => TbccCollected.collectedItemKey(it)));
  items = items.map((it) => {
    if (!keys.has(TbccCollected.collectedItemKey(it))) return it;
    const mergedTags = [...new Set([...(it.tags || []), ...tags])];
    return TbccCollected.normalizeCollectedItem({
      ...it,
      tags: mergedTags,
      note: note || it.note,
      collectionId: batchId || it.collectionId,
      collectionLabel: label || it.collectionLabel,
    });
  });
  await TbccCollected.setItems(items);
  render();
  setStatus("Updated " + picked.length + " item(s).");
}

function postStageToParent(toSend, autoSend) {
  const payload = {
    type: "tbcc-collected-stage-dest",
    items: toSend,
    destMode: destModeEl ? destModeEl.value : "saved",
    tagsCsv: tagsInput ? tagsInput.value.trim() : "",
    caption: captionInput ? captionInput.value.trim() : "",
    poolId: poolSelect && poolSelect.value ? parseInt(poolSelect.value, 10) : null,
    autoSend: !!autoSend,
  };
  try {
    window.parent.postMessage(payload, "*");
  } catch (e) {
    setStatus(String(e.message || e));
  }
}

selectAllCb.addEventListener("change", () => {
  const vis = visibleItems();
  if (selectAllCb.checked) vis.forEach((it) => selected.add(TbccCollected.collectedItemKey(it)));
  else selected.clear();
  render();
});

poolSelect.addEventListener("change", () => {
  if (poolSelect.value) chrome.storage.local.set({ tbccPoolId: parseInt(poolSelect.value, 10) });
});

if (destModeEl) {
  destModeEl.addEventListener("change", () => {
    chrome.storage.local.set({ tbccCollectedDestMode: destModeEl.value });
  });
}

btnApplyMeta.addEventListener("click", () => void applyMetaToSelected());

btnStageDest.addEventListener("click", () => {
  const toSend = getSelectedItems();
  if (!toSend.length) return;
  postStageToParent(toSend, false);
  setStatus("Opened Dest on main gallery — review caption/tags, then Send.");
});

btnStageAndSend.addEventListener("click", () => {
  const toSend = getSelectedItems();
  if (!toSend.length) return;
  postStageToParent(toSend, true);
  setStatus("Sending from main gallery…");
});

btnRemove.addEventListener("click", async () => {
  const keys = [...selected];
  if (!keys.length) return;
  await TbccCollected.removeKeys(keys);
  selected.clear();
  await loadCollected();
});

btnClearAll.addEventListener("click", async () => {
  if (!items.length) return;
  if (!confirm("Clear all collected media?")) return;
  await TbccCollected.setItems([]);
  selected.clear();
  filterCollectionId = "";
  await loadCollected();
  setStatus("Collection cleared.");
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes[TbccCollected.STORAGE_COLLECTED]) return;
  void loadCollected();
});

void loadPools();
void (async () => {
  try {
    const { tbccCollectedDestMode } = await chrome.storage.local.get("tbccCollectedDestMode");
    if (
      destModeEl &&
      tbccCollectedDestMode &&
      [...destModeEl.options].some((o) => o.value === tbccCollectedDestMode)
    ) {
      destModeEl.value = tbccCollectedDestMode;
    }
  } catch (_) {}
  await loadCollected();
})();
