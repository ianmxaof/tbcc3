import assert from 'node:assert/strict';
import test from 'node:test';

// Lightweight parse mirror for CI (DOM module not loaded in node)
function parseSex(text) {
  const t = String(text || '').replace(/\s+/g, ' ');
  const m =
    t.match(/\b(\d{2})\s*(CD\/TV|MtF|FtM|GF|GQ|IS|TG|TV|CD|[MF])\b/i) ||
    t.match(/\b(\d{2})(CD\/TV|MtF|FtM|GF|GQ|IS|TG|[MF])\b/i);
  if (!m) return null;
  return m[2].toUpperCase();
}

test('parseSex reads M/F/MtF', () => {
  assert.equal(parseSex('32M Dom'), 'M');
  assert.equal(parseSex('28F sub'), 'F');
  assert.equal(parseSex('25MtF switch'), 'MTF');
  assert.equal(parseSex('no vitals here'), null);
});
