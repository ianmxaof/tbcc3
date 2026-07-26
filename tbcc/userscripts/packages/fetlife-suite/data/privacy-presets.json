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
