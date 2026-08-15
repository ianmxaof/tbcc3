# System Blueprint — `@aof_secretary_bot` × Format Engine (FE-LLMv4)

**Audience:** any LLM or engineer without repo access.  
**Snapshot date:** 2026-08-14  
**Stage:** Phase 1 sales-rep — **Pilot HITL drafts live**; Auto optional per customer; clone fleet (Phase 2) schema-only.  
**Canonical username:** `aof_secretary_bot` (`TBCC_SECRETARY_BOT_USERNAME`). Checkout must **never** resolve here — Stars/packs live on the payment bot.

Related in-repo doc: `tbcc/docs/FORMAT_ENGINE.md` (operator cheat sheet). This file is the full operational logic.

---

## 1. What this system is

`@aof_secretary_bot` is a **multi-role Telegram process**, not a single FAQ script:

| Layer | Role |
|--------|------|
| **Consumer FAQ** | Direct DMs + Telegram Business Chat Automation. Answers access/subscription questions; **never collects payment**. |
| **Format Engine (FE-LLMv4)** | Persistent per-user emotional/phase state; injects a context suffix into the LLM system prompt. |
| **Sales coach** | Retrieves `sales_strategy` knowledge + DM funnel RAG; injects another suffix; shows a one-line Coach hint on draft cards. |
| **HITL draft (Pilot)** | Customer sees silence; admin gets a draft card (Send / Drop / Pro·Casual·Short / Pilot·Auto). |
| **Admin ops hub** | Inbox, stack, flywheel, Zeus menus, LLM `/config`, affiliates `/sponsors`, Storage Hub `/deposit`, leave-message cleanup. |

**Product intent (not fully implemented):** become a **triage layer** that offers the admin a **curated set of organic replies** grounded in a conversion + psychology corpus. Today the bot generates **one** LLM draft, then optionally **rewrites tone** (pro / casual / short). It does **not** present a menu of alternatives, and it does **not** load a dedicated behavioral-psychology corpus.

---

## 2. Runtime and topology

- **Process:** `python -m bots.secretary_bot` (island Docker `secretary_bot`; Windows tray id `secretary`).
- **Doctrine:** cloud/island is runtime truth. Do not start a second poller (Telegram 409 Conflict). Home secretary should stay Off when island secretary is Up.
- **Token:** `TBCC_SECRETARY_BOT_TOKEN` / `SECRETARY_BOT_TOKEN`.
- **Polling:** `allowed_updates=Update.ALL_TYPES` so Business messages arrive.
- **Co-host:** `build_application(token)` can be reused by Zeus co-host without a second `run_polling`.
- **Phase 2 clones:** table `secretary_bot_instances` + helpers exist; **not** wired to tray/compose. Shared brain intended: FE + RAG + coach + `reply_mode`.

**Surfaces**

1. **Direct bot DM** — customer opens `@aof_secretary_bot`.
2. **Telegram Business** — customer DMs the **operator’s personal account**; the bot is connected as a Business chatbot. Replies must pass `business_connection_id` (plain `reply_text` is rejected).
3. **Admin private chat** with the bot — ops, drafts, config. **Admin user ids never enter the customer draft pipeline** (FE drafts only for non-admins). Test with `/as_customer <text>` (synthetic negative uid) or a fourth Telegram account.

---

## 3. Data model (persistent)

### `secretary_user_contexts` (one row per Telegram user)

- `telegram_user_id` (unique), `telegram_username`
- `current_phase`: `introduction` | `engagement` | `support` | `recovery`
- `interaction_format_json`: FE v4 living format (see §5)
- `emotional_summary`, `message_count`, `last_user_at`, `last_assistant_at`
- `reply_mode`: `pilot` | `auto` | **NULL** (inherit env)

### `secretary_message_records`

Append-only `user` / `assistant` turns (content ≤ 8000 chars). User rows store `emotion_json`. Retention prune: last N (default 80).

### `secretary_knowledge_entries`

FAQ + sales chunks: `title`, `body`, `tags`, `source_path`, optional `embedding_json`. Sales seed: `source_path=seed:sales_playbook`, tags include `sales_strategy`.

### `secretary_settings` (singleton)

Dashboard overrides: FE on/off, verbosity `compact|standard`, public FAQ, RAG, LLM refine-on-phase-change, system prompt, extra prompt, LLM provider/model/key.

### In-memory only (lost on restart)

