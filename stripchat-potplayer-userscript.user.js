// ==UserScript==
// @match        *://*.stripchat.com/*
// @match        *://*.instantfapcams.com/*
// @match        *://*.xhamsterlive.com/*
// @match        *://*.cambb.xxx/models/stripchat/*
// @match        *://*.nudecams.xxx/models/stripchat/*
// @match        *://*.cambb.xxx/models/chaturbate/*
// @match        *://*.nudecams.xxx/models/chaturbate/*
// @match        *://chaturbate.com/*
// @name         Play stripchat or chaturbate videos with potplayer,vlc,nplayer,mpv, etc V2
// @description  Play stripchat or chaturbate videos with potplayer,vlc,nplayer,mpv, etc. (cambb layout patch)
// @namespace    https://greasyfork.org/zh-CN/scripts/473187
// @version      2.9.1-cambb-patch
// @license      MIT
// @downloadURL  https://update.sleazyfork.org/scripts/485007/Play%20stripchat%20or%20chaturbate%20videos%20with%20potplayer%2Cvlc%2Cnplayer%2Cmpv%2C%20etc%20V2.user.js
// @updateURL    https://update.sleazyfork.org/scripts/485007/Play%20stripchat%20or%20chaturbate%20videos%20with%20potplayer%2Cvlc%2Cnplayer%2Cmpv%2C%20etc%20V2.meta.js
// ==/UserScript==

