# AOF CTA retarget draft — forum-as-library twin (Week-1, DRAFT ONLY)

**Status: draft.** No live Linkvertise dashboard edits, no invite changes, no checkout keyboard changes happen from this document. It exists so the eventual flip (once the twin exists and hard-cutover is separately ACK'd) is a paste job, not a design session.

Against operator ACK 2026-08-22: forum-as-library · twin (not in-place paywall) · CTA retarget = draft now / live later. Full directive: `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md`. Current live destinations of record: `tbcc/docs/GATE_LINK_AUDIT.md`.

## Retarget matrix

| CTA surface | Current live destination | Week-1 change | Future (post hard-cutover, separate ACK) |
| ----------- | ------------------------- | -------------- | ------------------------------------------ |
| `@aofmainhub` pinned 3-button CTA | Stars + Crypto + Gumroad checkout (mainhub) | **None.** Top-of-funnel keeps pointing at existing checkout. | Add/replace one button with twin library CTA once twin membership flow exists. |
| Loot Room bulletin / links hub | `https://telegram.me/+97f4Crv3G1RkMGU5` (free join) | **None.** Loot Room stays the free hangout invite. | Unchanged — Loot Room is never the paywall under this doctrine; twin is separate. |
| LV gate `loot` | wk-campaign beacon → loot bot `?start=src_lv_loot_wkNN`, default room `+97f4…` | **None.** Still resolves to free Loot Room / loot bot. | Could add a second gate variant pointing at twin invite once membership sale exists — not this track. |
| LV gate `main` / `main_group` | `https://telegram.me/aof_lootgod_bot` | **None.** | Unchanged — Loot God bot stays the taste/sampler funnel entry. |
| Loot God bot (`@aof_lootgod_bot`) 24h key | Rolls-only cadence, no forum seat | **None to the key mechanic.** Doctrine note added (see `AOF_PLACEMENT_DOCTRINE.md` → Library access rules) making explicit: key ≠ seat. | If a paid key tier is ever designed to grant twin seat, that's a new SKU decision — out of scope here and not ACK'd. |
| Lane LV gates (ai, ass, blowjob, big_tits, taboo, voyeur, milf, abg, goon, bop, packs) | Each → that lane's free channel invite | **None.** Free lanes stay free party boards (CADENCE track cadence, unchanged). | Not part of the library product — these remain top-of-funnel/free regardless of twin cutover. |
| AOF VIP native Stars sub | `createChatSubscriptionInviteLink`, 30-day, channel-only | **None.** VIP is deferred game/vault, not ACK'd as product this track. | If/when vault inventory is named, VIP's relationship to the twin (same product? separate?) needs its own ACK — not decided here. |
| **AOF Library (twin)** | *(does not exist yet)* | **New surface.** Operator creates the private forum; Week-1 wires one AI topic + remixer feed. No public CTA points at it yet — invite is handed manually to grandfathered VIP members only, per dry-run in Phase 3. | Once hard-cutover is ACK'd: a real CTA (mainhub button and/or Loot Room pin) can point here. That edit is explicitly out of scope until that ACK lands. |

## What this draft deliberately does NOT do

- Does not touch any Linkvertise dashboard destination field.
- Does not change `MAIN_GROUP_INVITE`, `ADDLIST_RAW`, or any `aof_network.py` invite constant.
- Does not add a twin row to `BULLETIN_CHANNEL_INVITES` — the twin isn't registered yet (blocked on operator pasting `chat_id`, Phase 1).
- Does not decide VIP/vault's long-term relationship to the twin.

## Trigger for "go live"

This matrix only becomes executable once **all** of the following are true, each requiring its own explicit operator ACK:
1. Twin forum exists and is registered (Phase 1).
2. Hard-cutover is ACK'd as a separate directive (paywalling Loot Room, killing the public invite, addlist surgery — all explicitly out of scope for `loot-forum-twin-week1`).
3. Grandfather auto-seat has actually executed (not just dry-run counted).

Until then, treat every "Future" cell above as a placeholder, not a plan of record.