- `_pending_drafts[DRAFT_ID]` — full reply, `llm_messages`, `business_connection_id`, `chat_id`, coach hint
- `_business_msg_seen` — 45s dedupe key `bc_id:user_id:message_id`
- `_rate_log` — 12 msgs/min/user (admins uncapped)
- PTB `user_data`: FAQ history (`secretary_history`), Business customer line buffer (`secretary_biz_customer_lines`)

---

## 4. Reply-mode state machine

**Per customer**, resolved as:

1. If `secretary_user_contexts.reply_mode` is `pilot` or `auto` → use it.
2. Else inherit env:
   - **Business:** `TBCC_SECRETARY_AUTO_REPLY` truthy → `auto`, else **`pilot` (default)**.
   - **Direct DM:** `TBCC_SECRETARY_SUGGEST_DIRECT` (default **on**) → `pilot`, else `auto`.

| Mode | Customer sees | Admin sees |
|------|----------------|------------|
| **Pilot** | Nothing until ✓ Send | Draft card + optional inbox “Draft ready” |
| **Auto** | Immediate LLM reply in that chat (Business uses `business_connection_id`) | Optional new-lead ping only |
| **Admin live** | Immediate FAQ/ops | Admin is never suggest-mode |

Toggle **Pilot / Auto** on any draft card. **Does not auto-send the current draft.** Later turns follow the new mode.

Observed ops fact (sprint 2026-08-14): customer `Alicia_rios` (`8427563777`) is **Pilot**; **7 user messages / 0 assistant** — drafts were generated (or FE recorded inbound) but **nothing was approved into the Business thread**. Operator still closes those chats by hand (e.g. Zelle pitch, not AOF Stars checkout).

---

## 5. Format Engine (FE-LLMv4) — exact dynamics

**Module:** `format_engine.py`. `FORMAT_VERSION = 4`. Name of default format: `support-adaptive`.

### Ethical charter (hardcoded)

Support and clarity only. No manipulation, false intimacy, or financial pressure. Distress → de-escalate + facts; offer human admin. Never infer malicious intent.

This charter **collides** with the sales-coach suffix (“steer to payment bot”). The LLM sees both. Default FE verbosity is **compact**, so the charter often collapses to: `Support only — no manipulation.`

### Emotion analysis (heuristic, not a model)

Keyword bags → scores (hits × 0.35, cap 1.0): `distress`, `confusion`, `positive`, `urgency`, `disengagement`. Dominant = max score else `neutral`. Distress/disengagement flags at ≥ 0.35.

Tone map (injected as `tone_directive`):

| Dominant | Directive |
|----------|-----------|
| distress | calm, empathetic, factual |
| confusion | patient, step-by-step |
| positive | warm, brief |
| urgency | direct, prioritized |
| disengagement | respectful, low-pressure, one line |
| neutral | clear, professional, concise |

### Phase inference

- Distress → `support`
- Disengagement after >2 user msgs → `recovery`
- Leave `support` when not distressed and dominant ∈ {neutral, positive, confusion} → `engagement`
- Leave `recovery` when not disengaging → `engagement`
- ≥48h since last user and count > 1 → `recovery`
- ≤2 user messages → `introduction`
- else → `engagement`

On **phase change**, optional LLM refine (`TBCC_FORMAT_ENGINE_LLM_REFINE`, default **off**) may overwrite `tone_directive` / `current_focus`.

### Living format JSON (fields that matter)

- `phase`, `phase_history` (last 20 transitions)
- `dominant_emotions` (last 12), `observed_triggers` (last 16)
- `communication_preferences.preferred_tone`, `response_length` (`short` if urgency, `medium` if confusion)
- `interaction_guidelines.current_focus`, `tone_directive`, `recovery_note`, `escalation_hint`
- `metrics`: user/assistant counts, distress_events, positive_signals

Focus examples: intro = “Orient user: what this bot does, where checkout lives”; support = de-escalate + snippet of user text.

### Suffix injected into LLM

**Compact (default):**  
`FE context: phase=…; signal=…; tone=…; focus=…; triggers=…. Support only — no manipulation.`

**Standard:** multi-line block `--- Format Engine (FE-LLMv4) context ---` plus recovery/escalation/gap notes.

### Turn lifecycle

1. `prepare_user_turn(uid, text)` — persist user row, evolve format, return `(suffix, context_id, is_new_lead)`.
2. LLM generates reply.
3. **Auto:** `finalize_assistant_turn(context_id, reply)` immediately.
4. **Pilot:** finalize **only after ✓ Send** via `finalize_assistant_turn_for_user(uid, text)`. Dropped drafts leave **user turns with no assistant** in FE (matches the 7/0 observation).

`is_new_lead` = first recorded user message → inbox `meta.code=secretary_new_lead`.

---

