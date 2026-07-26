/* Strip Perchance social chrome + blur/age gates. Generator-only AOF surface. */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const STYLE_ID = 'tbcc-pc-lean-generator-css';
  const KILLED = 'data-tbcc-pc-social-killed';
  let mo = null;
  let timer = null;
  let lastNsfwPush = 0;

  const HIDE_CSS = `
/* TBCC lean generator — kill forum / public gallery / social chrome */
html[data-tbcc-pc-lean="1"] iframe[src*="comment" i],
html[data-tbcc-pc-lean="1"] iframe[src*="forum" i],
html[data-tbcc-pc-lean="1"] iframe[src*="gallery" i],
html[data-tbcc-pc-lean="1"] [${KILLED}],
html[data-tbcc-pc-lean="1"] [class*="comment" i],
html[data-tbcc-pc-lean="1"] [class*="forum" i],
html[data-tbcc-pc-lean="1"] [id*="comment" i],
html[data-tbcc-pc-lean="1"] [id*="forum" i],
html[data-tbcc-pc-lean="1"] [class*="social" i],
html[data-tbcc-pc-lean="1"] [id*="social" i],
html[data-tbcc-pc-lean="1"] [class*="public-gallery" i],
html[data-tbcc-pc-lean="1"] [id*="public-gallery" i],
html[data-tbcc-pc-lean="1"] [class*="community-gallery" i],
html[data-tbcc-pc-lean="1"] .iframe-comments,
html[data-tbcc-pc-lean="1"] .comments-root,
html[data-tbcc-pc-lean="1"] .gallery-root,
html[data-tbcc-pc-lean="1"] .public-gallery,
html[data-tbcc-pc-lean="1"] [data-name="comments"],
html[data-tbcc-pc-lean="1"] [data-name="gallery"],
html[data-tbcc-pc-lean="1"] a[href*="forum" i],
html[data-tbcc-pc-lean="1"] a[href*="comments-plugin" i],
html[data-tbcc-pc-lean="1"] a[href*="gallery-plugin" i] {
  display: none !important;
  visibility: hidden !important;
  max-height: 0 !important;
  max-width: 0 !important;
  overflow: hidden !important;
  pointer-events: none !important;
  opacity: 0 !important;
  position: absolute !important;
  left: -99999px !important;
}

html[data-tbcc-pc-lean="1"] button[class*="hide-comment" i],
html[data-tbcc-pc-lean="1"] button[class*="hide-gallery" i],
html[data-tbcc-pc-lean="1"] button[class*="show-comment" i],
html[data-tbcc-pc-lean="1"] button[class*="show-gallery" i] {
  display: none !important;
  pointer-events: none !important;
}

html[data-tbcc-pc-lean="1"] [class*="blur" i],
html[data-tbcc-pc-lean="1"] [class*="restricted" i],
html[data-tbcc-pc-lean="1"] [class*="nsfw-gate" i],
html[data-tbcc-pc-lean="1"] [class*="age-gate" i],
html[data-tbcc-pc-lean="1"] [class*="content-warning" i],
html[data-tbcc-pc-lean="1"] div:has(> button:is([class*="show-image" i], [class*="showImage" i])) {
  filter: none !important;
  backdrop-filter: none !important;
}
html[data-tbcc-pc-lean="1"] img[style*="blur"],
html[data-tbcc-pc-lean="1"] canvas[style*="blur"],
html[data-tbcc-pc-lean="1"] video[style*="blur"] {
  filter: none !important;
}
`;

  function ensureStyle() {
    document.documentElement?.setAttribute('data-tbcc-pc-lean', '1');
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement('style');
    el.id = STYLE_ID;
    el.textContent = HIDE_CSS;
    (document.documentElement || document.head || document.body).appendChild(el);
  }

  function clickIfVisible(el) {
    if (!el || el.disabled) return false;
    if (el.getAttribute?.(KILLED)) return false;
    try {
      el.click();
      return true;
    } catch (_) {
      return false;
    }
  }

  function textOf(el) {
    return (el.textContent || el.value || el.getAttribute?.('aria-label') || el.title || '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function textMatch(el, re) {
    return re.test(textOf(el));
  }

  function killNode(el) {
    if (!el || el === document.body || el === document.documentElement) return;
    if (el.getAttribute?.(KILLED)) return;
    try {
      el.setAttribute(KILLED, '1');
      el.style.setProperty('display', 'none', 'important');
      el.style.setProperty('visibility', 'hidden', 'important');
      el.style.setProperty('pointer-events', 'none', 'important');
      el.style.setProperty('max-height', '0', 'important');
      el.style.setProperty('overflow', 'hidden', 'important');
    } catch (_) {}
  }

  function killSocialHost(start) {
    let n = start;
    for (let i = 0; i < 10 && n && n !== document.body; i++) {
      const h = n.offsetHeight || 0;
      const kids = n.children ? n.children.length : 0;
      const t = textOf(n).slice(0, 280);
      const socialHint =
        /Type a comment|submit comment|SFW Forum|NSFW Forum|Feedback Forum|hide comments|hide gallery|show comments|show gallery/i.test(
          t
        );
      if (socialHint && h > 60 && kids >= 1 && h < window.innerHeight * 0.95) {
        killNode(n);
        return true;
      }
      n = n.parentElement;
    }
    if (start) killNode(start);
    return !!start;
  }

  function stripSocialChrome() {
    document.querySelectorAll('button, a, [role="button"], label').forEach((el) => {
      const t = textOf(el);
      if (/^hide\s+comments$/i.test(t) || /^hide\s+gallery$/i.test(t)) {
        clickIfVisible(el);
        killNode(el);
        return;
      }
      // Framework flips label to "show …" once hidden — kill both so social stays gone.
      if (/^show\s+comments$/i.test(t) || /^show\s+gallery$/i.test(t)) {
        killNode(el);
      }
    });

    document.querySelectorAll('iframe').forEach((frame) => {
      const src = `${frame.src || ''} ${frame.getAttribute('name') || ''} ${frame.id || ''}`.toLowerCase();
      if (/comment|forum|gallery-plugin|public.?gallery|community/.test(src)) {
        killNode(frame);
        killSocialHost(frame.parentElement);
      }
    });

    const needles = [
      /Type a comment/i,
      /submit comment/i,
      /SFW Forum/i,
      /NSFW Forum/i,
      /Feedback Forum/i,
    ];
    document.querySelectorAll('div, section, aside, form, textarea, button, h1, h2, h3, span').forEach((el) => {
      const t = textOf(el);
      if (!t || t.length > 400) return;
      if (!needles.some((re) => re.test(t))) return;
      if (/Type a comment|submit comment/i.test(t) || /SFW Forum|NSFW Forum/i.test(t)) {
        killSocialHost(el);
      }
    });

    document.querySelectorAll('textarea').forEach((ta) => {
      const ph = `${ta.placeholder || ''} ${ta.getAttribute('aria-label') || ''}`;
      if (/comment|forum/i.test(ph) || /Type a comment/i.test(textOf(ta.parentElement || ta))) {
        killSocialHost(ta);
      }
    });
  }

  function forceNsfwMode() {
    const now = Date.now();
    if (now - lastNsfwPush < 800) return;
    lastNsfwPush = now;
    const borderOnly = document.documentElement?.getAttribute('data-tbcc-pc-border-only') === '1';

    document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach((cb) => {
      const label =
        (cb.labels && cb.labels[0] && cb.labels[0].textContent) ||
        cb.getAttribute('aria-label') ||
        (cb.parentElement && cb.parentElement.textContent) ||
        '';
      const lab = String(label).replace(/\s+/g, ' ').trim();
      if (/show\s*all|uncensor|nsfw\s*mode|enable\s*nsfw|adult|18\+/i.test(lab) && !/sfw\s*only|disable\s*nsfw/i.test(lab)) {
        if (!cb.checked) {
          cb.checked = true;
          cb.dispatchEvent(new Event('input', { bubbles: true }));
          cb.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      if (/^sfw$|sfw\s*only|blur\s*nsfw|censor/i.test(lab) && !/uncensor|show\s*all/i.test(lab)) {
        if (cb.checked) {
          cb.checked = false;
          cb.dispatchEvent(new Event('input', { bubbles: true }));
          cb.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });

    document.querySelectorAll('button, a, [role="button"], [role="tab"]').forEach((el) => {
      if (textMatch(el, /^nsfw(\s+mode)?$/i) || textMatch(el, /switch\s+to\s+nsfw|enable\s+nsfw|uncensor/i)) {
        clickIfVisible(el);
      }
      if (
        textMatch(el, /i\s*am\s*18|enter|continue|i\s*agree|yes,?\s*i'?m\s*18/i) &&
        !textMatch(el, /hide|cancel|no\b|sfw/i)
      ) {
        clickIfVisible(el);
      }
      if (textMatch(el, /^show\s+image$/i) || textMatch(el, /^show\s+all$/i)) {
        clickIfVisible(el);
      }
    });

    // During border-only frame mode, Lab zeros Art Style to Default — do not force NSFW smut styles back on.
    if (borderOnly) return;

    document.querySelectorAll('select').forEach((sel) => {
      const lab = `${sel.getAttribute('aria-label') || ''} ${sel.previousElementSibling?.textContent || ''} ${
        sel.parentElement?.textContent || ''
      }`.slice(0, 120);
      if (!/art\s*style/i.test(lab)) return;
      const cur = (sel.options[sel.selectedIndex]?.textContent || '').trim();
      if (/nsfw/i.test(cur) && !/anti-nsfw|sfw/i.test(cur)) return;
      let pick = null;
      for (const opt of Array.from(sel.options)) {
        const t = (opt.textContent || '').trim();
        if (/^NSFW\s*-\s*Realistic$/i.test(t)) {
          pick = opt;
          break;
        }
        if (!pick && /nsfw.*realistic/i.test(t)) pick = opt;
      }
      if (pick && sel.value !== pick.value) {
        sel.value = pick.value;
        sel.dispatchEvent(new Event('input', { bubbles: true }));
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  }

  function unblurMedia() {
    document.querySelectorAll('img, canvas, video').forEach((m) => {
      if (m.style && m.style.filter && /blur/i.test(m.style.filter)) {
        m.style.filter = 'none';
      }
    });
  }

  function tick() {
    ensureStyle();
    stripSocialChrome();
    forceNsfwMode();
    unblurMedia();
  }

  PC.features.leanGenerator = {
    start() {
      ensureStyle();
      tick();
      if (!mo) {
        mo = new MutationObserver(() => {
          if (timer) clearTimeout(timer);
          timer = setTimeout(tick, 100);
        });
        mo.observe(document.documentElement || document.body, {
          childList: true,
          subtree: true,
        });
      }
      setTimeout(tick, 0);
      setTimeout(tick, 400);
      setTimeout(tick, 1200);
      setTimeout(tick, 3000);
      setTimeout(tick, 6000);
    },
    stop() {
      if (mo) {
        mo.disconnect();
        mo = null;
      }
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      document.documentElement?.removeAttribute('data-tbcc-pc-lean');
      document.getElementById(STYLE_ID)?.remove();
      document.querySelectorAll(`[${KILLED}]`).forEach((el) => {
        el.removeAttribute(KILLED);
        el.style.removeProperty('display');
        el.style.removeProperty('visibility');
        el.style.removeProperty('pointer-events');
        el.style.removeProperty('max-height');
        el.style.removeProperty('overflow');
      });
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
