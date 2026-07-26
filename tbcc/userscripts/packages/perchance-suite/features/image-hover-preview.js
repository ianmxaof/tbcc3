/* Full-res hover preview for generated T2I images + Ctrl+wheel zoom-to-cursor. */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const ROOT_ID = 'tbcc-pc-hover-preview';
  const STYLE_ID = 'tbcc-pc-hover-preview-css';
  const MIN_SCALE = 1;
  const MAX_SCALE = 8;
  const ZOOM_STEP = 1.12;

  let root = null;
  let stage = null;
  let imgEl = null;
  let metaEl = null;
  let hideTimer = null;
  let activeThumb = null;
  let scale = 1;
  let tx = 0;
  let ty = 0;
  let mo = null;
  let bound = false;

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement('style');
    el.id = STYLE_ID;
    el.textContent = `
#${ROOT_ID} {
  position: fixed; z-index: 2147483000; display: none;
  pointer-events: none;
  max-width: min(92vw, 920px); max-height: min(92vh, 920px);
  background: #0a0a0c; border: 1px solid #5a5a5a; border-radius: 10px;
  box-shadow: 0 18px 48px rgba(0,0,0,.75);
  overflow: hidden;
}
#${ROOT_ID}.open { display: flex; flex-direction: column; pointer-events: auto; }
#${ROOT_ID} .tbcc-hp-stage {
  position: relative; overflow: hidden;
  width: min(92vw, 920px); height: min(88vh, 860px);
  background: #111;
  cursor: zoom-in;
  touch-action: none;
}
#${ROOT_ID} .tbcc-hp-stage img {
  position: absolute; left: 50%; top: 50%;
  transform-origin: 0 0;
  max-width: none; max-height: none;
  user-select: none; -webkit-user-drag: none;
  image-rendering: auto;
}
#${ROOT_ID} .tbcc-hp-meta {
  flex: 0 0 auto; padding: 6px 10px; font: 11px/1.35 system-ui, sans-serif;
  color: #b8b8b8; background: #161616; border-top: 1px solid #333;
}
#${ROOT_ID} .tbcc-hp-meta kbd {
  font: 10px ui-monospace, Consolas, monospace; background: #2a2a2a;
  border: 1px solid #444; border-radius: 3px; padding: 1px 5px; color: #ddd;
}
`;
    (document.documentElement || document.head).appendChild(el);
  }

  function ensureRoot() {
    if (root && document.body.contains(root)) return root;
    ensureStyle();
    root = document.createElement('div');
    root.id = ROOT_ID;
    root.innerHTML =
      '<div class="tbcc-hp-stage"><img alt="preview" /></div>' +
      '<div class="tbcc-hp-meta">Hover preview · <kbd>Ctrl</kbd>+wheel zoom to cursor · Esc closes</div>';
    document.documentElement.appendChild(root);
    stage = root.querySelector('.tbcc-hp-stage');
    imgEl = root.querySelector('img');
    metaEl = root.querySelector('.tbcc-hp-meta');

    root.addEventListener('mouseenter', () => clearHide());
    root.addEventListener('mouseleave', () => scheduleHide());
    stage.addEventListener(
      'wheel',
      (e) => {
        if (!e.ctrlKey) return;
        e.preventDefault();
        e.stopPropagation();
        // User request: wheel up = zoom out, wheel down = zoom in (opposite of many maps).
        const zoomIn = e.deltaY > 0;
        zoomAt(e.clientX, e.clientY, zoomIn);
      },
      { passive: false }
    );
    return root;
  }

  function clearHide() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function scheduleHide() {
    clearHide();
    hideTimer = setTimeout(() => hide(), 160);
  }

  function isSuiteChrome(el) {
    return !!(
      el.closest?.('#tbcc-pc-loot-god') ||
      el.closest?.('#tbcc-pc-flags') ||
      el.closest?.('#tbcc-pc-jobs') ||
      el.closest?.(`#${ROOT_ID}`) ||
      el.closest?.('[id^="tbcc-pc-"]')
    );
  }

  function isCandidateImg(img) {
    if (!img || img.tagName !== 'IMG') return false;
    if (isSuiteChrome(img)) return false;
    if (imgEl && img === imgEl) return false;
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    if (w < 96 || h < 96) return false;
    const src = img.currentSrc || img.src || '';
    if (!src || src.startsWith('data:image/svg')) return false;
    const box = img.getBoundingClientRect();
    if (box.width < 48 || box.height < 48) return false;
    const parentText = (img.parentElement?.textContent || '').slice(0, 80);
    if (/Waiting|Preparing|Loading/i.test(parentText) && w < 200) return false;
    return true;
  }

  function fullSrc(img) {
    return img.currentSrc || img.src || '';
  }

  function applyTransform() {
    if (!imgEl) return;
    // Center at scale 1; pan via tx/ty in screen px.
    imgEl.style.transform = `translate(calc(-50% + ${tx}px), calc(-50% + ${ty}px)) scale(${scale})`;
  }

  function fitContain() {
    if (!imgEl || !stage) return;
    const nw = imgEl.naturalWidth || 1;
    const nh = imgEl.naturalHeight || 1;
    const sw = stage.clientWidth || 1;
    const sh = stage.clientHeight || 1;
    const fit = Math.min(sw / nw, sh / nh, 1);
    scale = Math.max(MIN_SCALE * fit, fit);
    // At contain, keep centered
    tx = 0;
    ty = 0;
    // Store base fit so zoom multiplies from display size
    imgEl.style.width = `${nw}px`;
    imgEl.style.height = `${nh}px`;
    // Use a display scale relative to fitted size
    scale = fit;
    applyTransform();
    updateMeta();
  }

  function updateMeta() {
    if (!metaEl || !imgEl) return;
    const nw = imgEl.naturalWidth || 0;
    const nh = imgEl.naturalHeight || 0;
    metaEl.innerHTML =
      `${nw}×${nh} · zoom ${(scale * 100).toFixed(0)}% · ` +
      `<kbd>Ctrl</kbd>+wheel ↓ in / ↑ out (to cursor) · Esc closes`;
  }

  function zoomAt(clientX, clientY, zoomIn) {
    if (!imgEl || !stage) return;
    const rect = stage.getBoundingClientRect();
    const cx = clientX - rect.left - rect.width / 2;
    const cy = clientY - rect.top - rect.height / 2;
    const prev = scale;
    const next = Math.min(
      MAX_SCALE,
      Math.max(MIN_SCALE * 0.25, zoomIn ? prev * ZOOM_STEP : prev / ZOOM_STEP)
    );
    if (next === prev) return;
    // Keep the point under the cursor stable: content point = (cx - tx) / scale
    const contentX = (cx - tx) / prev;
    const contentY = (cy - ty) / prev;
    scale = next;
    tx = cx - contentX * scale;
    ty = cy - contentY * scale;
    applyTransform();
    updateMeta();
  }

  function placeNear(thumb) {
    if (!root || !thumb) return;
    const br = thumb.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const pw = Math.min(vw * 0.92, 920);
    const ph = Math.min(vh * 0.92, 920);
    let left = br.right + 12;
    let top = br.top;
    if (left + pw > vw - 8) left = br.left - pw - 12;
    if (left < 8) left = Math.max(8, (vw - pw) / 2);
    if (top + ph > vh - 8) top = Math.max(8, vh - ph - 8);
    if (top < 8) top = 8;
    root.style.left = `${Math.round(left)}px`;
    root.style.top = `${Math.round(top)}px`;
  }

  function showFor(thumb) {
    if (!isCandidateImg(thumb)) return;
    ensureRoot();
    clearHide();
    activeThumb = thumb;
    const src = fullSrc(thumb);
    root.classList.add('open');
    placeNear(thumb);
    scale = 1;
    tx = 0;
    ty = 0;
    if (imgEl.src !== src) {
      imgEl.onload = () => {
        fitContain();
      };
      imgEl.src = src;
    } else {
      fitContain();
    }
  }

  function hide() {
    clearHide();
    activeThumb = null;
    if (root) root.classList.remove('open');
  }

  function onOver(e) {
    const t = e.target;
    if (!t || t.tagName !== 'IMG') return;
    if (!isCandidateImg(t)) return;
    showFor(t);
  }

  function onOut(e) {
    const t = e.target;
    if (!t || t.tagName !== 'IMG') return;
    if (t === imgEl) return;
    const to = e.relatedTarget;
    if (to && (root?.contains(to) || to === activeThumb)) return;
    scheduleHide();
  }

  function onKey(e) {
    if (e.key === 'Escape') hide();
  }

  function wireExisting() {
    document.querySelectorAll('img').forEach((img) => {
      if (!isCandidateImg(img)) return;
      if (img.dataset.tbccHp === '1') return;
      img.dataset.tbccHp = '1';
    });
  }

  PC.features.imageHoverPreview = {
    start() {
      ensureRoot();
      if (!bound) {
        document.addEventListener('mouseover', onOver, true);
        document.addEventListener('mouseout', onOut, true);
        document.addEventListener('keydown', onKey, true);
        bound = true;
      }
      wireExisting();
      if (!mo) {
        mo = new MutationObserver(() => wireExisting());
        mo.observe(document.documentElement, { childList: true, subtree: true });
      }
    },
    stop() {
      if (bound) {
        document.removeEventListener('mouseover', onOver, true);
        document.removeEventListener('mouseout', onOut, true);
        document.removeEventListener('keydown', onKey, true);
        bound = false;
      }
      if (mo) {
        mo.disconnect();
        mo = null;
      }
      hide();
      root?.remove();
      root = null;
      document.getElementById(STYLE_ID)?.remove();
      document.querySelectorAll('img[data-tbcc-hp]').forEach((img) => delete img.dataset.tbccHp);
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
