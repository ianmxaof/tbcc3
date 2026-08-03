/**
 * ZIP naming heuristics (OnlyFans, Erome, Motherless, Fapello, X).
 * Run: node extension/tests/tbcc-zip-naming.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const naming = require(path.join(root, "tbcc-zip-naming.js")).TbccZipNaming;

const { inferZipContext, buildZipFilename, expandBundleTemplate, buildExportFilename, DEFAULT_TEMPLATE } = naming;

// OnlyFans creator from path
const of = inferZipContext({ sourceUrl: "https://onlyfans.com/jessicarose/posts/123" });
assert.strictEqual(of.name, "jessicarose");
assert.strictEqual(of.site, "onlyfans");

// OnlyFans /u/ form
const ofU = inferZipContext({ sourceUrl: "https://onlyfans.com/u/creator123" });
assert.strictEqual(ofU.name, "creator123");

// Erome album
const erome = inferZipContext({ sourceUrl: "https://www.erome.com/a/abc-album-title" });
assert.strictEqual(erome.gallery, "abc-album-title");
assert.ok(erome.name.length > 0);

// Motherless gallery id
const ml = inferZipContext({ sourceUrl: "https://motherless.com/G1234ABCD" });
assert.strictEqual(ml.gallery, "G1234ABCD");
assert.strictEqual(ml.name, "G1234ABCD");
assert.strictEqual(ml.site, "motherless");

// Fapello model slug
const fap = inferZipContext({ sourceUrl: "https://fapello.com/some-model" });
assert.strictEqual(fap.name, "some-model");
assert.strictEqual(fap.site, "fapello");

// X handle
const x = inferZipContext({ sourceUrl: "https://x.com/somehandle/status/1" });
assert.strictEqual(x.name, "somehandle");
assert.strictEqual(x.site, "x");

// Page title fallback
const titled = inferZipContext({
  sourceUrl: "https://example.com/gallery/1",
  pageTitle: "Hot Gallery | Erome",
});
assert.ok(titled.title.length > 0);

// Entry template uses model name
const entry = buildZipFilename(DEFAULT_TEMPLATE, { name: "jessicarose", index: 3, ext: "jpg" });
assert.match(entry, /jessicarose/);
assert.match(entry, /00003/);
assert.match(entry, /\.jpg$/);

// Custom bundle template tokens
const bundle = expandBundleTemplate("Pack · {name} · {site} · {gallery}", {
  sourceUrl: "https://onlyfans.com/jessicarose",
});
assert.match(bundle, /jessicarose/);
assert.match(bundle, /onlyfans/);
assert.match(bundle, /\.zip$/);

const exportName = buildExportFilename({
  sourceUrl: "https://onlyfans.com/jessicarose/posts/1",
  index: 2,
  ext: "jpg",
  heuristicNaming: true,
  template: DEFAULT_TEMPLATE,
});
assert.match(exportName, /jessicarose/);
assert.match(exportName, /00002/);

const legacy = buildExportFilename({
  sourceUrl: "https://onlyfans.com/jessicarose",
  index: 1,
  baseName: "photo.jpg",
  heuristicNaming: false,
});
assert.match(legacy, /^001_/);

console.log("tbcc-zip-naming: ok");
