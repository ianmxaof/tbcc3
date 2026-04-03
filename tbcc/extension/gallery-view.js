const API_BASE = "http://localhost:8000";
const STORAGE_COLLECTED = "tbcc_collected";

let items = [];
let selected = new Set();

const gridEl = document.getElementById("grid");
const emptyEl = document.getElementById("empty");
const countEl = document.getElementById("count");
const selectAllCb = document.getElementById("selectAll");
const poolSelect = document.getElementById("poolSelect");
const btnSend = document.getElementById("btnSend");
const btnDelete = document.getElementById("btnDelete");

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

async function loadCollected() {
  const raw = await new Promise((r) => chrome.storage.local.get(STORAGE_COLLECTED, (o) => r(o[STORAGE_COLLECTED])));
  items = Array.isArray(raw) ? raw : [];
  selected.clear();
  render();
}

function render() {
  gridEl.innerHTML = "";
  if (items.length === 0) {
    emptyEl.style.display = "block";
    countEl.textContent = "0";
    selectAllCb.checked = false;
    btnSend.disabled = true;
    return;
  }
  emptyEl.style.display = "none";
  items.forEach((item, idx) => {
    const key = item.url || idx;
    const div = document.createElement("div");
    div.className = "cell" + (selected.has(key) ? " selected" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selected.has(key);
    cb.addEventListener("change", () => { if (cb.checked) selected.add(key); else selected.delete(key); div.classList.toggle("selected", cb.checked); updateCount(); });
    div.appendChild(cb);
    const img = document.createElement("img");
    img.alt = "";
    img.referrerPolicy = "no-referrer";
    img.src = item.url;
    img.onerror = () => { const ph = document.createElement("div"); ph.className = "placeholder"; ph.textContent = "—"; div.appendChild(ph); img.remove(); };
    div.appendChild(img);
    div.addEventListener("click", (e) => { if (e.target === cb) return; cb.checked = !cb.checked; if (cb.checked) selected.add(key); else selected.delete(key); div.classList.toggle("selected", cb.checked); updateCount(); });
    gridEl.appendChild(div);
  });
  updateCount();
  selectAllCb.checked = items.length > 0 && items.every((_, i) => selected.has(items[i].url || i));
}

function updateCount() {
  countEl.textContent = selected.size;
  btnSend.disabled = selected.size === 0;
}

selectAllCb.addEventListener("change", () => {
  if (selectAllCb.checked) items.forEach((it, i) => selected.add(it.url || i));
  else selected.clear();
  render();
});

poolSelect.addEventListener("change", () => { if (poolSelect.value) chrome.storage.local.set({ tbccPoolId: parseInt(poolSelect.value, 10) }); });

btnSend.addEventListener("click", async () => {
  if (selected.size === 0) return;
  const poolId = parseInt(poolSelect.value, 10) || 1;
  const toSend = items.filter((it, i) => selected.has(it.url || i));
  btnSend.disabled = true;
  for (const it of toSend) {
    try {
      const r = await fetch(it.url, { mode: "cors", credentials: "omit" });
      const blob = await r.blob();
      const form = new FormData();
      form.append("file", blob, "media");
      form.append("pool_id", String(poolId));
      form.append("saved_only", "false");
      form.append("source", "extension:gallery-view");
      await fetch(API_BASE + "/import/bytes", { method: "POST", body: form });
    } catch (_) {}
  }
  btnSend.disabled = false;
});

btnDelete.addEventListener("click", () => {
  if (selected.size === 0) return;
  const keep = items.filter((it, i) => !selected.has(it.url || i));
  chrome.storage.local.set({ [STORAGE_COLLECTED]: keep }, () => loadCollected());
});

loadPools();
loadCollected();
