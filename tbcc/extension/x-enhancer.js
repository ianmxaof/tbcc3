/**
 * TBCC X / Twitter enhancer (ISOLATED world).
 *
 * Port of XEnhancer userscript features:
 *   - One-click media download buttons on tweets
 *   - Timestamp formatting (configurable)
 *   - Optional simplify-mode layout
 *
 * Media URLs come from x-enhancer-hook.js (MAIN world) via postMessage.
 */
(function () {
  if (window.__tbccXEnhancerLoaded) return;
  window.__tbccXEnhancerLoaded = true;

  var STORAGE_FMT = "tbccXe_fmt";
  var STORAGE_SIMPLIFY = "tbccXe_simplify_mode";
  var FMT_DEFAULT = 16;
  var MYNAME = "tbcc_x_enhancer";

  var strings = {
    download: "Download",
    completed: "Download completed",
    tip: "Click to download media",
    preparing: "Preparing download…",
    settings: "X enhancer settings",
    titleDateFormat: "Timestamp format:",
    buttonClose: "Save & close",
    simplifyMode: "Simplify layout (max 800px feed)",
    downloadFailed: "Download failed",
    noMedia: "No media found",
  };

  var fmt = String(FMT_DEFAULT);
  var simplifyMode = false;

  function injectStyles() {
    if (document.getElementById("tbcc-x-enhancer-css")) return;
    var link = document.createElement("link");
    link.id = "tbcc-x-enhancer-css";
    link.rel = "stylesheet";
    link.href = chrome.runtime.getURL("styles/x-enhancer.css");
    (document.head || document.documentElement).appendChild(link);
  }

  function loadSettings(cb) {
    chrome.storage.local.get([STORAGE_FMT, STORAGE_SIMPLIFY], function (data) {
      fmt = String(data[STORAGE_FMT] != null ? data[STORAGE_FMT] : FMT_DEFAULT);
      simplifyMode = data[STORAGE_SIMPLIFY] === "true";
      syncFmtIndex();
      cb();
    });
  }

  function saveFmt(next) {
    fmt = String(next);
    chrome.storage.local.set({ [STORAGE_FMT]: fmt });
  }

  function saveSimplify(enabled) {
    simplifyMode = !!enabled;
    if (simplifyMode) chrome.storage.local.set({ [STORAGE_SIMPLIFY]: "true" });
    else chrome.storage.local.remove(STORAGE_SIMPLIFY);
  }

  function syncFmtIndex() {
    var max = XSettingsDialog.formats.length - 1;
    var v = parseInt(String(fmt), 10);
    if (Number.isNaN(v) || v < 0 || v > max) {
      fmt = String(Math.min(Math.max(parseInt(String(FMT_DEFAULT), 10), 0), max));
      chrome.storage.local.set({ [STORAGE_FMT]: fmt });
    } else {
      fmt = String(v);
    }
  }

  var XSettingsDialog = {
    number: Math.ceil(Math.random() * 1e8),
    formats: [
      { format: "Do nothing", example: "N/A" },
      { format: "ISO 8601 T", example: "2025-07-09T22:57:30" },
      { format: "ISO 8601 (space + s)", example: "2025-07-09 22:57:30" },
      { format: "ISO 8601 (space, no s)", example: "2025-07-09 22:57" },
      { format: "US: MMM d, yyyy h:mm A", example: "Jul 9, 2025, 10:57 PM" },
      { format: "US: EEE, MMM d, yyyy h:mm A", example: "Wed, Jul 9, 2025, 10:57 PM" },
      { format: "US: MM/dd/yyyy h:mm A", example: "07/09/2025 10:57 PM" },
      { format: "US: MM/dd/yyyy HH:mm", example: "07/09/2025 22:57" },
      { format: "EU/UK: dd/MM/yyyy HH:mm", example: "09/07/2025 22:57" },
      { format: "DE: dd.MM.yyyy, HH:mm", example: "09.07.2025, 22:57" },
      { format: "EU long: d MMMM yyyy, HH:mm", example: "9 July 2025, 22:57" },
      { format: "CN: yyyy年M月d日 HH:mm", example: "2025年7月9日 22:57" },
      { format: "East Asia: yyyy/MM/dd HH:mm", example: "2025/07/09 22:57" },
      { format: "UK short: EEE d MMM yyyy HH:mm", example: "Wed 9 Jul 2025 22:57" },
      { format: "Unix ctime (en)", example: "Wed Jul  9 22:57:30 2025" },
      { format: "US full: EEEE, MMMM d, yyyy h:mm:ss A", example: "Wednesday, July 9, 2025, 10:57:30 PM" },
      { format: "Compact: hh.mm A·mmm d,yy", example: "10.57 PM·Jul 9,25" },
      { format: "TW ROC: Myyy-MM-dd HH:mm", example: "M114-07-09 22:57" },
    ],
    make: function () {
      var dialog = document.createElement("div");
      dialog.className = "dialog_u_" + this.number;
      dialog.style.cssText =
        "all:initial;background:#fff;border:1px solid #e1e8ed;border-radius:10px;" +
        "box-shadow:0 16px 48px rgba(15,20,25,.14),0 4px 16px rgba(15,20,25,.08);" +
        "font-family:monospace;font-size:12px;width:640px;max-width:calc(100vw - 24px);" +
        "box-sizing:border-box;padding:8px;position:fixed;right:8px;top:8px;" +
        "z-index:2147483647;overflow:auto;display:none;";
      var escHtml = function (s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      };
      var formatsHtml = '<table style="width:100%;border:1px solid #c0bfbf;border-collapse:collapse;">';
      for (var i = 1; i <= this.formats.length; i++) {
        if (i % 2 !== 0) formatsHtml += '<tr style="border:1px solid #c0bfbf;">';
        var item = this.formats[i - 1];
        var exTitle = String(item.example).replace(/"/g, "&quot;");
        formatsHtml +=
          '<td width="50%" style="border:1px solid #c0bfbf;padding:5px;vertical-align:top;" title="' +
          exTitle +
          '"><div><div style="color:#000;font-size:13px;">' +
          '<input type="radio" name="fmt" value="' +
          (i - 1) +
          '" /><b>【' +
          i +
          "】" +
          escHtml(item.format) +
          '</b></div><div style="color:#555;font-size:11px;margin-top:4px;padding-left:20px;">' +
          escHtml(item.example) +
          "</div></div></td>";
        if (i % 2 === 0) formatsHtml += "</tr>";
      }
      if (this.formats.length % 2 !== 0) formatsHtml += "</tr>";
      formatsHtml += "</table>";
      dialog.innerHTML =
        '<div style="font-size:17px;font-weight:700;margin:15px auto;padding:0 4px;text-align:center;' +
        'font-family:system-ui,-apple-system,\'Segoe UI\',Roboto,sans-serif;color:#0f1419;">' +
        escHtml(strings.titleDateFormat) +
        "</div><div>" +
        formatsHtml +
        '</div><div style="margin:12px 4px;">' +
        '<label style="font-family:system-ui,sans-serif;font-size:13px;color:#0f1419;">' +
        '<input type="checkbox" name="simplify" style="margin-right:6px;" />' +
        escHtml(strings.simplifyMode) +
        "</label></div>" +
        '<div style="margin-top:15px;text-align:center;">' +
        '<button type="button" name="closex" style="appearance:none;border:1px solid #1d9bf0;border-radius:999px;' +
        "padding:5px 18px;font-size:14px;font-weight:600;font-family:system-ui,sans-serif;" +
        'background:linear-gradient(180deg,#1d9bf0 0%,#1a8cd8 100%);color:#fff;cursor:pointer;">' +
        escHtml(strings.buttonClose) +
        "</button></div>";
      return dialog;
    },
    addEvent: function (dialog) {
      dialog.querySelector("button[name='closex']").addEventListener("click", function () {
        var radios = dialog.querySelectorAll('input[name="fmt"]');
        for (var i = 0; i < radios.length; i++) {
          if (radios[i].checked) {
            saveFmt(radios[i].value);
            break;
          }
        }
        var simp = dialog.querySelector('input[name="simplify"]');
        var wasSimplify = simplifyMode;
        var nextSimplify = !!(simp && simp.checked);
        saveSimplify(nextSimplify);
        dialog.style.display = "none";
        if (wasSimplify !== nextSimplify) location.reload();
        else XDateFormat.repldatetime();
      });
    },
    open: function (dialog) {
      if (dialog.style.display !== "none") return;
      var input = dialog.querySelector('input[name="fmt"][value="' + String(fmt) + '"]');
      if (input) input.checked = true;
      var simp = dialog.querySelector('input[name="simplify"]');
      if (simp) simp.checked = simplifyMode;
      dialog.style.display = "block";
    },
    init: function () {
      var dialog = this.make();
      this.addEvent(dialog);
      document.body.appendChild(dialog);
      var gear = document.createElement("button");
      gear.type = "button";
      gear.className = "tbcc-xe-settings-btn";
      gear.title = strings.settings;
      gear.textContent = "⚙";
      gear.addEventListener("click", function () {
        XSettingsDialog.open(dialog);
      });
      document.body.appendChild(gear);
      this._dialog = dialog;
    },
  };

  var XDateFormat = {
    df: function (date, f) {
      var WEEK_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
      var MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      var MONTH_FULL = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
      ];
      var pad = function (num) {
        return ("0" + num).slice(-2);
      };
      var YE = date.getFullYear();
      var YE2 = YE.toString().slice(-2);
      var YM = YE - 1911;
      var MO = pad(date.getMonth() + 1);
      var MO_IDX = date.getMonth();
      var MO_NAME = MONTH_SHORT[MO_IDX];
      var MO_NAME_FULL = MONTH_FULL[MO_IDX];
      var DA = pad(date.getDate());
      var dNum = parseInt(DA, 10);
      var weekAbbr = function () {
        return WEEK_FULL[date.getDay()].slice(0, 3);
      };
      var HO = pad(date.getHours());
      var MI = pad(date.getMinutes());
      var SE = pad(date.getSeconds());
      var h12 = date.getHours() % 12 || 12;
      var HO12 = pad(h12);
      var AMPM = date.getHours() >= 12 ? "PM" : "AM";
      var F = [
        YE + "-" + MO + "-" + DA + "T" + HO + ":" + MI + ":" + SE,
        YE + "-" + MO + "-" + DA + " " + HO + ":" + MI + ":" + SE,
        YE + "-" + MO + "-" + DA + " " + HO + ":" + MI,
        MO_NAME + " " + dNum + ", " + YE + ", " + HO12 + ":" + MI + " " + AMPM,
        weekAbbr() + ", " + MO_NAME + " " + dNum + ", " + YE + ", " + HO12 + ":" + MI + " " + AMPM,
        MO + "/" + DA + "/" + YE + " " + HO12 + ":" + MI + " " + AMPM,
        MO + "/" + DA + "/" + YE + " " + HO + ":" + MI,
        DA + "/" + MO + "/" + YE + " " + HO + ":" + MI,
        DA + "." + MO + "." + YE + ", " + HO + ":" + MI,
        dNum + " " + MO_NAME_FULL + " " + YE + ", " + HO + ":" + MI,
        YE + "年" + (MO_IDX + 1) + "月" + dNum + "日 " + HO + ":" + MI,
        YE + "/" + MO + "/" + DA + " " + HO + ":" + MI,
        weekAbbr() + " " + dNum + " " + MO_NAME + " " + YE + " " + HO + ":" + MI,
        weekAbbr() + " " + MO_NAME + " " + String(dNum).padStart(2, " ") + " " + HO + ":" + MI + ":" + SE + " " + YE,
        WEEK_FULL[date.getDay()] + ", " + MO_NAME_FULL + " " + dNum + ", " + YE + ", " + HO12 + ":" + MI + ":" + SE + " " + AMPM,
        HO12 + "." + MI + " " + AMPM + "·" + MO_NAME + " " + dNum + "," + YE2,
        "M" + YM + "-" + MO + "-" + DA + " " + HO + ":" + MI,
      ];
      return F[f] != null ? F[f] : F[0];
    },
    repldatetime: function () {
      var SEL =
        'main div[data-testid="primaryColumn"] section article time[datetime*=":"],' +
        'div[aria-labelledby="modal-header"] div[data-testid^="User-Name"] time[datetime],' +
        'div[aria-labelledby="modal-header"] div[aria-label] time[datetime],' +
        'main section[aria-labelledby="detail-header"] article div[data-testid^="User-Name"] time[datetime],' +
        'main section div[data-testid="conversation"] div[aria-label] time[datetime]';
      document.querySelectorAll(SEL).forEach(function (e) {
        if (fmt == 0) return;
        var SEL_ADD = "span.us-" + MYNAME;
        var d = e.getAttribute("datetime");
        if (!d) return;
        var df = XDateFormat.df(new Date(d), parseInt(fmt, 10) - 1);
        var pe = e.parentNode;
        if (!pe) return;
        var old = pe.querySelectorAll(SEL_ADD);
        if (!old.length) {
          var span = document.createElement("span");
          span.className = "us-" + MYNAME;
          span.setAttribute("datetime", d);
          span.setAttribute("local-datetime", df);
          span.textContent = df;
          span.style.cssText = e.style.cssText;
          e.style.setProperty("display", "none");
          pe.appendChild(span);
        } else if (old[0].getAttribute("local-datetime") != df) {
          old[0].setAttribute("local-datetime", df);
          old[0].textContent = df;
          old[0].style.cssText = e.style.cssText;
        }
      });
    },
  };

  var downloadSvg =
    '<g class="download"><path d="M11.99 16l-5.7-5.7L7.7 8.88l3.29 3.3V2.59h2v9.59l3.3-3.3 1.41 1.42-5.71 5.7zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z" /></g>' +
    '<g class="completed"><path d="M3,14 v5 q0,2 2,2 h14 q2,0 2,-2 v-5 M7,10 l3,4 q1,1 2,0 l8,-11" fill="none" stroke="#1DA1F2" stroke-width="2" stroke-linecap="round" /></g>' +
    '<g class="loading"><circle cx="12" cy="12" r="10" fill="none" stroke="#1DA1F2" stroke-width="4" opacity="0.4" /><path d="M12,2 a10,10 0 0 1 10,10" fill="none" stroke="#1DA1F2" stroke-width="4" stroke-linecap="round" /></g>' +
    '<g class="failed"><circle cx="12" cy="12" r="11" fill="#f33" stroke="currentColor" stroke-width="2" opacity="0.8" /><path d="M14,5 a1,1 0 0 0 -4,0 l0.5,9.5 a1.5,1.5 0 0 0 3,0 z M12,17 a2,2 0 0 0 0,4 a2,2 0 0 0 0,-4" fill="#fff" stroke="none" /></g>';

  var XDownload = {
    mediaMap: new Map(),
    ingestItems: function (items) {
      if (!items || !items.length) return;
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (item && item.entityId) this.mediaMap.set(item.entityId, item);
      }
    },
  };

  var XDownloadUI = {
    showSensitive: true,
    svg: downloadSvg,
    isTweetdeck: function () {
      return window.location.host.includes("tweetdeck");
    },
    extractStatusId: function (url) {
      return url ? (url.match(/\/status\/(\d+)/) || [null, null])[1] : null;
    },
    uniqueArray: function (arr) {
      return Array.from(new Set(arr));
    },
    getExtension: function (url) {
      try {
        return new URL(url).pathname.split(".").pop() || null;
      } catch (_) {
        return null;
      }
    },
    sanitizeFilename: function (filename) {
      return filename.replace(/[\/\\\?\%\*\:\|\\"<>\r\n]/g, "_");
    },
    setStatus: function (btn, classnames, title, style) {
      if (classnames) {
        btn.classList.remove("download", "completed", "loading", "failed");
        for (var i = 0; i < classnames.length; i++) btn.classList.add(classnames[i]);
      }
      if (title) btn.title = title;
      if (style) btn.style.cssText = style;
    },
    downloadUrl: function (url, filename, defaultExt) {
      var ext = this.getExtension(url) || defaultExt || "bin";
      var finalName = "tbcc/x/" + filename + "." + ext;
      return new Promise(function (resolve, reject) {
        chrome.runtime.sendMessage(
          {
            action: "tbcc-download-url-from-page-menu",
            url: url,
            refererPageUrl: location.href,
            filename: finalName,
          },
          function (resp) {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError);
              return;
            }
            if (resp && resp.ok) resolve();
            else reject(new Error((resp && resp.error) || strings.downloadFailed));
          }
        );
      });
    },
    clickDownloadEvent: function (btn, statusIds) {
      var self = this;
      var uniqueStatusIds = this.uniqueArray(statusIds);
      this.setStatus(btn, ["loading"], strings.preparing);
      var promises = uniqueStatusIds.map(function (statusId) {
        var media = XDownload.mediaMap.get(statusId);
        if (!media) return Promise.reject("no media for " + statusId);
        var filename = self.sanitizeFilename(media.text || media.entityId);
        if (media.video) return self.downloadUrl(media.video, filename, "mp4");
        if (media.photo) return self.downloadUrl(media.photo, filename, "jpg");
        return Promise.reject("empty");
      });
      Promise.allSettled(promises).then(function (results) {
        var anySuccess = results.some(function (r) {
          return r.status === "fulfilled";
        });
        if (anySuccess) self.setStatus(btn, ["completed"], strings.completed);
        else self.setStatus(btn, ["failed"], strings.noMedia);
      });
    },
    addButtonTo: function (article) {
      if (article.dataset.tbccXeDetected) return;
      article.dataset.tbccXeDetected = "true";
      var self = this;
      var statusIds = Array.from(article.querySelectorAll('a[href*="/status/"]'))
        .map(function (el) {
          return self.extractStatusId(el.href);
        })
        .filter(Boolean);
      if (!statusIds.length) return;
      var mediaSelector = [
        'a[href*="/photo/1"]',
        'div[role="progressbar"]',
        'button[data-testid="playButton"]',
        'div[data-testid="videoComponent"]',
        'a[href="/settings/content_you_see"]',
        "div.media-image-container",
        "div.media-preview-container",
        'div[aria-labelledby]>div:first-child>div[role="button"][tabindex="0"]',
      ];
      if (article.querySelector(mediaSelector.join(","))) {
        var btnGroup = article.querySelector(
          'div[role="group"]:last-of-type, ul.tweet-actions, ul.tweet-detail-actions'
        );
        if (btnGroup) {
          var children = Array.from(
            btnGroup.querySelectorAll(":scope>div>div, li.tweet-action-item>a, li.tweet-detail-action-item>a")
          );
          if (!children.length) return;
          var btnShare = children[children.length - 1].parentNode;
          var btnDownload = btnShare.cloneNode(true);
          btnDownload.style.marginLeft = "10px";
          var innerBtn = btnDownload.querySelector("button");
          if (innerBtn) innerBtn.removeAttribute("disabled");
          var svgContainer = this.isTweetdeck() ? btnDownload.firstElementChild : btnDownload.querySelector("svg");
          if (svgContainer) {
            if (this.isTweetdeck()) {
              svgContainer.innerHTML = '<svg viewBox="0 0 20 20" width="15" height="15">' + this.svg + "</svg>";
              svgContainer.removeAttribute("rel");
              btnDownload.classList.replace("pull-left", "pull-right");
            } else {
              svgContainer.innerHTML = this.svg;
            }
          }
          this.setStatus(btnDownload, ["x-master-dl", "download"], strings.tip);
          btnGroup.insertBefore(btnDownload, btnShare.nextSibling);
          btnDownload.onclick = function () {
            self.clickDownloadEvent(btnDownload, statusIds);
          };
          if (this.showSensitive) {
            var reveal = article.querySelector(
              'div[aria-labelledby] div[role="button"][tabindex="0"]:not([data-testid]) > div[dir] > span > span'
            );
            if (reveal) reveal.click();
          }
        }
      }
      var imgs = article.querySelectorAll('a[href*="/photo/"]');
      if (imgs.length > 1) {
        imgs.forEach(function (img) {
          var imgStatusId = self.extractStatusId(img.href);
          if (!imgStatusId || img.parentNode.querySelector(".x-master-dl.tmd-img")) return;
          var btnDownload = document.createElement("div");
          btnDownload.style.cssText = "position:absolute;top:0;right:0;z-index:10;margin:5px;";
          btnDownload.innerHTML =
            "<div><div><svg viewBox=\"0 0 20 20\" width=\"15\" height=\"15\">" + self.svg + "</svg></div></div>";
          self.setStatus(btnDownload, ["x-master-dl", "tmd-img", "download"], strings.download);
          img.parentNode.appendChild(btnDownload);
          btnDownload.onclick = function (e) {
            e.preventDefault();
            e.stopPropagation();
            self.clickDownloadEvent(btnDownload, [imgStatusId]);
          };
        });
      }
    },
    addButtonToMedia: function (listitems) {
      var self = this;
      listitems.forEach(function (li) {
        if (li.dataset.tbccXeDetected) return;
        li.dataset.tbccXeDetected = "true";
        var statusElement = li.querySelector('a[href*="/status/"]');
        var statusId = statusElement ? self.extractStatusId(statusElement.href) : null;
        if (!statusId) return;
        var btnDownload = document.createElement("div");
        btnDownload.innerHTML =
          "<div><div><svg viewBox=\"0 0 20 20\" width=\"15\" height=\"15\">" + self.svg + "</svg></div></div>";
        self.setStatus(btnDownload, ["x-master-dl", "tmd-media", "download"], strings.tip);
        li.appendChild(btnDownload);
        btnDownload.onclick = function () {
          self.clickDownloadEvent(btnDownload, [statusId]);
        };
      });
    },
    detect: function (node) {
      var article =
        (node.tagName === "ARTICLE" && node) ||
        (node.tagName === "DIV" && (node.querySelector("article") || node.closest("article")));
      if (article) this.addButtonTo(article);
      var listitems =
        node.tagName === "LI" && node.getAttribute("role") === "listitem"
          ? [node]
          : node.tagName === "DIV"
            ? node.querySelectorAll('li[role="listitem"]')
            : null;
      if (listitems && listitems.length) this.addButtonToMedia(Array.from(listitems));
    },
  };

  function applySimplifyMode() {
    if (!simplifyMode) return;
    document.documentElement.classList.add("tbcc-xe-simplify");
    function update() {
      var width = Math.min(document.documentElement.offsetWidth || 800, 800);
      if (window.innerWidth === width && document.documentElement.clientWidth === width) return;
      window.__defineGetter__("innerWidth", function () {
        return width;
      });
      document.documentElement.__defineGetter__("clientWidth", function () {
        return width;
      });
      if (window.visualViewport) {
        window.visualViewport.__defineGetter__("width", function () {
          return width;
        });
      }
      window.dispatchEvent(new Event("resize"));
      if (window.visualViewport) window.visualViewport.dispatchEvent(new Event("resize"));
    }
    window.addEventListener("load", update);
    window.addEventListener("resize", update);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", update);
    document.addEventListener("visibilitychange", update);
    update();
  }

  function onHookMessage(event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || !data.tbccXEnhancer || data.type !== "media") return;
    XDownload.ingestItems(data.items);
  }

  function startObserver() {
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType === 1) {
            XDownloadUI.detect(node);
            XDateFormat.repldatetime();
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    XDateFormat.repldatetime();
  }

  function whenBodyReady(fn) {
    if (document.body) {
      fn();
      return;
    }
    var obs = new MutationObserver(function () {
      if (document.body) {
        obs.disconnect();
        fn();
      }
    });
    obs.observe(document.documentElement, { childList: true });
  }

  window.addEventListener("message", onHookMessage);

  injectStyles();
  loadSettings(function () {
    applySimplifyMode();
    whenBodyReady(function () {
      XSettingsDialog.init();
      startObserver();
    });
  });
})();
