"""🛡 Guruh moderatsiyasi: .mute/.ban/.kick/.warn/.info/.admins, /report, reklama va so'kinishni avtomatik tozalash.

Aniqlagichlar (normalize, is_swear, ad_reason, parse_duration) - sof funksiyalar; Telegram bilan ishlaydigan qism pastda.
Spec: docs/superpowers/specs/2026-11-12-moderation-design.md"""
import re

from . import config

# ---------- so'kinish ----------
# Lotin/kirill, raqam-harf, cho'zish va ajratgichlar normalize() da bir xil ko'rinishga keltiriladi (q->k, h->x, apostrof yo'q,
# takror harflar bitta), shuning uchun ro'yxatdagi so'zlar ham shu shaklda solishtiriladi (_norm_list).
# EXACT - faqat butun so'z; PREFIX - so'z shu bilan boshlansa (o'zbekcha qo'shimchalar: jalablar, siktirsan);
# INSIDE - so'z ichida ham (qo'shib yozilgan: "onangnisikay"). Oddiy so'zlarga to'g'ri kelmaydiganlarigina bu yerda.
SWEAR_EXACT = ["suka", "suki", "blya", "xuy", "huy", "eban", "yeban", "pidor", "pidr", "mudak", "gandon", "qotaq",
               "jalap", "sik", "sikay", "ebal", "yebal", "ebalo", "yebalo"]  # "am", "suk", "skay" kabi qisqalari oddiy so'zlarga to'g'ri keladi - yo'q
SWEAR_PREFIX = ["jalab", "jalap", "qanjiq", "kanjik", "siktir", "sikay", "sikam", "sikdi", "sikib", "sikish", "sikkan",
                "sikip", "siksh", "sikmo", "qotoq", "qutoq", "kotok", "dalbayob", "dolboyob", "dolbaeb", "dalbaeb",
                "dolbayob", "blyat", "blyad", "pizd", "nahuy", "naxuy", "ebat", "yebat", "ebash",  # "ebal" - prefiks emas: "eballi" (barakalla)
                "yobany", "yoban", "pidaras", "pidoras", "pidar", "mudaki", "gandoni", "shlyux", "shlux", "zalup",
                "fohish", "haromzod", "suchka", "suchar", "ueban", "uyeban", "xuesos", "xuyes", "xuyn", "xuil", "xuev",
                "sukabl", "sukin"]
SWEAR_INSIDE = ["siktir", "sikay", "blyat", "pizd", "dalbayob", "dolboyob", "qanjiq", "jalab", "xuesos", "zalup"]

_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))
_LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "i"}
_APOS = "'`ʻʼ‘’"


def _base(word: str) -> str:
    """Bitta so'z (ajratgichsiz) - kichik harf, kirill -> lotin, harflar orasidagi raqam/belgi -> harf ("j4lab"),
    q->k, h->x, takror harflar bitta. So'z chetidagi raqam/belgi tashlanadi ("suka!" -> "suka", "blya100" -> "blya")."""
    w = [_CYR.get(ch, ch) for ch in word.lower()]
    alpha = [any(c.isalpha() for c in x) for x in w]
    out = []
    for i, ch in enumerate(w):
        if ch in _LEET and any(alpha[:i]) and any(alpha[i + 1:]):  # faqat so'z ichida
            ch = _LEET[ch]
        out.append(ch)
    s = "".join(out).replace("q", "k").replace("h", "x").replace("w", "v")
    s = "".join(c for c in s if c.isalpha() and c.isascii())
    return re.sub(r"(.)\1+", r"\1", s)


def _norm_list(words) -> list[str]:
    return sorted({_base(w.replace(" ", "")) for w in words if w and _base(w.replace(" ", ""))})


