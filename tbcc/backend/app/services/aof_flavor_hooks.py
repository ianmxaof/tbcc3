"""
Shared lane-flavor hook bank — Phase 2 of the AOF flavor caption resupply.
See tbcc/docs/handoffs/2026-08-13_aof-flavor-caption-resupply_phase2_report.md.

Design: one shared bank of ~50 hook templates (gold delivery/pipeline/curated-dump voice)
colored per lane by substituting the lane's display name, rather than hand-writing 50+
bespoke hooks per lane (13 lanes x 50 = 650 lines). This is the "shared bank + lane-colored
openers" option named in the brief's architecture requirement B — each lane still ends up
with its own >=50 distinct caption strings (the {lane} substitution makes every string
unique per lane), it's the wording structure that's shared, not the output text.

None of these touch footers, affiliate links, bot usernames, or the FOOTER_MARKER block —
callers are responsible for appending a footer separately (see aof_growth_hub._select_promo_footer).
"""

from __future__ import annotations

LANE_FLAVOR_HOOK_TEMPLATES: tuple[str, ...] = (
    "💥 <b>NEW DELIVERY</b> 💥\n🚀 <b>PLANET EXPRESS</b> 🚀\n\n🟡 Another curated {lane} dump cleared the pipeline — no apology.",
    "📦 <b>{lane} DROP LANDED</b>\n\nPipeline cleared another batch. No apology, no delay.",
    "🚀 <b>{lane} — FRESH OFF THE CONVEYOR</b>\n\nRelay fired, dump landed. Gates below.",
    "🟡 <b>{lane} — CURATED DUMP</b>\n\nAnother batch cleared QA. We don't explain the process, we ship it.",
    "🔥 <b>{lane} — NO FILLER</b>\n\nOne curated deposit, zero apology. Unlock below.",
    "🌀 <b>{lane} RELAY FIRED</b>\n\nStorage → pool → your feed. Another batch just rode the conveyor.",
    "📬 <b>{lane} — SIGNED, SEALED, DELIVERED</b>\n\nAnother parcel skipped the queue.",
    "🧬 <b>{lane} — CURATED, NOT SCRAPED BLIND</b>\n\nSomeone actually checked this batch before it shipped.",
    "🔞 <b>{lane} — PORN FIRST, PARAGRAPHS NEVER</b>\n\nPreview → gate → folder. That's the ritual.",
    "🖤 <b>{lane} — ZERO FLUFF DROP</b>\n\nNo lore, no essay. Just the parcel below.",
    "💯 <b>{lane} — STRAIGHT TO THE POINT</b>\n\nYou know what this is.",
    "⚫ <b>{lane} — NO SOFT LAUNCH</b>\n\nThis batch didn't get a marketing rollout. It just landed.",
    "🌑 <b>{lane} — ANOTHER MIRROR SAVED</b>\n\nHosts die, links rot. This batch got caught before the purge.",
    "🕳 <b>{lane} — THE INTERNET FORGOT THIS ONE</b>\n\nDeleted elsewhere. Still here — for now.",
    "🎯 <b>{lane} — FILTRATION, NOT CRUELTY</b>\n\nThe gate keeps tourists out. That's the whole point.",
    "🔒 <b>{lane} — THIN WINDOW</b>\n\nRotation clears the feed soon. Grab this one before it rolls forward.",
    "💎 <b>{lane} — NOT EVERYONE GETS THIS</b>\n\nLV step filters the room. VIP skips the circus.",
    "⏱ <b>{lane} — ROTATION MOVES FAST</b>\n\nThis post won't own the feed forever.",
    "📸 <b>{lane} — CURATED AT SCALE</b>\n\nSized batch, real previews, dual gates.",
    "🗂 <b>{lane} — LIBRARY ENERGY</b>\n\nHand-selected files. Daily rotation.",
    "🌌 <b>{lane} — IMAGINE HAVING THIS LOCAL</b>\n\nNo hunting, no dead links. One ad step away.",
    "👆 <b>{lane} — AT YOUR FINGERTIPS</b>\n\nPreview above, full drop below the gate.",
    "📲 <b>{lane} — ONE TAP FROM THE STACK</b>\n\nSkip the sketchy mirrors. Tap through instead.",
    "💾 <b>{lane} — YOUR DRIVE, YOUR RULES</b>\n\nImagine it sitting local while everyone else chases dead hosts.",
    "☕ <b>{lane} — CHEAPER THAN WASTING YOUR NIGHT</b>\n\nOne ad step vs. hours on dead hosts.",
    "🎬 <b>{lane} — LESS THAN ANOTHER EMPTY SCROLL</b>\n\nUnlock once, own the drop.",
    "🚀 <b>{lane} — NETWORK'S GROWING</b>\n\nStack's expanding, this lane's feeding harder.",
    "📈 <b>{lane} — FRESH DEPOSIT WINDOW</b>\n\nPipeline's hot. Don't sleep on this rotation.",
    "🌱 <b>{lane} — EARLY STACK ENERGY</b>\n\nMore lanes coming online. This drop lands while the room's still climbable.",
    "🔓 <b>{lane} — ACCESS BEFORE THE PUSH</b>\n\nDropping this early — get in before the hype cycle.",
    "🌟 <b>{lane} — EARLY ROOM ENERGY</b>\n\nThe ones here now will understand later.",
    "👌 <b>{lane} — ONE LANE, FULL STACK</b>\n\nThis drop's one lane. The rest waits in the footer.",
    "🗄 <b>{lane} — MORE THAN A CHAT</b>\n\nTagged deposits, not flood spam. Browse below.",
    "💀 <b>{lane} — YOU WEREN'T INVITED</b>\n\nYou clicked anyway. Gate's below.",
    "🖕 <b>{lane} — NO CORPORATE BIRD SPEAK</b>\n\nDense drop, real gates. Wrong lane if you want an essay.",
    "⚡ <b>{lane} — DEGENERATE-FRIENDLY DROP</b>\n\nSelf-aware filth, no PR department.",
    "🧾 <b>{lane} — RECEIPT BELOW</b>\n\nThe links are the proof of work.",
    "🗃 <b>{lane} — LOGGED AND SHIPPED</b>\n\nEvery parcel gets logged before it drops.",
    "🛎 <b>{lane} — OPERATOR CLEARED IT</b>\n\nSomeone signed off on this batch before it hit the feed.",
    "🏷 <b>{lane} — TAGGED AND SHIPPED</b>\n\nThis batch didn't skip QA.",
    "🐘 <b>{lane} — THIS ONE'S HEAVY</b>\n\nMega batch, not a teaser folder.",
    "🧱 <b>{lane} — STACKED DEPOSIT</b>\n\nThis isn't a light drop.",
    "🏋 <b>{lane} — HEAVYWEIGHT DUMP</b>\n\nBigger than the usual rotation.",
    "✅ <b>{lane} — GATE'S QUICK</b>\n\n30 seconds and the folder's yours.",
    "🧭 <b>{lane} — KNOW THE ROUTE</b>\n\nOne gate, one folder. You've done this before.",
    "🔑 <b>{lane} — KEY'S RIGHT THERE</b>\n\nThe gate is the only lock.",
    "🚪 <b>{lane} — ONE DOOR</b>\n\nNo maze, no tricks.",
    "😈 <b>{lane} — EDGE LANE ENERGY</b>\n\nThis batch isn't for the faint.",
    "🩻 <b>{lane} — NOT FOR EVERYONE</b>\n\nIf you're reading this, you're the target audience.",
    "🕰 <b>{lane} — TIMESTAMP THIS ONE</b>\n\nAnother delivery cleared right now.",
    "📅 <b>{lane} — TODAY'S DELIVERY</b>\n\nEvery day a new batch clears the pipeline.",
    "🔂 <b>{lane} — ROTATION, NOT REPEAT</b>\n\nEach delivery is a new parcel.",
)

