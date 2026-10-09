"""PRO obuna: xotiradagi kesh (bitta replika; db.load_pro ishga tushishda to'ldiradi) va ko'rinish yordamchilari."""
import re
import unicodedata
from datetime import datetime

from . import config

BADGE_ID, BADGE_FALLBACK = "5226766493886225846", "🌟"  # ismdan oldin (thecamelot to'plami)
TAIL_ID, TAIL_FALLBACK = "5220136481720409403", "🔥"  # ismdan keyin
PACKS = {7: (30, 100), 15: (55, 150), 30: (99, 249)}  # kun -> (olmos, stars)
CACHE: dict[int, tuple[datetime, str | None]] = {}  # uid -> (tugash vaqti, nickname)
_BAD_NICK = re.compile(r"@|https?:|t\.me|www\.|\badmin\b|\bbot\b", re.I)  # "Botir", "Admiral" - mumkin
_FAKE = re.compile(r"^[\s✅☑✔🌟⭐\ufe0f]*PRO\b[\s:|·•-]*(.*?)[\s🔥]*$", re.I | re.S)  # oddiy ismdagi "🌟 PRO … 🔥" soxta belgi


def _now() -> datetime:
    from .db import now
    return now()


def set_user(uid: int, until: datetime | None, nick: str | None) -> None:
    if until is None:
        CACHE.pop(uid, None)
    else:
        CACHE[uid] = (until, nick)


def load(rows) -> None:
    """rows: [(uid, pro_until, nickname)]"""
    CACHE.clear()
    for uid, until_, nick in rows:
        set_user(uid, until_, nick)


def until(uid: int) -> datetime | None:
    v = CACHE.get(uid)
    return v[0] if v and v[0] > _now() else None


def is_pro(uid: int) -> bool:
    return until(uid) is not None


NAME_MAX = 20  # botning hamma joyida ism shundan uzun bo'lsa "…" bilan qisqaradi (= nickname chegarasi)
MARKS_MAX = 2  # bir harf ustidagi urg'u/belgilar ("zalgo" ismlar qatorni bo'yiga cho'zadi)


def short(s: str) -> str:
    """Ko'rinadigan ism: ko'rinmas/yo'nalish belgilarisiz (emoji ZWJ qoladi), ortiqcha ustma-ust belgilarsiz, qisqa."""
    out, marks = [], 0
    for c in s:
        cat = unicodedata.category(c)
        if cat == "Cc" or cat == "Cf" and c != "‍":
            continue
        marks = marks + 1 if cat in ("Mn", "Me") else 0
        if marks <= MARKS_MAX:
            out.append(c)
    s = "".join(out).strip()
    if len(s) > NAME_MAX:
        s = s[:NAME_MAX - 1].rstrip() + "…"
    return s or "?"


def name(uid: int, fallback: str) -> str:
    """Ko'rsatiladigan ism: PRO va nickname bo'lsa - nickname. Oddiy foydalanuvchi ismidagi "✅ PRO" olib tashlanadi."""
    if is_pro(uid):
        return short(CACHE[uid][1] or fallback)
    return short(_FAKE.sub(r"\1", fallback) or fallback)


def badge() -> str:
    return f'<tg-emoji emoji-id="{BADGE_ID}">{BADGE_FALLBACK}</tg-emoji>'


def tail() -> str:
    return f'<tg-emoji emoji-id="{TAIL_ID}">{TAIL_FALLBACK}</tg-emoji>'


def label(uid: int, text: str) -> tuple[str, str | None]:
    """Tugma uchun: (matn, icon_custom_emoji_id)."""
    return (f"PRO {name(uid, text)}", BADGE_ID) if is_pro(uid) else (name(uid, text), None)


def price(uid: int, base: int) -> int:
    return base * 3 // 4 if is_pro(uid) else base  # -25%


def leave_free(uid: int) -> int:
    return 5 if is_pro(uid) else config.LEAVE_FREE


def win_reward(uid: int) -> int:
    return config.REWARD_WIN * 3 // 2 if is_pro(uid) else config.REWARD_WIN  # x1.5


def check_nick(s: str) -> str | None:
    """Xato matni yoki None (yaroqli)."""
    s = s.strip()
    if not 2 <= len(s) <= 20:
        return "❌ Nickname 2 dan 20 tagacha belgi bo'lsin."
    if any(unicodedata.category(c) in ("Cc", "Cf") for c in s):  # ko'rinmas/yo'nalish belgilari matnni buzadi
        return "❌ Nickname'da ko'rinmas belgilar bo'lmasin."
    if _BAD_NICK.search(s):
        return "❌ Nickname'da @, havola, «admin» yoki «bot» so'zi bo'lmasin."
    return None