def tokens(text: str) -> list[str]:
    """Matndagi so'zlar normal shaklda. Harfma-harf ajratib yozilgani ("a h m o q", "j.a.l.a.b") - bitta so'z."""
    t = text.lower()
    for a in _APOS:
        t = t.replace(a, "")
    raw = [w for w in re.split(r"[^0-9a-zа-яёўқғҳ@$!|]+", t) if w]
    out, run = [], []
    for w in raw:
        b = _base(w)
        if len(b) == 1:  # bitta harf - ajratib yozilgan so'zning bo'lagi bo'lishi mumkin
            run.append(b)
            continue
        if len(run) >= 3:
            out.append("".join(run))
        out += [x for x in run if len(run) < 3]
        run = []
        if b:
            out.append(b)
    if len(run) >= 3:
        out.append("".join(run))
    else:
        out += run
    return out


def is_swear(text: str, extra: list[str] | None = None) -> bool:
    """So'kinish bormi. extra - panelda qo'shilgan so'zlar (PREFIX kabi ishlaydi)."""
    if not text:
        return False
    prefix = _PREFIX + _norm_list(extra or [])
    for w in tokens(text):
        if w in _EXACT or any(w.startswith(p) for p in prefix) or any(x in w for x in _INSIDE):
            return True
    return False


_EXACT, _PREFIX, _INSIDE = set(_norm_list(SWEAR_EXACT)), _norm_list(SWEAR_PREFIX), _norm_list(SWEAR_INSIDE)


# ---------- reklama ----------
TG_LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(\+?[\w-]+)", re.I)
WEB_LINK = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|ru|uz|net|org|io|me|info|xyz|site|online|shop|app)\b(?:/\S*)?",
                      re.I)


def _own(link: str, own: set[str]) -> bool:
    """Guruhning o'z havolasi yoki shu botning havolasi - reklama emas."""
    m = TG_LINK.search(link)
    return bool(m and m.group(1).lower().lstrip("+") in own)


def ad_reason(text: str, entities, own: set[str], forwarded_channel: bool = False, has_buttons: bool = False,
              channel_mentions: set[str] = frozenset()) -> str | None:
    """Xabar reklamami - sabab ("link"/"forward"/"buttons"/"mention") yoki None.
    own - ruxsat etilgan nomlar (kichik harf): guruh username'i, taklif havolasi kodi, bot username'i.
    channel_mentions - matndagi @username'lardan kanal/guruh/bot ekanligi aniqlanganlari (kichik harf)."""
    if forwarded_channel:
        return "forward"
    if has_buttons:
        return "buttons"
    text = text or ""
    links = [e.url for e in entities or () if e.type == "text_link" and e.url]
    links += [m.group(0) for m in TG_LINK.finditer(text)]
    links += [m.group(0) for m in WEB_LINK.finditer(text)]
    for link in links:
        if TG_LINK.search(link):
            if not _own(link, own):
                return "link"
        else:
            return "link"
    for name in channel_mentions:
        if name not in own:
            return "mention"
    return None


def mentions(text: str, entities) -> list[str]:
    """@username'lar (kichik harf, @siz) - kanal/bot ekanini Telegram'dan so'rab aniqlash uchun."""
    out = []
    for e in entities or ():
        if e.type == "mention":
            out.append(_slice(text, e.offset, e.length).lstrip("@").lower())
    return out


def _slice(text: str, offset: int, length: int) -> str:
    """Telegram ofsetlari UTF-16 birliklarida."""
    b = text.encode("utf-16-le")
    return b[offset * 2:(offset + length) * 2].decode("utf-16-le", "ignore")


# ---------- vaqt ----------
DUR = re.compile(r"^(\d{1,4})(m|min|daq|h|soat|s|d|kun|k|w)?$", re.I)
UNIT = {"m": 60, "min": 60, "daq": 60, "h": 3600, "soat": 3600, "s": 3600, "d": 86400, "kun": 86400, "k": 86400,
        "w": 604800}
MIN_MUTE, MAX_MUTE, DEFAULT_MUTE = 60, 365 * 86400, 3600  # Telegram: 30 s dan kam / 366 kundan ko'p - "abadiy"


