# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Uzbek-language Telegram mafia game bot (aiogram 3, SQLAlchemy 2 async). User-facing brand is **Admiral Mafia**; the package (`mafia_zone`) and the original spec still say "Mafia Zone". Game rules come from `Mafia Zone - Game Guide & Technical Specification.pdf`; the design decisions that fill its gaps are in `docs/superpowers/specs/2026-10-06-mafia-zone-design.md`. All user-facing text is Uzbek (Latin); code comments are Uzbek too — keep that.

## Commands

```bash
pip install -r requirements.txt pytest     # deps (no lint/format tooling in the repo)
python -m mafia_zone                       # run the bot (reads .env: BOT_TOKEN, ADMIN_IDS, DATABASE_URL)
python -m pytest -q                        # full suite, ~4 min (10k+ random-game simulations)
python -m pytest -q -k "not simulate"      # fast run, seconds
python -m pytest -q tests/test_engine.py::test_voris_transforms   # single test
node --check mafia_zone/panel_static/app.js   # syntax check for the panel frontend (no build step)
```

- Env (`.env` locally, Railway Variables in prod): `BOT_TOKEN`, `ADMIN_IDS` (comma-separated owner ids), `DATABASE_URL`, plus optional `PANEL_URL` (else `https://$RAILWAY_PUBLIC_DOMAIN`, which Railway only injects on the deploy *after* a domain is generated), `PANEL_SECRET` (else derived from `BOT_TOKEN`), `PORT` (default 8080), `NEWS_URL`, `EMOJI_PACK` (empty = plain emoji).
- No `DATABASE_URL` (or empty) → local SQLite `mafia.db`. Railway gives `postgresql://…`; `config.py` rewrites it to `postgresql+asyncpg://`.
- Tests never touch `mafia.db`: `tests/conftest.py` points `DATABASE_URL` at a temp file before `mafia_zone.db` is imported.
- Schema: `db.init()` runs `Base.metadata.create_all` (new tables) then `_migrate` (adds columns listed in `db.COLUMNS` to existing tables). No Alembic — add every new column on an existing table to `COLUMNS`. SQLite returns naive datetimes; compare via `db._aware()`.
- Deploy: `Dockerfile` (copies `mafia_zone/` plus `kun.mp4`, `tun.mp4`), Railway + Railway PostgreSQL, exactly **one replica** (game state, rate limiters, one-time login nonces live in process memory). Bot polling and the web panel run in the same process.

## Architecture

**`engine/` is pure Python and knows nothing about Telegram.** `Game` (dataclass, JSON-serializable via `to_dict`/`from_dict`) takes actions and returns lists of `Event(kind, uid, target, data)`. All game rules live in `engine/game.py`; `roles.py` is data only (team, action kinds, description); `setup.py` deals roles by player count (4–60). Randomness is seeded (`Random(f"{seed}:{day}:night")`) so any game is reproducible.

