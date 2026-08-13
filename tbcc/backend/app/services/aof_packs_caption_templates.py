"""Caption strategy shells for AOF PACKS — swipe-inspired intros + untouched {{PACK_BODY}}."""

from __future__ import annotations

# Replaced at send time with pack-specific body (name, size, gates, footer links).
PACK_BODY_PLACEHOLDER = "{{PACK_BODY}}"

# Persuasion lanes mined from telegram_native_ads swipe file + AOF voice.
# Each strategy cycles independently; hooks are header + intro only — gates/footer live in PACK_BODY.
PACK_STRATEGIES: tuple[dict[str, object], ...] = (
    {
        "id": "differentiation",
        "tactic": "not_a_regular_channel",
        "hooks": (
            "🔥 <b>THIS IS NOT A REGULAR REPOST CHANNEL</b>\n\n"
            "TBCC scraped it. QA cleared it. You're not getting tourist spam — you're getting a curated mega parcel.",
            "🚫 <b>NOT YOUR TYPICAL TELEGRAM DUMP</b>\n\n"
            "No watermark farms. No recycled folders. One hand-picked batch — gated, tagged, dropped.",
            "⚠️ <b>SKIP THE REPOST FEEDS</b>\n\n"
            "This lane isn't another copy-paste channel. Original deposit. One unlock. Zero filler.",
            "🧹 <b>ZERO FLOOD ENERGY</b>\n\n"
            "Curated lane. Tagged deposit. The feed you mute elsewhere doesn't live here.",
        ),
    },
    {
        "id": "curator_builder",
        "tactic": "first_person_builder",
        "hooks": (
            "📚 <b>BUILT, NOT BORROWED</b>\n\n"
            "Months in the pipeline — scraped, sorted, wrapped. Not reposted. Not stolen. Curated.",
            "🛠 <b>PIPELINE DROP</b>\n\n"
            "Storage → pool → your feed. TBCC did the labor so you don't scroll through garbage.",
            "✨ <b>HAND-PICKED BATCH</b>\n\n"
            "Every file cleared QA before it hit PACKS. Creating a library, not flooding a chat.",
            "🏗 <b>CREATED, NOT COPIED</b>\n\n"
            "Years of pipeline work distilled into one parcel. The links below are the receipt.",
        ),
    },
    {
        "id": "extinction",
        "tactic": "loss_framing",
        "hooks": (
            "💀 <b>MOST OF IT IS GONE NOW</b>\n\n"
            "Deleted. DMCA'd. Blocked. This batch still exists — for now — behind the gate below.",
            "🕳 <b>THE INTERNET FORGOT THIS ONE</b>\n\n"
            "Hosts die. Links rot. TBCC preserved this parcel before it vanished like the rest.",
            "⏳ <b>LAST MIRROR ENERGY</b>\n\n"
            "What you hunted for on dead forums? Consolidated here before the next takedown wave.",
            "🪦 <b>DEAD LINKS EVERYWHERE ELSE</b>\n\n"
            "This folder is the exception — archived while the rest of the mirrors flatlined.",
            "🌑 <b>EXTINCTION EVENT FOR HOSTS</b>\n\n"
            "Another mirror just died. This parcel didn't — unlock while the gate still answers.",
        ),
    },
    {
        "id": "scarcity",
        "tactic": "filtration_scarcity",
        "hooks": (
            "🎯 <b>SCARCITY ISN'T CRUELTY — IT'S FILTRATION</b>\n\n"
            "The gate isn't punishment. It's how the folder stays alive while tourists bounce.",
            "🔒 <b>THIN WINDOW</b>\n\n"
            "Another rotation clears the feed soon. Grab this parcel or watch the slot roll forward.",
            "💎 <b>NOT EVERYONE GETS THIS DROP</b>\n\n"
            "LV step filters the room. VIP skips the circus. You already know which side you're on.",
            "⏱ <b>ROTATION MOVES FAST</b>\n\n"
            "PACKS doesn't wait. Next drop pushes this one down — unlock while it's still pinned.",
            "🔥 <b>LIMITED FEED SLOT</b>\n\n"
            "This post won't own the channel forever. Scarcity is the feed — move.",
        ),
    },
    {
        "id": "scale_proof",
        "tactic": "emoji_bullet_inventory",
        "hooks": (
            "📦 <b>MEGA PARCEL — NUMBERS BELOW</b>\n\n"
            "10,000+ monthly actives on the bot trust this lane. Size, contents, and gates — all in-thread.",
            "📸 <b>CURATED AT SCALE</b>\n\n"
            "Not a random zip — a sized batch with previews, dual gates, and a real folder behind the ad step.",
            "🗂 <b>LIBRARY ENERGY</b>\n\n"
            "Hand-selected files. Daily lane rotation. The inventory lines are under the fold — scroll.",
            "📊 <b>SIZE + CONTENTS IN-THREAD</b>\n\n"
            "No guessing. GB count, model list, dual gates — everything you need before you unlock.",
        ),
    },
    {
        "id": "imagine_possession",
        "tactic": "imagine_having_framing",
        "hooks": (
            "🌌 <b>IMAGINE HAVING THIS FOLDER LOCAL</b>\n\n"
            "No hunting. No dead links. One ad step between you and the full mega batch.",
            "👆 <b>AT YOUR FINGERTIPS</b>\n\n"
            "Preview grid above. Full parcel below the gates. Possession fantasy — meet friction reality.",
            "📲 <b>ONE TAP FROM THE STACK</b>\n\n"
            "Imagine skipping three sketchy mirrors. You didn't — you clicked PACKS instead. Good.",
            "💾 <b>YOUR DRIVE, YOUR RULES</b>\n\n"
            "Imagine the folder sitting local while everyone else chases dead mirrors. Gates below.",
        ),
    },
    {
        "id": "value_anchor",
        "tactic": "price_comparison_anchor",
        "hooks": (
            "☕ <b>CHEAPER THAN WASTING YOUR NIGHT</b>\n\n"
            "One ad step vs. three hours on dead hosts. Time is the real subscription — spend it smarter.",
            "🎬 <b>LESS THAN ANOTHER EMPTY SCROLL SESSION</b>\n\n"
            "You'd burn an evening hunting mirrors. Or unlock once and own the folder.",
            "💸 <b>ONE GATE · ONE FOLDER</b>\n\n"
            "Not twelve separate subs. Not a Netflix of disappointment. One parcel. One unlock.",
            "🍿 <b>LESS THAN TWO MONTHS OF STREAMING</b>\n\n"
            "You'd pay more to watch nothing. This parcel actually delivers — one gate below.",
        ),
    },
    {
        "id": "growing_window",
        "tactic": "growing_channel_promo_window",
        "hooks": (
            "🚀 <b>NETWORK'S GROWING — GOOD TIME TO LOCK IN</b>\n\n"
            "PACKS lane is feeding harder while the stack expands. Don't sleep on this rotation.",
            "📈 <b>FRESH DEPOSIT WINDOW</b>\n\n"
            "Pipeline's hot this week. Promo energy won't stay this loose forever — grab the drop.",
            "🌱 <b>EARLY STACK ENERGY</b>\n\n"
            "More lanes coming online. This parcel drops while the room is still climbable.",
            "🎟 <b>GROWTH PROMO WINDOW</b>\n\n"
            "Stack's expanding — entry's easier right now. I don't know how long that lasts.",
        ),
    },
    {
        "id": "early_access",
        "tactic": "pre_launch_early_access",
        "hooks": (
            "🔓 <b>STACK ACCESS BEFORE THE PUBLIC PUSH</b>\n\n"
            "Dropping the links here early — get in before the hype cycle starts.",
            "🌟 <b>EARLY ROOM ENERGY</b>\n\n"
            "The ones joining now will understand later. Parcel below — full stack in the footer.",
        ),
    },
    {
        "id": "addlist_punch",
        "tactic": "addlist_one_click_punch",
        "hooks": (
            "👌 <b>ALL LANES. ONE TAP.</b>\n\n"
            "One pack today — full AOF stack waiting in the footer. Tourists scroll; you tap through.",
            "😳 <b>ONE CLICK — FULL NETWORK</b>\n\n"
            "This drop is one lane. The full stack link unlocks the rest. Links unchanged below.",
        ),
    },
    {
        "id": "nostalgia_lane",
        "tactic": "nostalgia_hook",
        "hooks": (
            "🎶 <b>REMEMBER WHEN HOSTS DIDN'T COLLAPSE OVERNIGHT?</b>\n\n"
            "That era's gone. This batch is what survived — archived before the next purge.",
            "📼 <b>OLD INTERNET, NEW DROP</b>\n\n"
            "The vibe you miss. The files you lost. TBCC caught this one before the link died.",
        ),
    },
    {
        "id": "repository",
        "tactic": "repository_not_chat",
        "hooks": (
            "🗄 <b>MORE THAN ANOTHER CHAT</b>\n\n"
            "PACKS is a repository lane — tagged deposits, not flood spam. Browse the parcel below.",
            "📚 <b>TRUE LIBRARY LANE</b>\n\n"
            "Not a live chat. A curated stack you unlock once and keep. Details under the fold.",
        ),
    },
    {
        "id": "invited_not",
        "tactic": "aof_core_edge",
        "hooks": (
            "💀 <b>YOU WEREN'T INVITED</b>\n\n"
            "You clicked anyway. Gate's below. Tourists bounce — you're still here.",
            "🔞 <b>PORN FIRST, PARAGRAPHS NEVER</b>\n\n"
            "Skip the essay. Preview grid → gates → folder. That's the ritual.",
            "🖕 <b>NO CORPORATE BIRD SPEAK</b>\n\n"
            "Dense drop. Real gates. If you need a landing page essay, wrong lane.",
            "⚡ <b>DEGENERATE-FRIENDLY DROP</b>\n\n"
            "Self-aware filth. No PR department. Parcel and gates unchanged below.",
        ),
    },
    {
        "id": "vip_contrast",
        "tactic": "tiered_subscription_table",
        "hooks": (
            "⭐ <b>PUBLIC GETS THE GATE</b>\n\n"
            "VIP skips ads, bigger drops, daily /viproll. This parcel is wrapped for the room — unwrapped upstairs.",
            "🗝 <b>ONE AD STEP OR ZERO</b>\n\n"
            "Finish LV below — or @aofsubscriptions_bot /subscribe and stop doing ad calisthenics.",
            "👑 <b>VIP SKIPS THE CIRCUS</b>\n\n"
            "Public lane: wrapped gates. VIP: unwrapped hosts + weekly mega. Pick your suffering level.",
            "🎫 <b>STARS OR ADS — YOUR CALL</b>\n\n"
            "Pay the gate below or pay @aofsubscriptions_bot and walk past the line.",
        ),
    },
    # --- Phase 2 expansion (2026-08-13) — gold "Planet Express" delivery voice + 9 more
    # lanes, added to push unique PACKS hooks from 50 to 100+. Planet Express is ONE
    # strategy among many (delivery_pipeline) — not the opener on every hook, per voice
    # rules ("motif, not every line").
    {
        "id": "delivery_pipeline",
        "tactic": "planet_express_delivery",
        "hooks": (
            "💥 <b>NEW DELIVERY</b> 💥\n🚀 <b>PLANET EXPRESS</b> 🚀\n\n"
            "🟡 Another curated dump cleared the pipeline — no apology.",
            "📦 <b>DELIVERY CLEARED CUSTOMS</b>\n\n"
            "🚀 Planet Express doesn't do delays. Parcel's through — gates below.",
            "🛰 <b>INCOMING PARCEL</b>\n\n"
            "🚀 Relay fired, dump landed. No apology tour — just the folder.",
            "🟡 <b>PIPELINE CLEARED — AGAIN</b>\n\n"
            "🚀 Planet Express energy: it ships, it lands, no excuses.",
            "📬 <b>SIGNED, SEALED, DELIVERED</b>\n\n"
            "🚀 Another parcel skipped the queue. Unlock below.",
            "🚚 <b>FRESH OFF THE CONVEYOR</b>\n\n"
            "🟡 Curated dump landed clean — the pipeline doesn't stop for apologies.",
        ),
    },
    {
        "id": "no_apology_dump",
        "tactic": "no_apology_energy",
        "hooks": (
            "🟡 <b>NO APOLOGY DROP</b>\n\n"
            "Another batch cleared QA. We don't explain the process — we just ship it.",
            "😤 <b>ZERO EXCUSES ENERGY</b>\n\n"
            "This parcel isn't sorry for existing. Unlock and move on.",
            "🔥 <b>SHIPPED, NOT SORRY</b>\n\n"
            "Curated dump landed clean. No disclaimers, no softening — just the folder.",
            "💢 <b>UNAPOLOGETIC DROP</b>\n\n"
            "Some lanes hedge. This one doesn't. Gates below, folder waiting.",
            "🗯 <b>NO DISCLAIMER NEEDED</b>\n\n"
            "Another dump cleared the pipeline. We don't caption-apologize here.",
        ),
    },
    {
        "id": "relay_fired",
        "tactic": "conveyor_relay_energy",
        "hooks": (
            "🌀 <b>RELAY FIRED</b>\n\n"
            "Storage → pool → your feed. Another batch just rode the conveyor.",
            "⚙️ <b>CONVEYOR NEVER STOPS</b>\n\n"
            "Another parcel rolled off the belt. Gates below, folder waiting.",
            "🔌 <b>SIGNAL RELAYED</b>\n\n"
            "Another batch jumped the pipeline. Blink and you missed the last one.",
            "🛞 <b>BELT KEEPS MOVING</b>\n\n"
            "This is what falls off when the conveyor's this fast. Grab it.",
            "📡 <b>TRANSMISSION LANDED</b>\n\n"
            "Another relay cleared. No ceremony — just the drop.",
        ),
    },
    {
        "id": "porn_first_blunt",
        "tactic": "no_preamble_bluntness",
        "hooks": (
            "🔞 <b>NO FOREPLAY IN THE CAPTION</b>\n\n"
            "Preview → gate → folder. That's the whole pitch.",
            "🖤 <b>ZERO FLUFF DROP</b>\n\n"
            "No lore, no essay, no soft launch. Just the parcel below.",
            "💯 <b>STRAIGHT TO THE POINT</b>\n\n"
            "You know what this is. Gates below, folder after.",
            "🩸 <b>RAW DROP, NO PREAMBLE</b>\n\n"
            "Skip the intro. The folder's the pitch.",
            "⚫ <b>NO SOFT LAUNCH</b>\n\n"
            "This parcel didn't get a marketing rollout. It just landed. Unlock below.",
        ),
    },
    {
        "id": "curated_not_scraped",
        "tactic": "qa_before_ship",
        "hooks": (
            "🧬 <b>CURATED, NOT SCRAPED BLIND</b>\n\n"
            "Someone actually looked at this batch before it shipped. Rare, we know.",
            "🎛 <b>QA'D BEFORE IT HIT YOU</b>\n\n"
            "No blind scrape dump — every file passed a human check first.",
            "🧪 <b>TESTED PARCEL</b>\n\n"
            "Curated means someone opened every file first. This one passed.",
            "🔬 <b>NOT A RANDOM SCRAPE</b>\n\n"
            "Hand-checked batch, not a folder someone found and reposted. Gates below.",
            "🧵 <b>STITCHED TOGETHER ON PURPOSE</b>\n\n"
            "This parcel didn't assemble itself. Curated, checked, shipped.",
        ),
    },
    {
        "id": "feed_moves_fast",
        "tactic": "rotation_pressure",
        "hooks": (
            "⏰ <b>DROP WINDOW IS NOW</b>\n\n"
            "The feed moves. This parcel's on top today — buried tomorrow.",
            "🕰 <b>TIMESTAMP THIS ONE</b>\n\n"
            "Another delivery cleared right now. Rotation doesn't pause for you.",
            "⌛ <b>FEED MOVES FAST</b>\n\n"
            "This post won't stay pinned. Grab the parcel while it's on top.",
            "📅 <b>TODAY'S DELIVERY</b>\n\n"
            "Every day a new batch clears the pipeline. This is today's.",
            "🔂 <b>ROTATION, NOT REPEAT</b>\n\n"
            "Each delivery is a new parcel — this one's up now.",
        ),
    },
    {
        "id": "operator_receipt",
        "tactic": "pipeline_receipt_framing",
        "hooks": (
            "🧾 <b>RECEIPT BELOW</b>\n\n"
            "The links are the proof of work. Pipeline delivered — nothing else to say.",
            "🗃 <b>LOGGED AND SHIPPED</b>\n\n"
            "Every parcel gets logged before it drops. This one's logged. Unlock it.",
            "🛎 <b>OPERATOR CLEARED IT</b>\n\n"
            "Someone signed off on this batch before it hit the feed. Gates below.",
            "📋 <b>MANIFEST ATTACHED</b>\n\n"
            "Size, gates, folder — all accounted for. Pipeline receipt below.",
            "🏷 <b>TAGGED AND SHIPPED</b>\n\n"
            "This parcel didn't skip QA. Tagged, cleared, delivered.",
        ),
    },
    {
        "id": "goon_edge_blunt",
        "tactic": "edge_lane_confidence",
        "hooks": (
            "🌀 <b>YOU KNOW WHY YOU'RE HERE</b>\n\n"
            "No further explanation needed. Gates below.",
            "😈 <b>EDGE LANE ENERGY</b>\n\n"
            "This batch isn't for the faint. Unlock if you already know.",
            "🩻 <b>NOT FOR EVERYONE</b>\n\n"
            "If you're reading this, you're already the target audience. Folder below.",
            "🔩 <b>BUILT FOR THE REGULARS</b>\n\n"
            "This parcel isn't a tourist trap. You know the drill — gates below.",
            "🕳 <b>DEEP LANE DROP</b>\n\n"
            "Some parcels stay surface-level. This one doesn't. Unlock below.",
        ),
    },
    {
        "id": "mega_batch_flex",
        "tactic": "size_flex",
        "hooks": (
            "🐘 <b>THIS ONE'S HEAVY</b>\n\n"
            "Mega batch, not a teaser folder. Size in-thread — gates below.",
            "🧱 <b>STACKED PARCEL</b>\n\n"
            "This isn't a light drop. Full mega batch, gates below.",
            "🏋 <b>HEAVYWEIGHT DUMP</b>\n\n"
            "Bigger than the usual rotation. Details under the fold.",
            "📐 <b>SIZED FOR SERIOUS UNLOCKS</b>\n\n"
            "This parcel earns the mega label. Gates below.",
            "🗻 <b>MOUNTAIN OF CONTENT</b>\n\n"
            "Not a snack-size drop. Full stack — unlock below.",
        ),
    },
    {
        "id": "gate_confidence",
        "tactic": "gate_ritual_confidence",
        "hooks": (
            "✅ <b>GATE'S QUICK, TRUST THE PROCESS</b>\n\n"
            "30 seconds and the folder's yours. Tap below.",
            "🧭 <b>KNOW THE ROUTE</b>\n\n"
            "One gate, one folder. You've done this before — repeat it.",
            "🎯 <b>ONE STEP, FULL PARCEL</b>\n\n"
            "Complete Actions → Get Link → done. Gate below.",
            "🔑 <b>KEY'S RIGHT THERE</b>\n\n"
            "The gate is the only lock. Turn it and the folder opens.",
            "🚪 <b>ONE DOOR, ONE PARCEL</b>\n\n"
            "No maze, no tricks. One gate stands between you and the folder.",
        ),
    },
)


