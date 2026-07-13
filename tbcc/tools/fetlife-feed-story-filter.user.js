// ==UserScript==
// @name         FetLife Feed Story Filter (client-side)
// @namespace    local.fl.feed-filter
// @version      0.1.0
// @description  SUPERSEDED by tbcc/userscripts dist/fetlife-suite.user.js (storyFilter module). Kept as reference only.
// @author       local
// @match        https://fetlife.com/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const STORAGE_KEY = 'fl_feed_story_enabled_v1';
  const STYLE_ID = 'fl-feed-story-filter-style';
  const PANEL_ID = 'fl-feed-story-filter-panel';
  const HIDDEN_ATTR = 'data-fl-fsf-hidden';
  const TYPE_ATTR = 'data-fl-fsf-type';

  /**
   * Catalog mirrors FetLife settings/activity_feed checkboxes (name=feed[story_types][]).
   * checked=true means SHOW in feed (same as FL UI).
   */
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

  /** More-specific patterns first. Matched against story header/body text. */
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
    { id: 'relationship_changes', re: /(relationship|is now|partner)/i },

    { id: 'superloved_profile_update', re: /superloved .{0,80}profile\b/i },
    { id: 'loved_profile_update', re: /\bloved .{0,80}profile\b/i },
    { id: 'commented_on_profile_update', re: /commented on .{0,80}profile\b/i },
    { id: 'fetish_added', re: /(added|updated).{0,40}fetish/i },
    { id: 'profile_updates', re: /(updated|changed).{0,40}profile\b/i },

    { id: 'friendship_request_accepted', re: /(accepted|are now friends|friendship)/i },
    { id: 'sign_ups', re: /(signed up|joined fetlife|invited)/i },
    { id: 'following', re: /(is now following|started following|followed)\b/i },
  ];

  function defaultMap() {
    const map = {};
    for (const cat of CATALOG) {
      for (const item of cat.items) map[item.id] = item.defaultOn;
    }
    return map;
  }

  function loadEnabled() {
    const saved = GM_getValue(STORAGE_KEY, null);
    const base = defaultMap();
    if (!saved || typeof saved !== 'object') return base;
    return { ...base, ...saved };
  }

  function saveEnabled(map) {
    GM_setValue(STORAGE_KEY, map);
  }

  let enabled = loadEnabled();

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      [${HIDDEN_ATTR}="1"] { display: none !important; }
      #${PANEL_ID} {
        position: fixed; z-index: 999999; right: 16px; bottom: 16px;
        width: min(420px, calc(100vw - 24px)); max-height: min(70vh, 640px);
        overflow: auto; background: #1a1a1a; color: #d4d4d4;
        border: 1px solid #333; border-radius: 8px; box-shadow: 0 8px 28px rgba(0,0,0,.55);
        font: 13px/1.35 system-ui, sans-serif; display: none;
      }
      #${PANEL_ID}.open { display: block; }
      #${PANEL_ID} header {
        position: sticky; top: 0; background: #222; padding: 10px 12px;
        border-bottom: 1px solid #333; display: flex; gap: 8px; align-items: center;
      }
      #${PANEL_ID} header strong { flex: 1; }
      #${PANEL_ID} header button, #fl-fsf-fab {
        background: #333; color: #eee; border: 1px solid #555; border-radius: 6px;
        padding: 6px 10px; cursor: pointer;
      }
      #fl-fsf-fab {
        position: fixed; z-index: 999998; right: 16px; bottom: 16px;
      }
      #${PANEL_ID} .cat { padding: 8px 12px 4px; font-weight: 700; color: #bbb; }
      #${PANEL_ID} label {
        display: flex; gap: 8px; align-items: flex-start; padding: 4px 12px 4px 16px;
        cursor: pointer;
      }
      #${PANEL_ID} label input { margin-top: 2px; }
      #${PANEL_ID} .note { padding: 8px 12px 12px; color: #888; font-size: 12px; }
      /* Make official settings checkboxes usable for local prefs only */
      form#update_feed_settings_form label.fl-fsf-unlocked {
        opacity: 1 !important; cursor: pointer !important; pointer-events: auto !important;
      }
      form#update_feed_settings_form label.fl-fsf-unlocked input {
        opacity: 1 !important; cursor: pointer !important; pointer-events: auto !important;
      }
    `;
    document.documentElement.appendChild(style);
  }

  function classifyStoryText(text) {
    const t = (text || '').replace(/\s+/g, ' ').trim();
    if (!t) return null;
    for (const m of MATCHERS) {
      if (m.re.test(t)) return m.id;
    }
    return null;
  }

  function storyNodes(root = document) {
    const selectors = [
      '[data-fl-story]',
      '[data-story-id]',
      '[data-testid*="story" i]',
      '[data-testid*="feed-item" i]',
      '.stories-list > *',
      '#stories > *',
      'article',
    ];
    const found = new Set();
    for (const sel of selectors) {
      root.querySelectorAll(sel).forEach((el) => {
        // Prefer leaf-ish feed cards, skip tiny nodes
        if ((el.textContent || '').trim().length < 20) return;
        if (el.closest(`#${PANEL_ID}`)) return;
        found.add(el);
      });
    }
    // Deduplicate nested: keep outermost only
    return [...found].filter((el) => ![...found].some((other) => other !== el && other.contains(el)));
  }

  function applyFeedFilter() {
    if (!/\/home|\/users\/\d+\/activity|\/activity/i.test(location.pathname) && location.pathname !== '/') {
      // Still try on common feed routes
      if (!document.querySelector('.stories-list, #stories, [data-testid*="feed" i]')) return;
    }
    const nodes = storyNodes();
    let hidden = 0;
    let unknown = 0;
    for (const el of nodes) {
      const text = el.innerText || el.textContent || '';
      const type =
        el.getAttribute('data-feed-event') ||
        el.getAttribute('data-story-type') ||
        el.getAttribute('data-type') ||
        classifyStoryText(text);

      if (type) el.setAttribute(TYPE_ATTR, type);
      const show = !type || enabled[type] !== false;
      if (show) {
        el.removeAttribute(HIDDEN_ATTR);
      } else {
        el.setAttribute(HIDDEN_ATTR, '1');
        hidden += 1;
      }
      if (!type) unknown += 1;
    }
    if (hidden || unknown) {
      console.debug(`[FL Feed Story Filter] scanned=${nodes.length} hidden=${hidden} unclassified=${unknown}`);
    }
  }

  function unlockSettingsPage() {
    const form = document.getElementById('update_feed_settings_form');
    if (!form) return;

    const bannerId = 'fl-fsf-settings-banner';
    if (!document.getElementById(bannerId)) {
      const h2 = [...form.querySelectorAll('h2')].find((h) => /Hide\/Show Feed Stories/i.test(h.textContent));
      const banner = document.createElement('div');
      banner.id = bannerId;
      banner.style.cssText = 'margin:8px 0 12px;padding:8px 10px;background:#2a1f14;border:1px solid #664;border-radius:6px;color:#e8c48a;font-size:13px;';
      banner.textContent =
        'Client-side filter active: toggles below save in Tampermonkey and hide stories in your browser feed. They are NOT sent to FetLife Supporter settings.';
      (h2?.parentElement || form).insertBefore(banner, h2?.nextSibling || form.firstChild);
    }

    form.querySelectorAll('input[name="feed[story_types][]"]').forEach((input) => {
      if (!input.value) return;
      input.disabled = false;
      input.checked = enabled[input.value] !== false;
      const label = input.closest('label');
      if (label) {
        label.classList.add('fl-fsf-unlocked');
        label.classList.remove('cursor-not-allowed', 'opacity-50');
        label.style.opacity = '1';
        label.style.cursor = 'pointer';
        label.style.pointerEvents = 'auto';
      }
      if (input.dataset.flFsfBound) return;
      input.dataset.flFsfBound = '1';
      input.addEventListener(
        'click',
        (ev) => {
          // Prevent accidental native form submit / Rails handlers
          ev.stopPropagation();
        },
        true
      );
      input.addEventListener('change', (ev) => {
        ev.stopPropagation();
        enabled = { ...enabled, [input.value]: input.checked };
        saveEnabled(enabled);
        applyFeedFilter();
      });
    });

    // Block native form submit so we never hit Supporter-only PUT
    if (!form.dataset.flFsfSubmitBlocked) {
      form.dataset.flFsfSubmitBlocked = '1';
      form.addEventListener(
        'submit',
        (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          saveEnabled(enabled);
          console.info('[FL Feed Story Filter] Preferences saved locally (native submit blocked).');
        },
        true
      );
    }
  }

  function buildPanel() {
    if (document.getElementById(PANEL_ID)) return;
    const panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.innerHTML = `<header>
      <strong>Feed story filter</strong>
      <button type="button" data-act="all-on">All on</button>
      <button type="button" data-act="all-off">All off</button>
      <button type="button" data-act="close">Close</button>
    </header>
    <div class="note">Unchecked = hidden in your browser only. Does not change FetLife account settings.</div>`;

    for (const cat of CATALOG) {
      const h = document.createElement('div');
      h.className = 'cat';
      h.textContent = cat.category;
      panel.appendChild(h);
      for (const item of cat.items) {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = enabled[item.id] !== false;
        cb.dataset.id = item.id;
        cb.addEventListener('change', () => {
          enabled = { ...enabled, [item.id]: cb.checked };
          saveEnabled(enabled);
          unlockSettingsPage();
          applyFeedFilter();
        });
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(item.label));
        panel.appendChild(lab);
      }
    }

    panel.querySelector('[data-act="close"]').addEventListener('click', () => panel.classList.remove('open'));
    panel.querySelector('[data-act="all-on"]').addEventListener('click', () => {
      const next = { ...enabled };
      Object.keys(next).forEach((k) => (next[k] = true));
      enabled = next;
      saveEnabled(enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = true));
      unlockSettingsPage();
      applyFeedFilter();
    });
    panel.querySelector('[data-act="all-off"]').addEventListener('click', () => {
      const next = { ...enabled };
      Object.keys(next).forEach((k) => (next[k] = false));
      enabled = next;
      saveEnabled(enabled);
      panel.querySelectorAll('input[type=checkbox]').forEach((cb) => (cb.checked = false));
      unlockSettingsPage();
      applyFeedFilter();
    });

    document.documentElement.appendChild(panel);

    const fab = document.createElement('button');
    fab.id = 'fl-fsf-fab';
    fab.type = 'button';
    fab.textContent = 'Feed filter';
    fab.addEventListener('click', () => panel.classList.toggle('open'));
    document.documentElement.appendChild(fab);
  }

  function boot() {
    ensureStyle();
    unlockSettingsPage();
    buildPanel();
    applyFeedFilter();

    const mo = new MutationObserver(() => {
      unlockSettingsPage();
      applyFeedFilter();
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });

    // SPA navigations
    let last = location.href;
    setInterval(() => {
      if (location.href === last) return;
      last = location.href;
      setTimeout(() => {
        unlockSettingsPage();
        applyFeedFilter();
      }, 400);
    }, 800);
  }

  GM_registerMenuCommand('FL Feed Story Filter: open panel', () => {
    ensureStyle();
    buildPanel();
    document.getElementById(PANEL_ID)?.classList.add('open');
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