- Phases: `NIGHT → DAY → VOTING → (CONFIRM) → NIGHT …`, `FINISHED`. CONFIRM (👍/👎 before hanging) only when `Game.confirm` is on.
- `resolve_night()` runs the spec's priority order in one function: 1a block (Kezuvchi) → 1b Aferist steal, Qaroqchi rob → 2 heal/guard/disguise → 3 checks/info → 4 attacks (immunities, heal, Voris transform, items) → 5 revenge (Afsungar/Suitsid) → `_after_deaths` (Aka/Uka link, Serjant→Komissar, Mafiya→Don promotion) → `_check_win`. The mafia kill is stored as an action owned by the Don, so blocking/stealing the Don affects it; if the Don submits `SKIP` nobody is killed.
- Roles can change mid-night (Ovchi penalty → `tinch`, Voris transform), so `resolve_night` snapshots `roles0` at the start and puts `role` / `killer_roles` into `killed` and `witness` events. Texts must read roles from event data, not from the mutated `Player`.
- Winners (`_finish`): only **alive** members of the winning side; roles that win by dying (Suitsid, Tulki, G'azabkor) get `won=True` at death and keep it. `setup.deal` has balance rules (constants at the top: no Afsungar/Suitsid/Podshoh at ≤7 players, killer neutrals from 12, repeatable town roles from 30) — `test_deal` asserts them.
- Every night role can submit `SKIP` ("Hech narsa qilmayman"): it counts as acting (not AFK) and is never posted to the group feed.
- Adding a role = entry in `roles.py`, pool membership in `setup.py`, rule branches in `game.py`, texts in `texts.py` (`ACT_FEED`, `ROLE_PROMPT`), plus a scenario test.

**`runner.py` — one `Runner` per group chat** (registries: `RUNNERS[chat_id]`, `PLAYING[uid]`). It owns the lobby, the phase loop (`_step`: intro → wait until deadline or everyone acted → resolve under `asyncio.Lock` → announce), and persistence: the whole game state is saved as JSON into `games.state` after every action and phase change; `restore()` resumes running games on startup from `meta["deadline"]`.

- All Telegram sends go through `send()/edit()/_call()`: a global ~25 msg/s queue, a per-group sliding window (`GROUP_PER_MIN = 19`), `RetryAfter` handling, long-text splitting at 3800 chars. Live feed lines (night actions, votes) are sent one per message while the group budget allows and merged into one message when it doesn't. Don't bypass these for group messages.
- `_call()` never raises: Forbidden/BadRequest → `None`, network/5xx errors are retried then `None`, so one failed send cannot abort a game (an exception escaping `_loop` aborts the game). Start background coroutines with `runner.spawn()` (keeps a reference), not bare `asyncio.create_task`.
- Lobbies live in memory only; their message ids are mirrored in the `lobbies` table so `restore()` can unpin/delete them and tell the group after a redeploy. `/game` during an open lobby reposts it at the bottom (`repost_lobby`).
- Night actions and votes are cast in private chat via inline buttons; callback data embeds `game_id:day` so stale buttons are rejected.
- `/testgame N` (owner only) adds fake players with uids `>= FAKE_BASE`; they act randomly and are never messaged.

**`texts.py`** turns events into messages: `morning(g, ev)` returns `(public_messages, [(uid, private_text)])`. All HTML must stay within Telegram's subset (`b`, `i`, `s`, `a`, `code`, `tg-emoji`) — tests validate generated messages. Render player names through `mention()`/`pm()` (links + PRO badge) or `dn()`/`nm()` (plain/escaped, PRO nickname applied at render time) — never store the nickname into `Player.name`. Role names are rendered in math-bold via `bold()`.

**`handlers.py`** — aiogram router. Handler order matters: the catch-all `@router.message(GROUPS)` (`on_group_message`, enforces who may write during a game: numbers for everyone, `!`-prefixed for admins, normal text only for alive players by day) must stay at the end of the file. Edited messages are intentionally not checked (number → text edit is a deliberate loophole). A global `@router.errors()` handler swallows exceptions. An outer middleware (`drop_commands`) deletes every `/command` addressed to the bot in groups after handling. Admin checks go through `is_admin(bot, chat, uid, msg)` — pass `msg` so anonymous admins (`sender_chat == chat`) count.

- Anti-farming rules (values in `config.py`, used by handlers): `/leave` during a game is free `LEAVE_FREE`/day (PRO: 5), then confirm + `-LEAVE_FINE` (balance may go negative; leaving the group counts too); balance `<= DEBT_LIMIT` cannot join; referral bonus is paid only after the invitee finishes `REF_GAMES` games (`db.pay_referrals` in `Runner._finish`); `/send` needs `SEND_GAMES`, claiming a giveaway needs `CLAIM_GAMES`. There is no daily bonus.
- Profile wallet (`profile_kb` → `cb_menu` `m:buy|gem|pay|gift|groups`, `cb_wallet`): diamonds→dollars packs (`config.DOLLAR_PACKS`), diamonds for Stars for self or a friend (`config.DIAMOND_STARS`, payload `dm:<n>:<target>`, `db.add_paid_diamonds` deduplicated like PRO), private transfers. Inputs that need typed text ("@username 100") set `handlers.ASK[uid]`; `on_private_text` consumes it first.
- Giveaways (`/send N K`) are pinned and expire after `texts.GIVEAWAY_TTL_MIN`: unclaimed shares are refunded (`db.close_giveaway`), timers are re-armed on startup (`restore_giveaways`).

**`db.py`** — every balance/inventory/giveaway change is a single atomic `UPDATE … WHERE` (e.g. `dollars >= amount`, `left > 0`). Do not use read-modify-write on ORM objects for money: a concurrency test caught 49 claims on a 10-share giveaway that way.

**`panel.py` + `panel_static/` — web admin panel** (aiohttp, same process, listens on `PORT`). Login: admin sends `/panel` to the bot → one-time 5-min signed link → HttpOnly session cookie (12 h). Roles: `owner` (ADMIN_IDS) > `moderator` > `viewer` (`panel_admins` table); every handler calls `need(req, role)`. Mutating requests need `X-CSRF` + same Origin. Every action goes to `admin_log`. Frontend is vanilla JS with a `h()` DOM builder — never use `innerHTML` (user names are untrusted). CSP is `script-src 'self'; style-src 'self'`: no inline `<script>`/`style=""` in HTML (setting `el.style` from JS is fine). Broadcast text is normalized (`normalize_html`) and validated (`check_html`) server-side before sending. Economy values live on `config` and are overridden from the `settings` table (`db.load_settings`) — read them as `config.X`, never `from .config import X`. New columns on existing tables go in `db.COLUMNS` (`_migrate`). Tests: `tests/test_panel.py`.

**`pro.py` — PRO subscription.** In-memory cache `pro.CACHE[uid] = (pro_until, nickname)` (one replica; `db.load_pro()` fills it in `db.init()`, every purchase/panel change updates it). `texts.mention()` reads the cache, so any name rendered through `mention`/`pm` gets the badge (`<tg-emoji emoji-id="5197557379083804570">✅</tg-emoji> <b>PRO</b>`) and nickname automatically; buttons use `pro.label()` → `icon_custom_emoji_id`. Perks go through `pro.price()` (-25%), `pro.win_reward()` (x1.5), `pro.leave_free()` (5). Payments: diamonds (`db.buy_pro_diamonds`, atomic) or Telegram Stars (`send_invoice` currency `XTR`, `pre_checkout_query` validates payload/amount, `successful_payment` → `db.add_pro` deduplicated by `payments.charge_id` UNIQUE). If Telegram rejects custom emoji once, `emoji.PremiumEmoji` resends with `emoji.plain()` (strips `<tg-emoji>` and button icons) and sets `emoji.DISABLED`.

## Working notes

- When patching files from the shell, write the Python patch script to a file and run it; `\\n` inside Bash heredocs has repeatedly turned into real newlines and broken string literals.
- Write plain Unicode emoji in texts. `emoji.py` (session middleware) swaps the ones present in the `EMOJI_PACK` sticker set (default `RestrictedEmoji`, loaded at startup) for animated custom emoji, skipping `<a>`/`<code>`/`<pre>`; if Telegram rejects once, it resends plain and turns itself off until restart. Each role's emoji (first token of `Role.name`) must be unique.
