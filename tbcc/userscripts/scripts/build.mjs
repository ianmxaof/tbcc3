import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const packagesDir = path.join(root, 'packages');
const distDir = path.join(root, 'dist');

const args = new Set(process.argv.slice(2));
const shouldBump = !args.has('--no-bump');

function bumpPatch(version) {
  const parts = String(version || '0.0.0').split('.').map((n) => parseInt(n, 10) || 0);
  while (parts.length < 3) parts.push(0);
  parts[2] += 1;
  return parts.slice(0, 3).join('.');
}

function renderHeader(manifest) {
  const h = manifest.header;
  const lines = [
    '// ==UserScript==',
    `// @name         ${h.name}`,
    `// @namespace    ${h.namespace}`,
    `// @version      ${manifest.version}`,
    `// @description  ${h.description}`,
    '// @author       TBCC',
  ];
  for (const m of h.match || []) lines.push(`// @match        ${m}`);
  for (const g of h.grant || []) lines.push(`// @grant        ${g}`);
  if (h['run-at']) lines.push(`// @run-at       ${h['run-at']}`);
  if (h.license) lines.push(`// @license      ${h.license}`);
  // Local dev updates: run `npm run serve` then Tampermonkey "Check for updates"
  const updateUrl = h.updateURL || 'http://127.0.0.1:8765/fetlife-suite.user.js';
  const downloadUrl = h.downloadURL || updateUrl;
  lines.push(`// @updateURL    ${updateUrl}`);
  lines.push(`// @downloadURL  ${downloadUrl}`);
  lines.push('// ==/UserScript==', '');
  return lines.join('\n');
}

function buildSuite(suiteDir) {
  const manifestPath = path.join(suiteDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return null;
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const prev = manifest.version;

  if (shouldBump) {
    manifest.version = bumpPatch(manifest.version);
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  }

  const chunks = [
    renderHeader(manifest),
    `/* Built ${new Date().toISOString()} - v${manifest.version} - see tbcc/userscripts/NOTICE.md */`,
    '',
  ];

  for (const rel of manifest.files) {
    const abs = path.resolve(suiteDir, rel);
    if (!fs.existsSync(abs)) throw new Error(`Missing file in ${manifest.name}: ${rel}`);
    const body = fs.readFileSync(abs, 'utf8').replace(/\r\n/g, '\n');
    chunks.push(`/* ---- ${path.relative(root, abs).replace(/\\/g, '/')} ---- */`, body.trim(), '');
  }

  fs.mkdirSync(distDir, { recursive: true });
  const outName = `${manifest.name}.user.js`;
  const outPath = path.join(distDir, outName);
  fs.writeFileSync(outPath, chunks.join('\n') + '\n', 'utf8');
  return {
    name: manifest.name,
    outPath,
    bytes: fs.statSync(outPath).size,
    version: manifest.version,
    prev,
    bumped: shouldBump,
  };
}

const results = [];
for (const ent of fs.readdirSync(packagesDir, { withFileTypes: true })) {
  if (!ent.isDirectory() || ent.name === 'shared') continue;
  const built = buildSuite(path.join(packagesDir, ent.name));
  if (built) results.push(built);
}

if (!results.length) {
  console.error('No suites built');
  process.exit(1);
}

for (const r of results) {
  const ver = r.bumped ? `${r.prev} → ${r.version}` : r.version;
  console.log(`built ${r.name} v${ver} → ${path.relative(root, r.outPath)} (${r.bytes} bytes)`);
}
