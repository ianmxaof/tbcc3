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
