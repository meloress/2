# 🛡 Moderatsiya — bajarish rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.mute/.ban/.kick/.warn/.info/.admins`, `/report`, reklama va so'kinishni avtomatik tozalash, 3 warn → ban, `/settings` → 🛡 Moderatsiya.

**Architecture:** yangi `mafia_zone/moderation.py`: sof aniqlagichlar (`is_swear`, `ad_reason`, `parse_duration`) + o'z `Router`'i (buyruqlar, report tugmalari) — dispatcherga `handlers.router` dan **oldin** ulanadi. Avtomatik tozalash `handlers.drop_commands` ichidan chaqiriladi (`moderation.auto`), shuning uchun har guruh xabari undan o'tadi. Ma'lumot `db.py` da: `ModWarn`, `GroupMember` jadvallari, `bad_words` sozlamasi.

**Tech Stack:** aiogram 3.31, SQLAlchemy 2 async, pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-moderation-design.md`

## Global Constraints
- Avtomatik tozalash standart o'chiq (`mod_ads`, `mod_swear` = False); `mod_swear_min` = 30, `mod_warn_max` = 3, `mod_report` = True.
- Warn 30 kun amal qiladi (`db.WARN_DAYS`).
- Adminlar, bot egalari, yashirin admin, bog'langan kanal postlari hech qachon avtomatik jazolanmaydi.
- Repo ochiq: qo'shimcha so'kinish so'zlari faqat bazada (`settings.bad_words`).

## Review Focus
- Oddiy o'zbekcha/ruscha gaplar so'kinish deb ushlanmasin (false positive testlari).
- Bot huquqi yo'q guruhda hech narsa yiqilmasin (`_call` → None, foydalanuvchiga tushunarli javob).
- Admin/egani jazolash urinishi rad etiladi.
- Report tugmasini guruh admini bo'lmagan odam bosolmaydi; bir report bir marta hal bo'ladi.
- Har xabarda bazaga so'rov yo'q: sozlamalar keshda (`moderation.SETTINGS_TTL`).

### Task 1: Aniqlagichlar + testlar (`moderation.py`, `tests/test_moderation.py`)
### Task 2: DB (warn, a'zolar, info) + buyruqlar + warn→ban
### Task 3: Avtomatik tozalash (drop_commands → moderation.auto)
### Task 4: `/report`, `.admins`, `.info`
### Task 5: `/settings` → 🛡, panel so'zlar ro'yxati, menyu, CLAUDE.md, to'liq testlar