def parse_duration(arg: str) -> int | None:
    """"30m" / "2h" / "1d" / "30" (daqiqa) -> soniya (MIN_MUTE..MAX_MUTE ga kesiladi); vaqt emas - None."""
    m = DUR.fullmatch((arg or "").strip())
    if not m:
        return None
    secs = int(m.group(1)) * UNIT[(m.group(2) or "m").lower()]
    return max(MIN_MUTE, min(MAX_MUTE, secs))


def split_args(args: str | None) -> tuple[int | None, str]:
    """".mute 30m sabab" -> (1800, "sabab"); vaqtsiz - (None, butun matn)."""
    parts = (args or "").strip().split(maxsplit=1)
    if parts and (secs := parse_duration(parts[0])) is not None:
        return secs, parts[1].strip() if len(parts) > 1 else ""
    return None, (args or "").strip()


def extra_words() -> list[str]:
    return list(config.BAD_WORDS)


# =====================================================================================================================
# Telegram qismi
import logging  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from aiogram import Bot, F, Router  # noqa: E402
from aiogram.filters import Command, CommandObject  # noqa: E402
from aiogram.types import (CallbackQuery, ChatPermissions, InlineKeyboardButton as Btn,  # noqa: E402
                           InlineKeyboardMarkup as Kb, Message)

from . import db, texts  # noqa: E402
from .runner import _call, send, send_eph  # noqa: E402

log = logging.getLogger(__name__)
router = Router(name="moderation")
GROUPS = F.chat.type.in_({"group", "supergroup"})
TZ = timezone(timedelta(hours=5))  # Toshkent
MOD_CMDS = ("mute", "unmute", "ban", "unban", "kick", "warn", "unwarn", "warns")
REPORT_MUTE = 30 * 60
CALL_GAP = 300  # .admins va /report: bir odam bir guruhda shu soniyada 1 marta
SETTINGS_TTL = 30  # guruh sozlamalari keshi (har xabarda bazaga bormaslik uchun)
ADMINS_TTL = 300
NAME_TTL = 86400  # @username kanalmi - kesh

_settings: dict[int, tuple[float, dict, str]] = {}  # chat -> (vaqt, sozlamalar, taklif havolasi)
_admins: dict[int, tuple[float, set[int]]] = {}
_names: dict[str, tuple[float, bool]] = {}  # @username -> (vaqt, kanal/guruh/botmi)
_calls: dict[tuple[str, int, int], float] = {}  # (tur, guruh, odam) -> oxirgi chaqiruv
REPORTS: dict[str, tuple[str, list[tuple[int, int]]]] = {}  # "chat:msg" -> (matn, [(admin, pm xabar)])
_DONE: set[str] = set()  # ponytail: hal qilingan reportlar xotirada; restartdan keyin eski tugma yana ishlaydi (zararsiz)


def forget(chat_id: int) -> None:
    """/settings o'zgarganda keshni tozalash (darhol kuchga kirsin)."""
    _settings.pop(chat_id, None)


async def settings(chat_id: int) -> tuple[dict, str]:
    t, s, inv = _settings.get(chat_id, (0.0, None, ""))
    if s is None or time.monotonic() - t > SETTINGS_TTL:
        s, inv = await db.group_settings(chat_id), await db.group_invite(chat_id)
        _settings[chat_id] = (time.monotonic(), s, inv)
    return s, inv


async def admin_ids(bot: Bot, chat_id: int) -> set[int]:
    t, ids = _admins.get(chat_id, (float("-inf"), set()))
    if time.monotonic() - t > ADMINS_TTL:
        got = await _call(bot.get_chat_administrators, chat_id)
        if got is not None:
            ids = {m.user.id for m in got}
        _admins[chat_id] = (time.monotonic(), ids)
    return ids


def _anon_admin(msg: Message) -> bool:
    return bool(msg.sender_chat and msg.sender_chat.id == msg.chat.id)


async def can_moderate(bot: Bot, chat_id: int, uid: int | None, msg: Message | None = None) -> bool:
    """Bot egasi, yashirin admin yoki "a'zolarni cheklash" huquqi bor admin / guruh egasi."""
    if msg is not None and _anon_admin(msg):
        return True
    if uid is None:
        return False
    if uid in config.ADMIN_IDS:
        return True
    m = await _call(bot.get_chat_member, chat_id, uid)
    return bool(m) and (m.status == "creator"
                        or (m.status == "administrator" and bool(getattr(m, "can_restrict_members", False))))