MIN_LANE_FLAVOR_HOOKS = 50


def lane_flavor_hooks(network_key: str) -> list[str]:
    """
    Every LANE_FLAVOR_HOOK_TEMPLATES entry, colored with this lane's display name.
    >=50 distinct hook bodies per lane (currently 52) — callers append a footer
    separately, one footer per hook (see aof_growth_hub._append_lane_flavor_variations),
    never one hook cloned across every footer.
    """
    from app.data.aof_network import network_channel_by_key

    ch = network_channel_by_key(network_key)
    lane = (ch.display_name if ch else network_key.replace("_", " ").upper()).strip()
    return [t.format(lane=lane) for t in LANE_FLAVOR_HOOK_TEMPLATES]


# Distinct from aof_main_group_copy.vip_promo_minimal_bodies() (Gumroad-embed-specific,
# expanded in Phase 1) — this is a separate, larger general-purpose VIP hook bank for
# lane rotation, not tied to the bare-URL Telegram preview-card mechanic.
VIP_FLAVOR_HOOKS: tuple[str, ...] = (
    "⚡ <b>VIP = zero ad steps</b> — every gate skipped, every lane unwrapped. @aofsubscriptions_bot /subscribe",
    "🎟 <b>One sub, every lane</b> — VIP isn't per-channel, it's the whole stack. Pay ⭐ below.",
    "🚪 <b>Public waits at the gate. VIP walks in.</b> Tap Pay ⭐ · @aofsubscriptions_bot",
    "🧊 <b>Cold open, no ads</b> — VIP drops land unwrapped, same minute they're posted. @aofsubscriptions_bot",
    "🏎 <b>VIP moves first</b> — early drops, bigger albums, zero LV steps. /subscribe",
    "🎁 <b>Direct files, not detours</b> — VIP swaps every gate for a straight link. Pay ⭐ below.",
    "🛎 <b>Ring once, skip the line</b> — VIP checkout is one tap, not three ad pages. @aofsubscriptions_bot",
    "🧨 <b>Public gets filtered. VIP gets everything.</b> Tap Pay ⭐ below.",
    "🪙 <b>Stars buy silence from the ad wall</b> — VIP, no gate, ever. /subscribe",
    "🌊 <b>VIP rolls deeper</b> — bigger albums, no wait, no wrap. @aofsubscriptions_bot",
    "🔮 <b>See it before the public does</b> — VIP early drop window, same lane. Pay ⭐ below.",
    "🗝 <b>One key, every door</b> — VIP unlocks the whole network, not one channel. /subscribe",
    "🎯 <b>Direct hosts, no LV, no AdMaven</b> — that's the entire VIP pitch. @aofsubscriptions_bot",
    "🧿 <b>Skip the ritual</b> — VIP doesn't do Complete Actions → Get Link. Just the file.",
    "💰 <b>Pay once, stop clicking gates forever</b> — @aofsubscriptions_bot /subscribe",
    "🏁 <b>VIP finishes first</b> — early rolls, unwrapped hosts, zero filler. Pay ⭐ below.",
)


