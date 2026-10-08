"""Animatsion (custom) emoji. Ishga tushishda config.EMOJI_PACK to'plamidan oddiy emoji -> custom_emoji_id
olinadi; session middleware har bir xabar va tugmada to'plamda bor emojilarni almashtiradi, qolgani oddiy qoladi.
Telegram rad etsa (masalan, bot egasida Premium yo'q), xabar oddiy emoji bilan qayta yuboriladi va almashtirish
shu ishga tushish davomida o'chiriladi (har xabar ikki marta ketmasin).
"""
import logging
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendAnimation, SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)
VS16 = "️"
IDS: dict[str, str] = {}  # oddiy emoji (VS16siz) -> custom_emoji_id
_pattern: re.Pattern | None = None


def norm(s: str) -> str:
    return s.replace(VS16, "")


def load(mapping: dict[str, str]) -> None:
    global _pattern
    IDS.clear()
    for k, v in mapping.items():
        IDS.setdefault(norm(k), v)  # to'plamda takrorlansa - birinchisi
    keys = sorted(IDS, key=len, reverse=True)  # ZWJ ketma-ketliklari birinchi
    # har belgidan keyin VS16 ixtiyoriy: "⚖" va "⚖️" ikkalasi mos keladi.
    # Uzunroq emojining bo'lagi almashtirilmasin: oldida/ortida ZWJ yoki teri rangi bo'lmasin (👨‍💼 ichidagi 💼)
    opt = re.escape(VS16) + "?"
    body = "|".join(opt.join(map(re.escape, k)) + opt for k in keys)
    _pattern = re.compile(f"(?<!‍)(?:{body})(?![‍\U0001F3FB-\U0001F3FF])") if keys else None


async def load_pack(bot, name: str) -> None:
    if not name:
        return
    try:
        s = await bot.get_sticker_set(name)
    except Exception as e:  # to'plam topilmasa bot oddiy emoji bilan ishlayveradi
        log.warning("emoji to'plami %s yuklanmadi: %s", name, e)
        return
    load({x.emoji: x.custom_emoji_id for x in s.stickers if x.emoji and x.custom_emoji_id})
    log.info("emoji to'plami %s: %d ta", name, len(IDS))


# havola (o'yinchi ismlari), code/pre va mavjud tg-emoji ichiga tegilmaydi: ichma-ich entity rad etilishi mumkin
# USER: o'yinchi yozgan matn (texts.said) ikki tomonidan shu ko'rinmas belgi bilan o'ralgan - u aynan yuborilgandek qoladi
USER = "\u2063"
SKIP = re.compile(r"<(a|code|pre|tg-emoji)\b.*?</\1>|" + USER + ".*?" + USER, re.S)


def premiumize(html: str) -> str:
    """Matndagi oddiy emoji -> to'plamdagi animatsion emoji. USER belgilari har doim olib tashlanadi."""
    if not _pattern or not html:
        return html.replace(USER, "") if html else html
    sub = lambda s: _pattern.sub(lambda m: f'<tg-emoji emoji-id="{IDS[norm(m.group())]}">{m.group()}</tg-emoji>', s)
    out, i = [], 0
    for m in SKIP.finditer(html):
        out += [sub(html[i:m.start()]), m.group()]
        i = m.end()
    return ("".join(out) + sub(html[i:])).replace(USER, "")


def _icon_button(b: InlineKeyboardButton) -> InlineKeyboardButton:
    if b.icon_custom_emoji_id or not _pattern:
        return b
    m = _pattern.match(b.text)
    if not m or not b.text[m.end():].strip():
        return b
    return b.model_copy(update={"text": b.text[m.end():].strip(), "icon_custom_emoji_id": IDS[norm(m.group())]})


def iconize(kb):
    if not isinstance(kb, InlineKeyboardMarkup) or not _pattern:
        return kb
    return InlineKeyboardMarkup(inline_keyboard=[[_icon_button(b) for b in row] for row in kb.inline_keyboard])


TG_EMOJI = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)
DISABLED = False  # Telegram bir marta rad etgach: custom emoji'siz yuboriladi (qayta ishga tushguncha)
METHODS = (SendMessage, EditMessageText, EditMessageReplyMarkup, SendAnimation)


def _field(method) -> str:
    return "caption" if isinstance(method, SendAnimation) else "text"


def plain(method):
    """Custom emoji'siz nusxa: matndagi <tg-emoji> -> ichidagi oddiy emoji, tugma ikonkalari olib tashlanadi."""
    upd = {}
    if (t := getattr(method, _field(method), None)) is not None:
        upd[_field(method)] = TG_EMOJI.sub(r"\1", t)
    kb = method.reply_markup
    if isinstance(kb, InlineKeyboardMarkup):
        upd["reply_markup"] = InlineKeyboardMarkup(inline_keyboard=[
            [b.model_copy(update={"icon_custom_emoji_id": None}) for b in row] for row in kb.inline_keyboard])
    return method.model_copy(update=upd)


def _has_custom(method) -> bool:
    t = getattr(method, _field(method), None) or ""
    kb = method.reply_markup
    icons = isinstance(kb, InlineKeyboardMarkup) and any(b.icon_custom_emoji_id for r in kb.inline_keyboard for b in r)
    return "<tg-emoji" in t or icons


class PremiumEmoji(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        global DISABLED
        if not isinstance(method, METHODS):
            return await make_request(bot, method)
        text = getattr(method, _field(method), None)
        if text and USER in text:  # belgilar Telegramga bormasin
            method = method.model_copy(update={_field(method): text.replace(USER, "")})
        if DISABLED:
            return await make_request(bot, plain(method))
        new = method.model_copy(update={"reply_markup": iconize(method.reply_markup)}
                                | ({_field(method): premiumize(text)} if text is not None else {}))
        if not _has_custom(new):
            return await make_request(bot, method)
        try:
            return await make_request(bot, new)
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                raise
            res = await make_request(bot, plain(method))  # shu ham yiqilsa - xato emojida emas, odatdagidek ko'tariladi
            log.warning("custom emoji rad etildi, o'chirildi: %s", e)
            DISABLED = True
            load({})
            return res
