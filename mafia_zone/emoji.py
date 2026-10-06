"""Premium (custom) emoji. Bot egasi /emoji bilan oddiy emoji -> premium emoji moslaydi.

Session middleware Telegramga ketayotgan har bir xabar va tugmada mos emojini almashtiradi.
Telegram rad etsa (masalan, egasida Premium tugagan), xabar oddiy emoji bilan qayta yuboriladi.
"""
import logging
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendAnimation, SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .engine.roles import ACTION_LABELS, ROLES

log = logging.getLogger(__name__)
VS16 = "️"
IDS: dict[str, str] = {}  # oddiy emoji (VS16siz) -> custom_emoji_id
_pattern: re.Pattern | None = None


def norm(s: str) -> str:
    return s.replace(VS16, "")


def _first(label: str) -> str:
    return label.split(" ", 1)[0]


# /emoji menyusi uchun katalog: (emoji, izoh)
CATALOG: list[tuple[str, str]] = []
for _code, _r in ROLES.items():
    CATALOG.append((_first(_r.name), _r.name.split(" ", 1)[1]))
for _k, _label in ACTION_LABELS.items():
    CATALOG.append((_first(_label), _label.split(" ", 1)[1]))
for _ch in ("🌙 ☀️ 🗣 ⚖️ ☠️ 💀 💉 🌤 🏆 🏁 🎮 🎬 🎭 👥 ⏳ 🤫 🎯 💵 💎 🛡 🧄 📄 🎁 🔫 🔪 🪄 💥 💔 🔥 😴 🚪 🤷 🎉 "
            "😢 😱 👏 🤝 🔔 🛒 👤 📜 🥇 🥈 🥉 ✅ ❌ ⚠️ 🔍 🕯 💬 👂 ☝️ 🤐 💤 🎤 👀 ⛏ ⭐️ 😐 😔 🔁 🌫 🚬 🎊 🦇 🎒 🔁").split():
    CATALOG.append((_ch, ""))
_seen: set[str] = set()
CATALOG = [(c, d) for c, d in CATALOG if not (norm(c) in _seen or _seen.add(norm(c)))]


def load(mapping: dict[str, str]) -> None:
    global _pattern
    IDS.clear()
    IDS.update({norm(k): v for k, v in mapping.items()})
    keys = sorted(IDS, key=len, reverse=True)  # ZWJ ketma-ketliklari birinchi
    # har belgidan keyin VS16 ixtiyoriy: "⚖" va "⚖️" ikkalasi mos keladi
    opt = re.escape(VS16) + "?"
    _pattern = re.compile("|".join(opt.join(map(re.escape, k)) + opt for k in keys)) if keys else None


def premiumize(html: str) -> str:
    if not _pattern or not html:
        return html
    return _pattern.sub(lambda m: f'<tg-emoji emoji-id="{IDS[norm(m.group())]}">{m.group()}</tg-emoji>', html)


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


class PremiumEmoji(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        if not _pattern or not isinstance(method, (SendMessage, EditMessageText, EditMessageReplyMarkup,
                                                   SendAnimation)):
            return await make_request(bot, method)
        field = "caption" if isinstance(method, SendAnimation) else "text"
        text = getattr(method, field, None)
        kb = method.reply_markup
        new = method.model_copy(update={"reply_markup": iconize(kb)}
                                | ({field: premiumize(text)} if text is not None else {}))
        try:
            return await make_request(bot, new)
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                raise
            log.warning("premium emoji rad etildi, oddiy emoji bilan qayta yuborilmoqda: %s", e)
            return await make_request(bot, method)


def extract(text: str, entities) -> list[tuple[str, str]]:
    """Xabardagi custom emojilar: [(oddiy emoji, custom_emoji_id)]"""
    out = []
    for ent in entities or []:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            out.append((ent.extract_from(text), ent.custom_emoji_id))
    return out