def vip_flavor_hooks() -> list[str]:
    """>=15 distinct VIP hook bodies, all used (never sliced to [:1])."""
    return list(VIP_FLAVOR_HOOKS)


# Additional gate/FOMO bodies layered on top of aof_gate_promo_copy.gate_fomo_post_bodies()
# (5 bodies, already fully used per Phase 1) to reach >=15 total.
GATE_FLAVOR_HOOKS_EXTRA: tuple[str, ...] = (
    "🔗 <b>Gate ritual, part two</b>\nSame 3 taps every time — Complete Actions, Get Link, done.",
    "📎 <b>Ad wall isn't a wall</b>\nOne short step separates you from the folder. Tap through.",
    "🧠 <b>Muscle memory by now</b>\nYou've done this gate a hundred times. One more won't kill you.",
    "⏱ <b>30 seconds, not 30 minutes</b>\nThe gate is faster than the debate about the gate.",
    "🔓 <b>Complete Actions isn't optional</b>\nSkip a step and the link loops. Finish it, get the file.",
    "🧩 <b>One piece, one gate</b>\nComplete the step, the folder appears. No trick, no maze.",
    "🎫 <b>Ad step = toll booth</b>\nPay with 30 seconds instead of Stars, or skip both and subscribe.",
    "📡 <b>Gate's just a checkpoint</b>\nComplete Actions, Get Link, move on with your life.",
    "🔁 <b>Loop got you? Wait 5s.</b>\nSome gates need a second pass. Don't rage-quit the folder.",
    "🧭 <b>New here? Read this once.</b>\nTap link → Complete Actions → Get Link. Bookmark the flow.",
)


def gate_flavor_hooks() -> list[str]:
    """>=15 distinct gate/FOMO hook bodies, all used (never sliced to [:1])."""
    from app.services.aof_gate_promo_copy import gate_fomo_post_bodies

    return list(gate_fomo_post_bodies()) + list(GATE_FLAVOR_HOOKS_EXTRA)
