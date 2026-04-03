/* global chrome */
(function () {
  const el = document.getElementById("tbccModelSearchSummary");
  if (!el) return;

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function render() {
    chrome.storage.local.get("tbccModelSearchLastSummary", (data) => {
      const sum = data.tbccModelSearchLastSummary;
      if (!sum || !sum.query) {
        el.innerHTML =
          '<span style="color:#6c7086">Model search: select a username → right‑click → <strong>TBCC — Look up username</strong>. Est. match counts update here after a search (best‑effort from page HTML).</span>';
        return;
      }
      const rows = sum.rows || [];
      let html =
        '<div style="font-weight:600;color:#f5c2e7;margin-bottom:6px">Last lookup: <span style="color:#89b4fa">' +
        esc(sum.query) +
        "</span></div>";
      html += '<table style="width:100%;border-collapse:collapse;font-size:10px">';
      html += '<thead><tr><th align="left" style="padding:2px 4px;color:#a6adc8">Source</th><th align="right" style="padding:2px 4px;color:#a6adc8">Est. matches</th></tr></thead><tbody>';
      for (const r of rows) {
        let c = "—";
        if (r.fetchStatus === "pending") c = "…";
        else if (r.countHint != null && r.countHint !== "") c = String(r.countHint);
        else if (r.fetchStatus === "err") c = "err";
        else if (r.fetchStatus && String(r.fetchStatus).startsWith("http_")) c = "—";
        html +=
          "<tr><td style=\"padding:3px 4px;border-top:1px solid #313244\">" +
          esc(r.name) +
          '</td><td align="right" style="padding:3px 4px;border-top:1px solid #313244">' +
          esc(c) +
          "</td></tr>";
      }
      html += "</tbody></table>";
      el.innerHTML = html;
    });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.tbccModelSearchLastSummary) render();
  });
  render();
})();
