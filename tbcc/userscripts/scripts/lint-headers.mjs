import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '../dist');

if (!fs.existsSync(distDir)) {
  console.error('dist/ missing — run npm run build first (or build in CI before lint)');
  process.exit(1);
}

const files = fs.readdirSync(distDir).filter((f) => f.endsWith('.user.js'));
if (!files.length) {
  console.error('No dist/*.user.js files');
  process.exit(1);
}

let failed = 0;
for (const file of files) {
  const text = fs.readFileSync(path.join(distDir, file), 'utf8');
  const start = text.indexOf('==UserScript==');
  const end = text.indexOf('==/UserScript==');
  if (start < 0 || end < 0) {
    console.error(`${file}: missing UserScript header`);
    failed += 1;
    continue;
  }
  const head = text.slice(start, end);
  const need = ['@name', '@match', '@grant', '@version'];
  for (const n of need) {
    if (!head.includes(n)) {
      console.error(`${file}: header missing ${n}`);
      failed += 1;
    }
  }
  if (!head.includes('fetlife.com') && file.includes('fetlife')) {
    console.error(`${file}: expected fetlife.com @match`);
    failed += 1;
  }
  console.log(`ok ${file}`);
}

process.exit(failed ? 1 : 0);
