/* global chrome */

const STORAGE_ENABLED = "tbccReverseImageEnabledSites";

function buildEngineUrl(template, imageUrl) {
  return template.split("{imageUrl}").join(encodeURIComponent(imageUrl));
}

async function loadConfig() {
  const url = chrome.runtime.getURL("reverse-image-sites.json");
  const r = await fetch(url);
  if (!r.ok) throw new Error("Failed to load reverse-image-sites.json");
  return r.json();
}

function openOptions() {
  if (chrome.runtime.openOptionsPage) {
    chrome.runtime.openOptionsPage();
  }
}

document.getElementById("linkOptions").addEventListener("click", (e) => {
  e.preventDefault();
  openOptions();
});

function shortUrl(u) {
  if (!u || u.length < 80) return u || "";
  return u.slice(0, 36) + "…" + u.slice(-28);
}

let cachedImageUrl = "";

document.getElementById("btnOpenAllTabs").addEventListener("click", () => {
  if (!cachedImageUrl) return;
  chrome.storage.local.get(STORAGE_ENABLED, (data) => {
    const enabled = data[STORAGE_ENABLED] || {};
    loadConfig().then((cfg) => {
      const sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
      let first = true;
      for (const s of sites) {
        const u = buildEngineUrl(s.url, cachedImageUrl);
        chrome.tabs.create({ url: u, active: first });
        first = false;
      }
    });
  });
});

(async () => {
  const p = new URLSearchParams(window.location.search);
  const k = (p.get("k") || "").trim();
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");

  if (!k) {
    empty.hidden = false;
    empty.textContent =
      "Missing session key. Use the context menu on an image: Reverse image search (fan-out).";
    grid.style.display = "none";
    return;
  }

  const sessionData = await new Promise((resolve) => {
    chrome.storage.session.get(k, resolve);
  });
  const imageUrl = sessionData[k];
  try {
    chrome.storage.session.remove(k);
  } catch (_) {}

  if (!imageUrl || typeof imageUrl !== "string") {
    empty.hidden = false;
    empty.innerHTML =
      "Session expired or invalid. Run <strong>Reverse image search</strong> again from the image context menu.";
    grid.style.display = "none";
    return;
  }

  cachedImageUrl = imageUrl;
  document.getElementById("titleSrc").textContent = shortUrl(imageUrl);

  let cfg;
  try {
    cfg = await loadConfig();
  } catch (e) {
    empty.hidden = false;
    empty.textContent = String(e.message || e);
    grid.style.display = "none";
    return;
  }

  chrome.storage.local.get(STORAGE_ENABLED, (data) => {
    const enabled = data[STORAGE_ENABLED] || {};
    const sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);

    if (!sites.length) {
      empty.hidden = false;
      empty.innerHTML =
        'No reverse-image sources enabled. Open <a href="#" id="emptyOpts">extension options</a> → Reverse image.';
      grid.style.display = "none";
      document.getElementById("emptyOpts").addEventListener("click", (e) => {
        e.preventDefault();
        openOptions();
      });
      return;
    }

    empty.hidden = true;
    for (const s of sites) {
      const url = buildEngineUrl(s.url, imageUrl);
      const panel = document.createElement("div");
      panel.className = "panel";
      const top = document.createElement("div");
      top.className = "panel-top";
      const title = document.createElement("span");
      title.textContent = s.name || s.id;
      const openLink = document.createElement("a");
      openLink.href = url;
      openLink.target = "_blank";
      openLink.rel = "noopener noreferrer";
      openLink.textContent = "Open ↗";
      top.appendChild(title);
      top.appendChild(openLink);

      const wrap = document.createElement("div");
      wrap.className = "frame-wrap";
      const iframe = document.createElement("iframe");
      iframe.title = s.name || s.id;
      iframe.sandbox =
        "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox";
      iframe.referrerPolicy = "no-referrer";
      iframe.loading = "lazy";
      iframe.src = url;

      const fallback = document.createElement("div");
      fallback.className = "frame-fallback";
      fallback.innerHTML =
        "<span>This engine may block embedding.</span><br /><a href=\"" +
        url.replace(/"/g, "&quot;") +
        '" target="_blank" rel="noopener noreferrer">Open in new tab</a>';

      let shown = false;
      const showFallback = () => {
        if (shown) return;
        shown = true;
        fallback.classList.add("visible");
      };

      iframe.addEventListener("load", () => {
        try {
          const loc = iframe.contentWindow && iframe.contentWindow.location;
          if (loc && loc.href === "about:blank") showFallback();
        } catch (_) {}
      });
      setTimeout(() => {
        try {
          const d = iframe.contentDocument;
          if (d && d.body && d.body.children.length === 0 && d.body.innerText.trim() === "") {
            showFallback();
          }
        } catch (_) {}
      }, 8000);

      wrap.appendChild(iframe);
      wrap.appendChild(fallback);
      panel.appendChild(top);
      panel.appendChild(wrap);
      grid.appendChild(panel);
    }
  });
})();
