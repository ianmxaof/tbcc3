// ==UserScript==
// @name         Perchance AI Image Generator Improvements (Prompt History)
// @namespace    https://greasyfork.org
// @match        https://perchance.org/ai-text-to-image-generator*
// @match        https://*.perchance.org/ai-text-to-image-generator*
// @match        https://image-generation.perchance.org/gallery*
// @grant        none
// @version      1.0
// @license      GPL-3.0-or-later
// @run-at       document-start
// @description  Prompt history with auto-grouping by similarity, nested random selectors, expanded grid, gallery tab export/import, and auto-show NSFW images.
// @downloadURL https://update.greasyfork.org/scripts/576634/Perchance%20AI%20Image%20Generator%20Improvements%20%28Prompt%20History%29.user.js
// @updateURL https://update.greasyfork.org/scripts/576634/Perchance%20AI%20Image%20Generator%20Improvements%20%28Prompt%20History%29.meta.js
// ==/UserScript==

(function() {
    'use strict';

    // Block cross-tab gallery hijacking: prevent other tabs from forcing this tab's
    // gallery to switch sub-channel and sort order when an image is saved elsewhere.
    if (location.hostname.endsWith('perchance.org') && location.pathname.includes('ai-text-to-image-generator')) {
        window.addEventListener('storage', (e) => {
            if (e.key === 'saveImageToGalleryCount') {
                e.stopImmediatePropagation();
            }
        }, true);
    }

    const MAX_CONCURRENT = 5;
    const FAST_BATCH = 4;
    const STAGGER_MS = 1500;
    const SCAN_INTERVAL_MS = 500;
    const DEBUG = false;
    function log(...args) { if (DEBUG) console.log('[Perchance No-Lazy]', ...args); }

    // ========================================================================
    // CONCURRENCY QUEUE WITH STAGGER
    // ========================================================================
    // The first FAST_BATCH iframes dispatch immediately (no delay). After that,
    // each one is staggered by STAGGER_MS so the server gets a trickle rather
    // than a flood. The concurrency cap (MAX_CONCURRENT) still applies on top.

    let inFlight = 0;
    let totalDispatched = 0;
    const pending = [];

    function actuallyStart(el) {
        inFlight++;
        totalDispatched++;
        log('Activating iframe #', totalDispatched, '(in-flight:', inFlight, 'pending:', pending.length, ')');
        el.removeAttribute('srcdoc');
        el.dataset.alreadyAddedIntersectionObserver = 'yes';
        el.src = el.dataset.src;

        const onDone = () => {
            el.removeEventListener('load', onDone);
            el.removeEventListener('error', onDone);
            inFlight--;
            log('Iframe done (in-flight:', inFlight, 'pending:', pending.length, ')');
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
        }, 180_000);
    }

    function dispatchIframe(el) {
        if (!el || !el.dataset || !el.dataset.src) return;
        if (el.src && el.src !== '' && el.src !== 'about:blank' && !el.src.startsWith('about')) return;

        if (inFlight >= MAX_CONCURRENT) {
            pending.push(el);
            log('Queued iframe (in-flight:', inFlight, 'pending:', pending.length, ')');
            return;
        }

        const position = totalDispatched;

        if (position < FAST_BATCH) {
            actuallyStart(el);
        } else {
            pending.push(el);
            scheduleStaggeredDrain();
        }
    }

    let staggerTimer = null;
    function scheduleStaggeredDrain() {
        if (staggerTimer) return;
        if (pending.length === 0) return;
        staggerTimer = setTimeout(() => {
            staggerTimer = null;
            drainQueue();
            if (pending.length > 0) scheduleStaggeredDrain();
        }, STAGGER_MS);
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

    // ========================================================================
    // METHOD 1: Override IntersectionObserver constructor
    // ========================================================================

    function overrideIntersectionObserver() {
        const OriginalIO = window.IntersectionObserver;
        if (!OriginalIO) { log('IntersectionObserver not available'); return; }

        const patchedIO = function(callback, options) {
            const instance = new OriginalIO(callback, options);
            const originalObserve = instance.observe.bind(instance);

            instance.observe = function(target) {
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
        Object.defineProperty(patchedIO, 'name', { value: 'IntersectionObserver' });
        window.IntersectionObserver = patchedIO;
        log('IntersectionObserver constructor overridden');
    }

    // ========================================================================
    // METHOD 2: MutationObserver
    // ========================================================================

    function setupMutationObserver() {
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType !== Node.ELEMENT_NODE) continue;
                    if (node.matches && node.matches('.text-to-image-plugin-image-iframe')) {
                        dispatchIframe(node);
                    }
                    if (node.querySelectorAll) {
                        for (const iframe of node.querySelectorAll('.text-to-image-plugin-image-iframe')) {
                            dispatchIframe(iframe);
                        }
                    }
                }
            }
        });

        const startObserving = () => {
            observer.observe(document.body || document.documentElement, {
                childList: true,
                subtree: true
            });
            log('MutationObserver active');
        };

        if (document.body) startObserving();
        else document.addEventListener('DOMContentLoaded', startObserving);
    }

    // ========================================================================
    // METHOD 3: Periodic scan
    // ========================================================================

    function scanAndActivate() {
        const lazyIframes = document.querySelectorAll('.text-to-image-plugin-image-iframe');
        let count = 0;
        for (const el of lazyIframes) {
            if (!el.src || el.src === '' || el.src === 'about:blank' || el.src.startsWith('about')) {
                if (!pending.includes(el)) {
                    dispatchIframe(el);
                    count++;
                }
            }
        }
        if (count > 0) log('Periodic scan queued', count, 'iframes');
    }

    // ========================================================================
    // EXPAND GENERATION GRID — remove the 1000px cap so cards fill the viewport
    // ========================================================================

    function expandGenerationGrid() {
        const style = document.createElement('style');
        style.textContent = `
            #mainColumnEl85394739 { max-width: 100% !important; }
            #outputAreaEl .text-to-image-plugin-image-iframe { max-width: 100%; }
        `;
        (document.head || document.documentElement).appendChild(style);
    }

    expandGenerationGrid();

    // ========================================================================
    // INITIALIZATION (Lazy Loading)
    // ========================================================================

    const lazyLoadingDisabled = localStorage.getItem('ph-disable-lazy-loading') === '1';

    if (!lazyLoadingDisabled) {
        overrideIntersectionObserver();

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setupMutationObserver();
                scanAndActivate();
                setInterval(scanAndActivate, SCAN_INTERVAL_MS);
            });
        } else {
            setupMutationObserver();
            scanAndActivate();
            setInterval(scanAndActivate, SCAN_INTERVAL_MS);
        }
    }

    // ========================================================================
    // NESTED SELECTOR FLATTENING
    // ========================================================================

    const NESTED_MAX_ALTERNATIVES = 500;
    const NESTED_MAX_DEPTH = 50;

    function containsNestedSelectors(text) {
        let depth = 0;
        for (let i = 0; i < text.length; i++) {
            if (text[i] === '\\') { i++; continue; }
            if (text[i] === '{') { depth++; if (depth > 1) return true; }
            else if (text[i] === '}') depth--;
        }
        return false;
    }

    function flattenNestedSelectors(text) {
        const segments = parseSegments(text, 0);
        return segments.map(seg => {
            if (seg.type === 'text') return seg.value;
            if (seg.alternatives.length === 1) return seg.alternatives[0];
            return '{' + seg.alternatives.join('|') + '}';
        }).join('');
    }

    function parseSegments(str, depth) {
        if (depth > NESTED_MAX_DEPTH) return [{ type: 'text', value: str }];
        const segments = [];
        let i = 0;
        let buf = '';

        while (i < str.length) {
            if (str[i] === '\\' && i + 1 < str.length) {
                buf += str[i] + str[i + 1];
                i += 2;
                continue;
            }
            if (str[i] === '{') {
                if (buf) { segments.push({ type: 'text', value: buf }); buf = ''; }
                let braceDepth = 1;
                let j = i + 1;
                while (j < str.length && braceDepth > 0) {
                    if (str[j] === '\\') { j += 2; continue; }
                    if (str[j] === '{') braceDepth++;
                    else if (str[j] === '}') braceDepth--;
                    j++;
                }
                const inner = str.slice(i + 1, j - 1);
                const alternatives = splitTopLevelPipes(inner);
                const resolved = alternatives.map(alt => {
                    const subSegments = parseSegments(alt, depth + 1);
                    return flattenSegments(subSegments).alternatives;
                });
                const flat = resolved.flat();
                if (flat.length > NESTED_MAX_ALTERNATIVES) {
                    segments.push({ type: 'text', value: str.slice(i, j) });
                } else {
                    segments.push({ type: 'group', alternatives: flat });
                }
                i = j;
            } else {
                buf += str[i];
                i++;
            }
        }
        if (buf) segments.push({ type: 'text', value: buf });
        return segments;
    }

    function splitTopLevelPipes(str) {
        const parts = [];
        let depth = 0;
        let current = '';
        for (let i = 0; i < str.length; i++) {
            if (str[i] === '\\' && i + 1 < str.length) {
                current += str[i] + str[i + 1];
                i++;
                continue;
            }
            if (str[i] === '{') { depth++; current += str[i]; }
            else if (str[i] === '}') { depth--; current += str[i]; }
            else if (str[i] === '|' && depth === 0) { parts.push(current); current = ''; }
            else { current += str[i]; }
        }
        parts.push(current);
        return parts;
    }

    function flattenSegments(segments) {
        let results = [''];
        for (const seg of segments) {
            if (seg.type === 'text') {
                results = results.map(r => r + seg.value);
            } else if (seg.type === 'group') {
                const expanded = [];
                for (const prefix of results) {
                    for (const alt of seg.alternatives) {
                        expanded.push(prefix + alt);
                        if (expanded.length > NESTED_MAX_ALTERNATIVES) {
                            return { text: '{' + expanded.join('|') + '}', alternatives: expanded };
                        }
                    }
                }
                results = expanded;
            }
        }
        if (results.length === 1) {
            return { text: results[0], alternatives: results };
        }
        return { text: '{' + results.join('|') + '}', alternatives: results };
    }

    // ========================================================================
    // PROMPT HISTORY
    // ========================================================================

    const DB_NAME = 'perchance-prompt-history';
    const DB_VERSION = 1;
    const SIMILARITY_THRESHOLD_DEFAULT = 0.5;
    const SIMILARITY_THRESHOLD_MIN = 0.4;
    const SIMILARITY_THRESHOLD_MAX = 0.85;
    let SIMILARITY_THRESHOLD = parseFloat(localStorage.getItem('ph-similarity-threshold')) || SIMILARITY_THRESHOLD_DEFAULT;
    const QUICKFILL_PER_GROUP_DEFAULT = 2;
    const QUICKFILL_TOTAL_DEFAULT = 6;
    let QUICKFILL_PER_GROUP = parseInt(localStorage.getItem('ph-quickfill-per-group')) || QUICKFILL_PER_GROUP_DEFAULT;
    let QUICKFILL_TOTAL = parseInt(localStorage.getItem('ph-quickfill-total')) || QUICKFILL_TOTAL_DEFAULT;
    const RECENCY_WINDOW_MS = 2 * 24 * 60 * 60 * 1000;
    const MAX_COMPARE_PER_GROUP = 5;

    let historyDB = null;
    let lastUsedGroupId = null;
    let reusedFromGroupId = null;
    let overlayScrollTop = 0;

    // ---- IndexedDB ----

    function openDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains('groups')) {
                    const gs = db.createObjectStore('groups', { keyPath: 'id', autoIncrement: true });
                    gs.createIndex('updatedAt', 'updatedAt');
                }
                if (!db.objectStoreNames.contains('prompts')) {
                    const ps = db.createObjectStore('prompts', { keyPath: 'id', autoIncrement: true });
                    ps.createIndex('groupId', 'groupId');
                    ps.createIndex('text', 'text');
                }
            };
            req.onsuccess = (e) => { historyDB = e.target.result; resolve(historyDB); };
            req.onerror = (e) => reject(e.target.error);
        });
    }

    function tx(stores, mode) {
        const t = historyDB.transaction(stores, mode);
        const s = Array.isArray(stores) ? stores.map(n => t.objectStore(n)) : [t.objectStore(stores)];
        return { tx: t, stores: s };
    }

    function reqP(req) {
        return new Promise((resolve, reject) => {
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    async function getAllGroups() {
        const { stores } = tx('groups', 'readonly');
        return reqP(stores[0].getAll());
    }

    async function getGroup(id) {
        const { stores } = tx('groups', 'readonly');
        return reqP(stores[0].get(id));
    }

    async function addGroup(group) {
        const { stores } = tx('groups', 'readwrite');
        return reqP(stores[0].add(group));
    }

    async function putGroup(group) {
        const { stores } = tx('groups', 'readwrite');
        return reqP(stores[0].put(group));
    }

    async function deleteGroup(id) {
        const { stores } = tx('groups', 'readwrite');
        return reqP(stores[0].delete(id));
    }

    async function getPromptsByGroup(groupId) {
        const { stores } = tx('prompts', 'readonly');
        const idx = stores[0].index('groupId');
        return reqP(idx.getAll(groupId));
    }

    async function getAllPrompts() {
        const { stores } = tx('prompts', 'readonly');
        return reqP(stores[0].getAll());
    }

    async function getPrompt(id) {
        const { stores } = tx('prompts', 'readonly');
        return reqP(stores[0].get(id));
    }

    async function addPrompt(prompt) {
        const { stores } = tx('prompts', 'readwrite');
        return reqP(stores[0].add(prompt));
    }

    async function putPrompt(prompt) {
        const { stores } = tx('prompts', 'readwrite');
        return reqP(stores[0].put(prompt));
    }

    async function deletePrompt(id) {
        const { stores } = tx('prompts', 'readwrite');
        return reqP(stores[0].delete(id));
    }

    async function getPromptByText(text) {
        const { stores } = tx('prompts', 'readonly');
        return reqP(stores[0].index('text').get(text));
    }

    // ---- Similarity ----

    function tokenize(text) {
        return new Set(text.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(Boolean));
    }

    function jaccard(a, b) {
        const setA = a instanceof Set ? a : tokenize(a);
        const setB = b instanceof Set ? b : tokenize(b);
        let intersection = 0;
        for (const w of setA) { if (setB.has(w)) intersection++; }
        const union = setA.size + setB.size - intersection;
        return union === 0 ? 0 : intersection / union;
    }

    function groupName(text) {
        return text.split(/\s+/).slice(0, 10).join(' ');
    }

    // ---- Pill diff labels ----

    const STOPWORDS = new Set([
        'a','an','the','and','or','but','in','on','at','to','for','of','with','by','from',
        'is','are','was','were','be','been','being',
        'it','its','this','that','these','those',
        'i','me','my','we','our','you','your','he','she','they','them',
        'not','no','so','if','as','up','out','do','has','had','have',
    ]);

    function wordsOf(text) {
        const raw = [], clean = [];
        for (const w of text.split(/\s+/)) {
            const c = w.toLowerCase().replace(/[^\w]/g, '');
            if (c) { raw.push(w); clean.push(c); }
        }
        return { raw, clean };
    }

    function lcsWordDiff(oldWords, newWords) {
        const m = oldWords.length, n = newWords.length;
        const dp = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                dp[i][j] = oldWords[i - 1] === newWords[j - 1]
                    ? dp[i - 1][j - 1] + 1
                    : Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
        const ops = [];
        let i = m, j = n;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldWords[i - 1] === newWords[j - 1]) {
                ops.push({ type: 'keep', word: oldWords[i - 1] });
                i--; j--;
            } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                ops.push({ type: 'insert', word: newWords[j - 1] });
                j--;
            } else {
                ops.push({ type: 'delete', word: oldWords[i - 1] });
                i--;
            }
        }
        ops.reverse();
        return ops;
    }

    function cleanWord(w) { return w.toLowerCase().replace(/[^\w]/g, ''); }

    function stripStopwords(words) {
        let start = 0, end = words.length;
        while (start < end && STOPWORDS.has(cleanWord(words[start]))) start++;
        while (end > start && STOPWORDS.has(cleanWord(words[end - 1]))) end--;
        return words.slice(start, end);
    }

    function buildDiffFragments(oldText, newText) {
        const oldT = wordsOf(oldText), newT = wordsOf(newText);
        const ops = lcsWordDiff(oldT.clean, newT.clean);

        let oi = 0, ni = 0;
        const runs = [];
        let curType = null, curWords = [];
        for (const op of ops) {
            const displayWord = op.type === 'delete' ? oldT.raw[oi] : newT.raw[ni];
            if (op.type === 'keep') {
                if (curType) { runs.push({ type: curType, words: curWords }); curType = null; curWords = []; }
                oi++; ni++;
            } else if (op.type === 'delete') {
                if (curType && curType !== op.type) {
                    runs.push({ type: curType, words: curWords });
                    curType = null; curWords = [];
                }
                curType = op.type;
                curWords.push(displayWord);
                oi++;
            } else {
                if (curType && curType !== op.type) {
                    runs.push({ type: curType, words: curWords });
                    curType = null; curWords = [];
                }
                curType = op.type;
                curWords.push(displayWord);
                ni++;
            }
        }
        if (curType) runs.push({ type: curType, words: curWords });

        const fragments = [];

        for (let r = 0; r < runs.length; r++) {
            const run = runs[r];
            const next = runs[r + 1];

            const isSwap = next && (
                (run.type === 'delete' && next.type === 'insert') ||
                (run.type === 'insert' && next.type === 'delete')
            );
            if (isSwap) {
                const delRun = run.type === 'delete' ? run : next;
                const insRun = run.type === 'insert' ? run : next;
                let delW = delRun.words.slice(), insW = insRun.words.slice();
                while (delW.length > 0 && insW.length > 0 && cleanWord(delW[0]) === cleanWord(insW[0])) { delW.shift(); insW.shift(); }
                while (delW.length > 0 && insW.length > 0 && cleanWord(delW[delW.length - 1]) === cleanWord(insW[insW.length - 1])) { delW.pop(); insW.pop(); }

                const delStripped = stripStopwords(delW);
                const insStripped = stripStopwords(insW);

                if (delStripped.length === 0 && insStripped.length === 0) { r++; continue; }

                if (delStripped.length === 0) { fragments.push('+' + insStripped.join(' ')); r++; continue; }
                if (insStripped.length === 0) { fragments.push('-' + delStripped.join(' ')); r++; continue; }

                if (delStripped.length === 1 && insStripped.length === 1) {
                    const dw = cleanWord(delStripped[0]), iw = cleanWord(insStripped[0]);
                    const dNum = dw.replace(/[0-9.]+/g, ''), iNum = iw.replace(/[0-9.]+/g, '');
                    if (dNum === iNum && dw !== iw) {
                        const dMatch = dw.match(/[0-9.]+/), iMatch = iw.match(/[0-9.]+/);
                        if (dMatch && iMatch) {
                            fragments.push(dMatch[0] + '→' + iMatch[0] + (dNum ? ' ' + dNum : ''));
                            r++;
                            continue;
                        }
                    }
                    fragments.push(delStripped[0] + '→' + insStripped[0]);
                    r++;
                    continue;
                }

                if (delStripped.length > 0) fragments.push('-' + delStripped.join(' '));
                if (insStripped.length > 0) fragments.push('+' + insStripped.join(' '));
                r++;
                continue;
            }

            const stripped = stripStopwords(run.words);
            if (stripped.length === 0) continue;
            const prefix = run.type === 'delete' ? '-' : '+';
            fragments.push(prefix + stripped.join(' '));
        }

        return fragments;
    }

    function buildDiffLabel(oldText, newText, html) {
        const fragments = buildDiffFragments(oldText, newText);

        if (fragments.length === 0) {
            const oldSet = new Set(wordsOf(oldText).clean);
            const newSet = new Set(wordsOf(newText).clean);
            if (oldSet.size === newSet.size && [...oldSet].every(w => newSet.has(w))) {
                return { label: 'reordered', fragments: [] };
            }
            return null;
        }

        for (let i = fragments.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [fragments[i], fragments[j]] = [fragments[j], fragments[i]];
        }

        const MAX_LEN = 50;
        const parts = [];
        let len = 0;
        for (const f of fragments) {
            const needed = parts.length > 0 ? f.length + 1 : f.length;
            if (len + needed <= MAX_LEN) {
                parts.push(f);
                len += needed;
            } else if (parts.length === 0) {
                parts.push(f.length > MAX_LEN ? f.slice(0, MAX_LEN - 1) + '…' : f);
                break;
            }
        }

        if (!html) return { label: parts.join(' '), fragments };

        const label = parts.map(f => {
            const escaped = escHtml(f);
            if (f.startsWith('+')) return '<span style="color:#38a169">' + escaped + '</span>';
            if (f.startsWith('-')) return '<span style="color:#e53e3e">' + escaped + '</span>';
            if (f.includes('→')) return '<span style="color:#805ad5">' + escaped + '</span>';
            return escaped;
        }).join(' ');
        return { label, fragments };
    }

    // ---- Grouping Heuristic ----

    async function findBestGroup(text, lineageGroupId) {
        const now = Date.now();
        const allGroups = await getAllGroups();
        const candidateIds = new Set();

        for (const g of allGroups) {
            if (now - g.updatedAt < RECENCY_WINDOW_MS) candidateIds.add(g.id);
        }
        if (lineageGroupId != null) candidateIds.add(lineageGroupId);
        if (lastUsedGroupId != null) candidateIds.add(lastUsedGroupId);

        const tokens = tokenize(text);
        let bestGroupId = null;
        let bestScore = 0;

        for (const gid of candidateIds) {
            const prompts = await getPromptsByGroup(gid);
            prompts.sort((a, b) => Math.max(...b.timestamps) - Math.max(...a.timestamps));
            const recent = prompts.slice(0, MAX_COMPARE_PER_GROUP);
            for (const p of recent) {
                const score = jaccard(tokens, tokenize(p.text));
                if (score > bestScore) {
                    bestScore = score;
                    bestGroupId = gid;
                }
            }
        }

        return bestScore >= SIMILARITY_THRESHOLD ? bestGroupId : null;
    }

    // ---- Capture ----

    async function capturePrompt(text, artStyle, negativePrompt, resolution, lineageGroupId, hasNested) {
        if (!historyDB) return null;
        const trimmed = text.trim();
        if (!trimmed) return null;

        const now = Date.now();

        const existing = await getPromptByText(trimmed);
        if (existing) {
            existing.timestamps.push(now);
            if (hasNested && !existing.hasNested) existing.hasNested = true;
            await putPrompt(existing);
            const group = await getGroup(existing.groupId);
            if (group) { group.updatedAt = now; await putGroup(group); }
            lastUsedGroupId = existing.groupId;
            return group ? { name: group.name, isNew: false } : null;
        }

        let groupId = await findBestGroup(trimmed, lineageGroupId);
        let gName = null;
        let isNew = false;

        if (groupId != null) {
            const group = await getGroup(groupId);
            if (group) { group.updatedAt = now; await putGroup(group); gName = group.name; }
        } else {
            gName = groupName(trimmed);
            isNew = true;
            groupId = await addGroup({
                name: gName,
                createdAt: now,
                updatedAt: now,
            });
        }

        const promptRecord = {
            groupId,
            text: trimmed,
            artStyle: artStyle || '',
            negativePrompt: negativePrompt || '',
            resolution: resolution || '',
            timestamps: [now],
            parentGroupId: lineageGroupId || null,
        };
        if (hasNested) promptRecord.hasNested = true;
        await addPrompt(promptRecord);

        lastUsedGroupId = groupId;
        return { name: gName, isNew };
    }

    // ---- Read current inputs from the page ----

    function getCurrentInputs() {
        const wi = window.input || {};

        let description = '';
        if (typeof wi.description === 'string') {
            description = wi.description;
        } else {
            const el = document.querySelector('.paragraph-input') || document.querySelector('textarea');
            if (el) description = el.value;
        }

        let artStyle = '';
        if (wi.artStyle) {
            artStyle = typeof wi.artStyle.getName === 'string' ? wi.artStyle.getName
                     : typeof wi.artStyle === 'string' ? wi.artStyle : '';
        }
        if (!artStyle) {
            const sel = document.querySelector('select[data-name="artStyle"]');
            if (sel) { const o = sel.options[sel.selectedIndex]; artStyle = o ? o.textContent.trim() : ''; }
        }

        let negativePrompt = '';
        if (typeof wi.negative === 'string') {
            negativePrompt = wi.negative;
        } else {
            const el = document.querySelector('textarea[data-name="negative"], input[data-name="negative"]');
            if (el) negativePrompt = el.value;
        }

        let resolution = '';
        if (typeof wi.shape === 'string') {
            resolution = wi.shape;
        } else {
            const el = document.querySelector('select[data-name="shape"]');
            if (el) resolution = el.value;
        }

        return { description, artStyle, negativePrompt, resolution };
    }

    // ---- Hook into generate button ----

    function hookGenerateButton() {
        const poll = setInterval(() => {
            if (typeof window.___generateButtonClickEvent746291937 !== 'function') return;
            clearInterval(poll);

            const original = window.___generateButtonClickEvent746291937;
            window.___generateButtonClickEvent746291937 = async function(...args) {
                const inputs = getCurrentInputs();
                log('Generate intercepted, prompt:', inputs.description.slice(0, 60));
                const lineage = reusedFromGroupId;
                reusedFromGroupId = null;

                const rawDescription = inputs.description;
                const hasNested = containsNestedSelectors(rawDescription);
                let flatDescription = rawDescription;

                if (hasNested) {
                    flatDescription = flattenNestedSelectors(rawDescription);
                    const descEl = document.querySelector('textarea[data-name="description"]')
                        || document.querySelector('.paragraph-input')
                        || document.querySelector('textarea');
                    if (descEl) {
                        descEl.value = flatDescription;
                        descEl.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    if (window.input) window.input.description = flatDescription;
                }

                try {
                    const result = await capturePrompt(rawDescription, inputs.artStyle, inputs.negativePrompt, inputs.resolution, lineage, hasNested);
                    refreshQuickFill();
                    if (result) showGenToast(result.name, result.isNew);
                } catch (e) {
                    console.error('[Prompt History] capture failed:', e);
                }

                const ret = original.apply(this, args);

                if (hasNested) {
                    setTimeout(() => {
                        const descEl = document.querySelector('textarea[data-name="description"]')
                            || document.querySelector('.paragraph-input')
                            || document.querySelector('textarea');
                        if (descEl) {
                            descEl.value = rawDescription;
                            descEl.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        if (window.input) window.input.description = rawDescription;
                    }, 100);
                }

                return ret;
            };

            log('Generate button hooked for prompt history');
        }, 300);
    }

    // ---- Time formatting ----

    function formatTime(ts) {
        const now = Date.now();
        const diff = now - ts;
        if (diff < 60000) return 'just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        if (diff < 172800000) return 'yesterday';
        const d = new Date(ts);
        const month = d.toLocaleString('default', { month: 'short' });
        const day = d.getDate();
        const time = d.toLocaleTimeString('default', { hour: 'numeric', minute: '2-digit' });
        return `${month} ${day}, ${time}`;
    }

    // ---- CSS ----

    function injectStyles() {
        const style = document.createElement('style');
        style.textContent = `
            #ph-gen-row-wrapper {
                display: inline-flex;
                align-items: center;
                position: relative;
            }
            #ph-history-btn {
                position: absolute;
                left: 100%;
                margin-left: 8px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 6px 12px;
                border: none;
                border-radius: 6px;
                background: var(--box-color, #ebebeb);
                color: inherit;
                cursor: pointer;
                font-size: 14px;
                white-space: nowrap;
                transition: opacity 0.15s;
            }
            #ph-history-btn:hover { opacity: 0.7; }

            #ph-left-btns {
                position: absolute;
                right: 100%;
                margin-right: 8px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            #ph-settings-gear, #ph-info-btn {
                display: inline-flex;
                align-items: center;
                padding: 6px 8px;
                border: none;
                border-radius: 6px;
                background: var(--box-color, #ebebeb);
                color: inherit;
                cursor: pointer;
                font-size: 16px;
                white-space: nowrap;
                transition: opacity 0.15s;
            }
            #ph-settings-gear:hover, #ph-info-btn:hover { opacity: 0.7; }
            #ph-info-btn { font-size: 14px; font-weight: 700; font-style: italic; font-family: Georgia, serif; }

            #ph-settings-popover {
                display: none;
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: #2a2a2a;
                border: 1px solid rgba(128,128,128,0.4);
                border-radius: 8px;
                padding: 16px 20px;
                z-index: 10000;
                min-width: 280px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 4px 16px rgba(0,0,0,0.4);
                color: #eee;
                font-family: system-ui, sans-serif;
            }
            #ph-settings-popover.open { display: block; }
            #ph-settings-popover h3 {
                margin: 0 0 12px 0;
                font-size: 14px;
                font-weight: 600;
            }
            #ph-settings-popover label {
                font-size: 13px;
                display: block;
                margin-bottom: 6px;
            }
            #ph-settings-popover .ph-settings-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
            }
            #ph-settings-popover .ph-settings-reset {
                background: none;
                border: 1px solid rgba(128,128,128,0.4);
                color: #aaa;
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 4px;
                cursor: pointer;
            }
            #ph-settings-popover .ph-settings-reset:hover { color: #eee; border-color: rgba(128,128,128,0.7); }
            #ph-settings-popover hr {
                border: none;
                border-top: 1px solid rgba(128,128,128,0.3);
                margin: 14px 0;
            }
            #ph-settings-popover .ph-toggle-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                font-size: 13px;
            }
            #ph-settings-popover .ph-toggle-row + .ph-reload-hint {
                font-size: 11px;
                color: #e5a33a;
                margin-top: 4px;
                display: none;
            }
            #ph-settings-popover .ph-toggle-row + .ph-reload-hint.visible { display: block; }

            #ph-info-overlay {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 999999;
                background: rgba(0,0,0,0.55);
                justify-content: center;
                align-items: center;
            }
            #ph-info-overlay.ph-open { display: flex; }
            #ph-info-modal {
                background: #2a2a2a;
                color: #e2e8f0;
                width: 840px;
                max-width: 92vw;
                max-height: 85vh;
                border-radius: 12px;
                padding: 28px 32px;
                overflow-y: auto;
                box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                font-family: system-ui, sans-serif;
                line-height: 1.6;
            }
            #ph-info-modal h2 {
                margin: 0 0 16px;
                font-size: 20px;
                font-weight: 700;
            }
            #ph-info-modal h3 {
                margin: 20px 0 8px;
                font-size: 14px;
                font-weight: 700;
                color: #a0aec0;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            #ph-info-modal p {
                margin: 0 0 10px;
                font-size: 14px;
                color: #cbd5e0;
            }
            #ph-info-modal code {
                background: rgba(255,255,255,0.08);
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 13px;
                font-family: monospace;
                color: #b794f4;
            }
            #ph-info-modal ul {
                margin: 0 0 10px;
                padding-left: 20px;
                font-size: 14px;
                color: #cbd5e0;
            }
            #ph-info-modal li { margin-bottom: 4px; }
            #ph-info-modal {
                position: relative;
            }
            #ph-info-modal .ph-info-close {
                position: absolute;
                top: 16px;
                right: 16px;
                background: none;
                border: none;
                font-size: 22px;
                cursor: pointer;
                color: inherit;
                padding: 0 4px;
                opacity: 0.6;
                line-height: 1;
            }
            #ph-info-modal .ph-info-close:hover { opacity: 1; }

            #ph-gen-toast {
                position: absolute;
                left: 100%;
                top: 50%;
                transform: translateY(-50%);
                margin-left: 8px;
                white-space: nowrap;
                font-size: 13px;
                color: #aaa;
                opacity: 1;
                transition: opacity 0.5s;
                pointer-events: none;
                font-family: system-ui, sans-serif;
            }
            #ph-gen-toast.fade-out { opacity: 0; }

            #ph-quickfill {
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                gap: 5px;
                padding: 6px 0;
            }
            .ph-quickfill-pill {
                display: inline-flex;
                align-items: center;
                gap: 0;
                position: relative;
            }
            .ph-quickfill-btn {
                padding: 4px 10px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 12px 0 0 12px;
                background: var(--box-color, #ebebeb);
                color: inherit;
                font-size: 13px;
                cursor: pointer;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                transition: opacity 0.15s;
            }
            .ph-quickfill-btn:hover { opacity: 0.7; }
            .ph-quickfill-locate {
                padding: 4px 6px;
                border: 1px solid rgba(128,128,128,0.3);
                border-left: none;
                border-radius: 0 12px 12px 0;
                background: var(--box-color, #ebebeb);
                color: inherit;
                font-size: 10px;
                cursor: pointer;
                opacity: 0.5;
                transition: opacity 0.15s;
            }
            .ph-quickfill-locate:hover { opacity: 1; }
            .ph-pill-popover {
                display: none;
                position: absolute;
                bottom: 100%;
                left: 0;
                background: #1a1a2e;
                border: 1px solid rgba(128,128,128,0.4);
                border-radius: 8px;
                padding: 12px 16px;
                width: 500px;
                max-width: 90vw;
                max-height: 300px;
                overflow-y: auto;
                box-shadow: 0 4px 16px rgba(0,0,0,0.5);
                font-size: 12px;
                line-height: 1.5;
                color: #e2e8f0;
                white-space: normal;
                word-break: break-word;
                z-index: 9999;
                text-align: left;
            }
            .ph-pill-popover.ph-pop-visible { display: block; }
            .ph-pill-popover .ph-pill-pop-title {
                font-weight: 600;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #a0aec0;
                margin-bottom: 6px;
            }
            .ph-pill-popover .ph-pill-pop-prompt {
                font-size: 12px;
                color: #cbd5e0;
                white-space: pre-wrap;
                border-top: 1px solid rgba(128,128,128,0.25);
                padding-top: 8px;
                margin-top: 8px;
            }
            .ph-pill-pop-diff-line {
                padding: 2px 0;
                line-height: 1.5;
            }
            .ph-pill-pop-diff-type {
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.3px;
                display: inline-block;
                min-width: 58px;
                text-align: right;
                margin-right: 6px;
                vertical-align: baseline;
            }
            @keyframes ph-flash {
                0%, 100% { background: transparent; }
                50% { background: rgba(49,130,206,0.25); }
            }
            .ph-flash { animation: ph-flash 0.4s ease 3; }

            #ph-overlay {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 999999;
                background: rgba(0,0,0,0.55);
                justify-content: center;
                align-items: center;
            }
            #ph-overlay.ph-open { display: flex; }

            #ph-modal {
                background: var(--box-color, #fff);
                color: inherit;
                width: 92vw;
                max-width: 800px;
                height: 85vh;
                border-radius: 12px;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                position: relative;
            }

            #ph-modal-header {
                display: flex;
                align-items: center;
                padding: 16px 20px 12px;
                gap: 12px;
                border-bottom: 1px solid rgba(128,128,128,0.2);
                flex-shrink: 0;
            }
            #ph-modal-header h2 {
                margin: 0;
                font-size: 18px;
                flex-shrink: 0;
            }
            #ph-search {
                flex: 1;
                padding: 6px 10px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 6px;
                background: transparent;
                color: inherit;
                font-size: 14px;
                outline: none;
            }
            #ph-search:focus { border-color: rgba(128,128,128,0.6); }
            #ph-close-btn {
                background: none;
                border: none;
                font-size: 22px;
                cursor: pointer;
                color: inherit;
                padding: 0 4px;
                opacity: 0.6;
            }
            #ph-close-btn:hover { opacity: 1; }
            #ph-similarity-slider {
                width: 100%;
                cursor: pointer;
            }
            #ph-similarity-value {
                font-weight: 600;
                font-size: 13px;
            }
            .ph-export-import-row {
                display: flex;
                gap: 8px;
            }
            .ph-export-import-row button {
                flex: 1;
                padding: 6px 0;
                border: 1px solid rgba(128,128,128,0.4);
                border-radius: 6px;
                background: rgba(255,255,255,0.05);
                color: #ddd;
                font-size: 12px;
                cursor: pointer;
            }
            .ph-export-import-row button:hover { background: rgba(255,255,255,0.12); color: #fff; }

            #ph-import-panel {
                display: none;
                margin-top: 10px;
                padding: 12px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 8px;
                background: rgba(0,0,0,0.2);
            }
            #ph-import-panel.visible { display: block; }
            #ph-import-panel .ph-import-info {
                font-size: 12px;
                color: #ccc;
                margin-bottom: 10px;
                line-height: 1.4;
            }
            #ph-import-panel .ph-import-options {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-bottom: 10px;
            }
            #ph-import-panel .ph-import-options label {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 12px;
                cursor: pointer;
                margin: 0;
            }
            #ph-import-panel .ph-import-actions {
                display: flex;
                gap: 8px;
            }
            #ph-import-panel .ph-import-actions button {
                flex: 1;
                padding: 6px 0;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
            }
            #ph-import-panel .ph-import-confirm {
                background: #3182ce;
                color: #fff;
            }
            #ph-import-panel .ph-import-confirm:hover { opacity: 0.85; }
            #ph-import-panel .ph-import-cancel {
                background: transparent;
                border: 1px solid rgba(128,128,128,0.4) !important;
                color: #aaa;
            }
            #ph-import-panel .ph-import-cancel:hover { color: #eee; }
            #ph-import-panel .ph-import-result {
                font-size: 12px;
                margin-top: 8px;
                padding: 8px;
                border-radius: 6px;
                line-height: 1.4;
            }
            #ph-import-panel .ph-import-result.success {
                background: rgba(56,161,105,0.15);
                color: #68d391;
            }
            #ph-import-panel .ph-import-result.error {
                background: rgba(229,62,62,0.15);
                color: #fc8181;
            }

            #ph-filter-bar {
                display: flex;
                gap: 8px;
                padding: 8px 20px;
                border-bottom: 1px solid rgba(128,128,128,0.2);
                flex-shrink: 0;
                flex-wrap: wrap;
            }
            #ph-filter-bar select, #ph-filter-bar input {
                padding: 4px 8px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 4px;
                background: transparent;
                color: inherit;
                font-size: 13px;
            }
            #ph-view-toggle {
                padding: 4px 10px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 4px;
                background: transparent;
                color: inherit;
                font-size: 13px;
                cursor: pointer;
                margin-left: auto;
            }
            #ph-expand-all {
                padding: 4px 10px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 4px;
                background: transparent;
                color: inherit;
                font-size: 13px;
                cursor: pointer;
            }
            #ph-view-toggle:hover, #ph-expand-all:hover { background: rgba(128,128,128,0.12); }
            .ph-rename-btn {
                background: none;
                border: none;
                cursor: pointer;
                font-size: 13px;
                padding: 0 4px;
                opacity: 0.45;
                color: inherit;
                flex-shrink: 0;
            }
            .ph-rename-btn:hover { opacity: 0.85; }

            #ph-groups-ctn {
                flex: 1;
                overflow-y: auto;
                padding: 12px 20px;
            }

            .ph-empty-state {
                text-align: center;
                padding: 60px 20px;
                opacity: 0.5;
                font-size: 15px;
            }

            .ph-group {
                border: 1px solid rgba(128,128,128,0.2);
                border-radius: 8px;
                margin-bottom: 10px;
                overflow: hidden;
            }
            .ph-group-header {
                display: flex;
                align-items: center;
                padding: 10px 14px;
                cursor: pointer;
                gap: 10px;
                user-select: none;
            }
            .ph-group-header:hover { background: rgba(128,128,128,0.08); }
            .ph-group-arrow {
                font-size: 12px;
                transition: transform 0.15s;
                flex-shrink: 0;
            }
            .ph-group.ph-expanded .ph-group-arrow { transform: rotate(90deg); }
            .ph-group-select-all {
                flex-shrink: 0;
                width: 16px;
                height: 16px;
                cursor: pointer;
            }
            .ph-group-name {
                flex: 0 1 auto;
                font-weight: 600;
                font-size: 14px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                min-width: 0;
                text-align: left;
            }
            .ph-group-name-input {
                flex: 1;
                font-weight: 600;
                font-size: 14px;
                background: transparent;
                border: 1px solid rgba(128,128,128,0.4);
                border-radius: 4px;
                color: inherit;
                padding: 2px 6px;
                min-width: 0;
            }
            .ph-group-meta {
                font-size: 12px;
                opacity: 0.6;
                white-space: nowrap;
                flex-shrink: 0;
            }
            .ph-group-preview {
                font-size: 12px;
                opacity: 0.5;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                flex: 1;
                min-width: 0;
            }
            .ph-group.ph-expanded .ph-group-preview,
            .ph-detailed .ph-group-preview {
                display: none;
            }
            .ph-group-move-target {
                padding: 4px 10px;
                border: none;
                border-radius: 4px;
                background: #2bbb00;
                color: #fff;
                font-size: 12px;
                cursor: pointer;
                flex-shrink: 0;
                display: none;
            }
            .ph-group-move-target:hover { opacity: 0.85; }
            .ph-has-selection .ph-group-move-target { display: block; }

            .ph-group-body {
                display: none;
                border-top: 1px solid rgba(128,128,128,0.15);
            }
            .ph-group.ph-expanded .ph-group-body { display: block; }

            .ph-prompt {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px 14px;
                border-bottom: 1px solid rgba(128,128,128,0.08);
                font-size: 13px;
            }
            .ph-prompt:last-child { border-bottom: none; }
            .ph-prompt-check {
                flex-shrink: 0;
                width: 16px;
                height: 16px;
                cursor: pointer;
            }
            .ph-prompt-text {
                flex: 1;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                min-width: 0;
                cursor: default;
            }
            .ph-detailed .ph-prompt {
                align-items: flex-start;
            }
            .ph-detailed .ph-prompt-text {
                white-space: pre-wrap;
                overflow: visible;
                text-overflow: unset;
                text-align: left;
            }
            .ph-prompt-time {
                font-size: 11px;
                opacity: 0.55;
                white-space: nowrap;
                flex-shrink: 0;
            }
            .ph-prompt-actions {
                display: flex;
                gap: 4px;
                flex-shrink: 0;
            }
            .ph-prompt-actions button {
                background: none;
                border: 1px solid rgba(128,128,128,0.25);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
                cursor: pointer;
                color: inherit;
            }
            .ph-prompt-actions button:hover { background: rgba(128,128,128,0.15); }

            #ph-action-bar {
                display: none;
                position: sticky;
                bottom: 0;
                background: var(--box-color, #fff);
                border-top: 1px solid rgba(128,128,128,0.25);
                padding: 10px 20px;
                gap: 8px;
                justify-content: center;
                flex-shrink: 0;
            }
            #ph-action-bar.ph-visible { display: flex; }
            #ph-action-bar button {
                padding: 6px 16px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                color: #fff;
            }
            #ph-action-bar .ph-delete-sel { background: #e53e3e; }
            #ph-action-bar .ph-move-new { background: #3182ce; }
            #ph-action-bar .ph-compare-sel { background: #805ad5; }
            #ph-action-bar .ph-count { color: inherit; background: none; font-size: 13px; opacity: 0.7; cursor: default; }

            #ph-compare-overlay {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 1000000;
                background: rgba(0,0,0,0.5);
                justify-content: center;
                align-items: center;
            }
            #ph-compare-overlay.ph-open { display: flex; }
            #ph-compare-modal {
                background: var(--box-color, #fff);
                color: inherit;
                width: 850px;
                max-width: 94vw;
                max-height: 85vh;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.3);
                overflow-y: auto;
            }
            #ph-compare-modal h3 { margin: 0 0 14px; font-size: 16px; }
            .ph-diff-label {
                font-size: 11px;
                font-weight: 600;
                opacity: 0.5;
                margin-bottom: 4px;
            }
            .ph-diff-body {
                font-size: 14px;
                line-height: 1.6;
                white-space: pre-wrap;
                word-break: break-word;
                padding: 10px;
                border: 1px solid rgba(128,128,128,0.2);
                border-radius: 6px;
                margin-bottom: 14px;
            }
            .ph-diff-del {
                background: rgba(229,62,62,0.2);
                text-decoration: line-through;
                color: #e53e3e;
            }
            .ph-diff-ins {
                background: rgba(56,161,105,0.2);
                color: #38a169;
            }
            .ph-diff-columns {
                display: flex;
                gap: 14px;
            }
            .ph-diff-col {
                flex: 1;
                min-width: 0;
            }
            .ph-diff-inline-section { display: block; }
            .ph-diff-columns-section { display: flex; }
            @media (max-width: 600px) {
                .ph-diff-inline-section { display: block; }
                .ph-diff-columns-section { display: none; }
            }
            #ph-compare-close {
                display: block;
                margin: 8px 0 0 auto;
                padding: 6px 16px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 6px;
                background: transparent;
                color: inherit;
                cursor: pointer;
                font-size: 13px;
            }

            #ph-view-overlay {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 1000000;
                background: rgba(0,0,0,0.5);
                justify-content: center;
                align-items: center;
            }
            #ph-view-overlay.ph-open { display: flex; }
            #ph-view-modal {
                background: var(--box-color, #fff);
                color: inherit;
                width: 500px;
                max-width: 90vw;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            }
            #ph-view-modal h3 { margin: 0 0 12px; font-size: 16px; }
            #ph-view-textarea {
                width: 100%;
                min-height: 120px;
                padding: 10px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 6px;
                background: transparent;
                color: inherit;
                font-size: 14px;
                resize: vertical;
                font-family: inherit;
                box-sizing: border-box;
            }
            #ph-view-btns {
                display: flex;
                gap: 8px;
                justify-content: flex-end;
                margin-top: 12px;
            }
            #ph-view-btns button {
                padding: 6px 16px;
                border: 1px solid rgba(128,128,128,0.3);
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                background: transparent;
                color: inherit;
            }
            #ph-view-btns .ph-view-save { background: #3182ce; color: #fff; border: none; }

            @media (max-width: 600px) {
                #ph-modal { width: 98vw; height: 92vh; border-radius: 8px; }
                .ph-prompt { flex-wrap: wrap; gap: 6px; }
                .ph-group-preview { max-width: 150px; }
            }

            #ph-nested-indicator {
                display: none;
                align-items: center;
                gap: 6px;
                padding: 4px 10px;
                font-size: 12px;
                color: #a0aec0;
                cursor: default;
                position: relative;
                justify-content: center;
            }
            #ph-nested-indicator.visible { display: flex; }
            #ph-nested-indicator .ph-nested-badge {
                font-family: monospace;
                font-weight: 700;
                font-size: 13px;
                opacity: 0.7;
            }
            #ph-nested-popover {
                display: none;
                position: absolute;
                bottom: calc(100% + 6px);
                left: 50%;
                transform: translateX(-50%);
                background: #1a1a2e;
                border: 1px solid rgba(128,128,128,0.4);
                border-radius: 8px;
                padding: 12px 16px;
                max-width: 500px;
                min-width: 200px;
                max-height: 200px;
                overflow-y: auto;
                box-shadow: 0 4px 16px rgba(0,0,0,0.5);
                font-size: 12px;
                line-height: 1.5;
                color: #e2e8f0;
                white-space: pre-wrap;
                word-break: break-word;
                z-index: 9999;
            }
            #ph-nested-indicator:hover #ph-nested-popover { display: block; }
            #ph-nested-popover .ph-nested-title {
                font-weight: 600;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #a0aec0;
                margin-bottom: 6px;
            }

            .ph-nested-badge-inline {
                display: inline-block;
                font-family: monospace;
                font-size: 10px;
                font-weight: 700;
                padding: 1px 5px;
                border-radius: 3px;
                background: rgba(128,90,213,0.15);
                color: #b794f4;
                margin-left: 6px;
                vertical-align: middle;
            }

            .ph-reuse-pill {
                display: inline-flex;
                border-radius: 4px;
                overflow: hidden;
                border: 1px solid rgba(128,128,128,0.25);
            }
            .ph-reuse-pill button {
                background: none;
                border: none;
                border-radius: 0;
                padding: 2px 8px;
                font-size: 12px;
                cursor: pointer;
                color: inherit;
            }
            .ph-reuse-pill button:hover { background: rgba(128,128,128,0.15); }
            .ph-reuse-pill button + button {
                border-left: 1px solid rgba(128,128,128,0.25);
            }
        `;
        document.head.appendChild(style);
    }

    // ---- Overlay DOM ----

    function createOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'ph-overlay';
        overlay.innerHTML = `
            <div id="ph-modal">
                <div id="ph-modal-header">
                    <h2>Prompt History</h2>
                    <input id="ph-search" type="text" placeholder="Search prompts..." />
                    <button id="ph-close-btn" title="Close">&times;</button>
                </div>
                <div id="ph-filter-bar">
                    <select id="ph-filter-style"><option value="">All styles</option></select>
                    <input id="ph-filter-date-from" type="date" title="From date" />
                    <input id="ph-filter-date-to" type="date" title="To date" />
                    <button id="ph-view-toggle">Detailed view</button>
                    <button id="ph-expand-all">Expand all</button>
                </div>
                <div id="ph-groups-ctn"></div>
                <div id="ph-action-bar">
                    <button class="ph-count"></button>
                    <button class="ph-compare-sel">Compare</button>
                    <button class="ph-delete-sel">Delete</button>
                    <button class="ph-move-new">Move to new group</button>
                </div>
            </div>
        `;

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeOverlay();
        });
        overlay.querySelector('#ph-close-btn').addEventListener('click', closeOverlay);

        overlay.querySelector('#ph-search').addEventListener('input', debounce(renderGroups, 200));
        overlay.querySelector('#ph-filter-style').addEventListener('change', renderGroups);
        overlay.querySelector('#ph-filter-date-from').addEventListener('change', renderGroups);
        overlay.querySelector('#ph-filter-date-to').addEventListener('change', renderGroups);
        overlay.querySelector('#ph-view-toggle').addEventListener('click', toggleDetailedView);
        overlay.querySelector('#ph-expand-all').addEventListener('click', toggleExpandAll);

        overlay.querySelector('.ph-compare-sel').addEventListener('click', compareSelected);
        overlay.querySelector('.ph-delete-sel').addEventListener('click', deleteSelected);
        overlay.querySelector('.ph-move-new').addEventListener('click', moveSelectedToNewGroup);

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('ph-open')) closeOverlay();
        });

        document.body.appendChild(overlay);
        return overlay;
    }

    let selectedPromptIds = new Set();

    function openOverlay() {
        let overlay = document.getElementById('ph-overlay');
        if (!overlay) overlay = createOverlay();
        selectedPromptIds.clear();
        overlay.classList.add('ph-open');
        populateStyleFilter();
        renderGroups();
        applyDetailedView();
        const ctn = document.getElementById('ph-groups-ctn');
        if (ctn) ctn.scrollTop = overlayScrollTop;
    }

    function closeOverlay() {
        const overlay = document.getElementById('ph-overlay');
        if (!overlay) return;
        const ctn = document.getElementById('ph-groups-ctn');
        if (ctn) overlayScrollTop = ctn.scrollTop;
        selectedPromptIds.clear();
        overlay.classList.remove('ph-open');
    }

    async function populateStyleFilter() {
        const sel = document.getElementById('ph-filter-style');
        if (!sel) return;
        const allPrompts = await getAllPrompts();
        const styles = [...new Set(allPrompts.map(p => p.artStyle).filter(Boolean))].sort();
        const current = sel.value;
        sel.innerHTML = '<option value="">All styles</option>';
        for (const s of styles) {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            sel.appendChild(opt);
        }
        sel.value = current;
    }

    function debounce(fn, ms) {
        let timer;
        return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
    }

    async function renderGroups() {
        const ctn = document.getElementById('ph-groups-ctn');
        if (!ctn) return;

        const searchTerm = (document.getElementById('ph-search')?.value || '').toLowerCase().trim();
        const styleFilter = document.getElementById('ph-filter-style')?.value || '';
        const dateFrom = document.getElementById('ph-filter-date-from')?.value;
        const dateTo = document.getElementById('ph-filter-date-to')?.value;
        const dateFromTs = dateFrom ? new Date(dateFrom).getTime() : 0;
        const dateToTs = dateTo ? new Date(dateTo + 'T23:59:59').getTime() : Infinity;

        const allGroups = await getAllGroups();
        const allPrompts = await getAllPrompts();

        if (allGroups.length === 0) {
            ctn.innerHTML = '<div class="ph-empty-state">Your prompt history will appear here</div>';
            updateActionBar();
            return;
        }

        const promptsByGroup = {};
        for (const p of allPrompts) {
            if (!promptsByGroup[p.groupId]) promptsByGroup[p.groupId] = [];
            promptsByGroup[p.groupId].push(p);
        }

        let filteredGroups = allGroups.map(g => {
            let prompts = promptsByGroup[g.id] || [];
            if (searchTerm) prompts = prompts.filter(p => p.text.toLowerCase().includes(searchTerm));
            if (styleFilter) prompts = prompts.filter(p => p.artStyle === styleFilter);
            if (dateFromTs > 0 || dateToTs < Infinity) {
                prompts = prompts.filter(p => {
                    const latest = Math.max(...p.timestamps);
                    return latest >= dateFromTs && latest <= dateToTs;
                });
            }
            return { group: g, prompts };
        }).filter(x => x.prompts.length > 0);

        filteredGroups.sort((a, b) => b.group.updatedAt - a.group.updatedAt);

        for (const item of filteredGroups) {
            item.prompts.sort((a, b) => Math.max(...b.timestamps) - Math.max(...a.timestamps));
        }

        const expandedIds = new Set();
        for (const el of ctn.querySelectorAll('.ph-group.ph-expanded')) {
            if (el.dataset.groupId) expandedIds.add(el.dataset.groupId);
        }

        ctn.innerHTML = '';
        const hasSelection = selectedPromptIds.size > 0;

        for (const { group, prompts } of filteredGroups) {
            const gDiv = document.createElement('div');
            gDiv.className = 'ph-group';
            if (expandedIds.has(String(group.id))) gDiv.classList.add('ph-expanded');
            gDiv.dataset.groupId = group.id;

            const latest = prompts[0];
            const latestTs = Math.max(...latest.timestamps);

            const headerDiv = document.createElement('div');
            headerDiv.className = 'ph-group-header';
            headerDiv.innerHTML = `
                <span class="ph-group-arrow">&#9654;</span>
                <input type="checkbox" class="ph-group-select-all" title="Select all in group" />
                <span class="ph-group-name" title="${escHtml(group.name)}">${escHtml(group.name)}</span>
                <button class="ph-rename-btn" title="Rename group">&#9998;</button>
                <span class="ph-group-preview" title="${escHtml(latest.text)}">${escHtml(latest.text)}</span>
                <span class="ph-group-meta">${prompts.length} prompt${prompts.length > 1 ? 's' : ''} &middot; ${formatTime(latestTs)}</span>
                <button class="ph-group-move-target" data-target-group="${group.id}">Move here</button>
            `;

            headerDiv.querySelector('.ph-rename-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                startRename(gDiv, group);
            });

            const selectAll = headerDiv.querySelector('.ph-group-select-all');
            const allChecked = prompts.every(p => selectedPromptIds.has(p.id));
            selectAll.checked = allChecked;
            selectAll.addEventListener('click', (e) => { e.stopPropagation(); });
            selectAll.addEventListener('change', (e) => {
                e.stopPropagation();
                for (const p of prompts) {
                    if (selectAll.checked) selectedPromptIds.add(p.id);
                    else selectedPromptIds.delete(p.id);
                }
                renderGroups();
            });

            const moveBtn = headerDiv.querySelector('.ph-group-move-target');
            const groupPromptIds = new Set(prompts.map(p => p.id));
            const allSelectedInThisGroup = selectedPromptIds.size > 0 && [...selectedPromptIds].every(id => groupPromptIds.has(id));
            if (allSelectedInThisGroup) moveBtn.style.display = 'none';
            moveBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await moveSelectedToGroup(group.id);
            });

            headerDiv.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;
                gDiv.classList.toggle('ph-expanded');
            });

            gDiv.appendChild(headerDiv);

            const bodyDiv = document.createElement('div');
            bodyDiv.className = 'ph-group-body';

            for (const p of prompts) {
                const pDiv = document.createElement('div');
                pDiv.className = 'ph-prompt';
                pDiv.dataset.promptId = p.id;

                const latestPTs = Math.max(...p.timestamps);
                const countLabel = p.timestamps.length > 1 ? ` (${p.timestamps.length}x)` : '';
                const nestedBadge = p.hasNested ? '<span class="ph-nested-badge-inline">{·}</span>' : '';

                const reuseHtml = p.hasNested
                    ? `<span class="ph-reuse-pill"><button class="ph-reuse-btn" title="Reuse template">Reuse</button><button class="ph-reuse-flat-btn" title="Reuse flattened (no nesting)">Flat</button></span>`
                    : `<span class="ph-reuse-pill"><button class="ph-reuse-btn" title="Reuse this prompt">Reuse</button></span>`;

                pDiv.innerHTML = `
                    <input type="checkbox" class="ph-prompt-check" ${selectedPromptIds.has(p.id) ? 'checked' : ''} />
                    <span class="ph-prompt-text" title="${escHtml(p.text)}">${escHtml(p.text)}${nestedBadge}</span>
                    <span class="ph-prompt-time">${formatTime(latestPTs)}${countLabel}</span>
                    <span class="ph-prompt-actions">
                        <button class="ph-view-btn" title="View/edit prompt">${isDetailedView ? 'Edit' : 'View'}</button>
                        ${reuseHtml}
                        <button class="ph-delete-btn" title="Delete">&#10005;</button>
                    </span>
                `;

                pDiv.querySelector('.ph-prompt-check').addEventListener('change', (e) => {
                    if (e.target.checked) selectedPromptIds.add(p.id);
                    else selectedPromptIds.delete(p.id);
                    updateActionBar();
                    updateMoveTargetVisibility();
                    updateGroupCheckboxes();
                });

                pDiv.querySelector('.ph-view-btn').addEventListener('click', () => viewPrompt(p));
                pDiv.querySelector('.ph-reuse-btn').addEventListener('click', () => reusePrompt(p));
                const flatBtn = pDiv.querySelector('.ph-reuse-flat-btn');
                if (flatBtn) flatBtn.addEventListener('click', () => reusePromptFlat(p));
                pDiv.querySelector('.ph-delete-btn').addEventListener('click', () => deleteSinglePrompt(p));

                bodyDiv.appendChild(pDiv);
            }

            gDiv.appendChild(bodyDiv);
            ctn.appendChild(gDiv);
        }

        if (hasSelection) {
            ctn.classList.add('ph-has-selection');
        } else {
            ctn.classList.remove('ph-has-selection');
        }

        updateActionBar();
        updateMoveTargetVisibility();
    }

    function escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function updateActionBar() {
        const bar = document.getElementById('ph-action-bar');
        if (!bar) return;
        const n = selectedPromptIds.size;
        if (n > 0) {
            bar.classList.add('ph-visible');
            let countText = `${n} selected`;
            if (n === 1) countText += ' (select 2 to compare)';
            else if (n > 2) countText += ' (select only 2 to compare)';
            bar.querySelector('.ph-count').textContent = countText;
        } else {
            bar.classList.remove('ph-visible');
        }
        const cmpBtn = bar.querySelector('.ph-compare-sel');
        if (cmpBtn) {
            cmpBtn.disabled = n !== 2;
            cmpBtn.style.opacity = n === 2 ? '1' : '0.4';
            cmpBtn.style.cursor = n === 2 ? 'pointer' : 'default';
        }
    }

    function updateMoveTargetVisibility() {
        const ctn = document.getElementById('ph-groups-ctn');
        if (!ctn) return;
        if (selectedPromptIds.size > 0) {
            ctn.classList.add('ph-has-selection');
        } else {
            ctn.classList.remove('ph-has-selection');
        }
    }

    function updateGroupCheckboxes() {
        const ctn = document.getElementById('ph-groups-ctn');
        if (!ctn) return;
        for (const gDiv of ctn.querySelectorAll('.ph-group')) {
            const checks = gDiv.querySelectorAll('.ph-prompt-check');
            const selectAll = gDiv.querySelector('.ph-group-select-all');
            if (!selectAll || checks.length === 0) continue;
            selectAll.checked = [...checks].every(c => c.checked);
        }
    }

    let isDetailedView = localStorage.getItem('ph-detailed-view') === 'true';

    function toggleDetailedView() {
        isDetailedView = !isDetailedView;
        localStorage.setItem('ph-detailed-view', isDetailedView);
        applyDetailedView();
    }

    function applyDetailedView() {
        const ctn = document.getElementById('ph-groups-ctn');
        const btn = document.getElementById('ph-view-toggle');
        if (ctn) {
            if (isDetailedView) ctn.classList.add('ph-detailed');
            else ctn.classList.remove('ph-detailed');
        }
        if (btn) btn.textContent = isDetailedView ? 'Compact view' : 'Detailed view';
        for (const viewBtn of document.querySelectorAll('.ph-view-btn')) {
            viewBtn.textContent = isDetailedView ? 'Edit' : 'View';
        }
    }

    function toggleExpandAll() {
        const ctn = document.getElementById('ph-groups-ctn');
        const btn = document.getElementById('ph-expand-all');
        if (!ctn) return;
        const groups = ctn.querySelectorAll('.ph-group');
        const allExpanded = [...groups].every(g => g.classList.contains('ph-expanded'));
        for (const g of groups) {
            if (allExpanded) g.classList.remove('ph-expanded');
            else g.classList.add('ph-expanded');
        }
        if (btn) btn.textContent = allExpanded ? 'Expand all' : 'Collapse all';
    }

    // ---- Group rename ----

    function startRename(gDiv, group) {
        const nameSpan = gDiv.querySelector('.ph-group-name');
        if (!nameSpan) return;

        const renameBtn = gDiv.querySelector('.ph-rename-btn');

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'ph-group-name-input';
        input.value = group.name;

        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';
        saveBtn.style.cssText = 'padding:2px 10px;border:none;border-radius:4px;background:#3182ce;color:#fff;font-size:12px;cursor:pointer;flex-shrink:0;';

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';
        cancelBtn.style.cssText = 'padding:2px 8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:transparent;color:inherit;font-size:12px;cursor:pointer;flex-shrink:0;';

        nameSpan.replaceWith(input);
        if (renameBtn) renameBtn.replaceWith(saveBtn);
        input.parentNode.insertBefore(cancelBtn, saveBtn.nextSibling);

        input.focus();
        input.select();

        let done = false;
        const finish = async (save) => {
            if (done) return;
            done = true;
            if (save) {
                group.name = input.value.trim() || group.name;
                await putGroup(group);
            }
            renderGroups();
        };

        saveBtn.addEventListener('click', (e) => { e.stopPropagation(); finish(true); });
        cancelBtn.addEventListener('click', (e) => { e.stopPropagation(); finish(false); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') finish(true);
            if (e.key === 'Escape') finish(false);
        });
        input.addEventListener('click', (e) => e.stopPropagation());
    }

    // ---- Actions ----

    async function deleteSinglePrompt(prompt) {
        await deletePrompt(prompt.id);
        selectedPromptIds.delete(prompt.id);
        const remaining = await getPromptsByGroup(prompt.groupId);
        if (remaining.length === 0) await deleteGroup(prompt.groupId);
        renderGroups();
    }

    async function deleteSelected() {
        const ids = [...selectedPromptIds];
        const allP = await getAllPrompts();
        const affectedGroups = new Set();
        for (const id of ids) {
            const p = allP.find(x => x.id === id);
            if (p) affectedGroups.add(p.groupId);
            await deletePrompt(id);
        }
        selectedPromptIds.clear();
        for (const gid of affectedGroups) {
            const remaining = await getPromptsByGroup(gid);
            if (remaining.length === 0) await deleteGroup(gid);
        }
        renderGroups();
    }

    async function moveSelectedToGroup(targetGroupId) {
        const ids = [...selectedPromptIds];
        const allP = await getAllPrompts();
        const sourceGroups = new Set();
        for (const id of ids) {
            const p = allP.find(x => x.id === id);
            if (p) {
                sourceGroups.add(p.groupId);
                p.groupId = targetGroupId;
                await putPrompt(p);
            }
        }
        const targetGroup = await getGroup(targetGroupId);
        if (targetGroup) { targetGroup.updatedAt = Date.now(); await putGroup(targetGroup); }

        selectedPromptIds.clear();
        for (const gid of sourceGroups) {
            const remaining = await getPromptsByGroup(gid);
            if (remaining.length === 0) await deleteGroup(gid);
        }
        renderGroups();
    }

    async function moveSelectedToNewGroup() {
        const ids = [...selectedPromptIds];
        if (ids.length === 0) return;

        const allP = await getAllPrompts();
        const first = allP.find(x => x.id === ids[0]);
        const name = first ? groupName(first.text) : 'New Group';
        const now = Date.now();

        const newGroupId = await addGroup({ name, createdAt: now, updatedAt: now });

        const sourceGroups = new Set();
        for (const id of ids) {
            const p = allP.find(x => x.id === id);
            if (p) {
                sourceGroups.add(p.groupId);
                p.groupId = newGroupId;
                await putPrompt(p);
            }
        }

        selectedPromptIds.clear();
        for (const gid of sourceGroups) {
            const remaining = await getPromptsByGroup(gid);
            if (remaining.length === 0) await deleteGroup(gid);
        }
        renderGroups();
    }

    // ---- Compare ----

    function lcsWords(a, b) {
        const m = a.length, n = b.length;
        const dp = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                dp[i][j] = a[i - 1] === b[j - 1]
                    ? dp[i - 1][j - 1] + 1
                    : Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
        const result = [];
        let i = m, j = n;
        while (i > 0 && j > 0) {
            if (a[i - 1] === b[j - 1]) {
                result.unshift({ type: 'equal', word: a[i - 1] });
                i--; j--;
            } else if (dp[i - 1][j] >= dp[i][j - 1]) {
                result.unshift({ type: 'del', word: a[i - 1] });
                i--;
            } else {
                result.unshift({ type: 'ins', word: b[j - 1] });
                j--;
            }
        }
        while (i > 0) { result.unshift({ type: 'del', word: a[--i] }); }
        while (j > 0) { result.unshift({ type: 'ins', word: b[--j] }); }
        return result;
    }

    function renderDiffInline(ops) {
        let html = '';
        for (const op of ops) {
            const w = escHtml(op.word);
            if (op.type === 'equal') html += w + ' ';
            else if (op.type === 'del') html += `<span class="ph-diff-del">${w}</span> `;
            else html += `<span class="ph-diff-ins">${w}</span> `;
        }
        return html.trim();
    }

    function renderDiffSide(ops, side) {
        let html = '';
        for (const op of ops) {
            const w = escHtml(op.word);
            if (op.type === 'equal') html += w + ' ';
            else if (op.type === 'del' && side === 'older') html += `<span class="ph-diff-del">${w}</span> `;
            else if (op.type === 'ins' && side === 'newer') html += `<span class="ph-diff-ins">${w}</span> `;
        }
        return html.trim();
    }

    async function compareSelected() {
        const ids = [...selectedPromptIds];
        if (ids.length !== 2) return;

        const pA = await getPrompt(ids[0]);
        const pB = await getPrompt(ids[1]);
        if (!pA || !pB) return;

        const [older, newer] = Math.max(...pA.timestamps) <= Math.max(...pB.timestamps)
            ? [pA, pB] : [pB, pA];

        const ops = lcsWords(older.text.split(/\s+/), newer.text.split(/\s+/));
        const inlineHtml = renderDiffInline(ops);
        const olderHtml = renderDiffSide(ops, 'older');
        const newerHtml = renderDiffSide(ops, 'newer');
        const olderTime = formatTime(Math.max(...older.timestamps));
        const newerTime = formatTime(Math.max(...newer.timestamps));

        let cmpOverlay = document.getElementById('ph-compare-overlay');
        if (!cmpOverlay) {
            cmpOverlay = document.createElement('div');
            cmpOverlay.id = 'ph-compare-overlay';
            cmpOverlay.innerHTML = `
                <div id="ph-compare-modal">
                    <h3>Compare Prompts</h3>
                    <div class="ph-diff-inline-section">
                        <div class="ph-diff-label">DIFF</div>
                        <div class="ph-diff-body ph-diff-result"></div>
                    </div>
                    <div class="ph-diff-columns-section ph-diff-columns">
                        <div class="ph-diff-col">
                            <div class="ph-diff-label ph-diff-older-label"></div>
                            <div class="ph-diff-body ph-diff-older"></div>
                        </div>
                        <div class="ph-diff-col">
                            <div class="ph-diff-label ph-diff-newer-label"></div>
                            <div class="ph-diff-body ph-diff-newer"></div>
                        </div>
                    </div>
                    <button id="ph-compare-close">Close</button>
                </div>
            `;
            cmpOverlay.addEventListener('click', (e) => {
                if (e.target === cmpOverlay) cmpOverlay.classList.remove('ph-open');
            });
            cmpOverlay.querySelector('#ph-compare-close').addEventListener('click', () => {
                cmpOverlay.classList.remove('ph-open');
            });
            document.body.appendChild(cmpOverlay);
        }

        cmpOverlay.querySelector('.ph-diff-older-label').textContent = `OLDER — ${olderTime}`;
        cmpOverlay.querySelector('.ph-diff-newer-label').textContent = `NEWER — ${newerTime}`;
        cmpOverlay.querySelector('.ph-diff-result').innerHTML = inlineHtml;
        cmpOverlay.querySelector('.ph-diff-older').innerHTML = olderHtml;
        cmpOverlay.querySelector('.ph-diff-newer').innerHTML = newerHtml;
        cmpOverlay.classList.add('ph-open');
    }

    function viewPrompt(prompt) {
        let viewOverlay = document.getElementById('ph-view-overlay');
        if (!viewOverlay) {
            viewOverlay = document.createElement('div');
            viewOverlay.id = 'ph-view-overlay';
            viewOverlay.innerHTML = `
                <div id="ph-view-modal">
                    <h3>View / Edit Prompt</h3>
                    <textarea id="ph-view-textarea"></textarea>
                    <div id="ph-view-btns">
                        <button class="ph-view-cancel">Cancel</button>
                        <button class="ph-view-save">Save</button>
                    </div>
                </div>
            `;
            viewOverlay.addEventListener('click', (e) => {
                if (e.target === viewOverlay) viewOverlay.classList.remove('ph-open');
            });
            viewOverlay.querySelector('.ph-view-cancel').addEventListener('click', () => {
                viewOverlay.classList.remove('ph-open');
            });
            document.body.appendChild(viewOverlay);
        }

        const textarea = viewOverlay.querySelector('#ph-view-textarea');
        textarea.value = prompt.text;
        viewOverlay.classList.add('ph-open');
        textarea.focus();

        const saveBtn = viewOverlay.querySelector('.ph-view-save');
        const newSaveBtn = saveBtn.cloneNode(true);
        saveBtn.replaceWith(newSaveBtn);
        newSaveBtn.addEventListener('click', async () => {
            const newText = textarea.value.trim();
            if (newText && newText !== prompt.text) {
                const fresh = await getPrompt(prompt.id);
                if (fresh) {
                    fresh.text = newText;
                    await putPrompt(fresh);
                }
                renderGroups();
            }
            viewOverlay.classList.remove('ph-open');
        });
    }

    async function reusePrompt(prompt) {
        const { description, artStyle, negativePrompt, resolution } = getCurrentInputs();
        const trimmed = description.trim();
        if (trimmed) {
            try {
                await capturePrompt(trimmed, artStyle, negativePrompt, resolution, null);
            } catch (e) {
                console.error('[Prompt History] auto-save on reuse failed:', e);
            }
        }

        const descEl = document.querySelector('textarea[data-name="description"]')
            || document.querySelector('.paragraph-input')
            || document.querySelector('textarea');
        if (descEl) {
            descEl.value = prompt.text;
            descEl.dispatchEvent(new Event('input', { bubbles: true }));
        }

        reusedFromGroupId = prompt.groupId;
        closeOverlay();
    }

    async function reusePromptFlat(prompt) {
        const flatText = flattenNestedSelectors(prompt.text);
        const { description, artStyle, negativePrompt, resolution } = getCurrentInputs();
        const trimmed = description.trim();
        if (trimmed) {
            try {
                await capturePrompt(trimmed, artStyle, negativePrompt, resolution, null);
            } catch (e) {
                console.error('[Prompt History] auto-save on reuse failed:', e);
            }
        }

        const descEl = document.querySelector('textarea[data-name="description"]')
            || document.querySelector('.paragraph-input')
            || document.querySelector('textarea');
        if (descEl) {
            descEl.value = flatText;
            descEl.dispatchEvent(new Event('input', { bubbles: true }));
        }

        reusedFromGroupId = prompt.groupId;
        closeOverlay();
    }

    // ---- Inject history button ----

    function injectHistoryButton() {
        const poll = setInterval(() => {
            const genBtn = document.getElementById('generateButtonEl');
            if (!genBtn) return;
            if (document.getElementById('ph-history-btn')) { clearInterval(poll); return; }
            clearInterval(poll);

            const btn = document.createElement('button');
            btn.id = 'ph-history-btn';
            btn.type = 'button';
            btn.innerHTML = '&#128339; History';
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                openOverlay();
            });

            const wrapper = document.createElement('span');
            wrapper.id = 'ph-gen-row-wrapper';
            genBtn.parentNode.insertBefore(wrapper, genBtn);
            wrapper.appendChild(genBtn);
            wrapper.appendChild(btn);
        }, 300);
    }

    // ---- Nested selector indicator ----

    function injectNestedIndicator() {
        const descEl = document.querySelector('textarea[data-name="description"]')
            || document.querySelector('.paragraph-input')
            || document.querySelector('textarea');
        if (!descEl) return;

        const genBtn = document.getElementById('generateButtonEl');
        if (!genBtn) return;

        let container = document.getElementById('ph-nested-indicator');
        if (container) return;

        container = document.createElement('div');
        container.id = 'ph-nested-indicator';
        container.innerHTML = `
            <span class="ph-nested-badge">{·}</span>
            <span>Nested selectors — hover to preview expansion</span>
            <div id="ph-nested-popover">
                <div class="ph-nested-title">Expanded form</div>
                <div id="ph-nested-popover-body"></div>
            </div>
        `;

        const genRow = genBtn.closest('#ph-gen-row-wrapper') || genBtn.parentNode;
        genRow.parentNode.insertBefore(container, genRow);

        const popoverBody = container.querySelector('#ph-nested-popover-body');

        const update = () => {
            const text = descEl.value || '';
            if (containsNestedSelectors(text)) {
                container.classList.add('visible');
                try {
                    const flat = flattenNestedSelectors(text);
                    popoverBody.textContent = flat;
                } catch (e) {
                    popoverBody.textContent = '(error expanding)';
                }
            } else {
                container.classList.remove('visible');
            }
        };

        descEl.addEventListener('input', update);
        update();
    }

    // ---- Quick-fill buttons ----

    function locateInHistory(groupId, promptId) {
        openOverlay();
        setTimeout(() => {
            const ctn = document.getElementById('ph-groups-ctn');
            if (!ctn) return;
            const gDiv = ctn.querySelector(`.ph-group[data-group-id="${groupId}"]`);
            if (!gDiv) return;
            gDiv.classList.add('ph-expanded');
            setTimeout(() => {
                const pDiv = gDiv.querySelector(`.ph-prompt[data-prompt-id="${promptId}"]`);
                if (!pDiv) return;
                pDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
                pDiv.classList.add('ph-flash');
                pDiv.addEventListener('animationend', () => pDiv.classList.remove('ph-flash'), { once: true });
            }, 50);
        }, 100);
    }

    async function refreshQuickFill() {
        if (!historyDB) return;

        const descEl = document.querySelector('textarea[data-name="description"]')
            || document.querySelector('.paragraph-input')
            || document.querySelector('textarea');
        if (!descEl) return;

        const genBtn = document.getElementById('generateButtonEl');
        if (!genBtn) return;

        let container = document.getElementById('ph-quickfill');
        if (!container) {
            container = document.createElement('div');
            container.id = 'ph-quickfill';
            const genRow = genBtn.parentNode;
            genRow.parentNode.insertBefore(container, genRow);
        }

        const allGroups = await getAllGroups();
        const allPrompts = await getAllPrompts();
        if (allPrompts.length === 0) { container.innerHTML = ''; return; }

        const promptsByGroup = {};
        for (const p of allPrompts) {
            if (!promptsByGroup[p.groupId]) promptsByGroup[p.groupId] = [];
            promptsByGroup[p.groupId].push(p);
        }

        const sortedGroups = allGroups
            .filter(g => promptsByGroup[g.id] && promptsByGroup[g.id].length > 0)
            .sort((a, b) => b.updatedAt - a.updatedAt);

        const currentPlaceholder = descEl.placeholder || '';
        const currentValue = descEl.value || '';

        const chronoByGroup = {};
        for (const gid of Object.keys(promptsByGroup)) {
            chronoByGroup[gid] = promptsByGroup[gid]
                .slice()
                .sort((a, b) => Math.max(...a.timestamps) - Math.max(...b.timestamps));
        }

        const entries = [];
        for (const group of sortedGroups) {
            if (entries.length >= QUICKFILL_TOTAL) break;
            const prompts = promptsByGroup[group.id]
                .slice()
                .sort((a, b) => Math.max(...b.timestamps) - Math.max(...a.timestamps));
            const chrono = chronoByGroup[group.id];
            let added = 0;
            for (const p of prompts) {
                if (added >= QUICKFILL_PER_GROUP || entries.length >= QUICKFILL_TOTAL) break;
                if (entries.some(e => e.prompt.text === p.text)) continue;

                const isCurrent = p.text === currentPlaceholder || p.text === currentValue;
                const idx = chrono.findIndex(cp => cp.id === p.id);
                const prev = idx > 0 ? chrono[idx - 1] : null;
                const diffResult = prev ? buildDiffLabel(prev.text, p.text, true) : null;
                const diffLabel = diffResult ? diffResult.label : (prev ? '#' + (idx + 1) : null);
                const rawFragments = prev ? buildDiffFragments(prev.text, p.text) : [];
                const isReordered = diffResult && diffResult.label === 'reordered';

                entries.push({ prompt: p, groupName: group.name, diffLabel, rawFragments, isReordered, isCurrent });
                added++;
            }
        }

        function truncate(s, n) { return s.length > n ? s.slice(0, n) + '…' : s; }

        function diffFragmentToHtml(f) {
            if (f.startsWith('+')) {
                return { type: 'added', color: '#38a169', text: f.slice(1) };
            } else if (f.startsWith('-')) {
                return { type: 'removed', color: '#e53e3e', text: f.slice(1) };
            } else if (f.includes('→')) {
                return { type: 'changed', color: '#805ad5', text: f };
            }
            return { type: 'diff', color: '#a0aec0', text: f };
        }

        container.innerHTML = '';
        for (const { prompt: p, groupName, diffLabel, rawFragments, isReordered, isCurrent } of entries) {
            const row = document.createElement('div');
            row.className = 'ph-quickfill-pill';

            const escapedName = escHtml(truncate(groupName, 30));
            const label = diffLabel
                ? '<b>' + escapedName + '</b> - ' + diffLabel
                : '<b>' + escapedName + '</b>';

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ph-quickfill-btn';
            btn.innerHTML = label;
            if (isCurrent) {
                btn.style.background = 'rgba(128,128,128,0.08)';
                btn.style.cursor = 'default';
            } else {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    descEl.value = p.text;
                    descEl.dispatchEvent(new Event('input', { bubbles: true }));
                    reusedFromGroupId = p.groupId;
                    refreshQuickFill();
                });
            }

            const popover = document.createElement('div');
            popover.className = 'ph-pill-popover';
            let popHtml = '';
            if (isReordered) {
                popHtml += '<div class="ph-pill-pop-title" style="color:#a0aec0">Words reordered — same content, different order</div>';
            } else if (rawFragments.length > 0) {
                popHtml += '<div class="ph-pill-pop-title">Changes</div>';
                for (const f of rawFragments) {
                    const info = diffFragmentToHtml(f);
                    popHtml += `<div class="ph-pill-pop-diff-line"><span class="ph-pill-pop-diff-type" style="color:${info.color}">${escHtml(info.type)}:</span> <span style="color:${info.color}">${escHtml(info.text)}</span></div>`;
                }
            }
            popHtml += `<div class="ph-pill-pop-prompt">${escHtml(p.text)}</div>`;
            popover.innerHTML = popHtml;

            const locateBtn = document.createElement('button');
            locateBtn.type = 'button';
            locateBtn.className = 'ph-quickfill-locate';
            locateBtn.textContent = '⌕';
            locateBtn.title = 'Show in history';
            locateBtn.addEventListener('click', (e) => {
                e.preventDefault();
                locateInHistory(p.groupId, p.id);
            });

            row.appendChild(btn);
            row.appendChild(locateBtn);
            row.appendChild(popover);
            container.appendChild(row);
        }
    }

    let pillPopShowTimer = null;
    let pillPopActive = null;

    function positionPillPop(popover) {
        popover.style.left = '0';
        popover.style.right = 'auto';
        popover.classList.add('ph-pop-visible');
        const rect = popover.getBoundingClientRect();
        if (rect.right > window.innerWidth - 8) {
            popover.style.left = 'auto';
            popover.style.right = '0';
        }
        if (rect.left < 8) {
            popover.style.left = '0';
            popover.style.right = 'auto';
        }
    }

    function closePillPop() {
        clearTimeout(pillPopShowTimer);
        if (pillPopActive) {
            pillPopActive.classList.remove('ph-pop-visible');
            pillPopActive = null;
        }
    }

    document.addEventListener('mouseover', (e) => {
        const pill = e.target.closest('.ph-quickfill-pill');
        if (!pill) {
            closePillPop();
            return;
        }
        const popover = pill.querySelector('.ph-pill-popover');
        if (!popover) return;
        if (e.target.closest('.ph-pill-popover')) return;
        if (pillPopActive === popover) return;
        closePillPop();
        pillPopShowTimer = setTimeout(() => {
            pillPopActive = popover;
            positionPillPop(popover);
        }, 750);
    });

    document.addEventListener('mouseout', (e) => {
        const pill = e.target.closest('.ph-quickfill-pill');
        if (!pill) return;
        const related = e.relatedTarget;
        if (related && related.closest && related.closest('.ph-quickfill-pill') === pill) return;
        closePillPop();
    });

    // ---- Generate toast ----

    function showGenToast(name, isNew) {
        const histBtn = document.getElementById('ph-history-btn');
        if (!histBtn) return;

        let toast = document.getElementById('ph-gen-toast');
        if (toast) toast.remove();

        const escaped = name.replace(/&/g,'&amp;').replace(/</g,'&lt;');
        toast = document.createElement('span');
        toast.id = 'ph-gen-toast';
        toast.innerHTML = isNew
            ? 'New group: <em>' + escaped + '</em>'
            : 'Added to <em>' + escaped + '</em>';
        histBtn.appendChild(toast);

        setTimeout(() => toast.classList.add('fade-out'), 7500);
        setTimeout(() => toast.remove(), 8000);
    }

    // ---- Settings gear + popover ----

    function injectSettingsGear() {
        const poll = setInterval(() => {
            const wrapper = document.getElementById('ph-gen-row-wrapper');
            if (!wrapper) return;
            if (document.getElementById('ph-settings-gear')) { clearInterval(poll); return; }
            clearInterval(poll);

            const leftBtns = document.createElement('span');
            leftBtns.id = 'ph-left-btns';

            const infoBtn = document.createElement('button');
            infoBtn.id = 'ph-info-btn';
            infoBtn.type = 'button';
            infoBtn.textContent = 'i';
            infoBtn.title = 'About this extension';
            infoBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openInfoDialog();
            });

            const gear = document.createElement('button');
            gear.id = 'ph-settings-gear';
            gear.type = 'button';
            gear.innerHTML = '&#9881;';
            gear.title = 'Settings';

            const popover = document.createElement('div');
            popover.id = 'ph-settings-popover';

            const lazyDisabled = localStorage.getItem('ph-disable-lazy-loading') === '1';

            popover.innerHTML = `
                <h3>Settings</h3>
                <div class="ph-toggle-row">
                    <span>Parallel loading</span>
                    <input type="checkbox" id="ph-lazy-toggle" ${lazyDisabled ? '' : 'checked'} />
                </div>
                <div class="ph-reload-hint">Reload to apply</div>
                <hr/>
                <label>Group similarity threshold</label>
                <div class="ph-settings-row">
                    <span style="font-size:12px;color:#999;">${Math.round(SIMILARITY_THRESHOLD_MIN*100)}%</span>
                    <input id="ph-similarity-slider" type="range" min="${SIMILARITY_THRESHOLD_MIN*100}" max="${SIMILARITY_THRESHOLD_MAX*100}" step="1" value="${Math.round(SIMILARITY_THRESHOLD*100)}" />
                    <span style="font-size:12px;color:#999;">${Math.round(SIMILARITY_THRESHOLD_MAX*100)}%</span>
                </div>
                <div class="ph-settings-row" style="margin-top:6px;">
                    <span>Current: <span id="ph-similarity-value">${Math.round(SIMILARITY_THRESHOLD*100)}%</span></span>
                    <button class="ph-settings-reset">Reset to ${Math.round(SIMILARITY_THRESHOLD_DEFAULT*100)}%</button>
                </div>
                <hr/>
                <label>Quick pills per group</label>
                <div class="ph-settings-row">
                    <span style="font-size:12px;color:#999;">1</span>
                    <input id="ph-pills-per-group" type="range" min="1" max="10" step="1" value="${QUICKFILL_PER_GROUP}" style="flex:1;cursor:pointer;" />
                    <span style="font-size:12px;color:#999;">10</span>
                </div>
                <div class="ph-settings-row" style="margin-top:6px;">
                    <span>Current: <span id="ph-pills-per-group-value">${QUICKFILL_PER_GROUP}</span></span>
                    <button class="ph-settings-reset" data-reset="pills-per-group">Reset to ${QUICKFILL_PER_GROUP_DEFAULT}</button>
                </div>
                <label style="margin-top:10px;">Total quick pills</label>
                <div class="ph-settings-row">
                    <span style="font-size:12px;color:#999;">1</span>
                    <input id="ph-pills-total" type="range" min="1" max="20" step="1" value="${QUICKFILL_TOTAL}" style="flex:1;cursor:pointer;" />
                    <span style="font-size:12px;color:#999;">20</span>
                </div>
                <div class="ph-settings-row" style="margin-top:6px;">
                    <span>Current: <span id="ph-pills-total-value">${QUICKFILL_TOTAL}</span></span>
                    <button class="ph-settings-reset" data-reset="pills-total">Reset to ${QUICKFILL_TOTAL_DEFAULT}</button>
                </div>
                <hr/>
                <label>Import merge strategy</label>
                <div class="ph-settings-row" style="margin-bottom:8px;">
                    <select id="ph-merge-strategy" style="flex:1;padding:4px 6px;border-radius:4px;border:1px solid rgba(128,128,128,0.4);background:#333;color:#eee;font-size:12px;cursor:pointer;">
                        <option value="similarity"${(localStorage.getItem('ph-merge-strategy')||'similarity')==='similarity'?' selected':''}>By prompt similarity</option>
                        <option value="title"${localStorage.getItem('ph-merge-strategy')==='title'?' selected':''}>By group title</option>
                    </select>
                </div>
                <label>History data</label>
                <div class="ph-export-import-row">
                    <button id="ph-export-btn">Export</button>
                    <button id="ph-import-btn">Import</button>
                </div>
                <input type="file" id="ph-import-file" accept=".json" style="display:none;" />
                <div id="ph-import-panel">
                    <div class="ph-import-info"></div>
                    <div class="ph-import-options">
                        <label><input type="radio" name="ph-import-mode" value="merge" checked /> Merge (skip duplicates, match by strategy above)</label>
                        <label><input type="radio" name="ph-import-mode" value="replace" /> Replace all existing history</label>
                    </div>
                    <div class="ph-import-actions">
                        <button class="ph-import-cancel">Cancel</button>
                        <button class="ph-import-confirm">Import</button>
                    </div>
                    <div class="ph-import-result" style="display:none;"></div>
                </div>
            `;

            const lazyToggle = popover.querySelector('#ph-lazy-toggle');
            const reloadHint = popover.querySelector('.ph-reload-hint');
            const initialState = lazyDisabled;
            lazyToggle.addEventListener('change', () => {
                const nowDisabled = !lazyToggle.checked;
                localStorage.setItem('ph-disable-lazy-loading', nowDisabled ? '1' : '0');
                const changed = nowDisabled !== initialState;
                reloadHint.classList.toggle('visible', changed);
            });


            const similaritySlider = popover.querySelector('#ph-similarity-slider');
            const similarityValue = popover.querySelector('#ph-similarity-value');
            similaritySlider.addEventListener('input', () => {
                const val = parseInt(similaritySlider.value);
                similarityValue.textContent = val + '%';
                SIMILARITY_THRESHOLD = val / 100;
                localStorage.setItem('ph-similarity-threshold', SIMILARITY_THRESHOLD);
            });
            popover.querySelector('.ph-settings-reset:not([data-reset])').addEventListener('click', () => {
                SIMILARITY_THRESHOLD = SIMILARITY_THRESHOLD_DEFAULT;
                localStorage.removeItem('ph-similarity-threshold');
                similaritySlider.value = Math.round(SIMILARITY_THRESHOLD_DEFAULT * 100);
                similarityValue.textContent = Math.round(SIMILARITY_THRESHOLD_DEFAULT * 100) + '%';
            });

            const pillsPerGroupSlider = popover.querySelector('#ph-pills-per-group');
            const pillsPerGroupValue = popover.querySelector('#ph-pills-per-group-value');
            pillsPerGroupSlider.addEventListener('input', () => {
                const val = parseInt(pillsPerGroupSlider.value);
                pillsPerGroupValue.textContent = val;
                QUICKFILL_PER_GROUP = val;
                localStorage.setItem('ph-quickfill-per-group', val);
                refreshQuickFill();
            });
            popover.querySelector('[data-reset="pills-per-group"]').addEventListener('click', () => {
                QUICKFILL_PER_GROUP = QUICKFILL_PER_GROUP_DEFAULT;
                localStorage.removeItem('ph-quickfill-per-group');
                pillsPerGroupSlider.value = QUICKFILL_PER_GROUP_DEFAULT;
                pillsPerGroupValue.textContent = QUICKFILL_PER_GROUP_DEFAULT;
                refreshQuickFill();
            });

            const pillsTotalSlider = popover.querySelector('#ph-pills-total');
            const pillsTotalValue = popover.querySelector('#ph-pills-total-value');
            pillsTotalSlider.addEventListener('input', () => {
                const val = parseInt(pillsTotalSlider.value);
                pillsTotalValue.textContent = val;
                QUICKFILL_TOTAL = val;
                localStorage.setItem('ph-quickfill-total', val);
                refreshQuickFill();
            });
            popover.querySelector('[data-reset="pills-total"]').addEventListener('click', () => {
                QUICKFILL_TOTAL = QUICKFILL_TOTAL_DEFAULT;
                localStorage.removeItem('ph-quickfill-total');
                pillsTotalSlider.value = QUICKFILL_TOTAL_DEFAULT;
                pillsTotalValue.textContent = QUICKFILL_TOTAL_DEFAULT;
                refreshQuickFill();
            });

            popover.querySelector('#ph-merge-strategy').addEventListener('change', (e) => {
                localStorage.setItem('ph-merge-strategy', e.target.value);
            });

            popover.querySelector('#ph-export-btn').addEventListener('click', async () => {
                try {
                    const groups = await getAllGroups();
                    const prompts = await getAllPrompts();
                    const data = { version: 1, exportedAt: new Date().toISOString(), groups, prompts };
                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `prompt-history-${new Date().toISOString().slice(0,10)}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                } catch (err) {
                    alert('Export failed: ' + err.message);
                }
            });

            const importFileInput = popover.querySelector('#ph-import-file');
            const importPanel = popover.querySelector('#ph-import-panel');
            const importInfo = importPanel.querySelector('.ph-import-info');
            const importResult = importPanel.querySelector('.ph-import-result');
            const importConfirmBtn = importPanel.querySelector('.ph-import-confirm');
            const importCancelBtn = importPanel.querySelector('.ph-import-cancel');

            let pendingImportData = null;

            popover.querySelector('#ph-import-btn').addEventListener('click', () => {
                importFileInput.value = '';
                importFileInput.click();
            });

            importCancelBtn.addEventListener('click', () => {
                pendingImportData = null;
                importPanel.classList.remove('visible');
                importResult.style.display = 'none';
            });

            importFileInput.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                importResult.style.display = 'none';
                try {
                    const text = await file.text();
                    const data = JSON.parse(text);
                    if (!data.groups || !data.prompts) throw new Error('Invalid format: missing groups or prompts');
                    pendingImportData = data;

                    const existingGroups = await getAllGroups();
                    const existingPrompts = await getAllPrompts();
                    const hasExisting = existingGroups.length > 0 || existingPrompts.length > 0;

                    let info = `File: <b>${escHtml(file.name)}</b><br>`;
                    info += `Contains: ${data.groups.length} group(s), ${data.prompts.length} prompt(s)`;
                    if (hasExisting) {
                        info += `<br>Existing: ${existingGroups.length} group(s), ${existingPrompts.length} prompt(s)`;
                    }
                    importInfo.innerHTML = info;
                    importPanel.classList.add('visible');
                } catch (err) {
                    importInfo.innerHTML = `<span style="color:#fc8181">Error reading file: ${escHtml(err.message)}</span>`;
                    pendingImportData = null;
                    importPanel.classList.add('visible');
                }
            });

            importConfirmBtn.addEventListener('click', async () => {
                if (!pendingImportData) return;
                const data = pendingImportData;
                const modeRadio = importPanel.querySelector('input[name="ph-import-mode"]:checked');
                const mode = modeRadio ? modeRadio.value : 'merge';

                importConfirmBtn.disabled = true;
                importConfirmBtn.textContent = 'Importing...';

                try {
                    if (mode === 'replace') {
                        const { stores: [gs] } = tx('groups', 'readwrite');
                        await reqP(gs.clear());
                        const { stores: [ps] } = tx('prompts', 'readwrite');
                        await reqP(ps.clear());
                        const replaceIdMap = {};
                        for (const g of data.groups) {
                            const oldId = g.id;
                            delete g.id;
                            replaceIdMap[oldId] = await addGroup(g);
                        }
                        for (const p of data.prompts) {
                            delete p.id;
                            if (p.groupId in replaceIdMap) p.groupId = replaceIdMap[p.groupId];
                            await addPrompt(p);
                        }
                        showImportResult('success', 'Replaced all history with imported data.');
                    } else {
                        const mergeStrategy = localStorage.getItem('ph-merge-strategy') || 'similarity';
                        const existingPrompts = await getAllPrompts();
                        const existingGroups = await getAllGroups();
                        const existingPromptTexts = new Set(existingPrompts.map(p => p.text));
                        const preExistingGroupIds = new Set(existingGroups.map(g => g.id));
                        let skipped = 0;
                        let merged = 0;

                        if (mergeStrategy === 'title') {
                            const existingGroupsByName = {};
                            for (const g of existingGroups) existingGroupsByName[g.name] = g;
                            const oldIdToNew = {};
                            const usedNewGroups = new Set();
                            for (const g of data.groups) {
                                const oldId = g.id;
                                const match = existingGroupsByName[g.name];
                                if (match) {
                                    oldIdToNew[oldId] = match.id;
                                    merged++;
                                    if (g.updatedAt > match.updatedAt) {
                                        match.updatedAt = g.updatedAt;
                                        await putGroup(match);
                                    }
                                } else {
                                    delete g.id;
                                    const newId = await addGroup(g);
                                    oldIdToNew[oldId] = newId;
                                }
                            }
                            for (const p of data.prompts) {
                                if (existingPromptTexts.has(p.text)) {
                                    const existing = await getPromptByText(p.text);
                                    if (existing) {
                                        const newTs = (p.timestamps || []).filter(t => !existing.timestamps.includes(t));
                                        if (newTs.length > 0) {
                                            existing.timestamps.push(...newTs);
                                            await putPrompt(existing);
                                        }
                                    }
                                    skipped++;
                                    continue;
                                }
                                delete p.id;
                                if (!(p.groupId in oldIdToNew)) continue;
                                p.groupId = oldIdToNew[p.groupId];
                                usedNewGroups.add(p.groupId);
                                await addPrompt(p);
                            }
                            for (const [, newGid] of Object.entries(oldIdToNew)) {
                                if (!usedNewGroups.has(newGid)) {
                                    await deleteGroup(newGid);
                                }
                            }
                        } else {
                            const importedGroupMap = {};
                            for (const g of data.groups) {
                                importedGroupMap[g.id] = { name: g.name, createdAt: g.createdAt, updatedAt: g.updatedAt };
                            }
                            const deferredGroups = {};
                            for (const p of data.prompts) {
                                if (existingPromptTexts.has(p.text)) {
                                    const existing = await getPromptByText(p.text);
                                    if (existing) {
                                        const newTs = (p.timestamps || []).filter(t => !existing.timestamps.includes(t));
                                        if (newTs.length > 0) {
                                            existing.timestamps.push(...newTs);
                                            await putPrompt(existing);
                                        }
                                    }
                                    skipped++;
                                    continue;
                                }
                                const similarGroup = await findBestGroup(p.text, null);
                                if (similarGroup != null && preExistingGroupIds.has(similarGroup)) {
                                    delete p.id;
                                    p.groupId = similarGroup;
                                    merged++;
                                    await addPrompt(p);
                                } else {
                                    const origGid = p.groupId;
                                    if (!deferredGroups[origGid]) deferredGroups[origGid] = [];
                                    deferredGroups[origGid].push(p);
                                }
                            }
                            for (const [oldGid, prompts] of Object.entries(deferredGroups)) {
                                const gInfo = importedGroupMap[oldGid];
                                const newGid = await addGroup({
                                    name: gInfo ? gInfo.name : groupName(prompts[0].text),
                                    createdAt: gInfo ? gInfo.createdAt : Date.now(),
                                    updatedAt: gInfo ? gInfo.updatedAt : Date.now(),
                                });
                                for (const p of prompts) {
                                    delete p.id;
                                    p.groupId = newGid;
                                    await addPrompt(p);
                                }
                            }
                        }
                        const parts = ['Import complete.'];
                        if (skipped > 0) parts.push(`${skipped} duplicate(s) skipped (timestamps merged).`);
                        if (merged > 0) parts.push(`${merged} prompt(s) merged into existing groups by ${mergeStrategy}.`);
                        const imported = data.prompts.length - skipped;
                        if (imported > merged) parts.push(`${imported - merged} prompt(s) added as new.`);
                        showImportResult('success', parts.join(' '));
                    }
                    pendingImportData = null;
                    await renderGroups();
                    refreshQuickFill();
                } catch (err) {
                    showImportResult('error', 'Import failed: ' + escHtml(err.message));
                } finally {
                    importConfirmBtn.disabled = false;
                    importConfirmBtn.textContent = 'Import';
                }
            });

            function showImportResult(type, message) {
                importResult.className = 'ph-import-result ' + type;
                importResult.innerHTML = message;
                importResult.style.display = 'block';
                importPanel.querySelector('.ph-import-options').style.display = 'none';
                importPanel.querySelector('.ph-import-actions').style.display = 'none';
                importInfo.style.display = 'none';
                setTimeout(() => {
                    importPanel.classList.remove('visible');
                    importResult.style.display = 'none';
                    importPanel.querySelector('.ph-import-options').style.display = '';
                    importPanel.querySelector('.ph-import-actions').style.display = '';
                    importInfo.style.display = '';
                }, 4000);
            }

            gear.addEventListener('click', (e) => {
                e.stopPropagation();
                popover.classList.toggle('open');
            });
            document.addEventListener('click', (e) => {
                if (!popover.contains(e.target) && e.target !== gear) {
                    popover.classList.remove('open');
                }
            });

            leftBtns.appendChild(infoBtn);
            leftBtns.appendChild(gear);
            leftBtns.appendChild(popover);
            wrapper.appendChild(leftBtns);
        }, 300);
    }

    function openInfoDialog() {
        let overlay = document.getElementById('ph-info-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'ph-info-overlay';
            overlay.innerHTML = `
                <div id="ph-info-modal">
                    <button class="ph-info-close" title="Close">&times;</button>
                    <h2>Perchance Image Generator — Extension Features</h2>

                    <h3>Parallel Loading</h3>
                    <p>All image generation slots are queued immediately instead of waiting for scroll-into-view. The first batch fires instantly, then subsequent slots are staggered to avoid server flooding. Toggle this in Settings.</p>

                    <h3>Expanded Grid</h3>
                    <p>The image grid is no longer capped at 2 columns. Cards fill as many columns as your viewport allows while staying centered.</p>

                    <h3>Nested Random Selectors</h3>
                    <p>The site supports <code>{cat|dog}</code> to pick one at random. This extension adds <b>nesting</b>:</p>
                    <ul>
                        <li><code>{{wild|angry} cat|dog}</code> expands to <code>{wild cat|angry cat|dog}</code></li>
                        <li><code>{{A|B} {C|D}}</code> expands to <code>{A C|A D|B C|B D}</code></li>
                        <li>Works at any depth — inner groups expand via Cartesian product</li>
                        <li>Multiple top-level <code>{}</code> groups stay independent</li>
                    </ul>
                    <p>A hover indicator below the prompt shows the expanded form before you generate. The site only ever sees the flattened version.</p>

                    <h3>Prompt History</h3>
                    <p>Every prompt you generate is saved locally (IndexedDB) and auto-grouped by similarity. Click the <b>History</b> button to browse, search, compare, and reuse past prompts.</p>
                    <ul>
                        <li><b>Quick-fill pills</b> — recent prompts shown above the generate button for one-click reuse</li>
                        <li><b>Compare</b> — select two prompts to see a word-level diff</li>
                        <li><b>Reuse / Flat</b> — for nested prompts, "Reuse" fills the template; "Flat" fills the expanded version</li>
                        <li><b>Export / Import</b> — back up or transfer your history via JSON</li>
                    </ul>

                    <h3>Gallery Tab Tools</h3>
                    <p>Export and import your gallery sub-channel tabs between sessions or devices.</p>

                    <h3>Cross-Tab Protection</h3>
                    <p>Prevents other tabs from hijacking your gallery's sub-channel and sort order when images are saved elsewhere.</p>

                    <h3>Auto-Show NSFW Images</h3>
                    <p>Automatically reveals NSFW-blurred images in the gallery without clicking each one. Checks the "show all" box on the first image, then clicks through the rest. <b>Shocking</b> images (gore, vomit, etc.) are never auto-revealed.</p>

                </div>
            `;
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) overlay.classList.remove('ph-open');
            });
            overlay.querySelector('.ph-info-close').addEventListener('click', () => {
                overlay.classList.remove('ph-open');
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && overlay.classList.contains('ph-open')) overlay.classList.remove('ph-open');
            });
            document.body.appendChild(overlay);
        }
        overlay.classList.add('ph-open');
    }

    // ---- Boot prompt history ----

    async function initPromptHistory() {
        try {
            await openDB();
        } catch (e) {
            console.error('[Prompt History] IndexedDB failed:', e);
            return;
        }

        const waitForGeneratorUI = () => {
            const poll = setInterval(() => {
                if (!document.getElementById('generateButtonEl')) return;
                clearInterval(poll);
                log('Generator UI detected, initializing prompt history');
                injectStyles();
                injectHistoryButton();
                injectSettingsGear();
                injectNestedIndicator();
                hookGenerateButton();
                refreshQuickFill();
            }, 500);
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', waitForGeneratorUI);
        } else {
            waitForGeneratorUI();
        }
    }

    // Only run prompt history on the main generator page
    if (location.hostname === 'perchance.org' || !location.pathname.startsWith('/gallery')) {
        initPromptHistory();
    }

    // ========================================================================
    // GALLERY SUB-CHANNEL TABS — COPY / IMPORT
    // ========================================================================

    function initGalleryTabTools() {
        if (location.hostname !== 'image-generation.perchance.org') return;
        if (!location.pathname.startsWith('/gallery')) return;


        const CHANNEL_RE = /^[a-z0-9\-]+$/;

        function getChannel() {
            return new URLSearchParams(location.search).get('channel') || '';
        }

        function getStoredTabs() {
            const key = 'visitedSubChannels_' + getChannel();
            try { return JSON.parse(localStorage.getItem(key) || '[]'); }
            catch { return []; }
        }

        function setStoredTabs(tabs) {
            const key = 'visitedSubChannels_' + getChannel();
            localStorage.setItem(key, JSON.stringify(tabs));
        }

        function getVisibleTabNames() {
            const wrappers = document.querySelectorAll('#visitedSubChannelsCtn .visited-channel-wrapper[data-name]');
            return Array.from(wrappers).map(w => w.dataset.name);
        }

        function showToast(msg, isError) {
            const t = document.createElement('div');
            Object.assign(t.style, {
                position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
                background: isError ? '#d32f2f' : '#323232', color: '#fff',
                padding: '10px 24px', borderRadius: '6px', fontSize: '14px',
                zIndex: '999999', transition: 'opacity 0.3s', opacity: '1',
                fontFamily: 'system-ui, sans-serif', maxWidth: '90vw', textAlign: 'center'
            });
            t.textContent = msg;
            document.body.appendChild(t);
            setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 2500);
        }

        function parseTabNames(text) {
            return text.split(/[,\n]+/).map(s => s.trim().toLowerCase()).filter(s => CHANNEL_RE.test(s));
        }

        function dedup(names) {
            const seen = new Set();
            return names.filter(n => { if (seen.has(n)) return false; seen.add(n); return true; });
        }

        function esc(s) {
            return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // ---- Copy / Export dialog ----

        function openCopyDialog() {
            if (document.getElementById('gallery-copy-overlay')) return;

            const names = getVisibleTabNames();
            if (names.length === 0) { showToast('No tabs to copy', true); return; }

            const channel = getChannel();
            const storageKey = 'visitedSubChannels_' + channel;
            const jsonValue = JSON.stringify(names.map(n => ({ name: n })));

            const mergeSnippet = `(() => { const k = ${JSON.stringify(storageKey)}; const cur = JSON.parse(localStorage.getItem(k) || '[]'); const have = new Set(cur.map(t => t.name)); const add = ${JSON.stringify(names)}.filter(n => !have.has(n)); if (!add.length) return console.log('All tabs already present'); add.forEach(n => cur.push({name: n})); localStorage.setItem(k, JSON.stringify(cur)); console.log('Added', add.length, 'tab(s):', add.join(', ')); location.reload(); })()`;
            const replaceSnippet = `(() => { const k = ${JSON.stringify(storageKey)}; const tabs = ${JSON.stringify(names.map(n => ({ name: n })))}; localStorage.setItem(k, JSON.stringify(tabs)); console.log('Replaced with', tabs.length, 'tab(s)'); location.reload(); })()`;

            const formats = {
                text: { label: 'Text (for import dialog)', value: names.join(', ') },
                json: { label: 'JSON (for localStorage)', value: jsonValue },
                'js-merge': { label: 'JS Console — Merge', value: mergeSnippet },
                'js-replace': { label: 'JS Console — Replace', value: replaceSnippet }
            };

            const overlay = document.createElement('div');
            overlay.id = 'gallery-copy-overlay';
            Object.assign(overlay.style, {
                position: 'absolute', top: window.scrollY + 'px', left: '0',
                width: '100%', height: window.innerHeight + 'px',
                background: 'rgba(0,0,0,0.6)',
                display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                paddingTop: '60px', boxSizing: 'border-box',
                zIndex: '999999', fontFamily: 'system-ui, sans-serif'
            });

            const dialog = document.createElement('div');
            Object.assign(dialog.style, {
                background: '#1e1e1e', color: '#eee', borderRadius: '10px',
                padding: '20px', width: '480px', maxWidth: '95vw', maxHeight: 'calc(100% - 80px)',
                display: 'flex', flexDirection: 'column', gap: '12px',
                border: '1px solid #444', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                overflowY: 'auto'
            });

            const title = document.createElement('div');
            title.textContent = 'Export Gallery Tabs';
            Object.assign(title.style, { fontSize: '16px', fontWeight: '600' });
            dialog.appendChild(title);

            const subtitle = document.createElement('div');
            subtitle.textContent = `${names.length} tab(s): ${names.join(', ')}`;
            Object.assign(subtitle.style, { fontSize: '12px', color: '#aaa', wordBreak: 'break-word' });
            dialog.appendChild(subtitle);

            const modeRow = document.createElement('div');
            Object.assign(modeRow.style, { display: 'flex', flexWrap: 'wrap', gap: '8px 16px', fontSize: '13px' });

            let firstRadio;
            for (const [key, fmt] of Object.entries(formats)) {
                const label = document.createElement('label');
                Object.assign(label.style, { display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' });
                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'gallery-copy-format';
                radio.value = key;
                if (!firstRadio) { radio.checked = true; firstRadio = radio; }
                label.appendChild(radio);
                label.appendChild(document.createTextNode(fmt.label));
                modeRow.appendChild(label);
            }
            dialog.appendChild(modeRow);

            const hint = document.createElement('div');
            Object.assign(hint.style, { fontSize: '11px', color: '#888', minHeight: '14px' });
            dialog.appendChild(hint);

            const output = document.createElement('textarea');
            output.readOnly = true;
            Object.assign(output.style, {
                width: '100%', minHeight: '90px', background: '#2a2a2a', color: '#eee',
                border: '1px solid #555', borderRadius: '6px', padding: '8px',
                fontSize: '12px', resize: 'vertical', boxSizing: 'border-box',
                fontFamily: 'monospace', wordBreak: 'break-all'
            });
            dialog.appendChild(output);

            const btnRow = document.createElement('div');
            Object.assign(btnRow.style, { display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' });

            const closeBtn = document.createElement('button');
            closeBtn.textContent = 'Close';
            Object.assign(closeBtn.style, {
                padding: '7px 16px', borderRadius: '6px', border: '1px solid #555',
                background: 'transparent', color: '#ccc', cursor: 'pointer', fontSize: '13px'
            });
            closeBtn.addEventListener('click', () => overlay.remove());

            const copyBtn = document.createElement('button');
            copyBtn.textContent = 'Copy to Clipboard';
            Object.assign(copyBtn.style, {
                padding: '7px 16px', borderRadius: '6px', border: 'none',
                background: '#4a6', color: '#fff', cursor: 'pointer', fontSize: '13px',
                fontWeight: '600'
            });
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(output.value);
                    copyBtn.textContent = 'Copied!';
                    setTimeout(() => { copyBtn.textContent = 'Copy to Clipboard'; }, 1500);
                } catch { showToast('Clipboard access denied', true); }
            });

            btnRow.appendChild(closeBtn);
            btnRow.appendChild(copyBtn);
            dialog.appendChild(btnRow);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
            const onEsc = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onEsc); } };
            document.addEventListener('keydown', onEsc);

            const hints = {
                text: 'Paste into the Import dialog on another browser with the extension.',
                json: `Open DevTools → Application → Local Storage → https://image-generation.perchance.org → set key "${storageKey}" to this value, then reload.`,
                'js-merge': 'Open DevTools → Console on the gallery page, paste this snippet, and press Enter. Adds missing tabs without removing existing ones.',
                'js-replace': 'Open DevTools → Console on the gallery page, paste this snippet, and press Enter. Replaces all tabs with exactly this set.'
            };

            function updateOutput() {
                const mode = dialog.querySelector('input[name="gallery-copy-format"]:checked')?.value || 'text';
                output.value = formats[mode].value;
                hint.textContent = hints[mode];
            }

            modeRow.addEventListener('change', updateOutput);
            updateOutput();
        }

        // ---- Import dialog ----

        function openImportDialog() {
            if (document.getElementById('gallery-import-overlay')) return;

            const existing = getVisibleTabNames();
            const existingSet = new Set(existing);

            const overlay = document.createElement('div');
            overlay.id = 'gallery-import-overlay';
            Object.assign(overlay.style, {
                position: 'absolute', top: window.scrollY + 'px', left: '0',
                width: '100%', height: window.innerHeight + 'px',
                background: 'rgba(0,0,0,0.6)',
                display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                paddingTop: '60px', boxSizing: 'border-box',
                zIndex: '999999', fontFamily: 'system-ui, sans-serif'
            });

            const dialog = document.createElement('div');
            Object.assign(dialog.style, {
                background: '#1e1e1e', color: '#eee', borderRadius: '10px',
                padding: '20px', width: '420px', maxWidth: '95vw', maxHeight: 'calc(100% - 80px)',
                display: 'flex', flexDirection: 'column', gap: '12px',
                overflowY: 'auto',
                border: '1px solid #444', boxShadow: '0 8px 32px rgba(0,0,0,0.5)'
            });

            const title = document.createElement('div');
            title.textContent = 'Import Gallery Tabs';
            Object.assign(title.style, { fontSize: '16px', fontWeight: '600' });
            dialog.appendChild(title);

            const desc = document.createElement('div');
            desc.textContent = 'Paste tab names below (comma or newline separated):';
            Object.assign(desc.style, { fontSize: '13px', color: '#aaa' });
            dialog.appendChild(desc);

            const textarea = document.createElement('textarea');
            textarea.placeholder = 'e.g. public, chat, anime, landscapes';
            Object.assign(textarea.style, {
                width: '100%', minHeight: '80px', background: '#2a2a2a', color: '#eee',
                border: '1px solid #555', borderRadius: '6px', padding: '8px',
                fontSize: '13px', resize: 'vertical', boxSizing: 'border-box',
                fontFamily: 'system-ui, sans-serif'
            });
            dialog.appendChild(textarea);

            const preview = document.createElement('div');
            Object.assign(preview.style, {
                fontSize: '12px', color: '#aaa', minHeight: '40px',
                maxHeight: '150px', overflowY: 'auto', lineHeight: '1.5'
            });
            dialog.appendChild(preview);

            const modeRow = document.createElement('div');
            Object.assign(modeRow.style, { display: 'flex', gap: '12px', alignItems: 'center', fontSize: '13px' });

            function radioLabel(value, labelText, checked) {
                const label = document.createElement('label');
                Object.assign(label.style, { display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' });
                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'gallery-import-mode';
                radio.value = value;
                radio.checked = checked;
                label.appendChild(radio);
                label.appendChild(document.createTextNode(labelText));
                return label;
            }

            modeRow.appendChild(radioLabel('merge', 'Merge (add new)', true));
            modeRow.appendChild(radioLabel('replace', 'Replace all', false));
            dialog.appendChild(modeRow);

            const btnRow = document.createElement('div');
            Object.assign(btnRow.style, { display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' });

            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = 'Cancel';
            Object.assign(cancelBtn.style, {
                padding: '7px 16px', borderRadius: '6px', border: '1px solid #555',
                background: 'transparent', color: '#ccc', cursor: 'pointer', fontSize: '13px'
            });
            cancelBtn.addEventListener('click', () => overlay.remove());

            const applyBtn = document.createElement('button');
            applyBtn.textContent = 'Apply';
            applyBtn.disabled = true;
            Object.assign(applyBtn.style, {
                padding: '7px 16px', borderRadius: '6px', border: 'none',
                background: '#4a6', color: '#fff', cursor: 'pointer', fontSize: '13px',
                fontWeight: '600', opacity: '0.5'
            });

            btnRow.appendChild(cancelBtn);
            btnRow.appendChild(applyBtn);
            dialog.appendChild(btnRow);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);
            textarea.focus();

            overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
            const onEsc = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onEsc); } };
            document.addEventListener('keydown', onEsc);

            function getMode() {
                return dialog.querySelector('input[name="gallery-import-mode"]:checked')?.value || 'merge';
            }

            function updatePreview() {
                const raw = textarea.value;
                const parsed = dedup(parseTabNames(raw));
                const invalid = raw.split(/[,\n]+/).map(s => s.trim()).filter(s => s && !CHANNEL_RE.test(s.toLowerCase()));
                const mode = getMode();

                if (parsed.length === 0) {
                    preview.innerHTML = '<span style="color:#888">Enter tab names above to see a preview.</span>';
                    applyBtn.disabled = true;
                    applyBtn.style.opacity = '0.5';
                    applyBtn.style.cursor = 'not-allowed';
                    return;
                }

                let html = '';

                if (invalid.length > 0) {
                    html += `<div style="color:#e57373;margin-bottom:4px">Invalid (skipped): ${invalid.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                }

                if (mode === 'merge') {
                    const newOnes = parsed.filter(n => !existingSet.has(n));
                    const dupes = parsed.filter(n => existingSet.has(n));
                    if (newOnes.length > 0) {
                        html += `<div style="color:#81c784">+ Add: ${newOnes.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                    }
                    if (dupes.length > 0) {
                        html += `<div style="color:#888">Already present: ${dupes.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                    }
                    if (newOnes.length === 0) {
                        html += `<div style="color:#ffb74d;margin-top:2px">Nothing new to add.</div>`;
                    }
                    applyBtn.disabled = newOnes.length === 0;
                    applyBtn.style.opacity = newOnes.length === 0 ? '0.5' : '1';
                    applyBtn.style.cursor = newOnes.length === 0 ? 'not-allowed' : 'pointer';
                } else {
                    const removing = existing.filter(n => !parsed.includes(n));
                    const adding = parsed.filter(n => !existingSet.has(n));
                    const keeping = parsed.filter(n => existingSet.has(n));
                    if (adding.length > 0) html += `<div style="color:#81c784">+ Add: ${adding.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                    if (keeping.length > 0) html += `<div style="color:#888">Keep: ${keeping.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                    if (removing.length > 0) html += `<div style="color:#e57373">- Remove: ${removing.map(n => '<code>' + esc(n) + '</code>').join(', ')}</div>`;
                    applyBtn.disabled = false;
                    applyBtn.style.opacity = '1';
                    applyBtn.style.cursor = 'pointer';
                }

                preview.innerHTML = html;
            }

            textarea.addEventListener('input', updatePreview);
            modeRow.addEventListener('change', updatePreview);
            updatePreview();

            applyBtn.addEventListener('click', () => {
                const parsed = dedup(parseTabNames(textarea.value));
                if (parsed.length === 0) return;
                const mode = getMode();

                if (mode === 'merge') {
                    const tabs = getStoredTabs();
                    const names = new Set(tabs.map(t => t.name));
                    let added = 0;
                    for (const name of parsed) {
                        if (!names.has(name)) { tabs.push({ name }); names.add(name); added++; }
                    }
                    if (added === 0) return;
                    setStoredTabs(tabs);

                    const removedKey = 'removedDefaultSubChannels_' + getChannel();
                    try {
                        const removed = JSON.parse(localStorage.getItem(removedKey) || '[]');
                        const cleaned = removed.filter(n => !parsed.includes(n));
                        if (cleaned.length !== removed.length) localStorage.setItem(removedKey, JSON.stringify(cleaned));
                    } catch {}

                    showToast(`Added ${added} tab(s) — reloading…`);
                } else {
                    setStoredTabs(parsed.map(name => ({ name })));

                    const removedKey = 'removedDefaultSubChannels_' + getChannel();
                    try {
                        const removed = JSON.parse(localStorage.getItem(removedKey) || '[]');
                        const cleaned = removed.filter(n => !parsed.includes(n));
                        if (cleaned.length !== removed.length) localStorage.setItem(removedKey, JSON.stringify(cleaned));
                    } catch {}

                    showToast(`Replaced with ${parsed.length} tab(s) — reloading…`);
                }

                overlay.remove();
                setTimeout(() => location.reload(), 800);
            });
        }

        // ---- Inject buttons ----

        function injectButtons(addBtnWrapper) {
            const copyWrapper = document.createElement('div');
            copyWrapper.className = 'visited-channel-wrapper';
            copyWrapper.id = 'gallery-copy-wrapper';

            const copyBtn = document.createElement('button');
            copyBtn.className = 'visit-visited-channel-btn';
            copyBtn.textContent = '📋';
            copyBtn.title = 'Export tabs';
            Object.assign(copyBtn.style, { cursor: 'pointer', fontSize: '14px', minWidth: '32px' });
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openCopyDialog();
            });
            copyWrapper.appendChild(copyBtn);

            const importWrapper = document.createElement('div');
            importWrapper.className = 'visited-channel-wrapper';
            importWrapper.id = 'gallery-import-wrapper';

            const importBtn = document.createElement('button');
            importBtn.className = 'visit-visited-channel-btn';
            importBtn.textContent = '📥';
            importBtn.title = 'Import tabs';
            Object.assign(importBtn.style, { cursor: 'pointer', fontSize: '14px', minWidth: '32px' });
            importBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openImportDialog();
            });
            importWrapper.appendChild(importBtn);

            addBtnWrapper.parentNode.insertBefore(copyWrapper, addBtnWrapper.nextSibling);
            copyWrapper.parentNode.insertBefore(importWrapper, copyWrapper.nextSibling);
        }

        const poll = setInterval(() => {
            const ctn = document.getElementById('visitedSubChannelsCtn');
            if (!ctn) return;
            const addBtn = ctn.querySelector('.add-gallery-btn');
            if (!addBtn) return;
            if (document.getElementById('gallery-copy-wrapper')) { clearInterval(poll); return; }
            clearInterval(poll);

            const addBtnWrapper = addBtn.closest('.visited-channel-wrapper') || addBtn.parentElement;
            injectButtons(addBtnWrapper);
        }, 300);
    }

    initGalleryTabTools();

    // ========================================================================
    // AUTO-SHOW NSFW BLURS (not shocking)
    // ========================================================================

    function initAutoShowNsfw() {
        if (location.hostname !== 'image-generation.perchance.org') return;
        if (!location.pathname.startsWith('/gallery')) return;

        let showAllChecked = false;

        function revealNsfwImages(root) {
            const blurs = root.querySelectorAll('.nsfwBlur');
            if (!blurs.length) return;
            const origConfirm = window.confirm;
            window.confirm = () => true;
            try {
                for (const blur of blurs) {
                    const ctn = blur.closest('.imageCtn');
                    if (!ctn || ctn.dataset.isShocking === 'true') continue;
                    if (blur.dataset.phAutoShown) continue;
                    blur.dataset.phAutoShown = '1';
                    if (!showAllChecked) {
                        const checkbox = blur.querySelector('.removeAllBlursCheckbox');
                        if (checkbox && !checkbox.checked) checkbox.checked = true;
                        showAllChecked = true;
                    }
                    const btn = blur.querySelector('button');
                    if (btn) btn.click();
                }
            } finally {
                window.confirm = origConfirm;
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => revealNsfwImages(document));
        } else {
            revealNsfwImages(document);
        }

        new MutationObserver((mutations) => {
            for (const m of mutations) {
                for (const node of m.addedNodes) {
                    if (node.nodeType !== 1) continue;
                    if (node.classList?.contains('nsfwBlur')) {
                        const ctn = node.closest('.imageCtn');
                        if (ctn && ctn.dataset.isShocking !== 'true') {
                            revealNsfwImages(ctn);
                        }
                    } else if (node.querySelector?.('.nsfwBlur')) {
                        revealNsfwImages(node);
                    }
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    initAutoShowNsfw();

})();
