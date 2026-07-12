# Inbox

Drop candidate userscripts here before merging into a suite.

```text
inbox/
  fetlife/
  erome/
  cams/
  …
```

Intake checklist:

1. Note `@match`, `@grant`, license
2. keep / merge / drop / TBCC-port?
3. Implement as `packages/<suite>/features/<name>.js` with flag **default off**
4. Add to `manifest.json` → `npm run ci`