async def is_staff(bot: Bot, chat_id: int, uid: int) -> bool:
    """Jazolab bo'lmaydiganlar: bot egalari, guruh adminlari, botning o'zi."""
    return uid in config.ADMIN_IDS or uid == bot.id or uid in await admin_ids(bot, chat_id)


async def me_only(msg: Message, text: str) -> None:
    """Faqat yozganga ko'rinadigan javob (ephemeral); bo'lmasa oddiy javob."""
    if msg.from_user and not msg.sender_chat and await send_eph(msg.bot, msg.chat.id, msg.from_user.id, text):
        return
    await _call(msg.answer, text)


def _who(user) -> str:
    return texts.mention(user.id, user.full_name)


def _by(msg: Message) -> str:
    return "Admin" if _anon_admin(msg) or not msg.from_user else _who(msg.from_user)


def _target(msg: Message):
    """Reply qilingan odam (kanal posti yoki bog'langan kanal - yo'q)."""
    r = msg.reply_to_message
    if not r or not r.from_user or r.sender_chat or r.is_automatic_forward:
        return None
    return r.from_user


def msg_link(chat, msg_id: int) -> str | None:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{msg_id}"
    s = str(chat.id)
    return f"https://t.me/c/{s[4:]}/{msg_id}" if s.startswith("-100") else None


def _limited(kind: str, chat_id: int, uid: int) -> bool:
    now = time.monotonic()
    if now - _calls.get((kind, chat_id, uid), -CALL_GAP) < CALL_GAP:
        return True
    _calls[(kind, chat_id, uid)] = now
    return False


# ---------- jazolar (True - bajarildi) ----------
async def mute(bot: Bot, chat_id: int, uid: int, secs: int) -> bool:
    until = datetime.now(timezone.utc) + timedelta(seconds=secs)
    return bool(await _call(bot.restrict_chat_member, chat_id, uid, permissions=ChatPermissions(can_send_messages=False),
                            until_date=until))


FULL = dict(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True,
            can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True)


async def unmute(bot: Bot, chat_id: int, uid: int) -> bool:
    chat = await _call(bot.get_chat, chat_id)  # guruhning umumiy ruxsatlari qaytariladi
    perms = getattr(chat, "permissions", None) or ChatPermissions(**FULL)
    return bool(await _call(bot.restrict_chat_member, chat_id, uid, permissions=perms))


async def ban(bot: Bot, chat_id: int, uid: int) -> bool:
    ok = bool(await _call(bot.ban_chat_member, chat_id, uid))
    if ok:
        await db.clear_warns(chat_id, uid)
    return ok


async def warn(bot: Bot, chat_id: int, user, reason: str, admin_id: int | None, admin: str | None) -> str:
    """Ogohlantirish; chegaraga yetsa - ban. Guruhga yoziladigan matn qaytadi."""
    s, _ = await settings(chat_id)
    mx = int(s["mod_warn_max"])
    n = await db.add_warn(chat_id, user.id, reason, admin_id)
    if n >= mx and await ban(bot, chat_id, user.id):
        return texts.mod_warn_ban(_who(user), mx)
    return texts.mod_warned(_who(user), min(n, mx), mx, reason, admin)


