import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const core = require('./story-filter-core.js');

test('default map includes following and fetish defaults', () => {
  const map = core.defaultEnabledMap();
  assert.equal(map.following, true);
  assert.equal(map.fetish_added, false);
  assert.ok(Object.keys(map).length >= 50);
});

test('classifies common story phrases', () => {
  assert.equal(core.classifyStoryText('Alice is now following Bob'), 'following');
  assert.equal(core.classifyStoryText('Carol loved a picture by Dave'), 'loved_picture');
  assert.equal(core.classifyStoryText('Eve superloved a video'), 'superloved_video');
  assert.equal(core.classifyStoryText('Frank commented on a status'), 'status_comment_created');
});

test('unknown text returns null', () => {
  assert.equal(core.classifyStoryText('completely unrelated blurb'), null);
});

test('core attaches under __TBCC_US__ when loaded', () => {
  assert.ok(globalThis.__TBCC_US__.fetlife.storyFilterCore);
  assert.equal(
    path.basename(fileURLToPath(import.meta.url)),
    'story-filter.test.mjs'
  );
});
