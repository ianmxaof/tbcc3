/* global chrome */

const STORAGE_ENABLED = "tbccModelSearchEnabledSites";

function getQueryUsername() {
  const p = new URLSearchParams(window.location.search);
  const q = (p.get("q") || "").trim();
  return q;
}

function buildUrl(template, username) {
  return template.split("{username}").join(encodeURIComponent(username));
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
document.getElementById("linkOptions2").addEventListener("click", (e) => {
  e.preventDefault();
  openOptions();
});

document.getElementById("btnOpenAllTabs").addEventListener("click", () => {
  const username = getQueryUsername();
  if (!username) return;
  const onlySite = (new URLSearchParams(window.location.search).get("site") || "").trim();
  chrome.storage.local.get(STORAGE_ENABLED, (data) => {
    const enabled = data[STORAGE_ENABLED] || {};
    getMergedModelSearchSites().then((cfg) => {
      let sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
      if (onlySite) sites = sites.filter((s) => s.id === onlySite);
      let first = true;
      for (const s of sites) {
        const u = buildUrl(s.url, username);
        chrome.tabs.create({ url: u, active: first });
        first = false;
      }
    });
  });
});

(async () => {
  const username = getQueryUsername();
  document.getElementById("titleQuery").textContent = username || "(empty)";

  if (!username) {
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent =
      "Missing search query. Use the context menu on a selected username, or open this page from the extension.";
    document.getElementById("grid").style.display = "none";
    return;
  }

  let cfg;
  try {
    cfg = await getMergedModelSearchSites();
  } catch (e) {
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent = String(e.message || e);
    document.getElementById("grid").style.display = "none";
    return;
  }

  const onlySite = (new URLSearchParams(window.location.search).get("site") || "").trim();

  chrome.storage.local.get(STORAGE_ENABLED, (data) => {
    const enabled = data[STORAGE_ENABLED] || {};
    let sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
    if (onlySite) {
      sites = sites.filter((s) => s.id === onlySite);
    }
    const grid = document.getElementById("grid");
    const empty = document.getElementById("empty");

    if (!sites.length) {
      empty.hidden = false;
      grid.style.display = "none";
      return;
    }

    empty.hidden = true;
    for (const s of sites) {
      const url = buildUrl(s.url, username);
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
        "<span>This site may block embedding (blank frame).</span><br /><a href=\"" +
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
        } catch (_) {
          /* cross-origin: assume ok */
        }
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