# ---------- buyruqlar ----------
@router.message(Command(*MOD_CMDS, prefix="./", ignore_case=True), GROUPS)
async def cmd_mod(msg: Message, bot: Bot, command: CommandObject):
    name = command.command.lower()
    await _call(msg.delete)
    if msg.sender_chat and not _anon_admin(msg):
        return  # kanal nomidan yozilgan
    chat = msg.chat.id
    if name != "warns" and not await can_moderate(bot, chat, msg.from_user.id if msg.from_user else None, msg):
        return await me_only(msg, texts.MOD_ONLY_ADMIN)
    t = _target(msg)
    if not t:
        return await me_only(msg, texts.MOD_HOW[name])
    s, _ = await settings(chat)
    mx = int(s["mod_warn_max"])
    if name == "warns":
        items = [w for w in await db.warns(chat, t.id)]
        for w in items:
            w.created_at = db._aware(w.created_at)
        return await send(bot, chat, texts.mod_warn_list(_who(t), items, mx, db.now()))
    if name not in ("unmute", "unban", "unwarn") and await is_staff(bot, chat, t.id):
        return await me_only(msg, texts.MOD_NOT_STAFF)
    secs, reason = split_args(command.args)
    by = _by(msg)
    by_id = msg.from_user.id if msg.from_user and not _anon_admin(msg) else None
    if name == "mute":
        secs = secs or DEFAULT_MUTE
        ok, text = await mute(bot, chat, t.id, secs), texts.mod_muted(_who(t), secs, reason, by)
    elif name == "unmute":
        ok, text = await unmute(bot, chat, t.id), texts.mod_unmuted(_who(t), by)
    elif name == "ban":
        ok, text = await ban(bot, chat, t.id), texts.mod_banned(_who(t), reason, by)
    elif name == "unban":
        ok = bool(await _call(bot.unban_chat_member, chat, t.id, only_if_banned=True))
        text = texts.mod_unbanned(_who(t), by)
    elif name == "kick":
        ok = bool(await _call(bot.ban_chat_member, chat, t.id))
        if ok:
            await _call(bot.unban_chat_member, chat, t.id, only_if_banned=True)
        text = texts.mod_kicked(_who(t), reason, by)
    elif name == "warn":
        ok, text = True, await warn(bot, chat, t, reason, by_id, by)
    else:  # unwarn
        left = await db.pop_warn(chat, t.id)
        ok = True
        text = texts.mod_no_warns(_who(t)) if left is None else texts.mod_unwarned(_who(t), left, mx)
    if not ok:
        return await me_only(msg, texts.MOD_NO_RIGHTS)
    await send(bot, chat, text)


# ---------- avtomatik: reklama va so'kinish (handlers.drop_commands chaqiradi) ----------
async def _channel_mentions(bot: Bot, names: list[str], own: set[str]) -> set[str]:
    """@username'lardan kanal/guruh/bot bo'lganlari (Telegram'dan so'raladi, kesh 1 kun; bir xabarda ko'pi bilan 3 ta)."""
    out = set()
    for name in [n for n in names if n not in own][:3]:
        t, is_chan = _names.get(name, (float("-inf"), False))
        if time.monotonic() - t > NAME_TTL:
            if name.endswith("bot"):
                is_chan = True
            else:
                chat = await _call(bot.get_chat, "@" + name)  # odamni username bilan olib bo'lmaydi -> None
                is_chan = bool(chat and chat.type in ("channel", "group", "supergroup"))
            _names[name] = (time.monotonic(), is_chan)
        if is_chan:
            out.add(name)
    return out