## 6. End-to-end message pipeline (the Secretary layer)

Entry: `on_private_text` (private text only; media/voice → “I can only read text”).

```
inbound private text
  ├─ Business + sender is admin/owner? → DROP (avoid echoing the operator)
  ├─ Business + same message_id within 45s? → DROP
  ├─ Direct + not admin + public_faq_enabled=false? → “admin-only” + payment bot hint
  ├─ Rate limit (non-admin) → wait-a-minute
  ├─ Admin pending wizards (LLM key / model / sysprompt / affiliate URL)
  ├─ LLM not configured → customer: “offline”; admin: /config
  ├─ FAQ keyboard shortcuts (subscribe/shop/reset/mystatus)
  └─ Resolve reply_mode
        ├─ Pilot → suggest_mode (no typing indicator in customer chat)
        └─ Auto (or admin) → typing + in-thread reply
```

### Prompt assembly (order of suffixes appended to system)

1. Base system prompt: dashboard DB → `TBCC_SECRETARY_SYSTEM_PROMPT` → builtin  
   Builtin: concise AOF FAQ assistant; no minors/illegal; purchases via payment bot; **keep under ~400 words**.
2. Payment-bot username instruction (`@aofsubscriptions_bot` or configured).
3. Live catalog snippet: `GET {API}/subscription-plans/` (active subscription SKUs, Stars + days). Fail-soft empty.
4. **FE suffix** if enabled.
5. **Sales coach suffix** if any hits.
6. **FAQ RAG suffix** if `rag_enabled`.
7. Dashboard `system_prompt_extra`.
8. If Pilot: extra instruction that this is a **suggested** reply; customer has not seen prior bot messages.

LLM call: `complete_secretary_chat`, temperature **0.6**, max_tokens default **800**, timeout 90s. Model from `TBCC_SECRETARY_LLM_MODEL` / dashboard (ops: switched off Hcnsec weekly quota onto OpenRouter **`gpt-4o-mini`**).

### Pilot vs Auto conversation memory

| | Pilot / Business suggest | Auto / admin FAQ |
|--|--------------------------|------------------|
| History used | In-memory last 8 **customer** lines (`BIZ_LINES_KEY`) **only** — **does not load FE DB history** | In-memory `HISTORY_KEY` or FE DB last 8 if memory empty |
| After generate | Append customer line; store draft; **do not** write assistant to FE until Send | Reply in chat; finalize FE; append both roles to memory |

**Logic break:** after process restart, Pilot drafts lose thread memory even though FE DB still has user messages. Auto path already hydrates from DB.

### Business delivery

- Approve: `bot.send_message(chat_id, text, business_connection_id=bc_id)`.
- Auto: `_reply()` same `business_connection_id` + `reply_to_message_id`.
- Owner messages in the Business thread are ignored so the bot does not “answer” the admin.

### Draft card (admin DM)

- Id: 6 hex chars.
- Body: who, uid, mode, optional Coach title, customer snippet, `<pre>` reply.
- Buttons: Copy (≤256 chars) · ✓ Send · ✗ Drop · ↻ Pro / Casual / Short · Pilot · Auto.
- Also pushes inbox event `secretary_draft`.
- CLI: `/drafts`, `/approve ID`, `/reject ID`, `/redo ID pro|casual|short|custom …`.

**Tone remaps (not FE phases):** `REDO_STYLE_HINTS`

- `pro` — more professional, calm, shorter, same facts
- `casual` — warmer, casual, no new promises
- `short` — half length, keep payment-bot pointers

Redo **reuses stored `llm_messages`** and adds only the style suffix. It does **not** re-run FE/coach/RAG. Original `extra_system_suffix` is **not** stored on the draft object — so redo is a stylistic rewrite of the first completion’s message list (base system + user block), **without** FE/sales/RAG unless those were already concatenated into the system message at first call. (They **are** concatenated into system at first call via `extra_system_suffix`, and `llm_messages` is the **pre-suffix** list. Redo therefore **drops FE/coach/RAG** unless `complete_secretary_chat` is called with the same extra suffix — **it is not.**)

**Confirmed gap:** `item["llm_messages"]` is the list **before** suffix merge. Redo calls `complete_secretary_chat(llm_messages, extra_system_suffix=style_only)` → **Format Engine + sales coach + RAG are stripped on regenerate.** Casual/pro/short can drift off playbook and phase.

### LLM failure

- Pilot: **no customer-visible error**. Inbox “Secretary draft failed”.
- Auto: customer sees “couldn't generate a reply… payment bot”.

---

## 7. Sales coach + knowledge corpora (current)

