TBCC extension icons (Chrome toolbar + gallery favicon)

Vector source: tbcc-mark.svg (flat stroke, no gradient — 16px-safe).

Two PNG sets (regenerate via scripts/build-icons.py):

  icons/                  — with #1e1e2e background (gallery favicon, manifest listing, favicon.ico)
  icons/transparent/      — no background (Chrome toolbar, notifications)

PNG sizes (both sets):
  icon16.png   — toolbar, notifications, context
  icon32.png   — gallery favicon (high-DPI tabs)
  icon48.png   — extension management + gallery favicon
  icon128.png  — Chrome Web Store listing (manifest required)
  icon256.png  — hi-DPI source; embedded in favicon.ico for Windows tray/shortcuts

  favicon.ico  — multi-size ICO (16–256) with background, for gallery.html + TBCC Supervisor tray

Regenerate:
  cd tbcc/extension
  python scripts/build-icons.py
  python scripts/build-icons.py --mark-bleed 0.94   # zoom mark slightly if needed

Manifest:
  action.default_icon → icons/transparent/
  icons (store)       → icons/ (with background)
