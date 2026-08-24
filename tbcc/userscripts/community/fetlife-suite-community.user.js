// ==UserScript==
// @name         FetLife Enhancer
// @namespace    https://sleazyfork.org/users/1618643-ianmxaof
// @homepageURL  https://telegram.me/aofsubscriptions_bot
// @version      1.0.0
// @description  FetLife browsing: masonry home feed, story filter, mute, ASL/gender filter, auto-follow, place kinksters nav, infinite scroll, privacy presets. Community build — no analytics.
// @author       AOF community fork
// @match        https://fetlife.com/*
// @match        https://www.fetlife.com/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_addStyle
// @run-at       document-idle
// @license      MIT
// ==/UserScript==

/* AOF community build 2026-08-22T04:11:01.524Z - v1.0.0 - see tbcc/userscripts/NOTICE.md */

(function (g) { g.__TBCC_EDITION__ = 'community'; })(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/ns.js ---- */
/* TBCC userscripts shared bootstrap — concatenated first */
(function (global) {
  'use strict';
  const root = (global.__TBCC_US__ = global.__TBCC_US__ || {});
  root.shared = root.shared || {};
  root.suites = root.suites || {};
  root.version = root.version || '0.1.0';
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/storage.js ---- */
/* GM storage helpers; Chrome extension uses localStorage; mem last-resort */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const mem = Object.create(null);
  const LS_PREFIX = 'tbcc_us_';

  function hasGM() {
    return typeof GM_getValue === 'function' && typeof GM_setValue === 'function';
  }

  function lsGet(key, fallback) {
    try {
      if (typeof localStorage === 'undefined') return fallback;
      const raw = localStorage.getItem(LS_PREFIX + key);
      if (raw == null) return fallback;
      return JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  }

  function lsSet(key, value) {
    try {
      if (typeof localStorage === 'undefined') return false;
      localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  }

  S.storage = {
    get(key, fallback) {
      try {
        if (hasGM()) {
          const v = GM_getValue(key, fallback);
          return v === undefined ? fallback : v;
        }
      } catch (_) { /* ignore */ }
      if (typeof localStorage !== 'undefined') {
        return lsGet(key, key in mem ? mem[key] : fallback);
      }
      return key in mem ? mem[key] : fallback;
    },
    set(key, value) {
      try {
        if (hasGM()) {
          GM_setValue(key, value);
          return;
        }
      } catch (_) { /* ignore */ }
      if (lsSet(key, value)) return;
      mem[key] = value;
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/flags.js ---- */
/* Feature flags: defaults + persisted overrides */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;

  S.createFlags = function createFlags(storageKey, defaults) {
    const saved = S.storage.get(storageKey, null) || {};
    const state = { ...defaults, ...(typeof saved === 'object' ? saved : {}) };

    return {
      get(name) {
        return state[name] !== false;
      },
      raw(name) {
        return state[name];
      },
      set(name, on) {
        state[name] = !!on;
        S.storage.set(storageKey, { ...state });
      },
      all() {
        return { ...state };
      },
      defaults: { ...defaults },
    };
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/observer.js ---- */
/* Debounced document MutationObserver bus */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const listeners = new Set();
  let mo = null;
  let timer = null;

  function flush() {
    timer = null;
    for (const fn of listeners) {
      try {
        fn();
      } catch (err) {
        console.warn('[TBCC_US] observer listener error', err);
      }
    }
  }

  S.observer = {
    subscribe(fn) {
      listeners.add(fn);
      if (!mo && typeof MutationObserver !== 'undefined' && document.documentElement) {
        mo = new MutationObserver(() => {
          if (timer) return;
          timer = setTimeout(flush, 120);
        });
        mo.observe(document.documentElement, { childList: true, subtree: true });
      }
      return () => listeners.delete(fn);
    },
    ping() {
      flush();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/spa.js ---- */
/* SPA navigation hooks (pushState / replaceState / popstate) */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;
  const listeners = new Set();
  let hooked = false;

  function emit() {
    for (const fn of listeners) {
      try {
        fn(location.href);
      } catch (err) {
        console.warn('[TBCC_US] spa listener error', err);
      }
    }
  }

  function hookHistory(method) {
    const orig = history[method];
    history[method] = function () {
      const ret = orig.apply(this, arguments);
      setTimeout(emit, 50);
      return ret;
    };
  }

  S.spa = {
    onChange(fn) {
      listeners.add(fn);
      if (!hooked) {
        hooked = true;
        hookHistory('pushState');
        hookHistory('replaceState');
        window.addEventListener('popstate', () => setTimeout(emit, 50));
      }
      return () => listeners.delete(fn);
    },
    path() {
      return location.pathname || '';
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/shared/ui-panel.js ---- */
/* Minimal floating settings shell */
(function (global) {
  'use strict';
  const S = global.__TBCC_US__.shared;

  S.ensureStyle = function ensureStyle(id, css) {
    if (document.getElementById(id)) return;
    const el = document.createElement('style');
    el.id = id;
    el.textContent = css;
    document.documentElement.appendChild(el);
  };

  S.mountFlagPanel = function mountFlagPanel(opts) {
    const { id, title, flags, labels, onChange } = opts;
    const panelId = id + '-panel';
    const fabId = id + '-fab';

    S.ensureStyle(
      id + '-style',
      `
      #${panelId} {
        position: fixed; z-index: 999999; right: 16px; bottom: 64px;
        width: min(360px, calc(100vw - 24px)); max-height: min(70vh, 560px);
        overflow: auto; background: #1a1a1a; color: #d4d4d4;
        border: 1px solid #333; border-radius: 8px; box-shadow: 0 8px 28px rgba(0,0,0,.55);
        font: 13px/1.35 system-ui, sans-serif; display: none;
      }
      #${panelId}.open { display: block; }
      #${panelId} header {
        position: sticky; top: 0; background: #222; padding: 10px 12px;
        border-bottom: 1px solid #333; display: flex; gap: 8px; align-items: center;
      }
      #${panelId} header strong { flex: 1; }
      #${panelId} header button, #${fabId} {
        background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
        padding: 6px 10px; cursor: pointer;
      }
      #${fabId} { position: fixed; z-index: 999998; right: 16px; bottom: 16px; }
      #${panelId} label { display: flex; gap: 8px; padding: 6px 12px; cursor: pointer; }
      #${panelId} .note { padding: 8px 12px 12px; color: #888; font-size: 12px; }
    `
    );

    if (!document.getElementById(panelId)) {
      const panel = document.createElement('div');
      panel.id = panelId;
      panel.innerHTML = `<header><strong>${title}</strong><button type="button" data-act="close">Close</button></header>
        <div class="note">Flags persist in extension localStorage (or TM if present). Reload if a feature looks stuck.</div>`;
      const all = flags.all();
      Object.keys(all).forEach((key) => {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = all[key] !== false;
        cb.dataset.flag = key;
        cb.addEventListener('change', () => {
          flags.set(key, cb.checked);
          if (onChange) onChange(key, cb.checked);
        });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(labels[key] || key));
        panel.appendChild(lab);
      });
      panel.querySelector('[data-act="close"]').addEventListener('click', () => panel.classList.remove('open'));
      document.documentElement.appendChild(panel);

      const fab = document.createElement('button');
      fab.id = fabId;
      fab.type = 'button';
      fab.textContent = opts.fabLabel || 'Suite';
      fab.addEventListener('click', () => panel.classList.toggle('open'));
      document.documentElement.appendChild(fab);
    }

    function open() {
      document.getElementById(panelId)?.classList.add('open');
    }

    if (typeof GM_registerMenuCommand === 'function') {
      try {
        GM_registerMenuCommand(opts.menuLabel || `${title}: settings`, open);
      } catch (_) { /* ignore */ }
    }

    return { open };
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/story-filter-core.js ---- */
/**
 * Pure story-type catalog + classifier (no DOM).
 * Used by FetLife suite story-filter feature and unit tests.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  const g = root.__TBCC_US__ || (root.__TBCC_US__ = { shared: {}, suites: {} });
  g.fetlife = g.fetlife || {};
  g.fetlife.storyFilterCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const CATALOG = [
    {
      category: 'General Profile',
      items: [
        { id: 'friendship_request_accepted', label: 'Accepted a Friendship Request', defaultOn: true },
        { id: 'sign_ups', label: 'Sign ups & Invitations', defaultOn: true },
        { id: 'following', label: 'Following a Member', defaultOn: true },
      ],
    },
    {
      category: 'Profile Updates',
      items: [
        { id: 'profile_updates', label: 'Posted a Profile Update', defaultOn: true },
        { id: 'commented_on_profile_update', label: 'Commented on a Profile Update', defaultOn: true },
        { id: 'loved_profile_update', label: 'Loved a Profile Update', defaultOn: true },
        { id: 'superloved_profile_update', label: 'Superloved a Profile Update', defaultOn: true },
        { id: 'fetish_added', label: 'Added/Updated a Fetish', defaultOn: false },
      ],
    },
    {
      category: 'Relationship Updates',
      items: [
        { id: 'relationship_changes', label: 'Posted a Relationship Update', defaultOn: true },
        { id: 'commented_on_relationship', label: 'Commented on a Relationship Update', defaultOn: true },
        { id: 'loved_relationship', label: 'Loved a Relationship Update', defaultOn: true },
        { id: 'superloved_relationship_update', label: 'Superloved a Relationship Update', defaultOn: true },
      ],
    },
    {
      category: 'Status Updates',
      items: [
        { id: 'status_created', label: 'Posted a Status Update', defaultOn: true },
        { id: 'status_comment_created', label: 'Commented on a Status Update', defaultOn: true },
        { id: 'loved_status_update', label: 'Loved a Status Update', defaultOn: true },
        { id: 'superloved_status_update', label: 'Superloved a Status Update', defaultOn: true },
      ],
    },
    {
      category: 'Pictures',
      items: [
        { id: 'picture_created', label: 'Uploaded a New Picture/Album', defaultOn: true },
        { id: 'comment_created', label: 'Commented on a Picture/Album', defaultOn: true },
        { id: 'loved_picture', label: 'Loved a Picture/Album', defaultOn: true },
        { id: 'superloved_picture', label: 'Superloved a Picture/Album', defaultOn: true },
        { id: 'user_tagged_in_picture_approved', label: 'Tagged in a Picture', defaultOn: true },
        { id: 'tagged_picture_trending_created', label: 'Trending Picture', defaultOn: true },
      ],
    },
    {
      category: 'Videos',
      items: [
        { id: 'video_created', label: 'Uploaded a New Video', defaultOn: true },
        { id: 'video_comment_created', label: 'Commented on a Video', defaultOn: true },
        { id: 'loved_video', label: 'Loved a Video', defaultOn: true },
        { id: 'superloved_video', label: 'Superloved a Video', defaultOn: true },
        { id: 'user_tagged_in_video_approved', label: 'Tagged in a Video', defaultOn: true },
        { id: 'tagged_video_trending_created', label: 'Trending Video', defaultOn: true },
      ],
    },
    {
      category: 'Writings',
      items: [
        { id: 'post_created', label: 'Posted a New Writing/Collection', defaultOn: true },
        { id: 'post_comment_created', label: 'Commented on a Writing/Collection', defaultOn: true },
        { id: 'loved_writing', label: 'Loved a Writing/Collection', defaultOn: true },
        { id: 'superloved_writing', label: 'Superloved a Writing/Collection', defaultOn: true },
        { id: 'tagged_writing_trending_created', label: 'Trending Writing', defaultOn: true },
      ],
    },
    {
      category: 'Wall Posts',
      items: [
        { id: 'wall_posts', label: 'Posted on a Wall', defaultOn: true },
        { id: 'commented_on_wall_post', label: 'Commented on a Wall Post', defaultOn: true },
        { id: 'loved_wall_post', label: 'Loved a Wall Post', defaultOn: true },
        { id: 'superloved_wall_post', label: 'Superloved a Wall Post', defaultOn: true },
      ],
    },
    {
      category: 'Community Lists',
      items: [
        { id: 'community_list_created', label: 'Posted a Community List', defaultOn: true },
        { id: 'community_list_comment_created', label: 'Commented on a Community List', defaultOn: true },
        { id: 'loved_community_list', label: 'Loved a Community List', defaultOn: true },
        { id: 'superloved_community_list', label: 'Superloved a Community List', defaultOn: true },
      ],
    },
    {
      category: 'Ask Me Anything',
      items: [
        { id: 'ask_me_anything_story_created', label: 'Posted an AMA story', defaultOn: true },
        { id: 'ask_me_anything_story_comment_created', label: 'Commented on an AMA story', defaultOn: true },
        { id: 'loved_ask_me_anything_story', label: 'Loved an AMA story', defaultOn: true },
        { id: 'superloved_ama', label: 'Superloved an AMA story', defaultOn: true },
      ],
    },
    {
      category: 'Events',
      items: [
        { id: 'event_created', label: 'Created a New Event', defaultOn: true },
        { id: 'rsvp_created', label: 'RSVPed to an Event', defaultOn: true },
        { id: 'rsvp_updated', label: 'RSVP updated', defaultOn: true },
        { id: 'event_discussion_created', label: 'Posted Event Discussion', defaultOn: true },
        { id: 'loved_event_discussion', label: 'Loved Event Discussion', defaultOn: true },
        { id: 'superloved_event_discussion', label: 'Superloved an Event Discussion', defaultOn: true },
        { id: 'commented_on_event_discussion', label: 'Commented on Event Discussion', defaultOn: true },
      ],
    },
    {
      category: 'Groups - General',
      items: [
        { id: 'became_group_leader', label: 'Became Leader of a Group', defaultOn: true },
        { id: 'group_membership_created', label: 'Joined a Group', defaultOn: true },
      ],
    },
    {
      category: 'Groups - Member Of',
      items: [
        { id: 'group_post_being_member_by_friend', label: 'New Discussion by someone you follow', defaultOn: true },
        { id: 'group_post_being_member', label: "New Discussion by someone you don't follow", defaultOn: false },
        { id: 'group_comment_created_being_member_by_friend', label: 'Comment on a Discussion by someone you follow', defaultOn: true },
        { id: 'loved_group_discussion_being_member', label: 'Loved a Group Discussion', defaultOn: true },
        { id: 'superloved_group_discussion_being_member', label: 'Superloved a Group Discussion', defaultOn: true },
      ],
    },
    {
      category: 'Groups - Not Member Of',
      items: [
        { id: 'group_post_not_being_member', label: 'New Discussion', defaultOn: false },
        { id: 'group_comment_not_being_member', label: 'Comment on a Discussion', defaultOn: false },
        { id: 'loved_group_discussion_not_being_member', label: 'Loved a Group Discussion', defaultOn: true },
        { id: 'superloved_group_discussion_not_being_member', label: 'Superloved a Group Discussion', defaultOn: true },
      ],
    },
  ];

  const MATCHERS = [
    { id: 'superloved_picture', re: /superloved .{0,80}(picture|album|pic)\b/i },
    { id: 'loved_picture', re: /\bloved .{0,80}(picture|album|pic)\b/i },
    { id: 'comment_created', re: /commented on .{0,80}(picture|album|pic)\b/i },
    { id: 'user_tagged_in_picture_approved', re: /tagged .{0,40}in .{0,40}(picture|album|pic)\b/i },
    { id: 'tagged_picture_trending_created', re: /trending .{0,40}(picture|album|pic)\b/i },
    { id: 'picture_created', re: /(uploaded|posted|added) .{0,40}(new )?(picture|album|pic)\b/i },
    { id: 'superloved_video', re: /superloved .{0,80}video\b/i },
    { id: 'loved_video', re: /\bloved .{0,80}video\b/i },
    { id: 'video_comment_created', re: /commented on .{0,80}video\b/i },
    { id: 'user_tagged_in_video_approved', re: /tagged .{0,40}in .{0,40}video\b/i },
    { id: 'tagged_video_trending_created', re: /trending .{0,40}video\b/i },
    { id: 'video_created', re: /(uploaded|posted|added) .{0,40}(new )?video\b/i },
    { id: 'superloved_writing', re: /superloved .{0,80}(writing|post|collection)\b/i },
    { id: 'loved_writing', re: /\bloved .{0,80}(writing|collection)\b/i },
    { id: 'post_comment_created', re: /commented on .{0,80}(writing|post|collection)\b/i },
    { id: 'tagged_writing_trending_created', re: /trending .{0,40}(writing|post)\b/i },
    { id: 'post_created', re: /(posted|published|wrote) .{0,40}(new )?(writing|collection)\b/i },
    { id: 'superloved_wall_post', re: /superloved .{0,80}wall\b/i },
    { id: 'loved_wall_post', re: /\bloved .{0,80}wall\b/i },
    { id: 'commented_on_wall_post', re: /commented on .{0,80}wall\b/i },
    { id: 'wall_posts', re: /(posted|wrote) .{0,40}on .{0,40}wall\b/i },
    { id: 'superloved_community_list', re: /superloved .{0,80}(community )?list\b/i },
    { id: 'loved_community_list', re: /\bloved .{0,80}(community )?list\b/i },
    { id: 'community_list_comment_created', re: /commented on .{0,80}(community )?list\b/i },
    { id: 'community_list_created', re: /(posted|created|updated) .{0,40}(community )?list\b/i },
    { id: 'superloved_ama', re: /superloved .{0,80}(ama|ask me anything)\b/i },
    { id: 'loved_ask_me_anything_story', re: /\bloved .{0,80}(ama|ask me anything)\b/i },
    { id: 'ask_me_anything_story_comment_created', re: /commented on .{0,80}(ama|ask me anything)\b/i },
    { id: 'ask_me_anything_story_created', re: /(posted|asked|answered).{0,40}(ama|ask me anything)\b/i },
    { id: 'superloved_event_discussion', re: /superloved .{0,80}event .{0,20}discussion\b/i },
    { id: 'loved_event_discussion', re: /\bloved .{0,80}event .{0,20}discussion\b/i },
    { id: 'commented_on_event_discussion', re: /commented on .{0,80}event .{0,20}discussion\b/i },
    { id: 'event_discussion_created', re: /(posted|started).{0,40}event .{0,20}discussion\b/i },
    { id: 'rsvp_updated', re: /rsvp(ed)? .{0,40}updated|updated .{0,40}rsvp/i },
    { id: 'rsvp_created', re: /rsvp(ed)? (to|for) .{0,60}event\b|is (going|interested)/i },
    { id: 'event_created', re: /(created|posted) .{0,40}(new )?event\b/i },
    { id: 'superloved_group_discussion_being_member', re: /superloved .{0,80}(group )?discussion\b/i },
    { id: 'loved_group_discussion_being_member', re: /\bloved .{0,80}(group )?discussion\b/i },
    { id: 'group_comment_created_being_member_by_friend', re: /commented on .{0,80}(group )?discussion\b/i },
    { id: 'group_post_being_member_by_friend', re: /(posted|started|created) .{0,40}(new )?(group )?discussion\b/i },
    { id: 'became_group_leader', re: /became .{0,40}(leader|owner).{0,40}group\b/i },
    { id: 'group_membership_created', re: /(joined|became a member of) .{0,60}group\b/i },
    { id: 'superloved_status_update', re: /superloved .{0,80}status\b/i },
    { id: 'loved_status_update', re: /\bloved .{0,80}status\b/i },
    { id: 'status_comment_created', re: /commented on .{0,80}status\b/i },
    { id: 'status_created', re: /(posted|updated) .{0,40}status\b/i },
    { id: 'superloved_relationship_update', re: /superloved .{0,80}relationship\b/i },
    { id: 'loved_relationship', re: /\bloved .{0,80}relationship\b/i },
    { id: 'commented_on_relationship', re: /commented on .{0,80}relationship\b/i },
    { id: 'following', re: /(is now following|started following|followed)\b/i },
    { id: 'relationship_changes', re: /\b(relationship|partner|in a relationship)\b/i },
    { id: 'superloved_profile_update', re: /superloved .{0,80}profile\b/i },
    { id: 'loved_profile_update', re: /\bloved .{0,80}profile\b/i },
    { id: 'commented_on_profile_update', re: /commented on .{0,80}profile\b/i },
    { id: 'fetish_added', re: /(added|updated).{0,40}fetish/i },
    { id: 'profile_updates', re: /(updated|changed).{0,40}profile\b/i },
    { id: 'friendship_request_accepted', re: /(accepted|are now friends|friendship)/i },
    { id: 'sign_ups', re: /(signed up|joined fetlife|invited)/i },
  ];

  function defaultEnabledMap() {
    const map = {};
    for (const cat of CATALOG) {
      for (const item of cat.items) map[item.id] = item.defaultOn;
    }
    return map;
  }

  function classifyStoryText(text) {
    const t = String(text || '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t) return null;
    for (const m of MATCHERS) {
      if (m.re.test(t)) return m.id;
    }
    return null;
  }

  return { CATALOG, MATCHERS, defaultEnabledMap, classifyStoryText };
});

/* ---- packages/fetlife-suite/features/story-filter.js ---- */
/* FetLife story filter — DOM layer (client-side only) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const core = US.fetlife.storyFilterCore;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const STORAGE_KEY = 'tbcc_fl_story_enabled_v1';
  const HIDDEN_ATTR = 'data-fl-fsf-hidden';
  const TYPE_ATTR = 'data-fl-fsf-type';
  const PANEL_ID = 'tbcc-fl-story-panel';

  function loadEnabled() {
    const saved = S.storage.get(STORAGE_KEY, null);
    const base = core.defaultEnabledMap();
    if (!saved || typeof saved !== 'object') return base;
    return { ...base, ...saved };
  }

  let enabled = loadEnabled();

  function storyNodes() {
    const selectors = ['#stories-list > *', '#fl-masonry-wrap .fl-masonry-col > *', '#stories > *'];
    const found = new Set();
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        if (el.classList?.contains('infinite-loading-container')) return;
        if ((el.textContent || '').trim().length < 20) return;
        if (el.closest(`#${PANEL_ID}`)) return;
        found.add(el);
      });
    }
    return [...found].filter((el) => ![...found].some((o) => o !== el && o.contains(el)));
  }

  function applyFeedFilter() {
    const nodes = storyNodes();
    let hidden = 0;
    for (const el of nodes) {
      const text = el.innerText || el.textContent || '';
      const type =
        el.getAttribute('data-feed-event') ||
        el.getAttribute('data-story-type') ||
        el.getAttribute('data-type') ||
        core.classifyStoryText(text);
      if (type) el.setAttribute(TYPE_ATTR, type);
      const show = !type || enabled[type] !== false;
      if (show) el.removeAttribute(HIDDEN_ATTR);
      else {
        el.setAttribute(HIDDEN_ATTR, '1');
        hidden += 1;
      }
    }
    if (hidden) console.debug(`[FL suite] storyFilter hidden=${hidden}/${nodes.length}`);
  }

  function unlockSettingsPage() {
    const form = document.getElementById('update_feed_settings_form');
    if (!form) return;
    if (!document.getElementById('tbcc-fl-fsf-banner')) {
      const h2 = [...form.querySelectorAll('h2')].find((h) => /Hide\/Show Feed Stories/i.test(h.textContent || ''));
      const banner = document.createElement('div');
      banner.id = 'tbcc-fl-fsf-banner';
      banner.style.cssText =
        'margin:8px 0 12px;padding:8px 10px;background:#2a1f14;border:1px solid #664;border-radius:6px;color:#e8c48a;font-size:13px;';
      banner.textContent =
        'TBCC FetLife Suite: toggles save locally and filter your browser feed. Not sent to FetLife Supporter APIs.';
      (h2?.parentElement || form).insertBefore(banner, h2?.nextSibling || form.firstChild);
    }
    form.querySelectorAll('input[name="feed[story_types][]"]').forEach((input) => {
      if (!input.value) return;
      input.disabled = false;
      input.checked = enabled[input.value] !== false;
      const label = input.closest('label');
      if (label) {
        label.style.opacity = '1';
        label.style.cursor = 'pointer';
        label.style.pointerEvents = 'auto';
      }
      if (input.dataset.tbccBound) return;
      input.dataset.tbccBound = '1';
      input.addEventListener('change', (ev) => {
        ev.stopPropagation();
        enabled = { ...enabled, [input.value]: input.checked };
        S.storage.set(STORAGE_KEY, enabled);
        applyFeedFilter();
      });
    });
    if (!form.dataset.tbccSubmitBlocked) {
      form.dataset.tbccSubmitBlocked = '1';
      form.addEventListener(
        'submit',
        (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          S.storage.set(STORAGE_KEY, enabled);
        },
        true
      );
    }
  }

  function buildTypePanel() {
    if (document.getElementById(PANEL_ID)) return;
    S.ensureStyle(
      'tbcc-fl-fsf-style',
      `[${HIDDEN_ATTR}="1"]{display:none!important}
       #${PANEL_ID}{position:fixed;z-index:999999;right:16px;bottom:110px;width:min(420px,calc(100vw - 24px));max-height:min(65vh,560px);overflow:auto;background:#1a1a1a;color:#d4d4d4;border:1px solid #333;border-radius:8px;display:none;font:13px/1.35 system-ui,sans-serif}
       #${PANEL_ID}.open{display:block}
       #${PANEL_ID} header{position:sticky;top:0;background:#222;padding:10px 12px;display:flex;gap:8px;align-items:center;border-bottom:1px solid #333}
       #${PANEL_ID} header strong{flex:1}
       #${PANEL_ID} button{background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 10px;cursor:pointer}
       #${PANEL_ID} .cat{padding:8px 12px 4px;font-weight:700;color:#bbb}
       #${PANEL_ID} label{display:flex;gap:8px;padding:4px 12px 4px 16px;cursor:pointer}
       #tbcc-fl-story-fab{position:fixed;z-index:999998;right:16px;bottom:60px;background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 10px;cursor:pointer}`
    );
    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `<header><strong>Story types</strong>
      <button type="button" data-act="all-on">All on</button>
      <button type="button" data-act="all-off">All off</button>
      <button type="button" data-act="close">Close</button></header>
      <div style="padding:8px 12px;color:#888;font-size:12px">Unchecked = hidden in browser only.</div>`;
    for (const cat of core.CATALOG) {
      const h = document.createElement('div');
      h.className = 'cat';
      h.textContent = cat.category;
      panel.appendChild(h);
      for (const item of cat.items) {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = enabled[item.id] !== false;
        cb.addEventListener('change', () => {
          enabled = { ...enabled, [item.id]: cb.checked };
          S.storage.set(STORAGE_KEY, enabled);
          unlockSettingsPage();
          applyFeedFilter();
        });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(item.label));
        panel.appendChild(lab);
      }
    }
    panel.querySelector('[data-act="close"]').onclick = () => panel.classList.remove('open');
    panel.querySelector('[data-act="all-on"]').onclick = () => {
      Object.keys(enabled).forEach((k) => (enabled[k] = true));
      S.storage.set(STORAGE_KEY, enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = true));
      applyFeedFilter();
    };
    panel.querySelector('[data-act="all-off"]').onclick = () => {
      Object.keys(enabled).forEach((k) => (enabled[k] = false));
      S.storage.set(STORAGE_KEY, enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = false));
      applyFeedFilter();
    };
    document.documentElement.appendChild(panel);
    const fab = document.createElement('button');
    fab.id = 'tbcc-fl-story-fab';
    fab.type = 'button';
    fab.textContent = 'Story types';
    fab.onclick = () => panel.classList.toggle('open');
    document.documentElement.appendChild(fab);
  }

  FL.features = FL.features || {};
  FL.features.storyFilter = {
    start() {
      unlockSettingsPage();
      buildTypePanel();
      applyFeedFilter();
      this._unsubObs = S.observer.subscribe(() => {
        unlockSettingsPage();
        applyFeedFilter();
      });
      this._unsubSpa = S.spa.onChange(() => setTimeout(applyFeedFilter, 300));
    },
    stop() {
      this._unsubObs?.();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/mute.js ---- */
/* Comment mute — adapted from brighid fetlife-mute-button */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});
  const STORAGE_KEY = 'tbcc_fl_muted_users_v1';
  const muteBtnClass = 'tbcc-fl-mute-btn';
  const replacerClass = 'tbcc-fl-muted-comment';

  function loadMuted() {
    const raw = S.storage.get(STORAGE_KEY, '');
    if (!raw) return [];
    if (Array.isArray(raw)) return raw.map(String);
    if (/^[\d,]+$/.test(String(raw))) return String(raw).split(',').filter(Boolean);
    return [];
  }

  let mutedUsers = loadMuted();

  function save() {
    S.storage.set(STORAGE_KEY, mutedUsers.join(','));
  }

  function muteUser(userId) {
    if (!/^\d+$/.test(userId) || mutedUsers.includes(userId)) return;
    mutedUsers.push(userId);
    save();
  }

  function unmuteUser(userId) {
    mutedUsers = mutedUsers.filter((id) => id !== userId);
    save();
  }

  function findComments() {
    return [...document.querySelectorAll('section#comments article.fl-comment, article.fl-comment')].map((root) => {
      const nickEl =
        root.querySelector('a.fl-comment__user') ||
        root.querySelector('a[href*="/users/"]');
      if (!nickEl) return null;
      const href = nickEl.getAttribute('href') || '';
      const m = href.match(/\/users\/(\d+)/);
      if (!m) return null;
      return { root, nickEl, nick: (nickEl.textContent || '').trim(), userId: m[1] };
    }).filter(Boolean);
  }

  function hideComment(root, userId, nick) {
    [...root.children].forEach((ch) => {
      if (!ch.classList.contains(replacerClass)) ch.style.display = 'none';
    });
    if (root.querySelector(`.${replacerClass}`)) return;
    const div = document.createElement('div');
    div.className = replacerClass;
    div.style.cssText = 'padding:8px;font-size:12px;opacity:.75';
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = `Muted comment from ${nick} (click to unmute)`;
    a.addEventListener('click', (ev) => {
      ev.preventDefault();
      unmuteUser(userId);
      apply();
    });
    div.appendChild(a);
    root.insertBefore(div, root.firstChild);
  }

  function unhideComment(root) {
    [...root.children].forEach((ch) => {
      ch.style.display = '';
    });
    root.querySelector(`.${replacerClass}`)?.remove();
  }

  function addMuteButton(nickEl, userId, nick) {
    if (nickEl.parentElement?.querySelector(`.${muteBtnClass}`)) return;
    const span = document.createElement('span');
    span.className = muteBtnClass;
    span.style.cssText = 'margin-left:6px;font-size:11px;opacity:.7';
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = '(mute)';
    a.addEventListener('click', (ev) => {
      ev.preventDefault();
      muteUser(userId);
      apply();
    });
    span.appendChild(a);
    nickEl.insertAdjacentElement('afterend', span);
  }

  function apply() {
    mutedUsers = loadMuted();
    for (const c of findComments()) {
      if (mutedUsers.includes(c.userId)) {
        hideComment(c.root, c.userId, c.nick);
      } else {
        unhideComment(c.root);
        addMuteButton(c.nickEl, c.userId, c.nick);
      }
    }
  }

  FL.features = FL.features || {};
  FL.features.mute = {
    start() {
      apply();
      this._unsub = S.observer.subscribe(apply);
    },
    stop() {
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/newest-discussions.js ---- */
/* Newest discussions redirect — adapted from GreasyFork script 29395 */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const FL = (US.fetlife = US.fetlife || {});

  function maybeRedirect() {
    const path = location.pathname || '';
    if (!/^\/groups\/\d+$/.test(path)) return;
    if (location.search.includes('order=')) return;
    location.replace(path + '?order=discussions');
  }

  FL.features = FL.features || {};
  FL.features.newestDiscussions = {
    start() {
      maybeRedirect();
      this._unsub = US.shared.spa.onChange(() => setTimeout(maybeRedirect, 50));
    },
    stop() {
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/home-feed.js ---- */
/* Home feed masonry — adapted from FetLife Suite - Home Feed (RYSTA, MIT) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const FILTERS = [
    { label: 'All', path: '/home' },
    { label: 'Pics', path: '/home/pictures' },
    { label: 'Vids', path: '/home/videos' },
    { label: 'Text', path: '/home/statuses' },
    { label: 'Writings', path: '/home/writings' },
    { label: 'AMA', path: '/home/ama' },
    { label: 'Audio', path: '/home/audio' },
    { label: 'For You', path: '/home/for-you' },
  ];

  let masonryWrap = null;
  let columns = [];
  let placedItems = new WeakSet();
  let currentColCount = 0;
  let postObserver = null;
  let started = false;

  function getColumnCount() {
    const w = window.innerWidth;
    if (w >= 2400) return 4;
    if (w >= 1200) return 3;
    if (w >= 720) return 2;
    return 1;
  }

  function getShortestColumn() {
    let shortest = 0;
    let minHeight = Infinity;
    columns.forEach((col, i) => {
      const h = col.offsetHeight;
      if (h < minHeight) {
        minHeight = h;
        shortest = i;
      }
    });
    return columns[shortest];
  }

  function getThemeVars() {
    const rgb = window.getComputedStyle(document.body).backgroundColor.match(/\d+/g);
    const isDark =
      !rgb || parseInt(rgb[0], 10) * 0.299 + parseInt(rgb[1], 10) * 0.587 + parseInt(rgb[2], 10) * 0.114 < 128;
    return isDark
      ? '--card-bg:#121212; --card-border:none; --card-shadow:none; --avatar-border:2px solid #333;'
      : '--card-bg:#f0f0f0; --card-border:1px solid #e2e8f0; --card-shadow:none; --avatar-border:2px solid #e2e8f0;';
  }

  function injectStyles() {
    S.ensureStyle(
      'tbcc-fl-home-feed-style',
      `
      #tbcc-fl-back-to-top {
        position: fixed; bottom: 28px; right: 100px; z-index: 9999;
        width: 44px; height: 44px; border-radius: 50%;
        background: rgba(30,30,30,.85); border: 1px solid #444; color: #ccc;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
        opacity: 0; visibility: hidden; transition: opacity .25s, visibility .25s;
      }
      #tbcc-fl-back-to-top.fl-visible { opacity: 1; visibility: visible; }
      #tbcc-fl-back-to-top:hover { background: #e11d48; border-color: #e11d48; color: #fff; }
      #fl-feed-filters {
        display: flex; gap: 6px; padding: 8px 0 10px; flex-wrap: wrap; width: 100%; box-sizing: border-box;
      }
      #fl-feed-filters a {
        display: inline-block; padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
        text-decoration: none; color: #aaa; background: #1e1e1e; border: 1px solid #333;
      }
      #fl-feed-filters a.fl-filter-active { color: #fff; background: #e11d48; border-color: #e11d48; }
      body.fl-home-active { ${getThemeVars()} }
      body.fl-home-active .max-w-screen-xl { max-width: 100vw !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
      body.fl-home-active .mx-auto.max-w-3xl { max-width: 100% !important; margin: 0 !important; }
      body.fl-home-active .flex.flex-col.lg\\:flex-row > aside { display: none !important; }
      #fl-masonry-wrap { display: flex !important; gap: 1.5rem; width: 100%; align-items: flex-start; }
      .fl-masonry-col { flex: 1; display: flex; flex-direction: column; gap: 1.5rem; min-width: 0; }
      .fl-masonry-col > div {
        border-radius: 12px; padding: 0 1.5rem !important;
        background-color: var(--card-bg) !important; border: var(--card-border) !important;
      }
      .fl-masonry-col > div header a.flex-none { width: 72px !important; height: 72px !important; margin-right: 1.25rem !important; }
      .fl-masonry-col > div header a.flex-none img {
        width: 100% !important; height: 100% !important; border-radius: 50% !important; object-fit: cover;
        border: var(--avatar-border) !important;
      }
      body.fl-home-active header.flex.h-14 { position: sticky !important; top: 0; z-index: 50; }
    `
    );
  }

  function mountBackToTop() {
    if (document.getElementById('tbcc-fl-back-to-top')) return;
    const btn = document.createElement('button');
    btn.id = 'tbcc-fl-back-to-top';
    btn.type = 'button';
    btn.title = 'Back to top';
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-8 8h5v8h6v-8h5z"/></svg>';
    btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    document.body.appendChild(btn);
    window.addEventListener('scroll', () => {
      btn.classList.toggle('fl-visible', window.scrollY > 600);
    });
  }

  function getCurrentFilter() {
    const path = window.location.pathname;
    if (path === '/home') return '/home';
    for (const f of FILTERS) if (f.path !== '/home' && path.startsWith(f.path)) return f.path;
    return '/home';
  }

  function injectFilterBar() {
    if (document.getElementById('fl-feed-filters')) return;
    if (!/^\/home(\/|$)/.test(location.pathname)) return;
    const bar = document.createElement('div');
    bar.id = 'fl-feed-filters';
    const current = getCurrentFilter();
    FILTERS.forEach((f) => {
      const a = document.createElement('a');
      a.href = f.path;
      a.textContent = f.label;
      if (f.path === current) a.classList.add('fl-filter-active');
      bar.appendChild(a);
    });
    const main = document.getElementById('responsive-feed') || document.querySelector('main');
    if (main) main.insertBefore(bar, main.firstChild);
  }

  function createMasonryContainer(storiesList) {
    if (masonryWrap) {
      masonryWrap.remove();
      masonryWrap = null;
      columns = [];
    }
    currentColCount = getColumnCount();
    masonryWrap = document.createElement('div');
    masonryWrap.id = 'fl-masonry-wrap';
    for (let i = 0; i < currentColCount; i++) {
      const col = document.createElement('div');
      col.className = 'fl-masonry-col';
      masonryWrap.appendChild(col);
      columns.push(col);
    }
    storiesList.parentNode.insertBefore(masonryWrap, storiesList);
  }

  function distributeNewItems(storiesList) {
    const items = [];
    for (const child of Array.from(storiesList.children)) {
      if (child.nodeType !== 1) continue;
      if (child.classList.contains('infinite-loading-container')) continue;
      if (placedItems.has(child)) continue;
      items.push(child);
    }
    items.forEach((item) => {
      placedItems.add(item);
      getShortestColumn().appendChild(item);
    });
  }

  function fixInfiniteLoader() {
    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      const masonry = document.getElementById('fl-masonry-wrap');
      const storiesList = document.getElementById('stories-list');
      const loader = document.querySelector('.infinite-loading-container');
      if (masonry && storiesList && loader && storiesList.contains(loader)) {
        masonry.parentElement.appendChild(loader);
        clearInterval(interval);
      }
      if (attempts > 30) clearInterval(interval);
    }, 500);
  }

  function initMasonry() {
    const storiesList = document.getElementById('stories-list');
    if (!storiesList) return;
    if (!masonryWrap) createMasonryContainer(storiesList);
    distributeNewItems(storiesList);
    if (postObserver) postObserver.disconnect();
    postObserver = new MutationObserver(() => {
      setTimeout(() => distributeNewItems(storiesList), 150);
    });
    postObserver.observe(storiesList, { childList: true });
    fixInfiniteLoader();
  }

  function teardownMasonry() {
    if (postObserver) postObserver.disconnect();
    postObserver = null;
    if (masonryWrap) {
      const storiesList = document.getElementById('stories-list');
      if (storiesList) {
        columns.forEach((col) => {
          while (col.firstChild) storiesList.appendChild(col.firstChild);
        });
      }
      masonryWrap.remove();
      masonryWrap = null;
      columns = [];
      placedItems = new WeakSet();
      currentColCount = 0;
    }
  }

  function checkPage() {
    const isHome = location.pathname.startsWith('/home');
    document.body.classList.toggle('fl-home-active', isHome);
    injectFilterBar();
    if (isHome) setTimeout(initMasonry, 400);
    else teardownMasonry();
  }

  FL.features = FL.features || {};
  FL.features.homeFeed = {
    start() {
      if (started) return;
      started = true;
      injectStyles();
      mountBackToTop();
      checkPage();
      this._unsubSpa = S.spa.onChange(() => setTimeout(checkPage, 100));
      this._onResize = () => {
        if (!location.pathname.startsWith('/home')) return;
        const n = getColumnCount();
        if (n === currentColCount) return;
        const storiesList = document.getElementById('stories-list');
        if (!storiesList) return;
        columns.forEach((col) => {
          while (col.firstChild) {
            placedItems.delete(col.firstChild);
            storiesList.insertBefore(col.firstChild, storiesList.querySelector('.infinite-loading-container'));
          }
        });
        createMasonryContainer(storiesList);
        distributeNewItems(storiesList);
      };
      window.addEventListener('resize', this._onResize);
    },
    stop() {
      started = false;
      this._unsubSpa?.();
      if (this._onResize) window.removeEventListener('resize', this._onResize);
      teardownMasonry();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/place-nav.js ---- */
/* Place → kinksters navigation (no hardcoded city) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const CFG_KEY = 'tbcc_fl_place_nav_v1';
  const BOOKMARK_KEY = 'tbcc_fl_kinksters_bookmark_v1';
  const DEFAULT_CFG = {
    country: 'united-states',
    region: 'california',
    lastQuery: '',
    lastPath: '',
  };

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(partial) {
    const next = { ...loadCfg(), ...partial };
    S.storage.set(CFG_KEY, next);
    return next;
  }

  function slugifyPlace(name) {
    return String(name || '')
      .trim()
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/&/g, ' and ')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function kinkstersPath(placeName, cfg) {
    const c = cfg || loadCfg();
    const slug = slugifyPlace(placeName);
    if (!slug) return null;
    const country = slugifyPlace(c.country) || 'united-states';
    const region = slugifyPlace(c.region) || 'california';
    return `/p/${country}/${region}/${slug}/kinksters`;
  }

  function kinkstersUrl(placeName, cfg) {
    const path = kinkstersPath(placeName, cfg);
    if (!path) return null;
    return `https://fetlife.com${path}`;
  }

  /** Places search fallback when slug path is unknown / 404. */
  function placesSearchUrl(placeName) {
    const q = String(placeName || '').trim();
    if (!q) return null;
    // FetLife global search; user lands on results and can open Places → kinksters.
    return `https://fetlife.com/search?q=${encodeURIComponent(q)}`;
  }

  /** Human label from /p/{country}/{region}/{slug}/kinksters */
  function placeLabelFromPath(pathname) {
    const m = String(pathname || location.pathname).match(
      /\/p\/([^/]+)\/([^/]+)\/([^/]+)\/kinksters\/?/i
    );
    if (!m) return '';
    return decodeURIComponent(m[3]).replace(/-/g, ' ').trim();
  }

  function clearPlace() {
    return saveCfg({ lastQuery: '', lastPath: '' });
  }

  function loadBookmark() {
    const b = S.storage.get(BOOKMARK_KEY, null);
    return b && typeof b === 'object' && b.path ? b : null;
  }

  function saveBookmark(partial) {
    const prev = loadBookmark() || {};
    const next = {
      path: String(partial.path || prev.path || '').replace(/\?.*$/, ''),
      page: Math.max(1, Number(partial.page) || Number(prev.page) || 1),
      placeLabel: String(partial.placeLabel != null ? partial.placeLabel : prev.placeLabel || ''),
      ts: Date.now(),
    };
    if (!next.path) return null;
    S.storage.set(BOOKMARK_KEY, next);
    return next;
  }

  function clearBookmark() {
    S.storage.set(BOOKMARK_KEY, null);
  }

  function resumeBookmarkUrl(bm) {
    const b = bm || loadBookmark();
    if (!b?.path) return null;
    const page = Math.max(1, Number(b.page) || 1);
    const base = b.path.startsWith('http') ? b.path : `https://fetlife.com${b.path}`;
    try {
      const u = new URL(base);
      if (page > 1) u.searchParams.set('page', String(page));
      else u.searchParams.delete('page');
      return u.toString();
    } catch (_) {
      return page > 1 ? `${base}${base.includes('?') ? '&' : '?'}page=${page}` : base;
    }
  }

  /** Prefer live kinksters URL slug when on a place list; else lastQuery. */
  function displayPlaceQuery() {
    const fromUrl = placeLabelFromPath(location.pathname);
    if (fromUrl) return fromUrl;
    return loadCfg().lastQuery || '';
  }

  /**
   * Jump to kinksters for a place name.
   * Place is navigation-only — does NOT copy into ASL locationInclude (that caused
   * stale-city filters when switching regions).
   * @param {string} placeName e.g. "Palo Alto"
   * @param {{ syncAsl?: boolean, mode?: 'kinksters'|'search' }} opts
   */
  function goPlace(placeName, opts) {
    const q = String(placeName || '').trim();
    if (!q) return { ok: false, reason: 'empty' };
    const cfg = saveCfg({ lastQuery: q });
    // Opt-in only — never default-sync place into ASL vitals filter.
    if (opts?.syncAsl && FL.genderFilter?.saveCfg && FL.genderFilter?.loadCfg) {
      const g = FL.genderFilter.loadCfg();
      FL.genderFilter.saveCfg({ ...g, locationInclude: q });
      FL.genderFilter.apply?.();
    }
    const mode = opts?.mode || 'kinksters';
    if (mode === 'search') {
      const url = placesSearchUrl(q);
      if (!url) return { ok: false, reason: 'empty' };
      location.assign(url);
      return { ok: true, mode: 'search', url };
    }
    const path = kinkstersPath(q, cfg);
    const url = kinkstersUrl(q, cfg);
    saveCfg({ lastQuery: q, lastPath: path });
    if (path && location.pathname.replace(/\/+$/, '') === path.replace(/\/+$/, '')) {
      FL.overlay?.open?.('autofollow');
      return { ok: true, mode: 'kinksters', url, already: true };
    }
    location.assign(url);
    return { ok: true, mode: 'kinksters', url };
  }

  FL.placeNav = {
    CFG_KEY,
    BOOKMARK_KEY,
    loadCfg,
    saveCfg,
    clearPlace,
    loadBookmark,
    saveBookmark,
    clearBookmark,
    resumeBookmarkUrl,
    displayPlaceQuery,
    slugifyPlace,
    kinkstersPath,
    kinkstersUrl,
    placesSearchUrl,
    placeLabelFromPath,
    goPlace,
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/login-redirect.js ---- */
/* Login / home → last kinksters place (no hardcoded city) */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const SESSION_KEY = 'tbcc_fl_login_redirect_done';

  function destUrl() {
    const place = FL.placeNav?.loadCfg?.() || {};
    if (place.lastPath) return `https://fetlife.com${place.lastPath}`;
    if (place.lastQuery && FL.placeNav?.kinkstersUrl) {
      return FL.placeNav.kinkstersUrl(place.lastQuery, place);
    }
    return null;
  }

  function shouldRedirect() {
    const path = (location.pathname || '').replace(/\/+$/, '') || '/';
    if (path !== '/' && path !== '/home') return false;
    const dest = destUrl();
    if (!dest) return false;
    try {
      const destPath = new URL(dest).pathname.replace(/\/+$/, '');
      if (path === destPath) return false;
    } catch (_) {
      /* ignore */
    }
    return true;
  }

  function go() {
    if (sessionStorage.getItem(SESSION_KEY)) return;
    if (!shouldRedirect()) return;
    const dest = destUrl();
    if (!dest) return;
    sessionStorage.setItem(SESSION_KEY, '1');
    location.replace(dest);
  }

  FL.features = FL.features || {};
  FL.features.loginRedirect = {
    start() {
      go();
      this._unsub = S.spa.onChange(() => setTimeout(go, 80));
    },
    stop() {
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/gender-filter.js ---- */
/* ASL-style list filter: hide males / require female / require location text */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const HIDDEN = 'data-tbcc-fl-gender-hidden';
  const CFG_KEY = 'tbcc_fl_gender_filter_v1';
  const STYLE_ID = 'tbcc-fl-gender-style';

  const DEFAULT_CFG = {
    hideMale: true,
    hideFtM: false,
    /**
     * Hide cards whose sex parses as something other than F.
     * Unknown sex stays visible; auto-follow still refuses non-F when skip is on.
     */
    femaleOnly: true,
    locationInclude: '',
  };

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  function ensureHideCss() {
    S.ensureStyle(
      STYLE_ID,
      `[${HIDDEN}="1"]{display:none!important;pointer-events:none!important;height:0!important;overflow:hidden!important;margin:0!important;padding:0!important;border:none!important}`
    );
  }

  /**
   * Parse FetLife vitals: "28F Domme", "27M Switch", "25MtF", "47CD/TV", "46M Exploring".
   */
  function parseSex(text) {
    const t = String(text || '')
      .replace(/\u00a0/g, ' ')
      .replace(/[\u200b\u200c\u200d\ufeff]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t) return null;
    const m =
      t.match(/\b(\d{1,2})\s*(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
      t.match(/\b(\d{1,2})(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
      t.match(/(?:^|[^\dA-Za-z])(\d{2})\s*([MF])(?=[^a-zA-Z]|$)/);
    if (!m) return null;
    return String(m[2]).toUpperCase();
  }

  function controlLabel(btn) {
    const span = btn.querySelector?.('span');
    return (span ? span.textContent : btn.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function isFollowControl(btn) {
    return /^(Follow|Following|Follow Pending|Follow Back|Unfollow)$/i.test(controlLabel(btn));
  }

  function followControls(el) {
    if (!el || !el.querySelectorAll) return [];
    return [...el.querySelectorAll('button')].filter(isFollowControl);
  }

  /**
   * Prefer short vitals nodes; fall back to full card text.
   * Does not depend on /users/id URLs (FetLife often uses nickname links).
   */
  function vitalsText(card) {
    if (!card) return '';
    const nodes = card.querySelectorAll?.(
      '.fl-member-card__info, [class*="member-card__info"], span, div, p, a'
    );
    if (nodes && nodes.length) {
      let best = '';
      for (const n of nodes) {
        // Own text only — avoid sucking in the whole grid.
        let own = '';
        for (const child of n.childNodes || []) {
          if (child.nodeType === 3) own += child.textContent || '';
        }
        own = own.replace(/\s+/g, ' ').trim();
        if (!own || own.length > 80) continue;
        if (parseSex(own)) return own;
        if (!best && /\d{2}/.test(own)) best = own;
      }
      if (best) return best;
    }
    return (card.innerText || card.textContent || '').replace(/\s+/g, ' ').trim();
  }

  /**
   * Walk up from a Follow button (or vitals node) to the single-profile card.
   * Stop when the ancestor contains more than one Follow control (grid).
   */
  function resolveMemberCard(start) {
    if (!start) return null;
    let el = start.nodeType === 1 ? start : start.parentElement;
    let fallback = null;
    for (let i = 0; i < 20 && el && el !== document.body && el !== document.documentElement; i++) {
      const controls = followControls(el);
      if (controls.length > 1) break;

      const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      const sex = parseSex(vitalsText(el)) || parseSex(text);
      const hasImg = !!el.querySelector?.('img');

      if (controls.length === 1) {
        fallback = el;
        // Card sweet spot: one follow control + vitals and/or avatar.
        if (sex || (hasImg && text.length > 12 && text.length < 900)) {
          return el;
        }
      }

      // Started from a vitals span — grow until we pick up the Follow button.
      if (controls.length === 0 && sex && text.length < 120) {
        fallback = fallback || el;
      }

      el = el.parentElement;
    }
    return fallback;
  }

  function isMaleSex(sex, cfg) {
    if (!sex) return false;
    if (sex === 'M') return !!cfg.hideMale;
    if (sex === 'FTM' && cfg.hideFtM) return true;
    return false;
  }

  function locationNeedles(cfg) {
    return String(cfg.locationInclude || '')
      .split(/[,]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
  }

  function onGeoScopedListPage() {
    return /\/p\/[^/]+\/[^/]+\/[^/]+\/kinksters/i.test(location.pathname || '');
  }

  /** Single-member profile (not kinksters lists) — never ASL-remove header actions. */
  function onMemberProfilePage() {
    const path = String(location.pathname || '').replace(/\/+$/, '') || '/';
    if (/\/kinksters(\/|$)/i.test(path)) return false;
    if (/^\/users\/\d+(\/|$)/i.test(path)) return true;
    const m = path.match(
      /^\/([^/]+)(?:\/(about|pictures|videos|posts|friends|followers|following|activity|wall|relations))?$/i
    );
    if (!m) return false;
    const reserved = new Set([
      'home',
      'search',
      'login',
      'signup',
      'groups',
      'events',
      'videos',
      'pictures',
      'posts',
      'inbox',
      'notifications',
      'settings',
      'support',
      'p',
      'explore',
      'feed',
      'kinksters',
      'city',
      'places',
      'fetishes',
      'writings',
      'ads',
      'admin',
      'api',
      'oauth',
      'logout',
      'chat',
      'messages',
    ]);
    return !reserved.has(String(m[1] || '').toLowerCase());
  }

  function locationOk(text, cfg) {
    const needles = locationNeedles(cfg);
    if (!needles.length) return true;
    if (onGeoScopedListPage()) return true;
    const t = String(text || '').toLowerCase();
    return needles.some((n) => t.includes(n));
  }

  function shouldHideCard(text, cfg) {
    const sex = parseSex(text);
    if (isMaleSex(sex, cfg)) return true;
    if (cfg.femaleOnly && sex && sex !== 'F') return true;
    if (!locationOk(text, cfg)) return true;
    return false;
  }

  function shouldSkipFollow(card, cfg) {
    const c = cfg || loadCfg();
    const text = vitalsText(card) || (card?.innerText || card?.textContent || '');
    const sex = parseSex(text);
    if (isMaleSex(sex, c)) return true;
    if (c.femaleOnly) return sex !== 'F';
    if (c.hideMale && sex === 'M') return true;
    if (!locationOk(text, c)) return true;
    return false;
  }

  function hideCard(card) {
    if (!card || !card.isConnected) return;
    card.setAttribute(HIDDEN, '1');
    // Remove from DOM so flex/grid gaps collapse (display:none left empty slots).
    try {
      card.remove();
    } catch (_) {
      try {
        card.style.setProperty('display', 'none', 'important');
      } catch (__) { /* ignore */ }
    }
  }

  function unhideCard(card) {
    if (!card) return;
    card.removeAttribute(HIDDEN);
    try {
      card.style.removeProperty('display');
    } catch (_) { /* ignore */ }
  }

  /** Common parent of member cards (kinksters list). */
  function listRoot() {
    const marked = document.querySelector('[data-tbcc-fl-list="1"]');
    if (marked) return marked;
    const cards = cardRoots().filter((c) => c && c.isConnected);
    if (cards.length >= 2) {
      let a = cards[0];
      let b = cards[1];
      const path = new Set();
      for (let el = a; el; el = el.parentElement) path.add(el);
      for (let el = b; el; el = el.parentElement) {
        if (path.has(el) && el !== document.body && el !== document.documentElement) {
          return el;
        }
      }
    }
    if (cards[0]?.parentElement) return cards[0].parentElement;
    return null;
  }

  function cardRootsIn(root) {
    if (!root) return cardRoots();
    const cards = new Set();
    root.querySelectorAll('button').forEach((btn) => {
      if (!isFollowControl(btn)) return;
      const card = resolveMemberCard(btn);
      if (card && root.contains(card)) cards.add(card);
    });
    return [...cards];
  }

  function ensureListLayout(root) {
    if (!root) return;
    root.setAttribute('data-tbcc-fl-list', '1');
    S.ensureStyle(
      'tbcc-fl-list-layout',
      `[data-tbcc-fl-list="1"]{
        display:flex!important;flex-direction:column!important;flex-wrap:nowrap!important;
        gap:10px!important;width:100%!important;
      }
      [data-tbcc-fl-list="1"]>*{width:100%!important;max-width:100%!important;float:none!important;
        position:relative!important;left:auto!important;right:auto!important;grid-column:auto!important;
        grid-row:auto!important;}`
    );
  }

  /**
   * Discover cards primarily via Follow controls — works without /users/\d+ hrefs.
   */
  function cardRoots() {
    const cards = new Set();

    document.querySelectorAll('button').forEach((btn) => {
      if (!isFollowControl(btn)) return;
      const card = resolveMemberCard(btn);
      if (card) cards.add(card);
    });

    // Also anchor on short vitals text nodes (age+sex) in case Follow label differs.
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, {
      acceptNode(node) {
        if (!node || node.id === 'tbcc-fl-overlay') return NodeFilter.FILTER_REJECT;
        if (node.closest?.('#tbcc-fl-overlay')) return NodeFilter.FILTER_REJECT;
        const tag = node.tagName;
        if (tag !== 'SPAN' && tag !== 'DIV' && tag !== 'P' && tag !== 'A' && tag !== 'LI') {
          return NodeFilter.FILTER_SKIP;
        }
        let own = '';
        for (const child of node.childNodes || []) {
          if (child.nodeType === 3) own += child.textContent || '';
        }
        own = own.replace(/\s+/g, ' ').trim();
        if (own.length < 3 || own.length > 64) return NodeFilter.FILTER_SKIP;
        if (!parseSex(own)) return NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n;
    while ((n = walker.nextNode())) {
      const card = resolveMemberCard(n);
      if (card) cards.add(card);
    }

    return [...cards];
  }

  function apply() {
    ensureHideCss();
    if (onMemberProfilePage()) {
      // Profile header Follow/Friend/Message share one ancestor with vitals — never strip them.
      return { cards: 0, hidden: 0, kept: 0, skipped: 'profile' };
    }
    const cfg = loadCfg();
    const active =
      cfg.hideMale || cfg.hideFtM || cfg.femaleOnly || locationNeedles(cfg).length > 0;

    // Mark list root *before* removals so infinite scroll can still append into an emptied list.
    const root = listRoot();
    if (root) ensureListLayout(root);

    if (!active) {
      return { cards: 0, hidden: 0, kept: cardRoots().length };
    }

    const cards = cardRoots();
    let hidden = 0;
    let kept = 0;
    for (const card of cards) {
      if (!card.isConnected) continue;
      const text = vitalsText(card) || card.innerText || card.textContent || '';
      if (shouldHideCard(text, cfg)) {
        hideCard(card);
        hidden += 1;
      } else {
        kept += 1;
      }
    }

    console.info(`[FL suite] ASL apply: ${cards.length} cards, ${hidden} removed, ${kept} kept`, cfg);
    return { cards: cards.length, hidden, kept };
  }

  FL.genderFilter = {
    loadCfg,
    saveCfg,
    parseSex,
    vitalsText,
    resolveMemberCard,
    cardRoots,
    cardRootsIn,
    listRoot,
    ensureListLayout,
    apply,
    onMemberProfilePage,
    shouldHideCard,
    shouldSkipFollow,
    isMaleCard(el) {
      const card = resolveMemberCard(el) || el;
      return shouldHideCard(vitalsText(card) || card?.innerText || '', loadCfg());
    },
    isFilteredCard(el) {
      const card = resolveMemberCard(el) || el;
      if (card?.getAttribute?.(HIDDEN) === '1') return true;
      return shouldHideCard(vitalsText(card) || card?.innerText || '', loadCfg());
    },
  };

  FL.features = FL.features || {};
  FL.features.genderFilter = {
    start() {
      ensureHideCss();
      apply();
      this._unsub = S.observer.subscribe(() => apply());
      this._unsubSpa = S.spa.onChange(() => setTimeout(apply, 200));
      [400, 1200, 2500].forEach((ms) => setTimeout(apply, ms));
    },
    stop() {
      this._unsub?.();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/auto-follow.js ---- */
/* Auto-follow with scroll + speed — adapted from FetLife Auto-Follow */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const SPEED_PRESETS = {
    instant: { min: 10, max: 50, label: 'Instant (10-50ms)' },
    fast: { min: 50, max: 200, label: 'Fast (50-200ms)' },
    normal: { min: 200, max: 500, label: 'Normal (200-500ms)' },
    slow: { min: 500, max: 1000, label: 'Slow (500-1000ms)' },
    stealth: { min: 1000, max: 2000, label: 'Stealth (1-2s)' },
  };

  const CFG_KEY = 'tbcc_fl_autofollow_cfg_v1';
  const DEFAULT_CFG = {
    speed: 'fast',
    skipMale: true,
    autoStartOnKinksters: true,
    /** Open auto-follow panel on /search (global search) pages. */
    openOnSearch: true,
  };

  let MIN_DELAY = 50;
  let MAX_DELAY = 200;
  const MAX_RETRIES = 3;
  const SCROLL_DELAY = 1000;

  let followCount = 0;
  let isRunning = false;
  let started = false;

  function loadCfg() {
    const saved = S.storage.get(CFG_KEY, null);
    return { ...DEFAULT_CFG, ...(saved && typeof saved === 'object' ? saved : {}) };
  }

  function saveCfg(cfg) {
    S.storage.set(CFG_KEY, cfg);
  }

  function applySpeed(key) {
    const p = SPEED_PRESETS[key] || SPEED_PRESETS.fast;
    MIN_DELAY = p.min;
    MAX_DELAY = p.max;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function randomDelay() {
    return sleep(Math.random() * (MAX_DELAY - MIN_DELAY) + MIN_DELAY);
  }

  async function scrollToBottom() {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(SCROLL_DELAY);
  }

  function buttonLabel(btn) {
    const span = btn.querySelector('span');
    return (span ? span.textContent : btn.textContent || '').trim();
  }

  function cardForButton(btn) {
    return FL.genderFilter?.resolveMemberCard?.(btn) || fallbackCardForButton(btn);
  }

  function fallbackCardForButton(btn) {
    let el = btn;
    for (let i = 0; i < 8 && el; i++) {
      if (el.querySelector?.('a[href*="/users/"]')) return el;
      el = el.parentElement;
    }
    return btn.parentElement || btn;
  }

  function findFollowButtons() {
    const cfg = loadCfg();
    const gfCfg = FL.genderFilter?.loadCfg?.() || {};
    const buttons = [];
    // Re-apply ASL hide before each scan so newly scrolled cards are gone.
    try {
      FL.genderFilter?.apply?.();
    } catch (_) { /* ignore */ }

    document.querySelectorAll('button').forEach((btn) => {
      if (buttonLabel(btn) !== 'Follow') return;
      const card = cardForButton(btn);
      if (!card) return;
      if (card.getAttribute?.('data-tbcc-fl-gender-hidden') === '1') return;
      if (card.closest?.('[data-tbcc-fl-gender-hidden="1"]')) return;
      if (cfg.skipMale) {
        if (FL.genderFilter?.shouldSkipFollow?.(card, gfCfg)) return;
        if (FL.genderFilter?.isFilteredCard?.(card)) return;
      }
      buttons.push(btn);
    });
    return buttons;
  }

  async function followUser(button, retryCount = 0) {
    if (buttonLabel(button) !== 'Follow') return false;
    const cfg = loadCfg();
    const gfCfg = FL.genderFilter?.loadCfg?.() || {};
    const card = cardForButton(button);
    if (cfg.skipMale && FL.genderFilter?.shouldSkipFollow?.(card, gfCfg)) {
      return false;
    }
    button.focus();
    await sleep(10 + Math.random() * 15);
    // Final gate immediately before click — vitals may have painted late.
    if (cfg.skipMale && FL.genderFilter?.shouldSkipFollow?.(cardForButton(button), gfCfg)) {
      return false;
    }
    button.click();
    await sleep(75 + Math.random() * 50);
    const newText = buttonLabel(button);
    if (
      newText === 'Following' ||
      newText === 'Unfollow' ||
      newText === 'Follow pending' ||
      newText === 'Pending' ||
      button.disabled
    ) {
      followCount += 1;
      FL.autoFollow?.onProgress?.(followCount);
      return true;
    }
    if (retryCount < MAX_RETRIES) {
      await sleep(200 + Math.random() * 100);
      return followUser(button, retryCount + 1);
    }
    return false;
  }

  async function startAutoFollow() {
    if (isRunning) return;
    const cfg = loadCfg();
    applySpeed(cfg.speed);
    isRunning = true;
    followCount = 0;
    FL.autoFollow?.onState?.(true, followCount);

    const processed = new WeakSet();
    let consecutiveEmpty = 0;

    while (isRunning) {
      const all = findFollowButtons();
      const fresh = all.filter((b) => !processed.has(b));
      if (!fresh.length) {
        consecutiveEmpty += 1;
        if (consecutiveEmpty >= 3) {
          const before = all.length;
          await scrollToBottom();
          await sleep(SCROLL_DELAY / 2);
          const after = findFollowButtons().length;
          if (after <= before) break;
          consecutiveEmpty = 0;
          continue;
        }
        await sleep(200);
        continue;
      }
      consecutiveEmpty = 0;
      for (const btn of fresh) {
        if (!isRunning) break;
        processed.add(btn);
        await followUser(btn);
        if (isRunning) await randomDelay();
      }
      if (!isRunning) break;
      if (fresh.length < 10) await scrollToBottom();
      else await sleep(50);
    }

    isRunning = false;
    FL.autoFollow?.onState?.(false, followCount);
  }

  function stopAutoFollow() {
    isRunning = false;
    FL.autoFollow?.onState?.(false, followCount);
  }

  function isKinkstersPage() {
    return /\/kinksters/i.test(location.pathname);
  }

  function isSearchPage() {
    const path = location.pathname || '';
    return /\/search/i.test(path) || /[?&]q=/i.test(location.search || '');
  }

  FL.autoFollow = {
    SPEED_PRESETS,
    loadCfg,
    saveCfg,
    start: startAutoFollow,
    stop: stopAutoFollow,
    isRunning: () => isRunning,
    getCount: () => followCount,
    onProgress: null,
    onState: null,
    /** @deprecated use FL.placeNav.goPlace */
    goSanJoseFemales() {
      return FL.placeNav?.goPlace?.('San Jose', { syncAsl: true });
    },
    goPlace(placeName, opts) {
      return FL.placeNav?.goPlace?.(placeName, opts);
    },
  };

  FL.features = FL.features || {};
  FL.features.autoFollow = {
    start() {
      if (started) return;
      started = true;
      const cfg = loadCfg();
      applySpeed(cfg.speed);
      const maybeOpen = () => {
        if (isKinkstersPage()) {
          FL.overlay?.open?.('autofollow');
          if (cfg.autoStartOnKinksters && !isRunning) startAutoFollow();
          return;
        }
        if (cfg.openOnSearch !== false && isSearchPage()) {
          FL.overlay?.open?.('autofollow');
        }
      };
      setTimeout(maybeOpen, 800);
      this._unsubSpa = S.spa.onChange(() => setTimeout(maybeOpen, 400));
    },
    stop() {
      started = false;
      stopAutoFollow();
      this._unsubSpa?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/infinite-scroll.js ---- */
/* Kinksters infinite scroll — append next pages; ASL-filter as we go */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const STATUS_ID = 'tbcc-fl-infinite-status';
  const MIN_KEEPERS = 16;
  const MAX_PAGES_PER_TOPUP = 8;
  const FETCH_GAP_MS = 450;

  let started = false;
  let loading = false;
  let stopped = false;
  let nextPage = null;
  let totalResults = null;
  let pageSize = 20;
  let pagesFetched = 0;
  let keepersAppended = 0;
  let seenKeys = new Set();
  let onScroll = null;
  let topUpTimer = null;

  function isKinkstersList() {
    return /\/kinksters/i.test(location.pathname || '');
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function parseResultMeta() {
    const text = document.body?.innerText || '';
    const m = text.match(/(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)\s+of\s+(\d[\d,]*)/i);
    if (!m) return null;
    const start = parseInt(m[1].replace(/,/g, ''), 10);
    const end = parseInt(m[2].replace(/,/g, ''), 10);
    const total = parseInt(m[3].replace(/,/g, ''), 10);
    const size = Math.max(1, end - start + 1);
    const page = Math.max(1, Math.ceil(end / size));
    return { start, end, total, pageSize: size, page };
  }

  function pageFromUrl() {
    try {
      const p = new URL(location.href).searchParams.get('page');
      if (p) return Math.max(1, parseInt(p, 10) || 1);
    } catch (_) { /* ignore */ }
    return null;
  }

  function urlForPage(page) {
    const u = new URL(location.href);
    u.searchParams.set('page', String(page));
    return u.href;
  }

  function cardKey(card) {
    const links = [...(card.querySelectorAll?.('a[href]') || [])];
    for (const a of links) {
      const href = a.getAttribute('href') || '';
      if (/\/users\/\d+/.test(href)) return href.replace(/#.*$/, '');
      if (/^\/[A-Za-z0-9._-]{2,40}\/?$/.test(href)) return href.replace(/\/$/, '');
    }
    const t = (card.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    return t || Math.random().toString(36);
  }

  function seedSeenFromDom() {
    const gf = FL.genderFilter;
    const cards = gf?.cardRoots?.() || [];
    for (const c of cards) seenKeys.add(cardKey(c));
  }

  function hidePagination() {
    S.ensureStyle(
      'tbcc-fl-hide-pager',
      `[data-tbcc-fl-pager-hidden="1"]{display:none!important}`
    );
    const candidates = [...document.querySelectorAll('nav, div, ul, ol')];
    for (const el of candidates) {
      if (el.closest?.('#tbcc-fl-overlay')) continue;
      const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
      if (t.length > 120) continue;
      if (/\bPrev\b/i.test(t) && /\bNext\b/i.test(t) && /\b\d+\b/.test(t)) {
        el.setAttribute('data-tbcc-fl-pager-hidden', '1');
      }
    }
  }

  function ensureStatus() {
    let el = document.getElementById(STATUS_ID);
    if (el) return el;
    S.ensureStyle(
      STATUS_ID + '-css',
      `#${STATUS_ID}{
        position:fixed;z-index:999990;left:50%;transform:translateX(-50%);bottom:18px;
        background:#141414;color:#e8e8e8;border:1px solid #333;border-radius:999px;
        padding:8px 16px;font:12px/1.3 system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.45);
        max-width:min(92vw,520px);text-align:center;pointer-events:none;
      }`
    );
    el = document.createElement('div');
    el.id = STATUS_ID;
    document.documentElement.appendChild(el);
    return el;
  }

  function updateStatus(extra) {
    const el = ensureStatus();
    const kept = FL.genderFilter?.cardRoots?.()?.length ?? 0;
    const total = totalResults != null ? totalResults.toLocaleString() : '?';
    const page = nextPage != null ? nextPage - 1 : '?';
    el.textContent =
      extra ||
      `TBCC infinite · ${kept} on page · through index page ${page} · ${total} total` +
        (loading ? ' · loading…' : stopped ? ' · done' : '');
  }

  function nearBottom() {
    const doc = document.documentElement;
    const scrollPos = window.scrollY + window.innerHeight;
    const height = Math.max(doc.scrollHeight, document.body?.scrollHeight || 0);
    return scrollPos >= height - 900;
  }

  async function fetchDoc(page) {
    const url = urlForPage(page);
    const res = await fetch(url, {
      credentials: 'include',
      headers: {
        Accept: 'text/html',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const html = await res.text();
    return new DOMParser().parseFromString(html, 'text/html');
  }

  /**
   * Extract member cards from a fetched document using Follow controls.
   */
  function extractCards(doc) {
    const gf = FL.genderFilter;
    if (!gf?.resolveMemberCard) return [];
    const out = [];
    const seen = new Set();
    doc.querySelectorAll('button').forEach((btn) => {
      const span = btn.querySelector('span');
      const lab = (span ? span.textContent : btn.textContent || '').replace(/\s+/g, ' ').trim();
      if (!/^(Follow|Following|Follow Pending|Follow Back|Unfollow)$/i.test(lab)) return;
      const card = gf.resolveMemberCard(btn);
      if (!card || seen.has(card)) return;
      seen.add(card);
      out.push(card);
    });
    return out;
  }

  function appendKeepers(cards) {
    const gf = FL.genderFilter;
    const cfg = gf?.loadCfg?.() || {};
    const root = gf?.listRoot?.();
    if (!root || !gf) return 0;
    gf.ensureListLayout?.(root);
    let added = 0;
    for (const remote of cards) {
      const text = gf.vitalsText(remote) || remote.innerText || '';
      if (gf.shouldHideCard(text, cfg)) continue;
      const key = cardKey(remote);
      if (seenKeys.has(key)) continue;
      const node = document.importNode(remote, true);
      // Strip scripts from imported HTML
      node.querySelectorAll?.('script').forEach((s) => s.remove());
      const localKey = cardKey(node);
      if (seenKeys.has(localKey)) continue;
      seenKeys.add(key);
      seenKeys.add(localKey);
      node.setAttribute('data-tbcc-fl-appended', '1');
      root.appendChild(node);
      added += 1;
      keepersAppended += 1;
    }
    return added;
  }

  async function loadNextPage() {
    if (loading || stopped || nextPage == null) return 0;
    loading = true;
    updateStatus();
    try {
      const doc = await fetchDoc(nextPage);
      const cards = extractCards(doc);
      const added = appendKeepers(cards);
      pagesFetched += 1;
      nextPage += 1;
      // Breadcrumb: last completed page while scrolling kinksters.
      try {
        const path = location.pathname.replace(/\/+$/, '');
        if (/\/kinksters$/i.test(path)) {
          FL.placeNav?.saveBookmark?.({
            path,
            page: Math.max(1, nextPage - 1),
            placeLabel: FL.placeNav.placeLabelFromPath?.(path) || '',
          });
        }
      } catch (_) { /* ignore */ }
      // Stop when a page returns no cards at all (end of list / blocked).
      if (!cards.length) {
        stopped = true;
      }
      // Soft cap: if we've passed total/pageSize
      if (totalResults != null && pageSize > 0) {
        const maxPage = Math.ceil(totalResults / pageSize);
        if (nextPage > maxPage + 1) stopped = true;
      }
      console.info(`[FL suite] infinite page→ +${added} keepers (${cards.length} raw)`, {
        nextPage,
        keepersAppended,
      });
      return added;
    } catch (err) {
      console.warn('[FL suite] infinite fetch failed', err);
      updateStatus(`TBCC infinite · fetch error — retry on scroll (${String(err.message || err)})`);
      return 0;
    } finally {
      loading = false;
      updateStatus();
      // Re-run ASL on any leftover males that snuck in via markup quirks
      try {
        FL.genderFilter?.apply?.();
      } catch (_) { /* ignore */ }
    }
  }

  async function topUp(minKeepers) {
    const target = minKeepers ?? MIN_KEEPERS;
    let guard = 0;
    while (!stopped && guard < MAX_PAGES_PER_TOPUP) {
      const kept = FL.genderFilter?.cardRoots?.()?.filter((c) => c.isConnected).length || 0;
      if (kept >= target && !nearBottom()) break;
      if (!nearBottom() && kept >= Math.min(8, target)) break;
      guard += 1;
      await loadNextPage();
      await sleep(FETCH_GAP_MS);
      if (stopped) break;
    }
    updateStatus();
  }

  function scheduleTopUp() {
    if (topUpTimer) clearTimeout(topUpTimer);
    topUpTimer = setTimeout(() => {
      topUpTimer = null;
      void topUp(MIN_KEEPERS);
    }, 200);
  }

  function onScrollHandler() {
    if (!started || stopped) return;
    if (nearBottom()) void topUp(MIN_KEEPERS);
  }

  FL.infiniteScroll = {
    status: () => ({
      nextPage,
      totalResults,
      pagesFetched,
      keepersAppended,
      loading,
      stopped,
    }),
    loadMore: () => topUp(MIN_KEEPERS + 20),
  };

  FL.features = FL.features || {};
  FL.features.infiniteScroll = {
    start() {
      if (started) return;
      if (!isKinkstersList()) return;
      started = true;
      stopped = false;
      loading = false;
      keepersAppended = 0;
      pagesFetched = 0;
      seenKeys = new Set();

      const meta = parseResultMeta();
      if (meta) {
        totalResults = meta.total;
        pageSize = meta.pageSize;
        nextPage = meta.page + 1;
      } else {
        nextPage = (pageFromUrl() || 1) + 1;
      }

      seedSeenFromDom();
      hidePagination();
      FL.genderFilter?.ensureListLayout?.(FL.genderFilter.listRoot?.());
      FL.genderFilter?.apply?.();
      updateStatus();

      onScroll = onScrollHandler;
      window.addEventListener('scroll', onScroll, { passive: true });
      this._unsubSpa = S.spa.onChange(() => {
        if (!isKinkstersList()) return;
        setTimeout(() => {
          hidePagination();
          seedSeenFromDom();
          scheduleTopUp();
        }, 300);
      });

      // After ASL removes males, refill the viewport from following pages.
      [600, 1500, 3000].forEach((ms) => setTimeout(scheduleTopUp, ms));
      console.info('[FL suite] infinite scroll on', { nextPage, totalResults, pageSize });
    },
    stop() {
      started = false;
      stopped = true;
      if (onScroll) window.removeEventListener('scroll', onScroll);
      onScroll = null;
      if (topUpTimer) clearTimeout(topUpTimer);
      this._unsubSpa?.();
      document.getElementById(STATUS_ID)?.remove();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/data/privacy-presets.js ---- */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const FL = (US.fetlife = US.fetlife || {});
  FL.privacyPresets = {
  "version": 1,
  "sourceNote": "Baseline Lockdown mirrors Documents/fetlife-privacy-config.txt (Jul 2026). Edit this file, then npm run build:nobump in tbcc/userscripts.",
  "settingsUrl": "https://fetlife.com/settings/account",
  "activeKey": "tbcc_fl_privacy_active_v1",
  "pendingKey": "tbcc_fl_privacy_pending_v1",
  "levels": [
    {
      "id": "lockdown",
      "label": "1 · Lockdown",
      "short": "Current conservative baseline",
      "blurb": "Follow approval on, not recommended, places section hidden, RSVPs Only Me, wall No One.",
      "settings": {
        "followAllow": true,
        "followApprovalRequired": true,
        "allowRecommended": false,
        "friendRequests": "All FetLifers",
        "tags": "Only Friends of Friends",
        "eventInvites": "Friends and People I Follow",
        "groupInvites": "Friends and People I Follow",
        "kinkyPopular": { "pictures": true, "videos": true, "writings": true },
        "freshPervy": { "pictures": true, "videos": true, "writings": true },
        "searchContent": { "pictures": true, "videos": true, "writings": true, "statuses": true },
        "locationVisibility": { "city": true, "state": true, "country": true },
        "placesOverrideHide": true,
        "eventRsvp": "Only Me",
        "inboxProfile": "Open",
        "wallPosts": "No One",
        "viewCounts": true,
        "crushingOn": true,
        "communityLists": "Friends and Followers",
        "giftSupport": true
      }
    },
    {
      "id": "guarded",
      "label": "2 · Guarded",
      "short": "Slightly more findable locally",
      "blurb": "Still approve followers; show in Places at city level; RSVPs Friends; wall Friends.",
      "settings": {
        "followAllow": true,
        "followApprovalRequired": true,
        "allowRecommended": false,
        "friendRequests": "All FetLifers",
        "tags": "Only Friends of Friends",
        "eventInvites": "Friends and People I Follow",
        "groupInvites": "Friends and People I Follow",
        "kinkyPopular": { "pictures": true, "videos": true, "writings": true },
        "freshPervy": { "pictures": true, "videos": true, "writings": true },
        "searchContent": { "pictures": true, "videos": true, "writings": true, "statuses": true },
        "locationVisibility": { "city": true, "state": true, "country": true },
        "placesOverrideHide": false,
        "eventRsvp": "Friends",
        "inboxProfile": "Open",
        "wallPosts": "Friends",
        "viewCounts": true,
        "crushingOn": true,
        "communityLists": "Friends and Followers",
        "giftSupport": true
      }
    },
    {
      "id": "social",
      "label": "3 · Social",
      "short": "Discoverable + easier contact",
      "blurb": "No follow approval, allow recommendations, tags Friends, broader RSVP visibility.",
      "settings": {
        "followAllow": true,
        "followApprovalRequired": false,
        "allowRecommended": true,
        "friendRequests": "All FetLifers",
        "tags": "Friends",
        "eventInvites": "Friends and People I Follow",
        "groupInvites": "Friends and People I Follow",
        "kinkyPopular": { "pictures": true, "videos": true, "writings": true },
        "freshPervy": { "pictures": true, "videos": true, "writings": true },
        "searchContent": { "pictures": true, "videos": true, "writings": true, "statuses": true },
        "locationVisibility": { "city": true, "state": true, "country": true },
        "placesOverrideHide": false,
        "eventRsvp": "Friends and People I Follow",
        "inboxProfile": "Open",
        "wallPosts": "Friends",
        "viewCounts": true,
        "crushingOn": true,
        "communityLists": "Friends and Followers",
        "giftSupport": true
      }
    },
    {
      "id": "open",
      "label": "4 · Open",
      "short": "Most relaxed discoverability",
      "blurb": "Recommended, tags All FetLifers, wider invites/RSVPs. Still FetLife-only.",
      "settings": {
        "followAllow": true,
        "followApprovalRequired": false,
        "allowRecommended": true,
        "friendRequests": "All FetLifers",
        "tags": "All FetLifers",
        "eventInvites": "All FetLifers",
        "groupInvites": "Friends and People I Follow",
        "kinkyPopular": { "pictures": true, "videos": true, "writings": true },
        "freshPervy": { "pictures": true, "videos": true, "writings": true },
        "searchContent": { "pictures": true, "videos": true, "writings": true, "statuses": true },
        "locationVisibility": { "city": true, "state": true, "country": true },
        "placesOverrideHide": false,
        "eventRsvp": "All FetLifers",
        "inboxProfile": "Open",
        "wallPosts": "Friends",
        "viewCounts": true,
        "crushingOn": true,
        "communityLists": "All FetLifers",
        "giftSupport": true
      }
    }
  ]
};
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/data/genders.js ---- */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const FL = (US.fetlife = US.fetlife || {});
  FL.genderCatalog = [
  "Female",
  "Woman",
  "Man",
  "Cisgender",
  "Transgender",
  "Trans Woman",
  "Trans Man",
  "Trans Nonbinary",
  "Transmasculine",
  "Transfeminine",
  "Nonbinary",
  "Genderqueer",
  "Genderfluid",
  "Genderflux",
  "Genderfae",
  "Gender Neutral",
  "Gender Non-Conforming",
  "Gender Expansive",
  "Agender",
  "Apagender",
  "Genderless",
  "Gendervoid",
  "Bigender",
  "Polygender",
  "Omnigender",
  "Pangender",
  "Androgyne",
  "Androx",
  "Gynx",
  "Masc",
  "Femme",
  "Butch",
  "Crossdresser",
  "Genderfuck",
  "Intersex",
  "Intersex Male",
  "Intersex Female",
  "Two-Spirit",
  "Hijra",
  "Maverique",
  "Xenogender",
  "Plural",
  "Questioning",
  "Unsure",
  "Not Applicable"
];
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/privacy-console.js ---- */
/* FLConsole — apply FetLife account privacy presets via Settings page UI */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const PRESETS = () => FL.privacyPresets || { levels: [], settingsUrl: 'https://fetlife.com/settings/account' };
  let started = false;
  let lastStatus = '';

  function levels() {
    return PRESETS().levels || [];
  }

  function getLevel(id) {
    return levels().find((l) => l.id === id) || null;
  }

  function activeId() {
    return S.storage.get(PRESETS().activeKey || 'tbcc_fl_privacy_active_v1', 'lockdown');
  }

  function setActiveId(id) {
    S.storage.set(PRESETS().activeKey || 'tbcc_fl_privacy_active_v1', id);
  }

  function pendingId() {
    return S.storage.get(PRESETS().pendingKey || 'tbcc_fl_privacy_pending_v1', null);
  }

  function setPending(id) {
    if (id) S.storage.set(PRESETS().pendingKey || 'tbcc_fl_privacy_pending_v1', id);
    else S.storage.set(PRESETS().pendingKey || 'tbcc_fl_privacy_pending_v1', null);
  }

  function setStatus(msg) {
    lastStatus = String(msg || '');
    FL.privacyConsole?.onStatus?.(lastStatus);
  }

  function onSettingsPage() {
    const path = location.pathname || '';
    return /\/settings/i.test(path);
  }

  function norm(s) {
    return String(s || '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  function clickableFromText(needle) {
    const n = norm(needle);
    if (!n) return null;
    const nodes = document.querySelectorAll('button, a, label, [role="button"], [role="radio"], [role="option"]');
    for (const el of nodes) {
      const t = norm(el.textContent);
      if (!t) continue;
      if (t === n || t.includes(n)) return el;
    }
    return null;
  }

  function setCheckboxNearLabel(labelText, wantOn) {
    const label = clickableFromText(labelText);
    if (!label) return false;
    const root = label.closest('label') || label.parentElement || label;
    const input =
      (label.tagName === 'INPUT' && label) ||
      root.querySelector?.('input[type="checkbox"]') ||
      label.querySelector?.('input[type="checkbox"]');
    if (input && input.type === 'checkbox') {
      if (!!input.checked !== !!wantOn) {
        input.click();
        return true;
      }
      return true;
    }
    // Toggle-looking buttons / switches
    const pressed = label.getAttribute?.('aria-checked') || label.getAttribute?.('aria-pressed');
    if (pressed != null) {
      const on = pressed === 'true';
      if (on !== !!wantOn) label.click();
      return true;
    }
    return false;
  }

  function chooseOptionNearHeading(headingText, optionText) {
    const heading = Array.from(document.querySelectorAll('h1,h2,h3,h4,legend,label,div,span,p')).find((el) => {
      const t = norm(el.textContent);
      return t === norm(headingText) || (t.length < 80 && t.includes(norm(headingText)));
    });
    if (!heading) {
      const opt = clickableFromText(optionText);
      if (opt) {
        opt.click();
        return true;
      }
      return false;
    }
    let scope = heading.closest('section,fieldset,form,div') || heading.parentElement;
    for (let i = 0; i < 4 && scope; i++) {
      const cand = Array.from(scope.querySelectorAll('button, a, label, [role="radio"], [role="option"], select option')).find(
        (el) => norm(el.textContent) === norm(optionText) || norm(el.textContent).includes(norm(optionText))
      );
      if (cand) {
        if (cand.tagName === 'OPTION') {
          cand.selected = true;
          cand.parentElement?.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
          cand.click();
        }
        return true;
      }
      scope = scope.parentElement;
    }
    const fallback = clickableFromText(optionText);
    if (fallback) {
      fallback.click();
      return true;
    }
    return false;
  }

  function applySettingsObject(settings) {
    const hits = [];
    const miss = [];
    const tryCheck = (label, want) => {
      if (setCheckboxNearLabel(label, want)) hits.push(label);
      else miss.push(label);
    };
    const tryChoice = (heading, option) => {
      if (chooseOptionNearHeading(heading, option)) hits.push(`${heading}→${option}`);
      else miss.push(`${heading}→${option}`);
    };

    tryCheck('Allow members to follow me', settings.followAllow !== false);
    tryCheck('New followers must be approved first', !!settings.followApprovalRequired);
    tryCheck('Allow being recommended to potential followers', !!settings.allowRecommended);
    tryChoice('Who can send you a friend request?', settings.friendRequests);
    tryChoice('Who can tag you in a picture or video?', settings.tags);
    tryChoice('Who can invite you to an event?', settings.eventInvites);
    tryChoice('Who can invite you to a group?', settings.groupInvites);

    const kp = settings.kinkyPopular || {};
    tryCheck('Kinky & Popular', true); // section presence
    if ('pictures' in kp) tryCheck('Pictures', !!kp.pictures);
    // Fresh / search checkboxes often share "Pictures" labels — best-effort only.

    tryCheck("Don't display my profile in the places section", !!settings.placesOverrideHide);
    tryChoice("Who can see on my profile what events I've RSVP'd to?", settings.eventRsvp);
    tryChoice('Who can post on your wall?', settings.wallPosts);
    tryCheck('Display view counts on my posts', settings.viewCounts !== false);
    tryCheck('Allow others to crush on me', settings.crushingOn !== false);
    tryChoice('Who can add you to a Community List?', settings.communityLists);
    tryCheck('Allow people to gift me support', settings.giftSupport !== false);

    return { hits: hits.length, miss: miss.length, missList: miss.slice(0, 12) };
  }

  async function applyPendingIfAny() {
    const id = pendingId();
    if (!id || !onSettingsPage()) return null;
    const level = getLevel(id);
    if (!level) {
      setPending(null);
      return null;
    }
    setStatus(`Applying ${level.label}…`);
    await new Promise((r) => setTimeout(r, 600));
    const result = applySettingsObject(level.settings || {});
    setActiveId(id);
    setPending(null);
    const msg =
      result.miss > 0
        ? `Applied ${level.label}: ${result.hits} matched, ${result.miss} not found — review Settings manually.`
        : `Applied ${level.label}: ${result.hits} controls updated. Confirm Save if FetLife asks.`;
    setStatus(msg);
    console.info('[FLConsole] privacy apply', id, result);
    FL.overlay?.open?.('flconsole');
    return result;
  }

  /**
   * Queue preset and open FetLife Settings so controls can be driven.
   * Privacy is server-side — this is intentional navigation, not silent mutation.
   */
  function applyPreset(id) {
    const level = getLevel(id);
    if (!level) {
      setStatus(`Unknown preset: ${id}`);
      return { ok: false };
    }
    setPending(id);
    setActiveId(id);
    setStatus(`Opening Settings to apply ${level.label}…`);
    if (onSettingsPage()) {
      applyPendingIfAny();
      return { ok: true, queued: false, id };
    }
    const url = PRESETS().settingsUrl || 'https://fetlife.com/settings/account';
    location.assign(url);
    return { ok: true, queued: true, id };
  }

  FL.privacyConsole = {
    levels,
    getLevel,
    activeId,
    applyPreset,
    getStatus: () => lastStatus,
    onStatus: null,
    checklist(id) {
      const level = getLevel(id) || getLevel(activeId());
      if (!level) return [];
      const s = level.settings || {};
      return [
        `Follow allow: ${s.followAllow}`,
        `Follow approval: ${s.followApprovalRequired}`,
        `Recommended: ${s.allowRecommended}`,
        `Friend requests: ${s.friendRequests}`,
        `Tags: ${s.tags}`,
        `Places hidden: ${s.placesOverrideHide}`,
        `Event RSVP: ${s.eventRsvp}`,
        `Wall: ${s.wallPosts}`,
      ];
    },
  };

  FL.features = FL.features || {};
  FL.features.privacyConsole = {
    start() {
      if (started) return;
      started = true;
      setTimeout(() => applyPendingIfAny(), 900);
      this._unsub = S.spa.onChange(() => setTimeout(() => applyPendingIfAny(), 500));
    },
    stop() {
      started = false;
      this._unsub?.();
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/features/overlay.js ---- */
/* TBCC-style chevron overlay: collapsible + paginated suite control */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const COMMUNITY = global.__TBCC_EDITION__ === 'community';
  const SUITE_TITLE = COMMUNITY ? 'FetLife Enhancer' : 'TBCC FetLife Suite';
  const ROOT_ID = 'tbcc-fl-overlay';
  const TOP_KEY = 'tbcc_fl_overlay_top_v1';
  const UI_KEY = 'tbcc_fl_overlay_ui_v1';
  const SYNC_KEYS = [
    UI_KEY,
    TOP_KEY,
    'tbcc_fl_suite_flags_v1',
    'tbcc_fl_gender_filter_v1',
    'tbcc_fl_autofollow_cfg_v1',
    'tbcc_fl_social_proof_v1',
    'tbcc_fl_story_enabled_v1',
    'tbcc_fl_muted_users_v1',
    'tbcc_fl_place_nav_v1',
    'tbcc_fl_kinksters_bookmark_v1',
    'tbcc_fl_privacy_active_v1',
    'tbcc_fl_intel_rows_v1',
    'tbcc_fl_intel_meta_v1',
    'tbcc_fl_title_kw_v1',
  ];
  const INTEL_ROWS_KEY = 'tbcc_fl_intel_rows_v1';
  const INTEL_META_KEY = 'tbcc_fl_intel_meta_v1';
  const KW_KEY = 'tbcc_fl_title_kw_v1';
  const JUMP_STACK_ID = 'tbcc-fl-jump-stack';
  const PAGES_ALL = [
    { id: 'features', title: 'Features' },
    { id: 'autofollow', title: 'Auto-follow' },
    { id: 'gender', title: 'ASL filter' },
    { id: 'keywords', title: 'Keywords' },
    { id: 'flconsole', title: 'FLConsole' },
    { id: 'stories', title: 'Profile & stories' },
    { id: 'mute', title: 'Mute' },
    { id: 'intel', title: 'Intel' },
  ];
  const PAGES = COMMUNITY ? PAGES_ALL.filter((p) => p.id !== 'intel') : PAGES_ALL;

  let pageIndex = 0;
  let collapsed = true;
  let widthMode = 'slim';
  let hooks = {};
  let suppressUiPersist = false;
  let syncBound = false;

  function clampOverlayTop(px) {
    const max = Math.max(8, window.innerHeight - 140);
    return Math.min(max, Math.max(8, Math.round(Number(px) || 72)));
  }

  function loadOverlayTop() {
    const saved = S.storage.get(TOP_KEY, 72);
    return clampOverlayTop(saved);
  }

  function saveOverlayTop(px) {
    S.storage.set(TOP_KEY, clampOverlayTop(px));
  }

  function loadUiState() {
    const saved = S.storage.get(UI_KEY, null);
    const ui = saved && typeof saved === 'object' ? saved : {};
    let idx = Number(ui.pageIndex);
    if (!Number.isFinite(idx) || idx < 0 || idx >= PAGES.length) idx = 0;
    return {
      // Default collapsed when no saved UI (keeps Friend/Follow/Message clickable).
      collapsed: ui.collapsed !== false,
      pageIndex: idx,
      widthMode: (() => {
        const w = String(ui.widthMode || 'slim');
        return w === 'wide' || w === 'normal' || w === 'slim' ? w : 'slim';
      })(),
    };
  }

  function persistUiState() {
    if (suppressUiPersist) return;
    S.storage.set(UI_KEY, {
      collapsed: !!collapsed,
      pageIndex,
      widthMode,
    });
  }

  function applyOverlayTop(root) {
    if (!root) return;
    root.style.top = `${loadOverlayTop()}px`;
  }

  function applyUiState(ui, { renderBody = true } = {}) {
    if (!ui) return;
    suppressUiPersist = true;
    try {
      if (typeof ui.collapsed === 'boolean') collapsed = ui.collapsed;
      if (ui.widthMode === 'slim' || ui.widthMode === 'normal' || ui.widthMode === 'wide') {
        widthMode = ui.widthMode;
      }
      if (Number.isFinite(ui.pageIndex) && ui.pageIndex >= 0 && ui.pageIndex < PAGES.length) {
        pageIndex = ui.pageIndex;
      }
      const root = document.getElementById(ROOT_ID);
      if (root) {
        syncCollapsedUi(root);
        applyOverlayTop(root);
        if (renderBody) render();
      }
    } finally {
      suppressUiPersist = false;
    }
  }

  function bindCrossTabSync() {
    if (syncBound || typeof S.storage.subscribe !== 'function') return;
    syncBound = true;
    S.storage.subscribe(SYNC_KEYS, (key) => {
      if (key === UI_KEY) {
        applyUiState(loadUiState(), { renderBody: true });
        return;
      }
      if (key === TOP_KEY) {
        applyOverlayTop(document.getElementById(ROOT_ID));
        return;
      }
      // Hydrate / re-apply before refreshing the open panel.
      if (key === 'tbcc_fl_suite_flags_v1') {
        hooks.flags?.hydrate?.();
        hooks.onFlagsChange?.();
      }
      if (key === 'tbcc_fl_gender_filter_v1') FL.genderFilter?.apply?.();
      if (key === 'tbcc_fl_social_proof_v1') FL.socialProof?.apply?.();
      const root = document.getElementById(ROOT_ID);
      if (root && !collapsed) render();
    });
  }

  function bindChevronDrag(root, chevron) {
    let drag = null;
    const DRAG_THRESHOLD = 5;

    chevron.addEventListener('pointerdown', (e) => {
      if (e.button != null && e.button !== 0) return;
      drag = {
        pointerId: e.pointerId,
        startY: e.clientY,
        startTop: root.getBoundingClientRect().top,
        moved: false,
      };
      try {
        chevron.setPointerCapture(e.pointerId);
      } catch (_) { /* ignore */ }
      e.preventDefault();
    });

    chevron.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      const dy = e.clientY - drag.startY;
      if (!drag.moved && Math.abs(dy) < DRAG_THRESHOLD) return;
      drag.moved = true;
      const next = clampOverlayTop(drag.startTop + dy);
      root.style.top = `${next}px`;
      chevron.style.cursor = 'grabbing';
    });

    const endDrag = (e) => {
      if (!drag || (e && e.pointerId !== drag.pointerId)) return;
      const wasDrag = drag.moved;
      const top = root.getBoundingClientRect().top;
      if (wasDrag) saveOverlayTop(top);
      chevron.style.cursor = 'grab';
      try {
        if (e) chevron.releasePointerCapture(e.pointerId);
      } catch (_) { /* ignore */ }
      drag = null;
      if (wasDrag) {
        // Suppress the click that follows a drag so we don't toggle open/closed.
        chevron.dataset.suppressClick = '1';
        setTimeout(() => {
          delete chevron.dataset.suppressClick;
        }, 0);
      }
    };

    chevron.addEventListener('pointerup', endDrag);
    chevron.addEventListener('pointercancel', endDrag);
    chevron.addEventListener('lostpointercapture', () => {
      if (drag) {
        if (drag.moved) saveOverlayTop(root.getBoundingClientRect().top);
        drag = null;
        chevron.style.cursor = 'grab';
      }
    });
  }

  function syncCollapsedUi(root) {
    root.classList.toggle('collapsed', collapsed);
    root.classList.toggle('slim', widthMode === 'slim');
    root.classList.toggle('wide', widthMode === 'wide');
    const chevron = root.querySelector('.tbcc-chevron');
    if (chevron) chevron.textContent = collapsed ? 'FL ▸' : 'FL ◂';
    const Rail = global.TBCCSuiteRail;
    if (Rail) {
      Rail.syncJumpStack({
        stackId: JUMP_STACK_ID,
        overlayEl: root,
        visible: true,
        collapsed,
      });
    }
  }

  function loadKeywords() {
    const saved = S.storage.get(KW_KEY, null);
    if (saved && typeof saved === 'object') {
      return {
        titleInclude: String(saved.titleInclude || ''),
        titleExclude: String(saved.titleExclude || ''),
      };
    }
    return { titleInclude: '', titleExclude: '' };
  }

  function saveKeywords(kw) {
    S.storage.set(KW_KEY, {
      titleInclude: String(kw.titleInclude || ''),
      titleExclude: String(kw.titleExclude || ''),
    });
  }

  function keywordTargets() {
    const selectors = ['#stories-list > *', '#fl-masonry-wrap .fl-masonry-col > *', '#stories > *'];
    const found = new Set();
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        if (el.classList?.contains('infinite-loading-container')) return;
        if ((el.textContent || '').trim().length < 20) return;
        if (el.closest(`#${ROOT_ID}`)) return;
        found.add(el);
      });
    }
    return [...found].filter((el) => ![...found].some((o) => o !== el && o.contains(el)));
  }

  function applyKeywordFilters() {
    const Rail = global.TBCCSuiteRail;
    const kw = loadKeywords();
    const match = Rail
      ? (hay) => Rail.matchesKeywords(hay, kw.titleInclude, kw.titleExclude)
      : (hay) => {
          const text = String(hay || '').toLowerCase();
          const ex = String(kw.titleExclude || '')
            .toLowerCase()
            .split(/[\s,]+/)
            .filter(Boolean);
          if (ex.some((k) => text.includes(k))) return false;
          const inc = String(kw.titleInclude || '')
            .toLowerCase()
            .split(/[\s,]+/)
            .filter(Boolean);
          if (!inc.length) return true;
          return inc.every((k) => text.includes(k));
        };
    keywordTargets().forEach((el) => {
      const ok = match(el.textContent || '');
      el.classList.toggle('tbcc-suite-kw-filtered', !ok);
    });
  }

  function mountKeywordBar() {
    const Rail = global.TBCCSuiteRail;
    if (!Rail) return;
    const kw = loadKeywords();
    Rail.mountKeywordBar({
      barId: 'tbcc-fl-kw-bar',
      hint: 'Refines feed/story text on this page (space/comma separated). Same fields as Keywords tab.',
      getInclude: () => loadKeywords().titleInclude,
      getExclude: () => loadKeywords().titleExclude,
      shouldMount: () => true,
      onChange: (inc, exc) => {
        saveKeywords({ titleInclude: inc, titleExclude: exc });
        applyKeywordFilters();
      },
    });
    void kw;
  }

  function ensureDom() {
    if (document.getElementById(ROOT_ID)) return;

    S.ensureStyle(
      ROOT_ID + '-css',
      `
      #${ROOT_ID} {
        position: fixed; z-index: 1000000; top: 72px; right: 0;
        display: flex; align-items: stretch; font: 13px/1.4 system-ui, sans-serif;
        color: #e8e8e8; pointer-events: none;
      }
      #${ROOT_ID} * { box-sizing: border-box; }
      #${ROOT_ID} .tbcc-chevron {
        pointer-events: auto; width: 28px; min-height: 120px;
        background: #141414; border: 1px solid #333; border-right: none;
        border-radius: 10px 0 0 10px; cursor: grab; color: #f43f5e;
        display: flex; align-items: center; justify-content: center;
        writing-mode: vertical-rl; text-orientation: mixed; letter-spacing: .08em;
        font-size: 11px; font-weight: 700; padding: 10px 0;
        touch-action: none; user-select: none;
      }
      #${ROOT_ID} .tbcc-chevron:active { cursor: grabbing; }
      #${ROOT_ID} .tbcc-panel {
        pointer-events: auto; width: min(300px, calc(100vw - 40px));
        max-height: min(72vh, 560px); background: #121212; border: 1px solid #333;
        border-right: none; border-radius: 12px 0 0 12px;
        box-shadow: -8px 0 28px rgba(0,0,0,.45); display: flex; flex-direction: column;
        overflow: hidden;
      }
      #${ROOT_ID}.collapsed .tbcc-panel { display: none; }
      #${ROOT_ID}.slim .tbcc-panel { width: min(240px, calc(100vw - 40px)); }
      #${ROOT_ID}.wide .tbcc-panel { width: min(360px, calc(100vw - 40px)); }
      #${ROOT_ID} .tbcc-head {
        display: flex; align-items: center; gap: 8px; padding: 10px 12px;
        background: #1a1a1a; border-bottom: 1px solid #2a2a2a;
      }
      #${ROOT_ID} .tbcc-head strong { flex: 1; font-size: 13px; }
      #${ROOT_ID} .tbcc-head button, #${ROOT_ID} .tbcc-foot button, #${ROOT_ID} .tbcc-body button.primary {
        background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 6px;
        padding: 6px 10px; cursor: pointer;
      }
      #${ROOT_ID} .tbcc-head button:hover, #${ROOT_ID} .tbcc-foot button:hover {
        border-color: #f43f5e; color: #fff;
      }
      #${ROOT_ID} button.primary {
        background: #9f1239; border-color: #e11d48; width: 100%; margin-top: 8px; font-weight: 600;
      }
      #${ROOT_ID} button.primary.running { background: #3f1d1d; }
      #${ROOT_ID} .tbcc-tabs {
        display: flex; gap: 4px; padding: 8px; border-bottom: 1px solid #2a2a2a; overflow-x: auto;
      }
      #${ROOT_ID} .tbcc-tabs button {
        flex: 0 0 auto; background: transparent; border: 1px solid #333; color: #aaa;
        border-radius: 999px; padding: 4px 10px; cursor: pointer; font-size: 11px;
      }
      #${ROOT_ID} .tbcc-tabs button.active {
        background: #e11d48; border-color: #e11d48; color: #fff;
      }
      #${ROOT_ID} .tbcc-body { padding: 12px; overflow: auto; flex: 1; }
      #${ROOT_ID} .tbcc-foot {
        display: flex; gap: 8px; padding: 8px 12px; border-top: 1px solid #2a2a2a; background: #1a1a1a;
      }
      #${ROOT_ID} .tbcc-foot .page-ind { flex: 1; color: #888; font-size: 12px; align-self: center; }
      #${ROOT_ID} label.row {
        display: flex; gap: 8px; align-items: flex-start; padding: 6px 0; cursor: pointer;
      }
      #${ROOT_ID} .hint { color: #888; font-size: 12px; margin: 0 0 10px; }
      #${ROOT_ID} select, #${ROOT_ID} input[type="text"] {
        width: 100%; background: #1e1e1e; color: #eee; border: 1px solid #444;
        border-radius: 6px; padding: 6px 8px;
      }
      #${ROOT_ID} .field-row {
        display: flex; gap: 6px; align-items: stretch; margin-bottom: 4px;
      }
      #${ROOT_ID} .field-row input[type="text"] { flex: 1; min-width: 0; }
      #${ROOT_ID} button.clear-btn {
        flex: 0 0 auto; margin: 0; padding: 6px 10px; background: #2a2228; color: #eee;
        border: 1px solid #514049; border-radius: 6px; cursor: pointer; font-size: 12px;
      }
      #${ROOT_ID} button.clear-btn:hover { border-color: #f43f5e; }
      #${ROOT_ID} .stat { font-variant-numeric: tabular-nums; color: #fda4af; margin-top: 8px; }
      #${ROOT_ID} details.section {
        border: 1px solid #2a2a2a; border-radius: 8px; margin-bottom: 8px; padding: 0 8px;
      }
      #${ROOT_ID} details.section > summary {
        cursor: pointer; padding: 8px 4px; font-weight: 600; color: #ccc; list-style: none;
      }
      #${ROOT_ID} details.section > summary::-webkit-details-marker { display: none; }
      #${ROOT_ID} details.section > summary::before {
        content: '▸'; display: inline-block; margin-right: 6px; color: #f43f5e;
      }
      #${ROOT_ID} details.section[open] > summary::before { content: '▾'; }
    `
    );

    const root = document.createElement('div');
    root.id = ROOT_ID;
    root.innerHTML = `
      <button type="button" class="tbcc-chevron" title="${SUITE_TITLE}">FL ▸</button>
      <div class="tbcc-panel">
        <div class="tbcc-head">
          <strong>${SUITE_TITLE}</strong>
          <button type="button" data-act="width" title="Cycle panel width">Width</button>
          <button type="button" data-act="collapse">Hide</button>
        </div>
        <div class="tbcc-tabs"></div>
        <div class="tbcc-body"></div>
        <div class="tbcc-foot">
          <button type="button" data-jump="top" title="Back to top">↑</button>
          <button type="button" data-act="prev">Prev</button>
          <span class="page-ind"></span>
          <button type="button" data-act="next">Next</button>
          <button type="button" data-jump="bottom" title="Back to bottom">↓</button>
        </div>
      </div>`;
    document.documentElement.appendChild(root);
    applyOverlayTop(root);
    syncCollapsedUi(root);
    global.TBCCSuiteRail?.ensureStyles?.();
    global.TBCCSuiteRail?.bindFootJumps?.(root);

    const tabs = root.querySelector('.tbcc-tabs');
    PAGES.forEach((p, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = p.title;
      b.dataset.page = p.id;
      b.addEventListener('click', () => {
        pageIndex = i;
        persistUiState();
        render();
      });
      tabs.appendChild(b);
    });

    const chevron = root.querySelector('.tbcc-chevron');
    bindChevronDrag(root, chevron);
    chevron.addEventListener('click', () => {
      if (chevron.dataset.suppressClick) return;
      collapsed = !collapsed;
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="collapse"]').addEventListener('click', () => {
      collapsed = true;
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="width"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      widthMode = widthMode === 'slim' ? 'normal' : widthMode === 'normal' ? 'wide' : 'slim';
      syncCollapsedUi(root);
      persistUiState();
    });
    root.querySelector('[data-act="prev"]').addEventListener('click', () => {
      pageIndex = (pageIndex + PAGES.length - 1) % PAGES.length;
      persistUiState();
      render();
    });
    root.querySelector('[data-act="next"]').addEventListener('click', () => {
      pageIndex = (pageIndex + 1) % PAGES.length;
      persistUiState();
      render();
    });

    window.addEventListener(
      'resize',
      () => {
        applyOverlayTop(root);
      },
      { passive: true }
    );
  }

  function renderFeatures(body) {
    const flags = hooks.flags;
    const labels = hooks.labels || {};
    body.innerHTML = `<p class="hint">Toggle modules. Changes apply immediately.</p>`;
    Object.keys(flags.all()).forEach((key) => {
      if (COMMUNITY && key === 'socialProof') return;
      const lab = document.createElement('label');
      lab.className = 'row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = flags.get(key);
      cb.addEventListener('change', () => {
        flags.set(key, cb.checked);
        hooks.onFlagsChange?.(key, cb.checked);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(labels[key] || key));
      body.appendChild(lab);
    });
  }

  function renderAutoFollow(body) {
    const af = FL.autoFollow;
    const cfg = af?.loadCfg?.() || {};
    const placeCfg = FL.placeNav?.loadCfg?.() || {};
    const bm = FL.placeNav?.loadBookmark?.();
    const placeDisplay = FL.placeNav?.displayPlaceQuery?.() || placeCfg.lastQuery || '';
    const bmLabel = bm
      ? `Resume p.${bm.page}${bm.placeLabel ? ` · ${bm.placeLabel}` : ''}`
      : '';
    body.innerHTML = `
      <p class="hint">Clicks Follow on visible cards; infinite scroll fills the pool. Place opens /p/…/kinksters (navigation only — not the ASL vitals filter).</p>
      <label class="row">Place (city / area)</label>
      <div class="field-row">
        <input type="text" data-af="place" placeholder="e.g. Bangkok" />
        <button type="button" class="clear-btn" data-af="clear-place" title="Clear saved place">Clear</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button type="button" class="primary" data-af="go-place" style="margin-top:0;flex:1">Open kinksters</button>
        <button type="button" class="clear-btn" data-af="go-search" style="flex:0 0 auto">Search</button>
      </div>
      <p class="hint" data-af="place-hint" style="margin-top:6px">Default region for US slugs: California. Wrong slug? use Search.</p>
      <div style="display:flex;gap:8px;margin:8px 0;flex-wrap:wrap">
        <button type="button" class="clear-btn" data-af="resume" ${bm ? '' : 'disabled'} style="flex:1">${bm ? bmLabel : 'No bookmark yet'}</button>
        <button type="button" class="clear-btn" data-af="clear-bm" ${bm ? '' : 'disabled'}>Clear bookmark</button>
      </div>
      <label class="row">Speed</label>
      <select data-af="speed"></select>
      <label class="row"><input type="checkbox" data-af="skipMale" /> Respect ASL sex filters when following</label>
      <p class="hint" style="margin-top:0">When on: skip cards the ASL tab would remove (sex rules). ASL location needles do not apply on place kinksters pages.</p>
      <label class="row"><input type="checkbox" data-af="autoStartOnKinksters" /> Auto-start on /kinksters</label>
      <label class="row"><input type="checkbox" data-af="openOnSearch" /> Open this panel on /search</label>
      <div class="stat" data-af="stat">Followed: ${af?.getCount?.() || 0}</div>
      <button type="button" class="primary" data-af="toggle">Start auto-follow</button>
    `;
    const placeInput = body.querySelector('[data-af="place"]');
    placeInput.value = placeDisplay;
    const sel = body.querySelector('[data-af="speed"]');
    Object.entries(af?.SPEED_PRESETS || {}).forEach(([k, v]) => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = v.label;
      if (k === (cfg.speed || 'fast')) opt.selected = true;
      sel.appendChild(opt);
    });
    body.querySelector('[data-af="skipMale"]').checked = cfg.skipMale !== false;
    body.querySelector('[data-af="autoStartOnKinksters"]').checked = cfg.autoStartOnKinksters !== false;
    body.querySelector('[data-af="openOnSearch"]').checked = cfg.openOnSearch !== false;

    const persist = () => {
      af.saveCfg({
        speed: sel.value,
        skipMale: body.querySelector('[data-af="skipMale"]').checked,
        autoStartOnKinksters: body.querySelector('[data-af="autoStartOnKinksters"]').checked,
        openOnSearch: body.querySelector('[data-af="openOnSearch"]').checked,
      });
    };
    sel.addEventListener('change', persist);
    body.querySelector('[data-af="skipMale"]').addEventListener('change', persist);
    body.querySelector('[data-af="autoStartOnKinksters"]').addEventListener('change', persist);
    body.querySelector('[data-af="openOnSearch"]').addEventListener('change', persist);

    const persistPlace = () => {
      FL.placeNav?.saveCfg?.({ lastQuery: placeInput.value.trim() });
    };
    placeInput.addEventListener('change', persistPlace);
    placeInput.addEventListener('blur', persistPlace);

    body.querySelector('[data-af="clear-place"]').addEventListener('click', () => {
      placeInput.value = '';
      FL.placeNav?.clearPlace?.();
      const hint = body.querySelector('[data-af="place-hint"]');
      if (hint) hint.textContent = 'Place cleared (saved). ASL location filter is unchanged — clear it on the ASL tab if needed.';
    });

    const go = (mode) => {
      const q = placeInput.value.trim();
      const hint = body.querySelector('[data-af="place-hint"]');
      if (!q) {
        if (hint) hint.textContent = 'Enter a place name first (e.g. Bangkok).';
        return;
      }
      // Navigation only — do not sync into ASL locationInclude.
      const r = FL.placeNav?.goPlace?.(q, { syncAsl: false, mode });
      if (hint && r?.url) hint.textContent = `Going: ${r.url}`;
    };
    body.querySelector('[data-af="go-place"]').addEventListener('click', () => go('kinksters'));
    body.querySelector('[data-af="go-search"]').addEventListener('click', () => go('search'));
    placeInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        go('kinksters');
      }
    });

    body.querySelector('[data-af="resume"]').addEventListener('click', () => {
      const url = FL.placeNav?.resumeBookmarkUrl?.();
      if (!url) return;
      location.assign(url);
    });
    body.querySelector('[data-af="clear-bm"]').addEventListener('click', () => {
      FL.placeNav?.clearBookmark?.();
      renderAutoFollow(body);
    });

    const btn = body.querySelector('[data-af="toggle"]');
    const syncBtn = () => {
      const running = af?.isRunning?.();
      btn.textContent = running ? `Stop (${af.getCount()} followed)` : 'Start auto-follow';
      btn.classList.toggle('running', !!running);
      body.querySelector('[data-af="stat"]').textContent = `Followed: ${af?.getCount?.() || 0}`;
    };
    btn.addEventListener('click', () => {
      if (af.isRunning()) af.stop();
      else {
        try {
          const path = location.pathname.replace(/\/+$/, '');
          if (/\/kinksters$/i.test(path)) {
            const page = Number(new URL(location.href).searchParams.get('page')) || 1;
            FL.placeNav?.saveBookmark?.({
              path,
              page,
              placeLabel: FL.placeNav.placeLabelFromPath?.(path) || placeInput.value.trim(),
            });
          }
        } catch (_) { /* ignore */ }
        af.start();
        const hint = body.querySelector('[data-af="place-hint"]');
        if (hint) hint.textContent = 'Bookmarking page progress — Resume later from this tab.';
      }
      syncBtn();
    });
    af.onProgress = () => syncBtn();
    af.onState = () => syncBtn();
    syncBtn();
  }

  function renderFlConsole(body) {
    const pc = FL.privacyConsole;
    const active = pc?.activeId?.() || 'lockdown';
    const levels = pc?.levels?.() || FL.privacyPresets?.levels || [];
    const status = pc?.getStatus?.() || '';
    body.innerHTML = `
      <p class="hint"><b>FLConsole</b> — one-tap FetLife <em>account</em> privacy tiers. These live on FetLife’s Settings page (not just this extension). Applying opens Settings and sets matching controls; review before you leave.</p>
      <div data-fc="levels"></div>
      <p class="hint" data-fc="status" style="margin-top:8px">${status || `Active preset: ${active}`}</p>
      <details class="section">
        <summary>Checklist for active preset</summary>
        <ul data-fc="check" style="margin:8px 0;padding-left:18px;color:#bbb;font-size:12px"></ul>
      </details>
      <details class="section">
        <summary>Gender catalog (reference)</summary>
        <p class="hint">From your FetLife gender list — for future ASL filters. Not applied automatically yet.</p>
        <p style="font-size:11px;color:#999;line-height:1.5" data-fc="genders"></p>
      </details>
    `;
    const wrap = body.querySelector('[data-fc="levels"]');
    levels.forEach((lv) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'primary';
      b.style.marginTop = '6px';
      b.textContent = lv.id === active ? `✓ ${lv.label}` : lv.label;
      b.title = lv.blurb || lv.short || '';
      const note = document.createElement('p');
      note.className = 'hint';
      note.style.margin = '2px 0 8px';
      note.textContent = lv.short || '';
      b.addEventListener('click', () => {
        pc?.applyPreset?.(lv.id);
        const st = body.querySelector('[data-fc="status"]');
        if (st) st.textContent = pc?.getStatus?.() || `Queued ${lv.label}`;
        renderFlConsole(body);
      });
      wrap.appendChild(b);
      wrap.appendChild(note);
    });
    const ul = body.querySelector('[data-fc="check"]');
    (pc?.checklist?.(active) || []).forEach((line) => {
      const li = document.createElement('li');
      li.textContent = line;
      ul.appendChild(li);
    });
    const gEl = body.querySelector('[data-fc="genders"]');
    if (gEl) gEl.textContent = (FL.genderCatalog || []).join(' · ');
    if (pc) {
      pc.onStatus = (msg) => {
        const st = body.querySelector('[data-fc="status"]');
        if (st) st.textContent = msg;
      };
    }
  }

  function renderKeywords(body) {
    const kw = loadKeywords();
    body.innerHTML = `
      <p class="hint">Include/Exclude for feed story text (same sticky bar). Include = all must match; exclude = hide if any. Space/comma separated.</p>
      <label class="row">Include (all must match)</label>
      <input type="text" data-kw-inc placeholder="e.g. rope bondage" autocomplete="off" />
      <label class="row">Exclude (hide if any)</label>
      <input type="text" data-kw-exc placeholder="e.g. cishet" autocomplete="off" />
      <div style="display:flex;gap:8px;margin-top:10px">
        <button type="button" class="primary" data-kw-apply>Apply</button>
        <button type="button" class="clear-btn" data-kw-clear>Clear</button>
      </div>
      <p class="hint" data-kw-status style="margin-top:8px">Ready</p>
    `;
    const inc = body.querySelector('[data-kw-inc]');
    const exc = body.querySelector('[data-kw-exc]');
    const status = body.querySelector('[data-kw-status]');
    inc.value = kw.titleInclude || '';
    exc.value = kw.titleExclude || '';
    const apply = () => {
      saveKeywords({ titleInclude: inc.value.trim(), titleExclude: exc.value.trim() });
      applyKeywordFilters();
      const bar = document.getElementById('tbcc-fl-kw-bar');
      if (bar) {
        const bi = bar.querySelector('[data-kw="inc"]');
        const be = bar.querySelector('[data-kw="exc"]');
        if (bi) bi.value = inc.value.trim();
        if (be) be.value = exc.value.trim();
      }
      if (status) status.textContent = 'Keywords applied';
    };
    body.querySelector('[data-kw-apply]')?.addEventListener('click', apply);
    body.querySelector('[data-kw-clear]')?.addEventListener('click', () => {
      inc.value = '';
      exc.value = '';
      apply();
    });
    inc.addEventListener('change', apply);
    exc.addEventListener('change', apply);
  }

  function renderGender(body) {
    const gf = FL.genderFilter;
    const cfg = gf?.loadCfg?.() || {};
    const onGeoKinksters = /\/p\/[^/]+\/[^/]+\/[^/]+\/kinksters/i.test(location.pathname);
    body.innerHTML = `
      <p class="hint">Client-side ASL filter. Matching cards are <b>removed</b> so the list reflows. Location needles apply on search/global lists — on place kinksters pages the URL is the geo scope (location text is ignored).</p>
      <label class="row"><input type="checkbox" data-g="hideMale" /> Hide Male (M)</label>
      <label class="row"><input type="checkbox" data-g="femaleOnly" /> Female only (hide non-F when sex known)</label>
      <label class="row"><input type="checkbox" data-g="hideFtM" /> Also hide FtM</label>
      <label class="row">Location must include (comma-separated)</label>
      <div class="field-row">
        <input type="text" data-g="location" placeholder="blank = any (vitals text match)" />
        <button type="button" class="clear-btn" data-g="clear-location" title="Clear location needles">Clear</button>
      </div>
      <p class="hint" data-g="status" style="margin-top:8px">${
        onGeoKinksters
          ? 'On a place kinksters list — location needles idle; Clear still wipes saved text for other pages.'
          : 'Persists on change. Clear writes blank immediately.'
      }</p>
      <button type="button" class="primary" data-g="apply">Re-apply filter</button>
    `;
    body.querySelector('[data-g="hideMale"]').checked = cfg.hideMale !== false;
    body.querySelector('[data-g="femaleOnly"]').checked = cfg.femaleOnly !== false;
    body.querySelector('[data-g="hideFtM"]').checked = !!cfg.hideFtM;
    const locInput = body.querySelector('[data-g="location"]');
    locInput.value = cfg.locationInclude != null ? cfg.locationInclude : '';
    const save = () => {
      gf.saveCfg({
        hideMale: body.querySelector('[data-g="hideMale"]').checked,
        femaleOnly: body.querySelector('[data-g="femaleOnly"]').checked,
        hideFtM: body.querySelector('[data-g="hideFtM"]').checked,
        locationInclude: locInput.value.trim(),
      });
      const result = gf.apply?.() || {};
      const hint = body.querySelector('[data-g="status"]');
      if (hint) {
        hint.textContent =
          result.skipped === 'profile'
            ? 'ASL skipped on member profiles (keeps Friend / Follow / Message).'
            : result.cards != null
              ? `Last apply: ${result.hidden || 0} removed / ${result.kept ?? '?'} kept`
              : 'Filter re-applied';
      }
    };
    body.querySelector('[data-g="hideMale"]').addEventListener('change', save);
    body.querySelector('[data-g="femaleOnly"]').addEventListener('change', save);
    body.querySelector('[data-g="hideFtM"]').addEventListener('change', save);
    locInput.addEventListener('change', save);
    locInput.addEventListener('blur', save);
    body.querySelector('[data-g="clear-location"]').addEventListener('click', () => {
      locInput.value = '';
      gf.saveCfg({
        hideMale: body.querySelector('[data-g="hideMale"]').checked,
        femaleOnly: body.querySelector('[data-g="femaleOnly"]').checked,
        hideFtM: body.querySelector('[data-g="hideFtM"]').checked,
        locationInclude: '',
      });
      gf.apply?.();
      const hint = body.querySelector('[data-g="status"]');
      if (hint) hint.textContent = 'Location needles cleared.';
    });
    body.querySelector('[data-g="apply"]').addEventListener('click', () => {
      save();
      gf.apply();
    });
  }

  function renderStories(body) {
    if (typeof FL.socialProof?.renderStoriesPanel === 'function') {
      FL.socialProof.renderStoriesPanel(body);
      return;
    }
    body.innerHTML = `
      <strong style="display:block;margin-bottom:8px">Story types</strong>
      <div data-story-catalog></div>
    `;
    FL.storyFilter?.mountCatalog?.(body.querySelector('[data-story-catalog]'));
  }

  function renderMute(body) {
    body.innerHTML = `<p class="hint">Mute adds a (mute) link next to comment authors. List is stored in extension/local storage.</p>
      <p class="stat">Muted IDs: ${(S.storage.get('tbcc_fl_muted_users_v1', '') || '(none)')}</p>`;
  }

  function render() {
    ensureDom();
    const root = document.getElementById(ROOT_ID);
    const page = PAGES[pageIndex];
    root.querySelectorAll('.tbcc-tabs button').forEach((b) => {
      b.classList.toggle('active', b.dataset.page === page.id);
    });
    root.querySelector('.page-ind').textContent = `${pageIndex + 1} / ${PAGES.length} — ${page.title}`;
    const body = root.querySelector('.tbcc-body');
    if (page.id === 'features') renderFeatures(body);
    else if (page.id === 'autofollow') renderAutoFollow(body);
    else if (page.id === 'gender') renderGender(body);
    else if (page.id === 'keywords') renderKeywords(body);
    else if (page.id === 'flconsole') renderFlConsole(body);
    else if (page.id === 'stories') renderStories(body);
    else if (page.id === 'mute') renderMute(body);
    else if (page.id === 'intel') FL.overlayIntel?.render?.(body, render);
  }

  FL.overlay = {
    mount(opts) {
      hooks = opts || {};
      const ui = loadUiState();
      pageIndex = ui.pageIndex;
      collapsed = ui.collapsed;
      widthMode = ui.widthMode || 'slim';
      ensureDom();
      syncCollapsedUi(document.getElementById(ROOT_ID));
      applyOverlayTop(document.getElementById(ROOT_ID));
      mountKeywordBar();
      applyKeywordFilters();
      render();
      bindCrossTabSync();
      if (!global.__tbccFlKwObs) {
        global.__tbccFlKwObs = new MutationObserver(() => {
          clearTimeout(global.__tbccFlKwT);
          global.__tbccFlKwT = setTimeout(applyKeywordFilters, 300);
        });
        try {
          global.__tbccFlKwObs.observe(document.body, { childList: true, subtree: true });
        } catch (_) {}
      }
      if (typeof GM_registerMenuCommand === 'function') {
        try {
          GM_registerMenuCommand(SUITE_TITLE + ': open overlay', () => FL.overlay.open());
        } catch (_) { /* ignore */ }
      }
    },
    open(pageId) {
      ensureDom();
      const root = document.getElementById(ROOT_ID);
      collapsed = false;
      if (pageId) {
        const i = PAGES.findIndex((p) => p.id === pageId);
        if (i >= 0) pageIndex = i;
      }
      syncCollapsedUi(root);
      applyOverlayTop(root);
      persistUiState();
      render();
    },
    collapse() {
      const root = document.getElementById(ROOT_ID);
      if (!root) return;
      collapsed = true;
      syncCollapsedUi(root);
      persistUiState();
    },
    refresh() {
      const root = document.getElementById(ROOT_ID);
      if (!root) return;
      applyUiState(loadUiState(), { renderBody: true });
    },
  };
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

/* ---- packages/fetlife-suite/boot.js ---- */
/* FetLife suite boot — flags + overlay + feature sync */
(function (global) {
  'use strict';
  const US = global.__TBCC_US__;
  const S = US.shared;
  const FL = (US.fetlife = US.fetlife || {});

  const COMMUNITY = global.__TBCC_EDITION__ === 'community';
  const FLAG_KEY = 'tbcc_fl_suite_flags_v1';
  const DEFAULTS = {
    loginRedirect: true,
    homeFeed: true,
    storyFilter: true,
    mute: true,
    newestDiscussions: true,
    genderFilter: true,
    autoFollow: true,
    infiniteScroll: true,
    socialProof: !COMMUNITY,
    privacyConsole: true,
  };
  if (COMMUNITY) delete DEFAULTS.socialProof;

  const LABELS = {
    loginRedirect: 'Redirect login/home → last kinksters place',
    homeFeed: 'Home feed masonry + pills',
    storyFilter: 'Client-side story type filter',
    mute: 'Comment mute buttons',
    newestDiscussions: 'Groups → newest discussions',
    genderFilter: 'ASL filter (female / location)',
    autoFollow: 'Auto-follow controls (panel)',
    infiniteScroll: 'Kinksters infinite scroll (fill gaps)',
    privacyConsole: 'FLConsole privacy presets',
  };
  if (FL.socialProofFlagLabel) LABELS.socialProof = FL.socialProofFlagLabel;

  const flags = S.createFlags(FLAG_KEY, DEFAULTS);
  // Force-enable new defaults for users who already have an old flags blob
  {
    const saved = S.storage.get(FLAG_KEY, null);
    const upgrade = (key) => {
      if (!saved || typeof saved !== 'object' || !(key in saved)) flags.set(key, true);
    };
    upgrade('autoFollow');
    upgrade('genderFilter');
    upgrade('loginRedirect');
    upgrade('infiniteScroll');
    if (!COMMUNITY) upgrade('socialProof');
    upgrade('privacyConsole');
  }

  const running = Object.create(null);

  function syncFeatures() {
    const feats = FL.features || {};
    for (const name of Object.keys(DEFAULTS)) {
      const want = flags.get(name);
      const feat = feats[name];
      if (!feat) continue;
      if (want && !running[name]) {
        feat.start();
        running[name] = true;
      } else if (!want && running[name]) {
        feat.stop?.();
        running[name] = false;
      }
    }
  }

  function onRemoteFlags() {
    flags.hydrate?.();
    syncFeatures();
    FL.overlay.refresh?.();
  }

  function boot() {
    FL.overlay.mount({
      flags,
      labels: LABELS,
      onFlagsChange() {
        syncFeatures();
      },
    });
    syncFeatures();

    // Keep module flags live across FetLife tabs.
    if (typeof S.storage.subscribe === 'function') {
      S.storage.subscribe(FLAG_KEY, onRemoteFlags);
    }

    // Open overlay on kinksters landing (persists open state to other tabs).
    if (/\/kinksters/i.test(location.pathname)) {
      setTimeout(() => FL.overlay.open('autofollow'), 700);
    }

    console.info(COMMUNITY ? '[AOF FetLife Enhancer] community ready' : '[TBCC FetLife Suite] v1.8 ready', flags.all());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);

