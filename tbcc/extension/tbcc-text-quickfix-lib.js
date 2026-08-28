/**
 * Raycast-style Quick Fix helpers — local caps/spacing cleanup + LLM reply cleanup.
 * Shared by content script and service worker (importScripts).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccTextQuickfix: api };
  }
  root.TbccTextQuickfix = api;
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this, function () {
  const COMMON_TYPOS = {
    teh: "the",
    adn: "and",
    taht: "that",
    wiht: "with",
    recieve: "receive",
    occurence: "occurrence",
    seperate: "separate",
    defintely: "definitely",
    occured: "occurred",
    untill: "until",
    wich: "which",
    becuase: "because",
    dont: "don't",
    wont: "won't",
    cant: "can't",
    im: "I'm",
    i: "I",
  };

  const KNOWN_ACRONYMS = new Set([
    "API",
    "URL",
    "HTTP",
    "HTTPS",
    "TBCC",
    "LLM",
    "GPT",
    "JSON",
    "HTML",
    "CSS",
    "SQL",
    "CPU",
    "GPU",
    "RAM",
    "USB",
    "VPN",
    "DNS",
    "SSH",
    "AWS",
    "GCP",
    "NASA",
    "FAQ",
    "PDF",
    "PNG",
    "JPG",
    "MP4",
    "ZIP",
    "CEO",
    "CTO",
    "CFO",
    "USA",
    "UK",
    "EU",
  ]);

  const LLM_PREFIX_RE =
    /^(?:here(?:'s| is) the corrected (?:text|version)[:\s]*|corrected(?: text)?[:\s]*)/i;

  function letterStats(word) {
    const letters = String(word || "").replace(/[^a-zA-Z]/g, "");
    if (!letters) return { letters: "", upper: 0, ratio: 0 };
    const upper = (letters.match(/[A-Z]/g) || []).length;
    return { letters, upper, ratio: upper / letters.length };
  }

  function looksLikeAcronym(word) {
    const letters = String(word || "").replace(/[^a-zA-Z]/g, "");
    if (!letters || letters.length < 3) return false;
    if (letters !== letters.toUpperCase()) return false;
    return KNOWN_ACRONYMS.has(letters);
  }

  function isMostlyUppercaseText(text) {
    const letters = String(text || "").replace(/[^a-zA-Z]/g, "");
    if (!letters) return false;
    const upper = (letters.match(/[A-Z]/g) || []).length;
    return upper / letters.length >= 0.7;
  }

  function normalizeWordCaps(word, aggressive) {
    if (!word) return word;
    const stats = letterStats(word);
    if (!stats.letters) return word;
    if (looksLikeAcronym(word)) return word;
    if (aggressive || stats.ratio >= 0.75 || (stats.ratio > 0.15 && stats.ratio < 0.85)) {
      const lower = word.toLowerCase();
      if (lower === "i") return "I";
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }
    return word;
  }

  function fixCommonTypos(word) {
    const bare = String(word || "");
    const lower = bare.toLowerCase();
    const hit = COMMON_TYPOS[lower];
    if (!hit) return bare;
    if (bare === bare.toUpperCase()) return hit.toUpperCase();
    if (bare.charAt(0) === bare.charAt(0).toUpperCase()) {
      return hit.charAt(0).toUpperCase() + hit.slice(1);
    }
    return hit;
  }

  function normalizeWhitespace(text) {
    const lines = String(text || "").split("\n");
    const trimmed = lines.map((line) => line.replace(/[ \t]+$/g, "").replace(/^[ \t]+/g, (m) => (m.length > 1 ? " " : m)));
    let out = trimmed.join("\n");
    out = out.replace(/[ \t]{2,}/g, " ");
    out = out.replace(/\n{3,}/g, "\n\n");
    return out.trim();
  }

  function capitalizeLeadingLetter(text) {
    const raw = String(text || "");
    const idx = raw.search(/[a-zA-Z]/);
    if (idx < 0) return raw;
    return raw.slice(0, idx) + raw.charAt(idx).toUpperCase() + raw.slice(idx + 1);
  }

  function sentenceCaseLine(line, aggressive) {
    return String(line || "")
      .split(/(\s+)/)
      .map((chunk) => {
        if (!chunk || /^\s+$/.test(chunk)) return chunk;
        const typoFixed = fixCommonTypos(chunk);
        return normalizeWordCaps(typoFixed, aggressive);
      })
      .join("");
  }

  function localQuickFix(text) {
    const raw = String(text || "");
    if (!raw.trim()) return raw;
    const normalized = normalizeWhitespace(raw);
    const lines = normalized.split("\n");
    const aggressive = isMostlyUppercaseText(normalized);
    const fixed = lines
      .map((line) => {
        if (!line.trim()) return line;
        const parts = line.split(/([.!?]+\s+)/);
        let rebuilt = "";
        for (let i = 0; i < parts.length; i++) {
          const part = parts[i];
          if (/^[.!?]+\s*$/.test(part)) {
            rebuilt += part;
            continue;
          }
          rebuilt += capitalizeLeadingLetter(sentenceCaseLine(part, aggressive));
        }
        return rebuilt || capitalizeLeadingLetter(sentenceCaseLine(line, aggressive));
      })
      .join("\n");
    return fixed;
  }

  function stripLlmReply(text) {
    let out = String(text || "").trim();
    if (!out) return out;
    out = out.replace(/^["'`“”]+|["'`“”]+$/g, "").trim();
    out = out.replace(LLM_PREFIX_RE, "").trim();
    return out;
  }

  const QUICKFIX_SYSTEM =
    "Fix spelling, grammar, and capitalization in the user's text. Preserve meaning, tone, URLs, code identifiers, and line breaks. Return only the corrected text with no quotes, labels, or commentary.";

  return {
    COMMON_TYPOS,
    localQuickFix,
    stripLlmReply,
    QUICKFIX_SYSTEM,
  };
});
