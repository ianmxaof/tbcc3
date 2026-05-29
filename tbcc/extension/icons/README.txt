TBCC extension icons (Chrome toolbar + gallery favicon)

Generated from docs/tbcc-icon-master.png (lightning + hexagon mark).

PNG sizes:
  icon16.png   — toolbar, notifications, context (manifest required)
  icon32.png   — gallery favicon (high-DPI tabs)
  icon48.png   — extension management + gallery favicon
  icon128.png  — Chrome Web Store listing (manifest required)

  favicon.ico  — multi-size ICO (16, 32, 48) for gallery.html <link rel="icon">

Regenerate after art changes:
  cd tbcc/extension
  python scripts/build-icons.py path/to/master.png

Manifest references: icon16, icon48, icon128 (see manifest.json).
