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
