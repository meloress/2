# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Mafia Zone — Uzbek-language Telegram mafia game bot (aiogram 3, SQLAlchemy 2 async). Game rules come from `Mafia Zone - Game Guide & Technical Specification.pdf`; the design decisions that fill its gaps are in `docs/superpowers/specs/2026-10-06-mafia-zone-design.md`. All user-facing text is Uzbek (Latin); code comments are Uzbek too — keep that.

## Commands

```bash
python -m mafia_zone                       # run the bot (reads .env: BOT_TOKEN, ADMIN_IDS, DATABASE_URL)
python -m pytest -q                        # full suite, ~4 min (10k+ random-game simulations)
python -m pytest -q -k "not simulate"      # fast run, seconds
python -m pytest -q tests/test_engine.py::test_voris_transforms   # single test
```

- No `DATABASE_URL` (or empty) → local SQLite `mafia.db`. Railway gives `postgresql://…`; `config.py` rewrites it to `postgresql+asyncpg://`.
- Tests never touch `mafia.db`: `tests/conftest.py` points `DATABASE_URL` at a temp file before `mafia_zone.db` is imported.
- Schema is created with `Base.metadata.create_all` (no Alembic yet) — it adds new tables but **cannot add columns** to existing ones.
- Deploy: `Dockerfile` (copies `mafia_zone/` plus `kun.mp4`, `tun.mp4`), Railway + Railway PostgreSQL, exactly **one replica** (state and rate limiters live in process memory).

## Architecture

**`engine/` is pure Python and knows nothing about Telegram.** `Game` (dataclass, JSON-serializable via `to_dict`/`from_dict`) takes actions and returns lists of `Event(kind, uid, target, data)`. All game rules live in `engine/game.py`; `roles.py` is data only (team, action kinds, description); `setup.py` deals roles by player count (4–60). Randomness is seeded (`Random(f"{seed}:{day}:night")`) so any game is reproducible.

- Phases: `NIGHT → DAY → VOTING → (CONFIRM) → NIGHT …`, `FINISHED`. CONFIRM (👍/👎 before hanging) only when `Game.confirm` is on.
- `resolve_night()` runs the spec's priority order in one function: 1a block (Kezuvchi) → 1b Aferist steal, Qaroqchi rob → 2 heal/guard/disguise → 3 checks/info → 4 attacks (immunities, heal, Voris transform, items) → 5 revenge (Afsungar/Suitsid) → `_after_deaths` (Aka/Uka link, Serjant→Komissar, Mafiya→Don promotion) → `_check_win`. The mafia kill is stored as an action owned by the Don, so blocking/stealing the Don affects it.
- Adding a role = entry in `roles.py`, pool membership in `setup.py`, rule branches in `game.py`, texts in `texts.py` (`ACT_FEED`, `ROLE_PROMPT`), plus a scenario test. The emoji catalog is derived from `ROLES`/`ACTION_LABELS` automatically.

**`runner.py` — one `Runner` per group chat** (registries: `RUNNERS[chat_id]`, `PLAYING[uid]`). It owns the lobby, the phase loop (`_step`: intro → wait until deadline or everyone acted → resolve under `asyncio.Lock` → announce), and persistence: the whole game state is saved as JSON into `games.state` after every action and phase change; `restore()` resumes running games on startup from `meta["deadline"]`.

- All Telegram sends go through `send()/edit()/_call()`: a global ~25 msg/s queue, a per-group sliding window (`GROUP_PER_MIN = 19`), `RetryAfter` handling, long-text splitting at 3800 chars. Live feed lines (night actions, votes) are sent one per message while the group budget allows and merged into one message when it doesn't. Don't bypass these for group messages.
- Night actions and votes are cast in private chat via inline buttons; callback data embeds `game_id:day` so stale buttons are rejected.
- `/testgame N` (owner only) adds fake players with uids `>= FAKE_BASE`; they act randomly and are never messaged.

**`texts.py`** turns events into messages: `morning(g, ev)` returns `(public_messages, [(uid, private_text)])`. All HTML must stay within Telegram's subset (`b`, `i`, `a`, `code`) — tests validate every generated message. Role names are rendered in math-bold via `bold()`.

**`emoji.py` — premium emoji is a session middleware**, not something texts know about: it rewrites plain emoji to `<tg-emoji>` in outgoing text/captions and turns a button's leading emoji into `icon_custom_emoji_id`, using the mapping in the `emojis` table. If Telegram rejects it (bot owner lost Premium), the original request is resent. Owner commands: `/emoji` (map manually), `/emojipack` (`emoji_pack.py` builds 100×100 badges from Twemoji, CC-BY, and uploads a custom-emoji sticker set).

**`handlers.py`** — aiogram router. Handler order matters: the catch-all `@router.message(GROUPS)` (`on_group_message`, enforces who may write during a game: numbers for everyone, `!`-prefixed for admins, normal text only for alive players by day) must stay at the end of the file. Edited messages are intentionally not checked (number → text edit is a deliberate loophole). A global `@router.errors()` handler swallows exceptions.

**`db.py`** — every balance/inventory/giveaway change is a single atomic `UPDATE … WHERE` (e.g. `dollars >= amount`, `left > 0`). Do not use read-modify-write on ORM objects for money: a concurrency test caught 49 claims on a 10-share giveaway that way.

## Working notes

- When patching files from the shell, write the Python patch script to a file and run it; `\\n` inside Bash heredocs has repeatedly turned into real newlines and broken string literals.
- The bot owner (`ADMIN_IDS`) has Telegram Premium; premium emoji only works because of that.
