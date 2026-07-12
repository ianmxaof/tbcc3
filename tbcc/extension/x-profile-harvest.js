/**
 * TBCC X / Twitter profile media harvest (ISOLATED world).
 *
 * Uses the same GraphQL endpoints as the logged-in X tab (UserMedia / UserTweets).
 * Driven by:
 *   - tbcc-x-profile-harvest-run     → paginate profile media into a list
 *   - tbcc-x-profile-harvest-snapshot  → return last harvest bag
 *
 * Companion: x-profile-overlay.js (on-page grid + ZIP handoff to gallery).
 */
(function () {
  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("x_profile_gallery", function () {
  if (window.__tbccXProfileHarvestLoaded) return;
  window.__tbccXProfileHarvestLoaded = true;

  var GQL_FEATURES =
    "%7B%22rweb_video_screen_enabled%22%3Afalse%2C%22profile_label_improvements_pcf_label_in_post_enabled%22%3Atrue%2C%22responsive_web_profile_redirect_enabled%22%3Afalse%2C%22rweb_tipjar_consumption_enabled%22%3Atrue%2C%22verified_phone_label_enabled%22%3Afalse%2C%22creator_subscriptions_tweet_preview_api_enabled%22%3Atrue%2C%22responsive_web_graphql_timeline_navigation_enabled%22%3Atrue%2C%22responsive_web_graphql_skip_user_profile_image_extensions_enabled%22%3Afalse%2C%22premium_content_api_read_enabled%22%3Afalse%2C%22communities_web_enable_tweet_community_results_fetch%22%3Atrue%2C%22c9s_tweet_anatomy_moderator_badge_enabled%22%3Atrue%2C%22responsive_web_grok_analyze_button_fetch_trends_enabled%22%3Afalse%2C%22responsive_web_grok_analyze_post_followups_enabled%22%3Atrue%2C%22responsive_web_jetfuel_frame%22%3Atrue%2C%22responsive_web_grok_share_attachment_enabled%22%3Atrue%2C%22responsive_web_grok_annotations_enabled%22%3Afalse%2C%22articles_preview_enabled%22%3Atrue%2C%22responsive_web_edit_tweet_api_enabled%22%3Atrue%2C%22graphql_is_translatable_rweb_tweet_is_translatable_enabled%22%3Atrue%2C%22view_counts_everywhere_api_enabled%22%3Atrue%2C%22longform_notetweets_consumption_enabled%22%3Atrue%2C%22responsive_web_twitter_article_tweet_consumption_enabled%22%3Atrue%2C%22tweet_awards_web_tipping_enabled%22%3Afalse%2C%22responsive_web_grok_show_grok_translated_post%22%3Afalse%2C%22responsive_web_grok_analysis_button_from_backend%22%3Atrue%2C%22post_ctas_fetch_enabled%22%3Atrue%2C%22creator_subscriptions_quote_tweet_preview_enabled%22%3Afalse%2C%22freedom_of_speech_not_reach_fetch_enabled%22%3Atrue%2C%22standardized_nudges_misinfo%22%3Atrue%2C%22tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled%22%3Atrue%2C%22longform_notetweets_rich_text_read_enabled%22%3Atrue%2C%22longform_notetweets_inline_media_enabled%22%3Atrue%2C%22responsive_web_grok_image_annotation_enabled%22%3Atrue%2C%22responsive_web_grok_imagine_annotation_enabled%22%3Atrue%2C%22responsive_web_grok_community_note_auto_translation_is_enabled%22%3Afalse%2C%22responsive_web_enhance_cards_enabled%22%3Afalse%7D";

  var GQL_FEATURES_OBJ = (function () {
    try {
      return JSON.parse(decodeURIComponent(GQL_FEATURES));
    } catch (_) {
      return {};
    }
  })();

  var GQL_QUERY_FALLBACK = {
    HomeTimeline: "c-CzHF1LboFilMpsx4ZCrQ",
    HomeLatestTimeline: "BKB7oi212Fi7kQtCBGE4zA",
  };

  var RESERVED_SEGMENTS = {
    home: 1,
    explore: 1,
    notifications: 1,
    messages: 1,
    settings: 1,
    compose: 1,
    search: 1,
    jobs: 1,
    lists: 1,
    i: 1,
    intent: 1,
    login: 1,
    signup: 1,
  };

  var lastBag = [];
  var lastMeta = {};

  function isXHost() {
    try {
      var h = (location.hostname || "").toLowerCase();
      return /(^|\.)x\.com$/i.test(h) || /(^|\.)twitter\.com$/i.test(h);
    } catch (_) {
      return false;
    }
  }

  function isXProfilePage(href) {
    if (!isXHost()) return false;
    try {
      var u = new URL(href || location.href);
      var parts = u.pathname.replace(/^\/+|\/+$/g, "").split("/");
      if (!parts.length || !parts[0]) return false;
      if (RESERVED_SEGMENTS[parts[0].toLowerCase()]) return false;
      if (parts[0] === "hashtag" || parts[0].charAt(0) === "#") return false;
      if (parts.length === 1 || (parts.length === 2 && parts[1] === "media")) return true;
      return false;
    } catch (_) {
      return false;
    }
  }

  function isXHomeFeedPage(href) {
    if (!isXHost()) return false;
    try {
      var parts = new URL(href || location.href).pathname.replace(/^\/+|\/+$/g, "").split("/");
      if (!parts.length || !parts[0]) return true;
      return parts[0].toLowerCase() === "home";
    } catch (_) {
      return false;
    }
  }

  function isXOverlayPage(href) {
    return isXProfilePage(href) || isXHomeFeedPage(href);
  }

  function getXHomeFeedMode() {
    try {
      var tabs = document.querySelectorAll('[role="tablist"] [role="tab"]');
      for (var i = 0; i < tabs.length; i++) {
        var tab = tabs[i];
        if (tab.getAttribute("aria-selected") !== "true") continue;
        var label = String(tab.textContent || "").toLowerCase();
        if (label.indexOf("following") >= 0) return "following";
        if (label.indexOf("for you") >= 0 || label.indexOf("foryou") >= 0) return "for_you";
      }
      if (/\/following(?:\/|$)/i.test(location.pathname)) return "following";
    } catch (_) {}
    return "for_you";
  }

  function discoverGqlQueryId(operationName) {
    var cached = window.__tbccXGqlQueryIds && window.__tbccXGqlQueryIds[operationName];
    if (cached) return cached;
    try {
      var html = document.documentElement.innerHTML;
      var patterns = [
        new RegExp('"operationName":"' + operationName + '"[^}]{0,240}?"queryId":"([A-Za-z0-9_-]+)"'),
        new RegExp('"queryId":"([A-Za-z0-9_-]+)"[^}]{0,240}?"operationName":"' + operationName + '"'),
        new RegExp("/graphql/([A-Za-z0-9_-]+)/" + operationName),
      ];
      for (var pi = 0; pi < patterns.length; pi++) {
        var m = html.match(patterns[pi]);
        if (m && m[1]) return m[1];
      }
    } catch (_) {}
    return GQL_QUERY_FALLBACK[operationName] || "";
  }

  function uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 3) | 8).toString(16);
    });
  }

  function transactionId() {
    return window.btoa(uuid());
  }

  function getScreenNameFromUrl(href) {
    try {
      var parts = new URL(href || location.href).pathname.replace(/^\/+|\/+$/g, "").split("/");
      return parts[0] || "";
    } catch (_) {
      return "";
    }
  }

  function getUserIDFromScripts(userName) {
    if (!userName) return undefined;
    var esc = userName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    var re = new RegExp('"screen_name":"' + esc + '"[\\s\\S]{0,800}?"rest_id":"(\\d+)"', "i");
    var scripts = document.querySelectorAll("script");
    for (var i = 0; i < scripts.length; i++) {
      var t = scripts[i].textContent || "";
      if (t.indexOf(userName) < 0) continue;
      var m = t.match(re);
      if (m) return m[1];
    }
    return undefined;
  }

  function getUserID(screenName) {
    var userName = screenName || getScreenNameFromUrl();
    if (!userName) return undefined;

    var fromScripts = getUserIDFromScripts(userName);
    if (fromScripts) return fromScripts;

    var followBTNs = Array.from(document.querySelectorAll("button[data-testid][aria-label]"));
    if (followBTNs.length) {
      var needle = "@" + String(userName).toLowerCase();
      var btn =
        followBTNs.find(function (b) {
          return String(b.getAttribute("aria-label") || "").toLowerCase().indexOf(needle) >= 0;
        }) || followBTNs[0];
      var tid = btn.getAttribute("data-testid");
      if (tid && tid.match(/(\d+)/)) return tid.match(/(\d+)/)[1];
    }

    var anchors = document.querySelectorAll('a[href*="/' + userName + '"]');
    for (var ai = 0; ai < anchors.length; ai++) {
      var href = anchors[ai].getAttribute("href") || "";
      var m = href.match(/\/i\/user\/(\d+)/);
      if (m) return m[1];
    }

    return undefined;
  }

  function createHeader(clientUuid) {
    var headers = new Headers();
    headers.set(
      "authorization",
      "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    );
    headers.set("Pragma", "no-cache");
    headers.set("Cache-Control", "no-cache");
    headers.set("content-type", "application/json");
    headers.set("x-client-uuid", clientUuid);
    headers.set("x-twitter-auth-type", "OAuth2Session");
    headers.set("x-twitter-client-language", "en");
    headers.set("x-twitter-active-user", "yes");
    headers.set("x-client-transaction-id", transactionId());
    headers.set("Sec-Fetch-Dest", "empty");
    headers.set("Sec-Fetch-Mode", "cors");
    headers.set("Sec-Fetch-Site", "same-origin");
    var csrfToken = document.cookie.match(/ct0=(\w+)/);
    if (!csrfToken) throw new Error("Not logged in to X (missing ct0 cookie)");
    headers.set("x-csrf-token", csrfToken[1]);
    return headers;
  }

  function homeForYouEntriesToItems(entries) {
    var items = [];
    var ids = [];
    var cursor;
    for (var ei = 0; ei < (entries.entries || []).length; ei++) {
      var entry = entries.entries[ei];
      if (
        entry.content &&
        entry.content.entryType === "TimelineTimelineItem" &&
        !String(entry.entryId || "").startsWith("promoted-")
      ) {
        if (!entry.content.itemContent || !entry.content.itemContent.tweet_results) continue;
        if (!entry.content.itemContent.tweet_results.result) continue;
        items.push(entry.content);
        var leg = entry.content.itemContent.tweet_results.result.legacy;
        if (leg && leg.id_str) ids.push(leg.id_str);
        var rt =
          leg &&
          leg.retweeted_status_result &&
          leg.retweeted_status_result.result &&
          leg.retweeted_status_result.result.legacy;
        if (rt && rt.id_str) ids.push(rt.id_str);
      } else if (
        entry.content &&
        entry.content.entryType === "TimelineTimelineModule" &&
        entry.content.displayType === "VerticalConversation"
      ) {
        (entry.content.items || []).forEach(function (i) {
          if (!i.item || !i.item.itemContent || !i.item.itemContent.tweet_results) return;
          if (!i.item.itemContent.tweet_results.result) return;
          items.push(i.item);
          var lg = i.item.itemContent.tweet_results.result.legacy;
          if (lg && lg.id_str) ids.push(lg.id_str);
        });
      } else if (
        entry.content &&
        entry.content.entryType === "TimelineTimelineCursor" &&
        String(entry.entryId || "").startsWith("cursor-bottom")
      ) {
        cursor = entry.content.value;
      }
    }
    return { items: items, ids: ids, cursor: cursor };
  }

  function checkoutMedias(item) {
    var ic = item.itemContent || item;
    var tr = ic.tweet_results && ic.tweet_results.result;
    var sources = [
      tr && tr.legacy && tr.legacy.entities && tr.legacy.entities.media,
      tr &&
        tr.legacy &&
        tr.legacy.retweeted_status_result &&
        tr.legacy.retweeted_status_result.result &&
        tr.legacy.retweeted_status_result.result.tweet &&
        tr.legacy.retweeted_status_result.result.tweet.legacy &&
        tr.legacy.retweeted_status_result.result.tweet.legacy.entities &&
        tr.legacy.retweeted_status_result.result.tweet.legacy.entities.media,
      tr &&
        tr.legacy &&
        tr.legacy.retweeted_status_result &&
        tr.legacy.retweeted_status_result.result &&
        tr.legacy.retweeted_status_result.result.legacy &&
        tr.legacy.retweeted_status_result.result.legacy.entities &&
        tr.legacy.retweeted_status_result.result.legacy.entities.media,
      tr && tr.tweet && tr.tweet.legacy && tr.tweet.legacy.entities && tr.tweet.legacy.entities.media,
    ];
    var mediaIdSet = {};
    var ret = [];
    for (var si = 0; si < sources.length; si++) {
      var arr = sources[si];
      if (!arr || !arr.length) continue;
      for (var mi = 0; mi < arr.length; mi++) {
        var me = arr[mi];
        if (!me || !me.id_str || mediaIdSet[me.id_str]) continue;
        mediaIdSet[me.id_str] = 1;
        ret.push(me);
      }
    }
    var tweetId =
      (tr && tr.tweet && tr.tweet.legacy && tr.tweet.legacy.retweeted_status_result &&
        tr.tweet.legacy.retweeted_status_result.result &&
        tr.tweet.legacy.retweeted_status_result.result.legacy &&
        tr.tweet.legacy.retweeted_status_result.result.legacy.id_str) ||
      (tr && tr.tweet && tr.tweet.legacy && tr.tweet.legacy.id_str) ||
      (tr &&
        tr.legacy &&
        tr.legacy.retweeted_status_result &&
        tr.legacy.retweeted_status_result.result &&
        tr.legacy.retweeted_status_result.result.legacy &&
        tr.legacy.retweeted_status_result.result.legacy.id_str) ||
      (tr && tr.legacy && tr.legacy.id_str);
    return [ret, tweetId];
  }

  function bestVideoUrl(media) {
    if (!media || !media.video_info || !Array.isArray(media.video_info.variants)) return "";
    var best = "";
    var bitrate = -1;
    for (var i = 0; i < media.video_info.variants.length; i++) {
      var v = media.video_info.variants[i];
      if (!v || !v.url) continue;
      var ct = String(v.content_type || "").toLowerCase();
      if (ct === "application/x-mpegurl" || /\.m3u8(\?|#|$)/i.test(v.url)) continue;
      var b = Number(v.bitrate) || 0;
      if (b >= bitrate) {
        bitrate = b;
        best = v.url;
      }
    }
    return best;
  }

  function videoFilenameFromVariant(media, mp4Url) {
    var ext = media.media_url_https.split(".").pop().split("?")[0];
    var baseSrc = media.media_url_https.replace("." + ext, "");
    var stem = media.id_str + "-" + baseSrc.split("/").pop();
    if (mp4Url && /\.mp4(\?|#|$)/i.test(mp4Url)) return stem + ".mp4";
    if (mp4Url) {
      try {
        var seg = new URL(mp4Url).pathname.split("/").pop() || "";
        var m = seg.match(/\.(mp4|webm|mov|m4v)(\?|$)/i);
        if (m) return stem + "." + m[1].toLowerCase();
      } catch (_) {}
    }
    return stem + ".mp4";
  }

  function mediaToItem(media, index, opts) {
    if (!media || !media.media_url_https) return null;
    var includeVideo = opts.includeVideo !== false;
    if (!includeVideo && (media.type === "video" || media.type === "animated_gif")) return null;
    if (media.type !== "video" && media.type !== "photo" && media.type !== "animated_gif") return null;

    var ext = media.media_url_https.split(".").pop().split("?")[0];
    var baseSrc = media.media_url_https.replace("." + ext, "");
    var thumbSrc = baseSrc + "?format=" + ext + "&name=" + (media.sizes && media.sizes.small ? "small" : "thumb");
    var largeSrc;
    if (opts.fetchOriginal && media.original_info) {
      largeSrc = baseSrc + "?format=" + ext + "&name=orig";
    } else {
      largeSrc =
        baseSrc +
        "?format=" +
        ext +
        "&name=" +
        (media.sizes && media.sizes.large
          ? "large"
          : media.sizes && media.sizes.medium
            ? "medium"
            : "small");
    }
    var href = String(media.expanded_url || "").replace(/\/(photo|video)\/\d+/, "");
    href = href + "/" + (media.type === "video" ? "video" : "photo") + "/" + (index + 1);

    var downloadUrl = largeSrc;
    var mediaType = "image";
    var filename = media.id_str + "-" + baseSrc.split("/").pop() + "." + ext;
    if (media.video_info) {
      var mp4 = bestVideoUrl(media);
      if (mp4) {
        downloadUrl = mp4;
        mediaType = "video";
        filename = videoFilenameFromVariant(media, mp4);
      } else if (media.type === "video" || media.type === "animated_gif") {
        return null;
      }
    }

    return {
      url: downloadUrl,
      thumbnail_url: thumbSrc,
      media_type: mediaType,
      filename: filename,
      href: href,
      tweet_media_id: media.id_str,
    };
  }

  function parseTimelineItems(rawItems, opts, state) {
    var out = [];
    var cap = Number(opts.maxItems) || 120;
    for (var i = 0; i < rawItems.length; i++) {
      if (state.count >= cap) break;
      var pair = checkoutMedias(rawItems[i]);
      var mediaList = pair[0];
      if (!mediaList.length) continue;
      if (opts.reverseMultipleImagesPost) mediaList = mediaList.slice().reverse();
      for (var j = 0; j < mediaList.length; j++) {
        if (state.count >= cap) break;
        var row = mediaToItem(mediaList[j], j, opts);
        if (!row || state.seen[row.url]) continue;
        state.seen[row.url] = 1;
        out.push(row);
        state.count++;
      }
    }
    return out;
  }

  async function fetchMediaPage(userId, chapterId, cursor, clientUuid) {
    var url = "";
    if (chapterId === 0) {
      var variables0 =
        '{"userId":"' +
        userId +
        '","count":20,' +
        (cursor ? '"cursor":"' + cursor + '",' : "") +
        '"includePromotedContent":true,"withQuickPromoteEligibilityTweetFields":true,"withVoice":true}';
      url =
        location.origin +
        "/i/api/graphql/ehYmFq6d3xwc49yqt52MIg/UserTweets?variables=" +
        encodeURIComponent(variables0) +
        "&features=" +
        GQL_FEATURES +
        "&fieldToggles=%7B%22withArticlePlainText%22%3Afalse%7D";
    } else {
      var variables1 =
        '{"userId":"' +
        userId +
        '","count":20,' +
        (cursor ? '"cursor":"' + cursor + '",' : "") +
        '"includePromotedContent":false,"withClientEventToken":false,"withBirdwatchNotes":false,"withVoice":true,"withV2Timeline":true}';
      url =
        location.origin +
        "/i/api/graphql/MjGtmDI0wpveHq8k2zIlUQ/UserMedia?variables=" +
        encodeURIComponent(variables1) +
        "&features=" +
        GQL_FEATURES +
        "&fieldToggles=%7B%22withArticlePlainText%22%3Afalse%7D";
    }

    var res = await fetch(url, {
      headers: createHeader(clientUuid),
      credentials: "include",
      signal: AbortSignal.timeout(15000),
    });
    var json = await res.json();
    if (res.status !== 200 && json && json.errors && json.errors[0] && json.errors[0].message) {
      throw new Error(json.errors[0].message);
    }

    if (chapterId === 0) {
      var timeline0 =
        json &&
        json.data &&
        json.data.user &&
        json.data.user.result &&
        json.data.user.result.timeline &&
        json.data.user.result.timeline.timeline;
      if (!timeline0 || !timeline0.instructions) throw new Error("UserTweets timeline missing");
      var entries0 = timeline0.instructions.find(function (ins) {
        return ins.type === "TimelineAddEntries";
      });
      if (!entries0) throw new Error("UserTweets entries missing");
      var parsed0 = homeForYouEntriesToItems(entries0);
      return { items: parsed0.items, cursor: parsed0.cursor };
    }

    var timeline1 =
      json &&
      json.data &&
      json.data.user &&
      json.data.user.result &&
      json.data.user.result.timeline &&
      json.data.user.result.timeline.timeline;
    if (!timeline1 || !timeline1.instructions) throw new Error("UserMedia timeline missing");
    var instructions = timeline1.instructions;
    var items = [];
    var addToModule = instructions.find(function (ins) {
      return ins.type === "TimelineAddToModule";
    });
    var entries1 = instructions.find(function (ins) {
      return ins.type === "TimelineAddEntries";
    });
    if (!entries1) throw new Error("UserMedia entries missing");
    if (addToModule && addToModule.moduleItems) {
      addToModule.moduleItems.forEach(function (i) {
        if (i.item) items.push(i.item);
      });
    }
    if (!items.length) {
      var mod = entries1.entries.find(function (entry) {
        return entry.content && entry.content.entryType === "TimelineTimelineModule";
      });
      if (mod && mod.content && mod.content.items) {
        mod.content.items.forEach(function (i) {
          if (i.item) items.push(i.item);
        });
      }
    }
    for (var ei = 0; ei < entries1.entries.length; ei++) {
      var entry = entries1.entries[ei];
      if (entry.content && entry.content.entryType === "TimelineTimelineItem") {
        items.push(entry.content);
      }
    }
    var nextCursor;
    var cursorEntry = entries1.entries.find(function (entry) {
      return (
        entry.content &&
        entry.content.entryType === "TimelineTimelineCursor" &&
        String(entry.entryId || "").startsWith("cursor-bottom")
      );
    });
    if (cursorEntry && cursorEntry.content) nextCursor = cursorEntry.content.value;
    return { items: items, cursor: nextCursor };
  }

  function extractHomeTimelineInstructions(json) {
    var home = json && json.data && json.data.home;
    if (!home) return null;
    var timeline = home.home_timeline_urt || home.home_latest_timeline_urt;
    if (!timeline || !timeline.instructions) return null;
    return timeline.instructions;
  }

  async function fetchHomeFeedPage(cursor, feedMode, clientUuid) {
    var op = feedMode === "following" ? "HomeLatestTimeline" : "HomeTimeline";
    var queryId = discoverGqlQueryId(op);
    if (!queryId) {
      throw new Error("Could not resolve X home feed API — scroll the feed once, then retry");
    }
    var variables = {
      count: 20,
      includePromotedContent: true,
      latestControlAvailable: true,
      requestContext: "launch",
      withCommunity: true,
    };
    if (cursor) variables.cursor = cursor;
    if (op === "HomeTimeline") variables.seenTweetIds = [];

    var url = location.origin + "/i/api/graphql/" + encodeURIComponent(queryId) + "/" + op;
    var res = await fetch(url, {
      method: "POST",
      headers: createHeader(clientUuid),
      credentials: "include",
      body: JSON.stringify({
        variables: variables,
        features: GQL_FEATURES_OBJ,
        queryId: queryId,
      }),
      signal: AbortSignal.timeout(15000),
    });
    var json = await res.json();
    if (res.status !== 200 && json && json.errors && json.errors[0] && json.errors[0].message) {
      throw new Error(json.errors[0].message);
    }
    var instructions = extractHomeTimelineInstructions(json);
    if (!instructions) throw new Error("Home feed timeline missing — switch Following/For you tab and retry");
    var entriesIns = instructions.find(function (ins) {
      return ins.type === "TimelineAddEntries";
    });
    if (!entriesIns || !entriesIns.entries) throw new Error("Home feed entries missing");
    var parsed = homeForYouEntriesToItems(entriesIns);
    return { items: parsed.items, cursor: parsed.cursor };
  }

  async function harvestHomeFeedMedia(options, onProgress) {
    if (!isXHomeFeedPage()) throw new Error("Not on X home feed");
    var opts = Object.assign(
      {
        maxItems: 120,
        includeVideo: true,
        fetchOriginal: false,
        reverseMultipleImagesPost: false,
        feedMode: "auto",
      },
      options || {}
    );
    var cap = Math.min(Math.max(Number(opts.maxItems) || 120, 20), 300);
    opts.maxItems = cap;
    var feedMode = opts.feedMode === "following" || opts.feedMode === "for_you" ? opts.feedMode : getXHomeFeedMode();
    var feedLabel = feedMode === "following" ? "Following" : "For you";

    var clientUuid = uuid();
    var state = { count: 0, seen: {} };
    var all = [];
    var cursor;
    var pages = 0;
    var truncated = false;
    var started = Date.now();

    while (state.count < cap) {
      var page = await fetchHomeFeedPage(cursor, feedMode, clientUuid);
      pages++;
      var batch = parseTimelineItems(page.items || [], opts, state);
      for (var bi = 0; bi < batch.length; bi++) all.push(batch[bi]);
      if (typeof onProgress === "function") {
        onProgress({ count: state.count, max: cap, pages: pages, phase: "harvest-home", feed: feedLabel });
      }
      if (!page.cursor || !page.items || !page.items.length) break;
      if (state.count >= cap) {
        truncated = true;
        break;
      }
      cursor = page.cursor;
      await new Promise(function (r) {
        setTimeout(r, 350);
      });
    }

    lastBag = all;
    lastMeta = {
      screenName: "",
      userId: "",
      feedMode: feedMode,
      feedLabel: feedLabel,
      count: all.length,
      truncated: truncated,
      pages: pages,
      elapsedMs: Date.now() - started,
      sourceUrl: location.href.split("#")[0],
    };

    return {
      ok: true,
      list: all,
      truncated: truncated,
      summary: lastMeta,
    };
  }

  async function harvestMedia(options, onProgress) {
    if (isXHomeFeedPage()) return harvestHomeFeedMedia(options, onProgress);
    return harvestProfileMedia(options, onProgress);
  }

  async function harvestProfileMedia(options, onProgress) {
    if (!isXProfilePage()) throw new Error("Not on an X profile page");
    var opts = Object.assign(
      {
        maxItems: 120,
        includeVideo: true,
        chapterId: 1,
        fetchOriginal: false,
        reverseMultipleImagesPost: false,
      },
      options || {}
    );
    var cap = Math.min(Math.max(Number(opts.maxItems) || 120, 20), 300);
    opts.maxItems = cap;

    var clientUuid = uuid();
    var userId = getUserID();
    if (!userId) throw new Error("Could not read profile user id — scroll the profile header into view and retry");

    var state = { count: 0, seen: {} };
    var all = [];
    var cursor;
    var pages = 0;
    var truncated = false;
    var started = Date.now();

    while (state.count < cap) {
      var page = await fetchMediaPage(userId, opts.chapterId, cursor, clientUuid);
      pages++;
      var batch = parseTimelineItems(page.items || [], opts, state);
      for (var bi = 0; bi < batch.length; bi++) all.push(batch[bi]);
      if (typeof onProgress === "function") {
        onProgress({ count: state.count, max: cap, pages: pages, phase: "harvest" });
      }
      if (!page.cursor || !page.items || !page.items.length) break;
      if (state.count >= cap) {
        truncated = true;
        break;
      }
      cursor = page.cursor;
      await new Promise(function (r) {
        setTimeout(r, 350);
      });
    }

    /** If UserMedia returned very little, also scan posts timeline for embedded media. */
    if (opts.chapterId === 1 && state.count < Math.min(20, cap)) {
      cursor = undefined;
      while (state.count < cap) {
        var postsPage = await fetchMediaPage(userId, 0, cursor, clientUuid);
        pages++;
        var postsBatch = parseTimelineItems(postsPage.items || [], opts, state);
        for (var pi = 0; pi < postsBatch.length; pi++) all.push(postsBatch[pi]);
        if (typeof onProgress === "function") {
          onProgress({ count: state.count, max: cap, pages: pages, phase: "harvest-posts" });
        }
        if (!postsPage.cursor || !postsPage.items || !postsPage.items.length) break;
        if (state.count >= cap) {
          truncated = true;
          break;
        }
        cursor = postsPage.cursor;
        await new Promise(function (r) {
          setTimeout(r, 350);
        });
      }
    }

    lastBag = all;
    lastMeta = {
      screenName: getScreenNameFromUrl(),
      userId: userId,
      count: all.length,
      truncated: truncated,
      pages: pages,
      elapsedMs: Date.now() - started,
      sourceUrl: location.href.split("#")[0],
    };

    return {
      ok: true,
      list: all,
      truncated: truncated,
      summary: lastMeta,
    };
  }

  window.__tbccXProfileHarvestRun = harvestMedia;
  window.__tbccXProfileHarvestSnapshot = function () {
    return { list: lastBag.slice(), summary: lastMeta };
  };
  window.__tbccXProfileIsProfilePage = isXProfilePage;
  window.__tbccXProfileIsHomeFeedPage = isXHomeFeedPage;
  window.__tbccXProfileIsOverlayPage = isXOverlayPage;
  window.__tbccXProfileHomeFeedMode = getXHomeFeedMode;

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (!msg || typeof msg.action !== "string") return;
    if (msg.action === "tbcc-x-profile-harvest-snapshot") {
      try {
        sendResponse({ ok: true, list: lastBag.slice(), summary: lastMeta });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
      return true;
    }
    if (msg.action === "tbcc-x-profile-harvest-run") {
      harvestMedia(msg.options || {}, function (p) {
        try {
          chrome.runtime.sendMessage({ action: "tbcc-x-profile-harvest-progress", progress: p });
        } catch (_) {}
      })
        .then(function (r) {
          sendResponse(r);
        })
        .catch(function (e) {
          sendResponse({ ok: false, error: String(e.message || e) });
        });
      return true;
    }
  });
  });
})();
