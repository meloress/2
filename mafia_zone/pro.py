"""PRO obuna: xotiradagi kesh (bitta replika; db.load_pro ishga tushishda to'ldiradi) va ko'rinish yordamchilari."""
import re
from datetime import datetime

from . import config

BADGE_ID = "5197557379083804570"  # ✅ "Verified" custom emoji
BADGE_FALLBACK = "✅"
PACKS = {7: (30, 100), 15: (55, 150), 30: (99, 249)}  # kun -> (olmos, stars)
CACHE: dict[int, tuple[datetime, str | None]] = {}  # uid -> (tugash vaqti, nickname)
_BAD_NICK = re.compile(r"@|https?:|t\.me|www\.|admin|bot", re.I)


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


def name(uid: int, fallback: str) -> str:
    """Ko'rsatiladigan ism: PRO va nickname bo'lsa - nickname."""
    return (CACHE[uid][1] or fallback) if is_pro(uid) else fallback


def badge() -> str:
    return f'<tg-emoji emoji-id="{BADGE_ID}">{BADGE_FALLBACK}</tg-emoji>'


def label(uid: int, text: str) -> tuple[str, str | None]:
    """Tugma uchun: (matn, icon_custom_emoji_id)."""
    return (f"PRO {name(uid, text)}", BADGE_ID) if is_pro(uid) else (text, None)


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
    if _BAD_NICK.search(s):
        return "❌ Nickname'da @, havola, «admin» yoki «bot» so'zi bo'lmasin."
    return None
