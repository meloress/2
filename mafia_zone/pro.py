"""Pro obuna (1/2/3-daraja, guruh egasi toifasi): xotiradagi kesh (bitta replika; db.load_pro ishga tushishda to'ldiradi) va ko'rinish yordamchilari."""
import re
import unicodedata
from datetime import datetime, timezone

from . import config
from .emoji import USER

# o'z to'plamimiz (admiral_roles_by_AdmiralMafiabot): "pro boshi" ismdan oldin, galochka keyin (Pro - qizil, Vip - qora)
BADGE_ID, BADGE_FALLBACK = "5444964086792104275", "🎩"
TAIL_ID, TAIL_FALLBACK = "5444981103452531111", "☑️"
VIP_TAIL_ID, VIP_TAIL_FALLBACK = "5442967463870380552", "✔️"
# Bot egasi (config.ADMIN_IDS): PRO o'rniga "👑 Creator <nickname> ✅" (o'z to'plamimiz: oltin toj va oltin galochka) - faqat ko'rinish, imtiyoz emas
OWNER_ID, OWNER_FALLBACK = "5445221694635551153", "👑"
OWNER_TAIL_ID, OWNER_TAIL_FALLBACK = "5445219637346216382", "✅"
DAYS = 7  # har paket shuncha kun
PACKS = {1: (9, 50), 2: (19, 100), 3: (29, 150)}  # daraja -> (olmos, stars), DAYS kunga
DISCOUNT = {1: 5, 2: 10, 3: 15, None: 25}  # do'kon chegirmasi %; None - eski (darajasiz) PRO, muddati tugaguncha
WIN = {1: 100, 2: 125, 3: 150, None: 150}  # g'alaba puli %
FOREVER = datetime(2100, 1, 1, tzinfo=timezone.utc)  # guruh egasi toifasi - cheksiz Pro 3
# uid -> (tugash vaqti, nickname, daraja (None = eski PRO, Pro 3 kabi), toifa (guruh nomi + " Owner"; bor bo'lsa "Vip" ko'rinadi) yoki None)
CACHE: dict[int, tuple[datetime, str | None, int | None, str | None]] = {}
FORCED: dict[int, str] = {}  # uid -> qulflangan ism (settings "name_lock", db._apply): nickname/ismdan ustun, o'zgarmaydi
_BAD_NICK = re.compile(r"@|https?:|t\.me|www\.|\badmin\b|\bbot\b|\bowner\b|\bcreator\b|\bvip\b", re.I)  # "Botir", "Admiral" - mumkin
# oddiy ismdagi "🎩 Pro … ☑️" / "👑 Creator … ✅" soxta belgi
_FAKE = re.compile(r"^[\s✅☑✔🌟⭐👑🎩\ufe0f]*(?:PRO|VIP|OWNER|CREATOR|𝐏𝐫𝐨|𝐕𝐢𝐩|𝐂𝐫𝐞𝐚𝐭𝐨𝐫)\b[\s:|·•-]*(.*?)[\s🔥👍✅☑✔\ufe0f]*$", re.I | re.S)


def _now() -> datetime:
    from .db import now
    return now()


def set_user(uid: int, until: datetime | None, nick: str | None, level: int | None = None,
             title: str | None = None) -> None:
    if until is None:
        CACHE.pop(uid, None)
    else:
        CACHE[uid] = (until, nick, level, title)


def load(rows) -> None:
    """rows: [(uid, pro_until, nickname, daraja, toifa)]"""
    CACHE.clear()
    for row in rows:
        set_user(*row)


def until(uid: int) -> datetime | None:
    v = CACHE.get(uid)
    return v[0] if v and v[0] > _now() else None


def is_pro(uid: int) -> bool:
    return until(uid) is not None


def _raw(uid: int) -> int | None:
    return CACHE[uid][2] if is_pro(uid) else 0


def tier(uid: int) -> int:
    """0 - Pro yo'q; 1..3. Eski (darajasiz) PRO - 3."""
    t = _raw(uid)
    return 3 if t is None else t


def title(uid: int) -> str | None:
    """Guruh egasi toifasi (saqlangan nomi "Shahar Mafia Owner"); bor bo'lsa ism oldida "Vip" yoziladi."""
    return CACHE[uid][3] if is_pro(uid) else None


_FANCY = {**{chr(65 + i): chr(0x1D468 + i) for i in range(26)}, **{chr(97 + i): chr(0x1D482 + i) for i in range(26)}}


