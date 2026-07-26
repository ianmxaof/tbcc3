import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(__dirname, '..', 'packages', 'perchance-suite', 'data');
const json = JSON.parse(fs.readFileSync(path.join(dir, 'loot-god-library.json'), 'utf8'));
const body = JSON.stringify(json, null, 2);
const out = `/* Loot God Card Lab library — synced with loot-god-library.json */
(function (global) {
  'use strict';
  const US = (global.__TBCC_US__ = global.__TBCC_US__ || {});
  const PC = (US.perchance = US.perchance || {});
  /* eslint-disable */
  PC.lootGodLibrary = ${body};
})(typeof unsafeWindow !== 'undefined' ? unsafeWindow : window);
`;
fs.writeFileSync(path.join(dir, 'loot-god-library.js'), out);
console.log(`synced loot-god-library.js v${json.version} presets=${Object.keys(json.generatorPresets || {}).length}`);
