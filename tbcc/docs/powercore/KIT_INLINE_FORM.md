# PowerCore Kit inline form (Early Access)

**Saved:** 2026-07-27  
**Kit account:** powercore.kit.com  
**Form name in Kit:** Copy of Clare form (Clare Inline template)  
**Use:** Primary email capture embed — highest-traffic insert form on the account.

## Embed snippet

Paste before `</body>` on any landing page (Cloudflare Pages, static HTML, etc.):

```html
<script async data-uid="074eace899" src="https://powercore.kit.com/074eace899/index.js"></script>
```

## Inline HTML (if Kit provides a container variant)

Some Kit setups need a mount element; if the script alone does not render, check **Kit → Landing pages & forms → Copy of Clare form → Embed** for the full block including any `<div>` wrapper.

## Where to use later

| Surface | Notes |
|---------|--------|
| `powercore.app/early-access` | Hero CTA below v0.1 spec |
| Static Forge landing (repo) | `docs/powercore/` or `tbcc/static/` when built |
| Kit post footer | Already on newsletter site via Kit native blocks |

## Related

- Published spec post: *PowerCore Early Access v0.1 — what's actually shipping*
- Server-side buyer capture: `backend/app/services/kit_buyer_capture.py` (Gumroad ping → Kit API; separate from this form)
- Env: `TBCC_KIT_CAPTURE_ENABLED`, `TBCC_KIT_API_SECRET` on revenue island

## Kit editor

Forms → **Copy of Clare form** → Embed / Save & Publish after copy changes.
