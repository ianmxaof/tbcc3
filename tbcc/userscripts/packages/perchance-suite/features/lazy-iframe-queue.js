/* Staggered iframe activation (from Prompt History upstream lazy-load queue) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const PC = (US.perchance = US.perchance || {});
  PC.features = PC.features || {};

  const MAX_CONCURRENT = 5;
  const FAST_BATCH = 4;
  const STAGGER_MS = 1500;
  const SCAN_INTERVAL_MS = 500;

  let inFlight = 0;
  let totalDispatched = 0;
  const pending = [];
  let staggerTimer = null;
  let scanTimer = null;
  let mo = null;
  let patched = false;
  let OriginalIO = null;

  function actuallyStart(el) {
    inFlight++;
    totalDispatched++;
    el.removeAttribute('srcdoc');
    el.dataset.alreadyAddedIntersectionObserver = 'yes';
    el.src = el.dataset.src;

    const onDone = () => {
      el.removeEventListener('load', onDone);
      el.removeEventListener('error', onDone);
      inFlight--;
      drainQueue();
    };
    el.addEventListener('load', onDone);
    el.addEventListener('error', onDone);
    setTimeout(() => {
      if (inFlight > 0) {
        el.removeEventListener('load', onDone);
        el.removeEventListener('error', onDone);
        inFlight--;
        drainQueue();
      }
    }, 180000);
  }

  function drainQueue() {
    if (inFlight >= MAX_CONCURRENT) return;
    if (pending.length === 0) return;
    const next = pending.shift();
    if (!next.isConnected) {
      drainQueue();
      return;
    }
    if (next.src && next.src !== '' && next.src !== 'about:blank' && !next.src.startsWith('about')) {
      drainQueue();
      return;
    }
    actuallyStart(next);
  }

  function scheduleStaggeredDrain() {
    if (staggerTimer) return;
    if (pending.length === 0) return;
    staggerTimer = setTimeout(() => {
      staggerTimer = null;
      drainQueue();
      if (pending.length > 0) scheduleStaggeredDrain();
    }, STAGGER_MS);
  }

  function dispatchIframe(el) {
    if (!el || !el.dataset || !el.dataset.src) return;
    if (el.src && el.src !== '' && el.src !== 'about:blank' && !el.src.startsWith('about')) return;
    if (inFlight >= MAX_CONCURRENT) {
      pending.push(el);
      return;
    }
    if (totalDispatched < FAST_BATCH) {
      actuallyStart(el);
    } else {
      pending.push(el);
      scheduleStaggeredDrain();
    }
  }

  function overrideIntersectionObserver() {
    OriginalIO = window.IntersectionObserver;
    if (!OriginalIO || patched) return;
    const patchedIO = function (callback, options) {
      const instance = new OriginalIO(callback, options);
      const originalObserve = instance.observe.bind(instance);
      instance.observe = function (target) {
        originalObserve(target);
        if (target.classList && target.classList.contains('text-to-image-plugin-image-iframe')) {
          instance.disconnect();
          if (!target.src || target.src === '' || target.src === 'about:blank' || target.src.startsWith('about')) {
            dispatchIframe(target);
          }
        }
      };
      return instance;
    };
    patchedIO.prototype = OriginalIO.prototype;
    window.IntersectionObserver = patchedIO;
    patched = true;
  }

  function scanAndActivate() {
    document.querySelectorAll('.text-to-image-plugin-image-iframe').forEach((el) => {
      if (!el.src || el.src === '' || el.src === 'about:blank' || el.src.startsWith('about')) {
        if (!pending.includes(el)) dispatchIframe(el);
      }
    });
  }

  function setupMutationObserver() {
    mo = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;
          if (node.matches && node.matches('.text-to-image-plugin-image-iframe')) dispatchIframe(node);
          if (node.querySelectorAll) {
            node.querySelectorAll('.text-to-image-plugin-image-iframe').forEach(dispatchIframe);
          }
        }
      }
    });
    const root = document.body || document.documentElement;
    mo.observe(root, { childList: true, subtree: true });
  }

  PC.features.lazyQueue = {
    start() {
      if (localStorage.getItem('ph-disable-lazy-loading') === '1') return;
      overrideIntersectionObserver();
      const go = () => {
        setupMutationObserver();
        scanAndActivate();
        scanTimer = setInterval(scanAndActivate, SCAN_INTERVAL_MS);
      };
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go);
      else go();
    },
    stop() {
      if (scanTimer) clearInterval(scanTimer);
      scanTimer = null;
      if (staggerTimer) clearTimeout(staggerTimer);
      staggerTimer = null;
      if (mo) mo.disconnect();
      mo = null;
      if (patched && OriginalIO) {
        window.IntersectionObserver = OriginalIO;
        patched = false;
      }
      pending.length = 0;
      inFlight = 0;
      totalDispatched = 0;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