(function () {
    'use strict';

    const LNK = [
        'edge11-rtm.live.mmcdn.com',
        'edge13-rtm.live.mmcdn.com',
        'edge17-rtm.live.mmcdn.com',
        'edge10-sea.live.mmcdn.com',
        'edge24-waw.live.mmcdn.com',
        'edge13-waw.live.mmcdn.com',
        'edge23-waw.live.mmcdn.com',
        'edge33-waw.live.mmcdn.com',
        'edge21-waw.live.mmcdn.com',
    ];

    const H264 = [
        '3633648a8122ab5bc3f2ae1c201f7d2631b642761d8a471db1044e23d086b9b8_trns_h264',
    ];

    const LIVE_URL_NUM = [
        '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
        '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
        '21', '22', '23', '24',
    ];

    const HOST = document.location.hostname.replace(/^www\./, '');

    function pick(arr) {
        return arr[Math.floor(Math.random() * arr.length)];
    }

    function stripchatUsernameFromPath() {
        const m = document.location.pathname.match(/\/models\/stripchat\/([^/?#]+)/i);
        return m ? decodeURIComponent(m[1]) : null;
    }

    function liveIdFromString(value) {
        if (!value) return null;
        const nums = String(value).match(/\d+/g);
        if (!nums || !nums.length) return null;
        // Original script used index [1]; fall back to longest numeric token.
        if (nums[1]) return nums[1];
        return nums.sort((a, b) => b.length - a.length)[0];
    }

    function extractStripchatLiveId() {
        const player = document.querySelector('#livestream-player');
        if (player) {
            const id = liveIdFromString(player.getAttribute('data-src') || player.getAttribute('src'));
            if (id) return id;
        }

        const blurImg = document.querySelector('.video-element-wrapper-blur.with-blur .image-background');
        if (blurImg && blurImg.src) {
            const id = liveIdFromString(blurImg.src);
            if (id) return id;
        }

        const selectors = [
            'img[src*="doppio"]',
            'img[src*="stripchat"]',
            'video[src]',
            'source[src]',
            '[data-src*="doppio"]',
            '[data-src*="stripchat"]',
            'iframe[src*="stripchat"]',
        ];
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const src = el.getAttribute('data-src') || el.getAttribute('src') || el.src || '';
                const id = liveIdFromString(src);
                if (id && id.length >= 5) return id;
            }
        }

        return null;
    }

    function buildStripchatHlsUrl(liveId) {
        const urlNum = pick(LIVE_URL_NUM);
        return `https://b-hls-${urlNum}.doppiocdn.com/hls/${liveId}/${liveId}.m3u8`;
    }

    function buildChaturbateHlsUrl(username) {
        const randomLnk = pick(LNK);
        const randomH264 = pick(H264);
        return `https://${randomLnk}/live-hls/amlst:${username}-sd-${randomH264}/playlist.m3u8`;
    }

    function resolveLiveUrl() {
        const path = document.location.pathname;
        const href = document.location.href;

        const supportedHost =
            HOST === 'cambb.xxx' ||
            HOST === 'camconsole.com' ||
            HOST === 'nudecams.xxx' ||
            HOST === 'chaturbate.com' ||
            HOST === 'stripchat.com' ||
            HOST === 'xhamsterlive.com' ||
            HOST === 'instantfapcams.com';

        if (!supportedHost) return null;

        // Chaturbate
        if (path.includes('/models/chaturbate') || HOST === 'chaturbate.com') {
            let username;

            if (HOST === 'chaturbate.com' && !path.includes('/fullvideo/')) {
                username = path.split('/')[1];
            } else if (path.includes('/fullvideo/')) {
                const matches = href.match(/chaturbate\.com\/fullvideo\/\?b=([^&]+)/);
                username = matches ? matches[1] : null;
            } else {
                username = href.split(/[=/]/).pop();
            }

            if (!username) return null;
            return buildChaturbateHlsUrl(username);
        }

        // Stripchat on aggregator pages
        if (path.includes('/models/stripchat')) {
            const liveId = extractStripchatLiveId();
            if (liveId) return buildStripchatHlsUrl(liveId);

            const username = stripchatUsernameFromPath();
            if (username) {
                alert(
                    'Could not read a live stream ID on this cambb/nudecams page.\n\n' +
                    'Open the model on Stripchat directly, then use the buttons there:\n' +
                    `https://stripchat.com/${username}`
                );
                window.open(`https://stripchat.com/${username}`, '_blank');
            } else {
                alert('Could not find Stripchat stream info on this page.');
            }
            return null;
        }

        // Stripchat direct / mirrors
        if (HOST === 'stripchat.com' || HOST === 'xhamsterlive.com' || HOST === 'instantfapcams.com') {
            const liveId = extractStripchatLiveId();
            if (!liveId) {
                alert('Could not find Stripchat stream info on this page. Is the room live?');
                return null;
            }
            return buildStripchatHlsUrl(liveId);
        }

        return null;
    }

    function findInjectionTarget() {
        if (HOST === 'cambb.xxx' || HOST === 'nudecams.xxx') {
            return (
                document.querySelector('.col-12.model-iframe') ||
                document.querySelector('main.model-page') ||
                document.querySelector('.container-fluid') ||
                document.querySelector('.page-wrap')
            );
        }

        if (HOST === 'stripchat.com' || HOST === 'xhamsterlive.com' || HOST === 'instantfapcams.com') {
            return document.querySelector('#portal-root') || document.querySelector('main') || document.body;
        }

        if (HOST === 'camconsole.com') {
            return document.querySelector('.separator-2') || document.querySelector('main') || document.body;
        }

        return document.querySelector('.videoPlayerDiv') || document.querySelector('main') || document.body;
    }

    function btnCom(playerName, copyUrl = false) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.innerHTML = playerName;
        btn.style.width = '100px';
        btn.style.height = '30px';
        btn.style.margin = '4px';
        btn.style.color = 'white';
        btn.style.background = '#2b2b2b';
        btn.style.border = '1px solid #e33e33';
        btn.style.borderRadius = '8px';
        btn.style.fontSize = '16px';
        btn.style.cursor = 'pointer';
        btn.style.zIndex = '99999';

        btn.onclick = function () {
            const liveUrl = resolveLiveUrl();
            console.log('Live URL:', liveUrl);
            if (!liveUrl) return;

            if (copyUrl) {
                navigator.clipboard.writeText(liveUrl).then(function () {
                    alert('Link copied to clipboard:\n' + liveUrl);
                }).catch(function (err) {
                    console.error('Unable to copy text to clipboard', err);
                    prompt('Copy this URL:', liveUrl);
                });
            } else {
                window.open(liveUrl, '_blank');
            }
        };

        const addBtn = () => {
            const target = findInjectionTarget();
            if (!target) {
                console.warn('[userscript] No injection target found on', HOST);
                return;
            }

            if (!target.querySelector(`[data-tbcc-player-btn="${playerName}"]`)) {
                btn.setAttribute('data-tbcc-player-btn', playerName);
                target.prepend(btn);
            }
        };

        if (document.readyState === 'complete') {
            addBtn();
        } else {
            window.addEventListener('load', addBtn);
        }
    }

    btnCom('Copy Link', true);
    btnCom('Open Link', false);
    btnCom('mpv', false);
    btnCom('vlc', false);
    btnCom('potplayer', false);
    btnCom('nplayer', false);
})();