async def auto(msg: Message, bot: Bot) -> bool:
    """Yoqilgan guruhda reklama/so'kinish: True - xabar o'chirildi (boshqa handlerlarga o'tmaydi)."""
    if msg.chat.type not in ("group", "supergroup") or not msg.from_user or msg.is_automatic_forward:
        return False
    if msg.sender_chat or msg.new_chat_members or msg.left_chat_member:
        return False
    s, invite = await settings(msg.chat.id)
    if not (s.get("mod_ads") or s.get("mod_swear")):
        return False
    uid, chat = msg.from_user.id, msg.chat.id
    if uid in config.ADMIN_IDS or uid in await admin_ids(bot, chat):
        return False
    text, ents = msg.text or msg.caption or "", msg.entities or msg.caption_entities or []
    if s.get("mod_swear") and is_swear(text, extra_words()):
        if not await _call(msg.delete):
            return False  # o'chirib bo'lmadi (huquq yo'q) - jazo ham yo'q
        secs = int(s["mod_swear_min"]) * 60
        if await mute(bot, chat, uid, secs):
            await send(bot, chat, texts.mod_swear_muted(_who(msg.from_user), secs))
        return True
    if s.get("mod_ads"):
        from . import runner
        own = {x.lower() for x in (msg.chat.username, runner.BOT_USERNAME, invite.rsplit("/", 1)[-1].lstrip("+")) if x}
        origin = getattr(msg, "forward_origin", None)
        reason = ad_reason(text, ents, own,
                           forwarded_channel=getattr(origin, "type", None) in ("channel", "chat"),
                           has_buttons=bool(msg.reply_markup and msg.reply_markup.inline_keyboard),
                           channel_mentions=await _channel_mentions(bot, mentions(text, ents), own))
        if reason:
            if not await _call(msg.delete):
                return False
            n = await db.add_warn(chat, uid, texts.MOD_WHY[reason], None)
            mx = int(s["mod_warn_max"])
            if n >= mx and await ban(bot, chat, uid):
                await send(bot, chat, texts.mod_warn_ban(_who(msg.from_user), mx))
            else:
                await send(bot, chat, texts.mod_ad_warned(_who(msg.from_user), min(n, mx), mx))
            return True
    return False


# ---------- /report ----------
def _report_kb(chat, target: int, mid: int) -> Kb:
    btn = lambda a: Btn(text=texts.REPORT_ACTS[a], callback_data=f"rp:{chat.id}:{target}:{mid}:{a}")
    rows = [[btn("m"), btn("b")], [btn("d"), btn("ok")]]
    if link := msg_link(chat, mid):
        rows.insert(0, [Btn(text=texts.GO_TO_MSG_BTN, url=link)])
    return Kb(inline_keyboard=rows)


@router.message(Command("report", prefix="./", ignore_case=True), GROUPS)
async def cmd_report(msg: Message, bot: Bot, command: CommandObject):
    await _call(msg.delete)
    if not msg.from_user or msg.sender_chat:
        return
    chat = msg.chat
    s, _ = await settings(chat.id)
    if not s.get("mod_report", True):
        return await me_only(msg, texts.REPORT_OFF)
    r = msg.reply_to_message
    if not r:
        return await me_only(msg, texts.REPORT_HOW)
    if _limited("report", chat.id, msg.from_user.id):
        return await me_only(msg, texts.REPORT_WAIT)
    tu = r.from_user if r.from_user and not r.sender_chat else None
    target = _who(tu) if tu else texts.escape(getattr(r.sender_chat, "title", None) or "?")
    text = texts.report_pm(chat.title or "?", _who(msg.from_user), target, (command.args or "").strip(),
                           r.text or r.caption or "")
    kb = _report_kb(chat, tu.id if tu else 0, r.message_id)
    sent = []
    for a in await _call(bot.get_chat_administrators, chat.id) or []:
        if a.user.is_bot:
            continue
        m = await send(bot, a.user.id, text, kb)
        if m:
            sent.append((a.user.id, m.message_id))
    REPORTS[f"{chat.id}:{r.message_id}"] = (text, sent)
    await me_only(msg, texts.REPORT_SENT if sent else texts.REPORT_NOBODY)


@router.callback_query(F.data.startswith("rp:"))
async def cb_report(cq: CallbackQuery, bot: Bot):
    try:
        _, chat, target, mid, act = cq.data.split(":")
        chat, target, mid = int(chat), int(target), int(mid)
    except ValueError:
        return await cq.answer()
    if act not in texts.REPORT_ACTS or not await can_moderate(bot, chat, cq.from_user.id):
        return await cq.answer(texts.MOD_ONLY_ADMIN, show_alert=True)
    key = f"{chat}:{mid}"
    if key in _DONE:
        return await cq.answer(texts.REPORT_ALREADY, show_alert=True)
    if act in ("m", "b") and target and await is_staff(bot, chat, target):
        return await cq.answer(texts.MOD_NOT_STAFF, show_alert=True)
    ok = True
    if act == "m" and target:
        ok = await mute(bot, chat, target, REPORT_MUTE)
    elif act == "b" and target:
        ok = await ban(bot, chat, target)
    if not ok:
        return await cq.answer(texts.MOD_NO_RIGHTS, show_alert=True)
    if act != "ok":
        await _call(bot.delete_message, chat, mid)
    _DONE.add(key)
    text, copies = REPORTS.pop(key, (getattr(cq.message, "html_text", None) or "🚨 Report", []))
    if not copies and cq.message:
        copies = [(cq.from_user.id, cq.message.message_id)]
    done = texts.report_done(text, _who(cq.from_user), act)
    for uid, m in copies:
        await _call(bot.edit_message_text, text=done, chat_id=uid, message_id=m, disable_web_page_preview=True)
    await cq.answer("✅")


