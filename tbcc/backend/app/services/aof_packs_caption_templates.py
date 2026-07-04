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
            "One pack today — full AOF stack waiting in the footer. Tourists scroll; you addlist.",
            "😳 <b>ONE CLICK — FULL NETWORK</b>\n\n"
            "This drop is one lane. The addlist unlocks the rest. Links unchanged below.",
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
)


def list_pack_strategy_ids() -> list[str]:
    return [str(s["id"]) for s in PACK_STRATEGIES]


def pack_strategy_for_index(index: int) -> dict[str, object]:
    strategies = list(PACK_STRATEGIES)
    if not strategies:
        raise ValueError("no pack strategies configured")
    return strategies[index % len(strategies)]


def pack_caption_template_variations() -> list[str]:
    """
    Strategy shells for content_variations rotation (~50 slots).
    Send-time wiring injects {{PACK_BODY}} — pack name, gates, and footer links stay untouched.
    """
    out: list[str] = []
    seen: set[str] = set()
    for strategy in PACK_STRATEGIES:
        sid = str(strategy.get("id") or "")
        hooks = strategy.get("hooks") or ()
        if not isinstance(hooks, tuple):
            hooks = tuple(hooks)  # type: ignore[arg-type]
        for hook in hooks:
            block = f"{hook}\n\n{PACK_BODY_PLACEHOLDER}"
            if block in seen:
                continue
            seen.add(block)
            out.append(block)
            if len(out) >= 50:
                return out
    # Pad with strategy repeats if hook count < 50 (shouldn't happen with current set)
    idx = 0
    while len(out) < 50 and PACK_STRATEGIES:
        strategy = PACK_STRATEGIES[idx % len(PACK_STRATEGIES)]
        hooks = strategy.get("hooks") or ()
        if hooks:
            block = f"{hooks[0]}\n\n{PACK_BODY_PLACEHOLDER}"
            if block not in seen:
                seen.add(block)
                out.append(block)
        idx += 1
    return out
