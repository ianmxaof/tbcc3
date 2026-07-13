/**
 * Jobs data shape smoke (no DOM).
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const jobsPath = path.join(__dirname, '../data/jobs.json');

test('jobs.json has promo + loot Gemini-parity entries', () => {
  const data = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
  assert.ok(Array.isArray(data.jobs));
  assert.ok(data.jobs.length >= 20);
  const lanes = new Set(data.jobs.map((j) => j.lane));
  assert.ok(lanes.has('promo'));
  assert.ok(lanes.has('loot'));
  const martyrs = data.jobs.find((j) => j.id === 'promo-martyrs-ma07-10');
  assert.ok(martyrs);
  assert.match(martyrs.prompt, /LAYOUT LOCK|AOF MEGA PACKS|OUTPUT:/i);
  const tier = data.jobs.find((j) => j.id === 'loot-tier-07');
  assert.ok(tier);
  assert.match(tier.prompt, /TIER|FILTH|loot/i);
});