def list_pack_strategy_ids() -> list[str]:
    return [str(s["id"]) for s in PACK_STRATEGIES]


def pack_strategy_for_index(index: int) -> dict[str, object]:
    strategies = list(PACK_STRATEGIES)
    if not strategies:
        raise ValueError("no pack strategies configured")
    return strategies[index % len(strategies)]


# Floor this module is expected to stay above (DONE WHEN: PACKS template set >=100 unique
# hooks). Not an artificial ceiling — pack_caption_template_variations() returns every
# distinct hook across PACK_STRATEGIES, currently 101.
MIN_PACK_TEMPLATES = 100


def pack_caption_template_variations() -> list[str]:
    """
    Strategy shells for content_variations rotation — every distinct hook across
    PACK_STRATEGIES (currently 101, see MIN_PACK_TEMPLATES for the floor).
    Send-time wiring injects {{PACK_BODY}} — pack name, gates, and footer links stay untouched.
    """
    out: list[str] = []
    seen: set[str] = set()
    for strategy in PACK_STRATEGIES:
        hooks = strategy.get("hooks") or ()
        if not isinstance(hooks, tuple):
            hooks = tuple(hooks)  # type: ignore[arg-type]
        for hook in hooks:
            block = f"{hook}\n\n{PACK_BODY_PLACEHOLDER}"
            if block in seen:
                continue
            seen.add(block)
            out.append(block)
    # Defensive pad if strategies ever shrink below the floor — shouldn't happen with the
    # current set (101 unique hooks), kept as a safety net for future edits.
    idx = 0
    guard = 0
    while len(out) < MIN_PACK_TEMPLATES and PACK_STRATEGIES and guard < len(PACK_STRATEGIES) * 20:
        strategy = PACK_STRATEGIES[idx % len(PACK_STRATEGIES)]
        for hook in strategy.get("hooks") or ():
            block = f"{hook}\n\n{PACK_BODY_PLACEHOLDER}"
            if block not in seen:
                seen.add(block)
                out.append(block)
                break
        idx += 1
        guard += 1
    return out
