/**
 * Download-routing "circuit board": rule matching + folder template expansion.
 * Run: node extension/tests/tbcc-download-router.test.mjs
 */
import assert from "assert";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const router = require(path.join(root, "tbcc-download-router.js")).TbccDownloadRouter;

const { matchRoute, buildRoutedFilename, extOf, hostnameOf } = router;

assert.strictEqual(extOf("photo.JPG"), "jpg");
assert.strictEqual(extOf("no-extension"), "");
assert.strictEqual(hostnameOf("https://www.onlyfans.com/x"), "onlyfans.com");

const routes = [
  { id: "1", enabled: true, matchType: "extension", matchValue: "jpg,png,webp", folder: "media/{domain}" },
  { id: "2", enabled: true, matchType: "domain", matchValue: "erome.com", folder: "erome/{YYYY}-{MM}" },
  { id: "3", enabled: false, matchType: "extension", matchValue: "zip", folder: "archives" },
  { id: "4", enabled: true, matchType: "mimePrefix", matchValue: "video/", folder: "video" },
  { id: "5", enabled: true, matchType: "urlRegex", matchValue: "reddit\\.com", folder: "reddit" },
];

// Extension match wins over later domain rule when it's first in order
const jpgItem = { filename: "IMG_001.jpg", url: "https://onlyfans.com/x/y.jpg", mime: "image/jpeg" };
const jpgRoute = matchRoute(routes, jpgItem);
assert.strictEqual(jpgRoute.id, "1");
assert.strictEqual(buildRoutedFilename(jpgRoute, jpgItem), "media/onlyfans.com/IMG_001.jpg");

// Domain match when extension doesn't match any extension rule
const eromeItem = { filename: "clip.mp4", url: "https://www.erome.com/a/xyz", mime: "video/mp4" };
const eromeRoute = matchRoute(routes, eromeItem);
assert.strictEqual(eromeRoute.id, "2");
const eromeFile = buildRoutedFilename(eromeRoute, eromeItem);
assert.match(eromeFile, /^erome\/\d{4}-\d{2}\/clip\.mp4$/);

// Disabled rule is skipped
const zipItem = { filename: "bundle.zip", url: "https://example.com/bundle.zip", mime: "application/zip" };
assert.strictEqual(matchRoute(routes, zipItem), null);

// mimePrefix fallback
const videoItem = { filename: "movie.webm", url: "https://example.com/movie.webm", mime: "video/webm" };
assert.strictEqual(matchRoute(routes, videoItem).id, "4");

// urlRegex
const redditItem = { filename: "img.png".replace("png", "gif"), url: "https://old.reddit.com/r/x/comments/1", mime: "" };
// gif isn't in the extension list, so this should fall through to the regex rule
assert.strictEqual(matchRoute(routes, redditItem).id, "5");

// No match at all -> null, caller leaves the download alone
assert.strictEqual(matchRoute(routes, { filename: "readme.txt", url: "https://example.com/readme.txt" }), null);

// Folder template with no folder configured yields no override
const noFolderRoute = { id: "6", enabled: true, matchType: "extension", matchValue: "pdf", folder: "" };
assert.strictEqual(buildRoutedFilename(noFolderRoute, { filename: "doc.pdf" }), null);

// Path traversal / illegal chars in a hostile domain token get sanitized, not escaped
const traversalRoute = { id: "7", folder: "../../evil/{domain}" };
const traversalOut = buildRoutedFilename(traversalRoute, { filename: "x.jpg", url: "https://bad.com/x.jpg" });
assert.ok(!traversalOut.includes(".."), "must not contain .. segments: " + traversalOut);

console.log("tbcc-download-router: ok");
