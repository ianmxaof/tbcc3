/**
 * Magic-byte sniff for tbcc-webp-convert (ZIP mislabel regression).
 * Run: node extension/tests/tbcc-webp-convert-sniff.test.mjs
 */
import { createRequire } from "module";
import assert from "assert";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const W = require(path.join(root, "tbcc-webp-convert.js"));

function u8(...bytes) {
  return new Uint8Array(bytes);
}

// JPEG SOI
assert.strictEqual(W.tbccSniffImageKindFromBytes(u8(0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0, 0, 0, 0, 0)), "jpeg");

// PNG
assert.strictEqual(
  W.tbccSniffImageKindFromBytes(u8(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0)),
  "png"
);

// WEBP RIFF....WEBP
assert.strictEqual(
  W.tbccSniffImageKindFromBytes(
    u8(0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50)
  ),
  "webp"
);

// Fake .jpg name must not force jpg when bytes are webp — align helper
const webpBytes = u8(0x52, 0x49, 0x46, 0x46, 0x10, 0, 0, 0, 0x57, 0x45, 0x42, 0x50, 0, 0, 0, 0);
const blob = new Blob([webpBytes], { type: "image/jpeg" });
const aligned = await W.tbccAlignFilenameToBlob(blob, "049_avatar.jpg");
assert.strictEqual(aligned, "049_avatar.webp");

const ensured = await W.tbccEnsureJpegBlob(blob, { name: "049_avatar.jpg", force: false });
// force false + default settings may still convert if storage missing (defaults true)
// With force false and we mock — just check failure path with force true that produces jpeg OR keeps webp
const forced = await W.tbccEnsureJpegBlob(blob, { name: "049_avatar.jpg", force: true });
if (forced.converted) {
  assert.ok(/\.jpe?g$/i.test(forced.name));
  const k = await W.tbccSniffImageKind(forced.blob);
  assert.strictEqual(k, "jpeg");
} else {
  assert.ok(/\.webp$/i.test(forced.name), "failed convert must keep .webp not fake .jpg");
}

console.log("tbcc-webp-convert-sniff: ok");