# ---------- .admins ----------
@router.message(Command("admins", prefix="./", ignore_case=True), GROUPS)
async def cmd_admins(msg: Message, bot: Bot):
    await _call(msg.delete)
    if not msg.from_user or (msg.sender_chat and not _anon_admin(msg)):
        return
    chat = msg.chat
    if _limited("admins", chat.id, msg.from_user.id):
        return await me_only(msg, texts.ADMINS_WAIT)
    admins = [a.user for a in await _call(bot.get_chat_administrators, chat.id) or []
              if not a.user.is_bot and not getattr(a, "is_anonymous", False)]
    if not admins:
        return await me_only(msg, texts.ADMINS_NONE)
    caller = "Admin" if _anon_admin(msg) else _who(msg.from_user)
    reply = msg.reply_to_message.message_id if msg.reply_to_message else None
    m = await send(bot, chat.id, texts.admins_called(caller, [_who(a) for a in admins]), reply_to=reply)
    link = msg_link(chat, m.message_id) if m else None
    kb = Kb(inline_keyboard=[[Btn(text=texts.GO_TO_MSG_BTN, url=link)]]) if link else None
    for a in admins:
        await send(bot, a.id, texts.admins_called_pm(chat.title or "?", caller), kb)


# ---------- .info ----------
def _fmt(dt: datetime | None) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d") if dt else ""


def _status(m) -> str:
    st = getattr(m, "status", None)
    if st == "creator":
        return "👑 guruh egasi"
    if st == "administrator":
        return "👮 admin"
    if st == "kicked":
        return "🚫 ban"
    if st == "left":
        return "🚪 guruhda emas"
    if st == "restricted" and not getattr(m, "can_send_messages", True):
        until = getattr(m, "until_date", None)
        if until and until.year > 1970:
            return f"🔇 mute ({until.astimezone(TZ).strftime('%Y-%m-%d %H:%M')} gacha)"
        return "🔇 mute (muddatsiz)"
    return "a'zo" if st else "—"


@router.message(Command("info", prefix="./", ignore_case=True), GROUPS)
async def cmd_info(msg: Message, bot: Bot):
    await _call(msg.delete)
    if msg.sender_chat and not _anon_admin(msg):
        return
    u = _target(msg) or msg.from_user
    if not u:
        return
    chat = msg.chat.id
    member = await _call(bot.get_chat_member, chat, u.id)
    s, _ = await settings(chat)
    ws = await db.warns(chat, u.id)
    mx = int(s["mod_warn_max"])
    warns = f"<b>{len(ws)}/{mx}</b>" + (f" (oxirgisi: {texts.escape(ws[-1].reason or '—')}, "
                                        f"{texts._ago(db._aware(ws[-1].created_at), db.now())})" if ws else "")
    info = await db.member_info(chat, u.id)
    if info["joined"]:
        joined = f"📅 Guruhga qo'shilgan: {_fmt(info['joined'])}"
    elif info["first"]:
        joined = f"📅 Botda birinchi ko'rilgan: {_fmt(info['first'])}"
    else:
        joined = "📅 Guruhga qo'shilgan: ma'lum emas"
    await send(bot, chat, texts.user_info(_who(u), u.id, u.username, _status(member), warns, joined,
                                          info["games"], info["wins"]))
