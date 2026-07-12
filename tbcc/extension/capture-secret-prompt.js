const API_BASES = ["http://127.0.0.1:8000", "http://localhost:8000"];

function qp(name) {
  return new URLSearchParams(location.search).get(name) || "";
}

async function fetchFirst(path, options) {
  let lastErr = null;
  for (const base of API_BASES) {
    try {
      return await fetch(base + path, options);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("unreachable");
}

async function main() {
  const value = qp("value");
  const pageUrl = qp("page_url");
  const preview = document.getElementById("preview");
  const keySel = document.getElementById("key");
  const status = document.getElementById("status");
  preview.textContent = value ? `${value.slice(0, 6)}…${value.slice(-4)} (${value.length} chars)` : "(empty)";

  let keys = [];
  let suggested = "";
  try {
    const r = await fetchFirst("/extension/capture-secret/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, page_url: pageUrl }),
    });
    const data = await r.json();
    keys = data.keys || [];
    suggested = data.suggested_key || "";
  } catch (e) {
    status.className = "err";
    status.textContent = "Backend offline — start TBCC API on localhost:8000.";
    return;
  }

  if (!keys.length) {
    const fallbacks = [
      "TBCC_IMGBB_API_KEY",
      "TBCC_CF_API_TOKEN",
      "TBCC_R2_ACCOUNT_ID",
      "TBCC_R2_PUBLIC_BASE_URL",
      "BUFFER_API_TOKEN",
      "OPENROUTER_API_KEY",
      "REPLICATE_API_TOKEN",
    ];
    keys = fallbacks;
    status.className = "hint";
    status.textContent = "No matching keys scanned from .env — pick a known name below.";
  }
  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k;
    opt.textContent = k;
    if (k === suggested) opt.selected = true;
    keySel.appendChild(opt);
  }
  if (suggested && !keys.includes(suggested)) {
    const opt = document.createElement("option");
    opt.value = suggested;
    opt.textContent = suggested + " (suggested)";
    opt.selected = true;
    keySel.appendChild(opt);
  }

  document.getElementById("save").onclick = async () => {
    status.textContent = "Saving…";
    status.className = "hint";
    const custom = (document.getElementById("custom").value || "").trim();
    const key = custom || keySel.value;
    if (!key) {
      status.className = "err";
      status.textContent = "Pick or type an env key name.";
      return;
    }
    try {
      const r = await fetchFirst("/extension/capture-secret", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value, key, page_url: pageUrl }),
      });
      const data = await r.json();
      if (!r.ok) {
        const d = data && data.detail;
        throw new Error(typeof d === "string" ? d : (d && d.message) || r.statusText);
      }
      status.className = "ok";
      status.textContent =
        `Saved ${data.key} to .env` + (data.backed_up_credential_manager ? " (+ Credential Manager)" : "");
      setTimeout(() => window.close(), 1200);
    } catch (e) {
      status.className = "err";
      status.textContent = String(e.message || e);
    }
  };
}

main();