**Not** a psychology library. Seed playbook (`seed_secretary_sales_playbook.py`, 12 titles):

1. Soft open — qualify interest  
2. Price objection — value then ladder  
3. Not sure / browsing — soft close  
4. Ready to buy — handoff to payment bot  
5. VIP vs packs ladder  
6. Scarcity without fake FOMO  
7. Recovery after frustration  
8. Loot curiosity bridge  
9. Undress / AI curiosity bridge  
10. Silence after pitch — one bump  
11. Compare tiers  
12. Crypto / Stars payment path  

Hard rules in seed + coach header: never invent prices, countdown timers, fake sold-out, or impersonate Telegram staff. Checkout commands: `/subscribe` `/packs` `/shop` on the **payment bot**.

Retrieval: prefer knowledge tagged `sales_strategy`; else funnel_rag `surface=dm`. Weakness: if keyword RAG misses tagged rows, coach may inject **first N tagged rows with score 1.0** regardless of query — **over-prompting / generic sales lecture**.

FAQ RAG is separate (keyword + optional embeddings). Coach still runs if general RAG is off (sales rows scanned).

---

## 8. Adjacent features (same process, not FE)

These shape operator experience and can steal latency/attention:

- Zeus hub IA: Network | Inbox | Ops | More (`zeus:*` → `sec:menu:*`)
- `/stack` display-only tray status
- Admin inbox categories: payment, loot, ops, critical
- Ops flywheel approve/reject; Cursor triage bundle
- Affiliate intake + `/sponsors`
- Storage Hub `/deposit` (optional)
- Loot Room leave-message cleanup
- Rate limit, public FAQ kill switch

**Public CTAs** elsewhere point humans at `@aof_secretary_bot` (“Suggest a deal”, growth hub, checkout-list tips). The bot is branded as **deal/FAQ secretary**, while FE’s default persona is **support-adaptive**, not a closer.

---

## 9. Intended behavioral flow (as coded)

```
Customer (Business or DM)
    → FE observe + persist user turn
    → Sales coach + FAQ RAG + catalog
    → One LLM draft (temp 0.6, ≤800 tokens, “~400 words”)
    → Pilot: silence to customer; admin triages ONE suggestion
         → Send → appears as the connected Business account / bot
         → Drop → FE still has the user message
         → Redo tone → NEW llm call WITHOUT FE/coach suffixes
    → Auto: send immediately as the bot in that thread
```

**Admin is the closer.** The LLM is a **scribe**, not a multi-option triage board.

---

## 10. Gap analysis — diagnosis of the response-generation pipeline

### Logic / product

| ID | Failure | Diagnosis |
|----|---------|-----------|
| G1 | **Single suggestion, not a curated set** | Pipeline returns one `complete_secretary_chat`. No n-best, no “organic vs formal vs close” parallel generations. Casual/pro/short are **post-hoc rewrites**, not first-class personas. |
| G2 | **AI-verbosity trap is structurally invited** | Builtin prompt allows ~400 words; max_tokens=800; temp=0.6; stacked suffixes (FE + 3 sales chunks + funnel + RAG + catalog + extra). Compact FE does not cap length. |
| G3 | **Support charter vs sales coach** | FE forbids financial pressure; coach demands checkout steer. Model averages into generic “helpful FAQ” unless operator redos Casual. |
| G4 | **No psychology corpus** | Emotion = English keyword bags. No Cialdini/commitment/reciprocity/scarcity-ethics playbook beyond 12 sales bullets. |
| G5 | **Redo strips FE + coach + RAG** | `llm_messages` stored pre-suffix; redo passes only style hint. |
| G6 | **Pilot ignores FE message DB for context** | Suggest path uses `BIZ_LINES_KEY` only. Restart / new process → amnesiac drafts. Auto path already loads DB. |
| G7 | **Dropped/unapproved drafts = orphan user turns** | FE metrics show user_messages ≫ assistant_messages (live: 7/0). Phase still advances on inbound. |
| G8 | **Drafts are RAM** | Restart secretary → pending cards dead; `/approve` fails. |
| G9 | **Sales retrieval can ignore relevance** | Fallback injects latest tagged rows at score 1.0. |
| G10 | **Admin never gets FE drafts of themselves** | Correct for ops; `/as_customer` is the only same-account test. Easy to think “bot is silent.” |
| G11 | **Business owner skip** | Operator typing in the Business inbox does not update FE as “assistant.” Human closes are invisible to the format. |
| G12 | **Checkout mismatch** | Sprint: some Business leads need **Zelle / off-platform** pitch; system always injects **Stars payment bot** SKUs. High conversion risk if the live offer is not AOF checkout. |
| G13 | **Clone fleet unwired** | Volume inbound skins not live. |
| G14 | **Text-only** | Photos/voice from buyers are discarded. |
| G15 | **Copy button truncates at 256** | Long drafts must Send or manual select. |

