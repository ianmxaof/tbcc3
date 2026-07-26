# AOF Gate Link Audit — telegram.me migration (2026-07-13)

Telegram linking shifted; **all** Linkvertise / AdMaven / Work.ink posts must destination to `telegram.me/…` (or `https://telegram.me/…`), not obsolete `t.me/+…` invites where rotated.

## Canonical clearnet destinations

| Role | URL (use exactly) |
|------|-------------------|
| Bulletin / affiliate hub | `https://telegram.me/aofmainhub` |
| Loot God bot (only bot CTA) | `https://telegram.me/aof_lootgod_bot` |
| Loot Room group | `https://telegram.me/+97f4Crv3G1RkMGU5` |

Watermark burn-in default: `telegram.me/aofmainhub` (`TBCC_WATERMARK_TEXT`).  
Optional secondary: `telegram.me/aof_lootgod_bot`.  
Loot-room clips: `telegram.me/+97f4Crv3G1RkMGU5`.

## Manual Linkvertise posts (retarget destination in LV dashboard)

Slug stays; **change the Telegram target** behind each:

| Key | Gate URL | Must destination to |
|-----|----------|---------------------|
| mainhub | https://link-center.net/1367336/DgIo85a7oux0 | https://telegram.me/aofmainhub |
| main / main_group | https://link-center.net/1367336/eURa9KVdlIR2 | https://telegram.me/aof_lootgod_bot |
| loot | https://direct-link.net/1367336/S4isAVBXklrz | https://telegram.me/+97f4Crv3G1RkMGU5 |
| ai | https://direct-link.net/1367336/ZrNHOhHaxSYM | *(lane invite — update to current telegram.me invite)* |
| ass | https://link-hub.net/1367336/6PIRZVafUcTa | *(lane invite)* |
| blowjob | https://link-target.net/1367336/QBzt1dFPTqai | *(lane invite)* |
| big_tits | https://direct-link.net/1367336/j3kYBP7ehwvi | *(lane invite)* |
| taboo | https://link-center.net/1367336/XNRjZbn41Sg8 | *(lane invite)* |
| voyeur | https://direct-link.net/1367336/N8IObaZoZEqE | *(lane invite)* |
| milf | https://link-target.net/1367336/0zFTaQqUG3S3 | *(lane invite)* |
| abg | https://link-hub.net/1367336/cnly0eLYXB9P | *(lane invite)* |
| goon | https://link-hub.net/1367336/HAOxJYVt7iD4 | *(lane invite)* |
| bop | https://link-center.net/1367336/vaTKeNRpy3tV | *(lane invite)* |
| packs | https://direct-link.net/1367336/ARbG9LkABgVV | *(lane invite)* |
| addlist | https://link-target.net/1367336/OXrWginA5Ztr | *(current addlist — prefer telegram.me/addlist/… if TG shows that form)* |

**Verified broken earlier:** loot gate `S4isAVBXklrz` still landed on old `t.me/+NWathiLSqZ1lMzlh` — retarget to `+97f4Crv3G1RkMGU5` ASAP.

## AdMaven + Work.ink

Dynamic wrappers (`TBCC_ADMAVEN_*`, `TBCC_WORKINK_BASE_LINK`) take the **destination from TBCC at wrap time**. After this migration:

1. Confirm code/env wrap targets use `telegram.me` (see `aof_telegram_links.py`).
2. Re-wrap any stored pack / loot / promo rows that still embed old `t.me/+…` destinations.
3. Smoke-test one AdMaven + one Work.ink wrapper: finish ads → lands on telegram.me URL.

Env tips:

- `TBCC_AOF_GATE_URL` — keep LV slug; destination of that slug → lootgod or mainhub per campaign.
- `TBCC_WORKINK_BASE_LINK` — template link; override destination on each wrap.
- Do **not** leave bare obsolete group invites inside pixeldrain / paste layers.

## Watermark / filenames (repo)

| Surface | New default |
|---------|-------------|
| `TBCC_WATERMARK_TEXT` | `telegram.me/aofmainhub` |
| Explorer / local watermark fallback | same |
| Zip brand (`tbcc-zip-naming.js`) | `telegram.me_aofmainhub` |
| Mega pack brand handle | `telegram.me/aofmainhub` |

## Operator checkbox

- [ ] LV loot → `+97f4…`
- [ ] LV mainhub → `telegram.me/aofmainhub`
- [ ] LV main_group → `telegram.me/aof_lootgod_bot`
- [ ] Each lane LV → current invite (telegram.me form)
- [ ] AdMaven/Workink smoke wrap
- [ ] New watermarked exports use `telegram.me/aofmainhub`
- [ ] Public CTA copy uses lootgod bare bot URL only
