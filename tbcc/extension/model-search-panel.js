/* global chrome */

(function () {
  const STORAGE_SUMMARY = "tbccModelSearchLastSummary";
  const input = document.getElementById("mspUsername");
  const statusEl = document.getElementById("mspStatus");
  const reportBody = document.getElementById("mspReportBody");
  const reportMeta = document.getElementById("mspReportMeta");
  const reportTotal = document.getElementById("mspReportTotal");
  const templateOut = document.getElementById("mspTemplateOut");
  const btnCopyTemplate = document.getElementById("btnCopyTemplate");

  let lastTemplate = "";

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.className = "msp-status" + (kind ? " msp-status--" + kind : "");
  }

  function getUsername() {
    return String((input && input.value) || "")
      .trim()
      .replace(/^@+/, "");
  }

  function renderSummary(sum) {
    if (!reportBody) return;
    if (!sum || sum.mode !== "macro") {
      reportBody.innerHTML =
        '<p class="msp-empty">Run a macro search to see sites with results. Sites with no hits are omitted.</p>';
      if (reportMeta) reportMeta.textContent = "";
      if (reportTotal) reportTotal.hidden = true;
      return;
    }

    if (sum.status === "running") {
      reportBody.innerHTML =
        '<p class="msp-empty">Searching… ' +
        esc(sum.scanned || 0) +
        " / " +
        esc(sum.totalSites || "?") +
        " sites</p>";
      if (reportMeta) reportMeta.textContent = "@" + esc(sum.query || "");
      if (reportTotal) {
        reportTotal.hidden = false;
        reportTotal.className = "msp-report-total msp-report-total--running";
        reportTotal.textContent = "Macro search in progress…";
      }
      return;
    }

    const hits = Array.isArray(sum.hits) ? sum.hits : [];
    if (reportMeta) {
      const when = sum.ts ? new Date(sum.ts).toLocaleString() : "";
      reportMeta.textContent =
        "@" +
        (sum.query || "") +
        (when ? " · " + when : "") +
        " · " +
        hits.length +
        " hit(s) of " +
        (sum.scanned || sum.totalSites || 0) +
        " scanned";
    }

    if (!hits.length) {
      reportBody.innerHTML =
        '<p class="msp-empty">No sites returned results for <strong>' +
        esc(sum.query || "") +
        "</strong>. Try tab search or verify URL templates in Manage sources.</p>";
    } else {
      let html = '<table class="msp-hits-table"><thead><tr><th>Source</th><th class="num">Results</th><th>Link</th></tr></thead><tbody>';
      for (const h of hits) {
        html +=
          "<tr><td>" +
          esc(h.name || h.siteId) +
          '</td><td class="num">' +
          esc(h.count) +
          '</td><td><a href="' +
          esc(h.url) +
          '" target="_blank" rel="noopener noreferrer">Open results</a></td></tr>';
      }
      html += "</tbody></table>";
      reportBody.innerHTML = html;
    }

    if (reportTotal) {
      reportTotal.hidden = false;
      reportTotal.className = "msp-report-total";
      reportTotal.textContent =
        "Total: " +
        (sum.totalCount || 0) +
        " estimated result(s) across " +
        hits.length +
        " site(s)";
    }
  }

  function loadSummaryFromStorage() {
    chrome.storage.local.get([STORAGE_SUMMARY], (data) => {
      renderSummary(data[STORAGE_SUMMARY]);
      const q = data[STORAGE_SUMMARY] && data[STORAGE_SUMMARY].query;
      if (q && input && !input.value.trim()) input.value = q;
    });
  }

  async function runMacroSearch() {
    const username = getUsername();
    if (!username) {
      setStatus("Enter a username first.", "err");
      return;
    }
    setStatus("Macro search running…", null);
    if (input) input.disabled = true;
    const btn = document.getElementById("btnMacroSearch");
    if (btn) btn.disabled = true;
    try {
      const resp = await chrome.runtime.sendMessage({
        action: "tbcc-macro-model-search",
        username,
      });
      if (!resp || !resp.ok) {
        setStatus((resp && resp.error) || "Macro search failed.", "err");
        return;
      }
      setStatus("Macro search finished.", "ok");
      renderSummary(resp.summary);
    } catch (e) {
      setStatus(String(e.message || e), "err");
    } finally {
      if (input) input.disabled = false;
      if (btn) btn.disabled = false;
    }
  }

  async function runTabSearch(category) {
    const username = getUsername();
    if (!username) {
      setStatus("Enter a username first.", "err");
      return;
    }
    setStatus("Opening tabs…", null);
    try {
      await chrome.runtime.sendMessage({
        action: "tbcc-launch-model-search-tabs",
        username,
        category,
      });
      setStatus("Tab search launched.", "ok");
    } catch (e) {
      setStatus(String(e.message || e), "err");
    }
  }

  document.getElementById("btnMacroSearch")?.addEventListener("click", () => void runMacroSearch());
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") void runMacroSearch();
  });
  document.getElementById("btnTabsOnlyfans")?.addEventListener("click", () =>
    void runTabSearch(MODEL_SEARCH_CATEGORY_ONLYFANS)
  );
  document.getElementById("btnTabsLivecams")?.addEventListener("click", () =>
    void runTabSearch(MODEL_SEARCH_CATEGORY_LIVECAMS)
  );
  document.getElementById("btnTabsVideos")?.addEventListener("click", () =>
    void runTabSearch(MODEL_SEARCH_CATEGORY_VIDEOS)
  );

  document.getElementById("btnDeriveTemplate")?.addEventListener("click", () => {
    const raw = String(document.getElementById("mspHelperUrl")?.value || "").trim();
    const user = String(document.getElementById("mspHelperUser")?.value || "").trim().replace(/^@+/, "");
    const tpl = deriveUsernameTemplateFromSearchUrl(raw, user);
    if (!tpl) {
      lastTemplate = "";
      if (templateOut) {
        templateOut.hidden = false;
        templateOut.textContent =
          "Could not find the username in that URL. Paste the exact address bar URL after searching.";
      }
      if (btnCopyTemplate) btnCopyTemplate.disabled = true;
      return;
    }
    lastTemplate = tpl;
    if (templateOut) {
      templateOut.hidden = false;
      templateOut.textContent = tpl;
    }
    if (btnCopyTemplate) btnCopyTemplate.disabled = false;
  });

  btnCopyTemplate?.addEventListener("click", async () => {
    if (!lastTemplate) return;
    try {
      await navigator.clipboard.writeText(lastTemplate);
      setStatus("Template copied.", "ok");
    } catch (_) {
      setStatus("Clipboard denied — select and copy manually.", "err");
    }
  });

  document.getElementById("btnManageSources")?.addEventListener("click", () => {
    if (window.parent !== window) {
      window.parent.postMessage(
        { type: "tbcc-panel-view", view: "options", scrollTo: "tbcc-add-source" },
        "*"
      );
    } else if (chrome.runtime.openOptionsPage) {
      chrome.runtime.openOptionsPage(() => {
        const el = document.getElementById("tbcc-add-source");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[STORAGE_SUMMARY]) {
      renderSummary(changes[STORAGE_SUMMARY].newValue);
    }
  });

  loadSummaryFromStorage();
})();