### Errors / latency

| ID | Failure | Diagnosis |
|----|---------|-----------|
| L1 | **LLM wallet thrash** | Hcnsec quota exhausted → OpenRouter `gpt-4o-mini`. 90s timeout. Sequential: catalog HTTP + FE DB + coach DB + RAG + LLM. Pilot hides failures; looks like “bot dead.” |
| L2 | **Telegram 409** | Two secretary pollers (home tray + island). |
| L3 | **403 on admin DM** | Admin must `/start` the bot once or draft cards never land; logged as warning. |
| L4 | **Catalog fetch 15s** | Adds latency before the LLM even starts. |
| L5 | **Phase-change LLM refine** | Extra sync completion if enabled; currently off. |
| L6 | **Conflict / NetworkError** | Swallowed with once-logs; no customer retry in Pilot. |

### Mapping “casual/natural” ↔ “formal/automated” to FEv4

**Today these are two different axes:**

1. **FE axis (automatic, persistent):** phase + emotion → `tone_directive` / `response_length`. This is **support calibration**, not sales persona. Compact mode is a one-liner the model can ignore.
2. **Redo axis (manual, ephemeral):** `pro` ≈ formal, `casual` ≈ natural, `short` ≈ terse. **Not stored** on the user context. Next turn regenerates from defaults, not last chosen tone.
3. **Pilot vs Auto:** **delivery policy**, not linguistic register. Auto is “automated send,” not “formal voice.”

There is **no** first-class mapping such as `persona=closer_casual` inside `interaction_format_json`. Default format `name` is always `support-adaptive`.

---

## 11. Dependencies (for an implementing LLM)

**Python host:** `tbcc/backend/bots/secretary_bot.py`  
**FE:** `app/services/format_engine.py`, `format_engine_llm.py`  
**Modes:** `secretary_reply_mode.py`  
**Coach:** `secretary_sales_coach.py` + `scripts/seed_secretary_sales_playbook.py`  
**LLM:** `secretary_llm.py` → `llm_completions.complete_chat_text_async`  
**RAG:** `secretary_rag.py`, `funnel_rag.py`  
**Settings:** `secretary_settings_effective.py`, API `app/api/secretary.py`  
**Tests:** `test_format_engine.py`, `test_secretary_reply_mode.py`, `test_secretary_sales_coach.py`, `test_secretary_new_lead.py`  
**Env knobs:** `TBCC_FORMAT_ENGINE_ENABLED`, `TBCC_FORMAT_ENGINE_VERBOSITY`, `TBCC_FORMAT_ENGINE_LLM_REFINE`, `TBCC_SECRETARY_AUTO_REPLY`, `TBCC_SECRETARY_SUGGEST_DIRECT`, `TBCC_SECRETARY_RAG_ENABLED`, `ADMIN_TELEGRAM_ID`, `TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID`, `TBCC_SECRETARY_LLM_MODEL`, `TBCC_SECRETARY_LLM_MAX_TOKENS`, `TBCC_SECRETARY_RATE_LIMIT_PER_MIN`

**Do not:** spawn a second secretary; send checkout invoices from this token; invent FOMO; treat FE emotion labels as clinical.

---

## 12. Recommended iteration vector (for the next implementer)

Goal: **triage layer** — curated organic replies + conversion/psychology corpora, anti-verbosity.

Minimum coherent slice:

1. Persist drafts (DB) so restart does not kill HITL.
2. Store the **full** system suffix on the draft so redo/n-best keep FE+coach.
3. Hydrate Pilot history from `secretary_message_records` (same as Auto).
4. Generate **3 short candidates** in one turn (e.g. natural / clear / close) with a hard **≤2 short sentences / ≤280 chars** cap — do not rely on “~400 words.”
5. Add a tagged corpus `psych_ethics` + `sales_strategy` with **query-relevant** retrieval only (no score-1.0 dump).
6. Record **human-sent** Business replies (or at least chosen candidate id) as assistant turns so FE phase matches reality.
7. Split “AOF Stars checkout” vs “off-platform / Zelle” offer context per customer/pilot so the catalog snippet does not fight the live pitch.

FE v4 can stay as **observational phase/emotion**. Do not overload it as the persona engine; add an explicit `reply_persona` (or candidate set) beside `reply_mode`.