_BOLD = {**{chr(65 + i): chr(0x1D400 + i) for i in range(26)}, **{chr(97 + i): chr(0x1D41A + i) for i in range(26)}}
# ism yonidagi yozuvlar matematik qalin shriftda: 𝐏𝐫𝐨 / 𝐕𝐢𝐩 / 𝐂𝐫𝐞𝐚𝐭𝐨𝐫
PRO_TAG, VIP_TAG, CREATOR_TAG = ("".join(_BOLD[c] for c in w) for w in ("Pro", "Vip", "Creator"))


def fancy(s: str) -> str:
    """Pro ismi: 𝑶𝒈'𝒂𝒃𝒆𝒌 (matematik qalin kursiv; lotin bo'lmagan harflar o'zgarmaydi)."""
    return "".join(_FANCY.get(c, c) for c in s)


NAME_MAX = 20  # botning hamma joyida ism shundan uzun bo'lsa "…" bilan qisqaradi (= nickname chegarasi)
MARKS_MAX = 2  # bir harf ustidagi urg'u/belgilar ("zalgo" ismlar qatorni bo'yiga cho'zadi)


def short(s: str) -> str:
    """Ko'rinadigan ism: ko'rinmas/yo'nalish belgilarisiz (emoji ZWJ qoladi), ortiqcha ustma-ust belgilarsiz, qisqa.
    USER belgisi bilan o'ralgan: ismdagi oddiy emoji premium emojiga almashtirilmaydi (emoji.py, matnda ham, tugmada ham);
    belgilar Telegramga yuborishdan oldin olib tashlanadi."""
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
    if any(unicodedata.bidirectional(c) in ("R", "AL") for c in s):
        # arabcha/ibroniycha ism: alohida "orolcha" LRM + (FSI..PDI) + LRM - ro'yxatdagi vergul va keyingi ismlar aralashmaydi
        s = "\u200e\u2068" + s + "\u2069\u200e"
    return f"{USER}{s or '?'}{USER}"


def name(uid: int, fallback: str) -> str:
    """Ko'rsatiladigan ism: Pro - qalin kursiv, Pro 3 (va egasi) nickname qo'ysa - nickname.
    Oddiy foydalanuvchi ismidagi "✅ PRO" olib tashlanadi."""
    if uid in FORCED:
        return short(fancy(FORCED[uid]) if is_pro(uid) else FORCED[uid])
    if is_pro(uid) or is_owner(uid):  # egasi Pro'siz ham nickname/haqiqiy ismini "Creator" bilan ko'rsatadi
        nick = CACHE[uid][1] if uid in CACHE and (tier(uid) >= 3 or is_owner(uid)) else None
        return short(fancy(nick or fallback))
    return short(_FAKE.sub(r"\1", fallback) or fallback)


def badge() -> str:
    return f'<tg-emoji emoji-id="{BADGE_ID}">{BADGE_FALLBACK}</tg-emoji>'


def tail() -> str:
    return f'<tg-emoji emoji-id="{TAIL_ID}">{TAIL_FALLBACK}</tg-emoji>'


def vip_tail() -> str:
    return f'<tg-emoji emoji-id="{VIP_TAIL_ID}">{VIP_TAIL_FALLBACK}</tg-emoji>'


def is_owner(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def owner_badge() -> str:
    return f'<tg-emoji emoji-id="{OWNER_ID}">{OWNER_FALLBACK}</tg-emoji>'


def owner_tail() -> str:
    return f'<tg-emoji emoji-id="{OWNER_TAIL_ID}">{OWNER_TAIL_FALLBACK}</tg-emoji>'


def label(uid: int, text: str) -> tuple[str, str | None]:
    """Tugma uchun: (matn, icon_custom_emoji_id). Egasi - Creator; toifa - "Vip"; Pro 3 - "Pro";
    Pro 2 - belgi ikonkasi; Pro 1 - faqat qalin kursiv ism."""
    n = name(uid, text)
    if is_owner(uid):
        return f"{CREATOR_TAG} {n}", OWNER_ID
    if title(uid):
        return f"{VIP_TAG} {n}", BADGE_ID
    lv = tier(uid)
    return (f"{PRO_TAG} {n}", BADGE_ID) if lv >= 3 else (n, BADGE_ID) if lv == 2 else (n, None)


def price(uid: int, base: int) -> int:
    return base * (100 - DISCOUNT[_raw(uid)]) // 100 if is_pro(uid) else base


def win_reward(uid: int) -> int:
    return config.REWARD_WIN * WIN[_raw(uid)] // 100 if is_pro(uid) else config.REWARD_WIN


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
