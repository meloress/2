import asyncio

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from mafia_zone import emoji


@pytest.fixture(autouse=True)
def mapping():
    emoji.DISABLED = False
    emoji.load({"⚖️": "222", "💼": "555", "💣": "777", "🙂": "1", "🙂️": "2"})
    yield
    emoji.load({})
    emoji.DISABLED = False


def test_premiumize_only_known_and_whole_emoji():
    out = emoji.premiumize("⚖ sud · ⚖️ sud · 💣 Afsungar · 🤵🏻 Don · 👨‍💼 Advokat · 💼")
    assert out.count('emoji-id="222"') == 2 and '<tg-emoji emoji-id="777">💣</tg-emoji>' in out
    assert "🤵🏻 Don" in out  # to'plamda yo'q - oddiy qoladi
    assert "👨‍💼 Advokat" in out and out.endswith('<tg-emoji emoji-id="555">💼</tg-emoji>')  # ZWJ bo'lagi emas
    assert emoji.IDS["🙂"] == "1"  # takrorlansa birinchisi


def test_premiumize_skips_links_and_code():
    html = '💣 <a href="tg://user?id=1">💣 Ali</a> <code>💣</code> 💣'
    out = emoji.premiumize(html)
    assert out.count("tg-emoji emoji-id") == 2 and '<a href="tg://user?id=1">💣 Ali</a>' in out


def test_iconize_buttons():
    kb = emoji.iconize(Kb(inline_keyboard=[[Btn(text="⚖️ Ovoz", callback_data="x"),
                                            Btn(text="⚖️", callback_data="y"),
                                            Btn(text="🤵🏻 Don", callback_data="z", style="danger")]]))
    a, b, c = kb.inline_keyboard[0]
    assert (a.text, a.icon_custom_emoji_id) == ("Ovoz", "222")
    assert b.icon_custom_emoji_id is None  # faqat emoji bo'lsa, matn bo'sh qolmasin
    assert c.text == "🤵🏻 Don" and c.icon_custom_emoji_id is None and c.style == "danger"


def test_middleware_falls_back_and_disables():
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        if "tg-emoji" in method.text:
            raise TelegramBadRequest(method=method, message="Bad Request: custom emoji not allowed")
        return "ok"

    m = SendMessage(chat_id=1, text="⚖️ Sud", reply_markup=Kb(inline_keyboard=[[Btn(text="⚖️ Ovoz", callback_data="v")]]))
    assert asyncio.run(emoji.PremiumEmoji()(make_request, None, m)) == "ok"
    assert len(calls) == 2 and "tg-emoji" in calls[0].text and calls[1].text == "⚖️ Sud"
    assert calls[0].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id == "222"
    assert not emoji.IDS  # bir marta rad etilsa - o'chadi, keyingi xabarlar bir marta ketadi
    assert asyncio.run(emoji.PremiumEmoji()(make_request, None, m)) == "ok" and len(calls) == 3


def test_load_pack_failure_is_quiet():
    class Bot:
        async def get_sticker_set(self, name):
            raise RuntimeError("yo'q")
    asyncio.run(emoji.load_pack(Bot(), "Nope"))
    assert emoji.IDS  # fixture mosligi o'zgarmadi


def test_user_text_kept_as_sent():
    """O'yinchi yozgani (so'nggi so'z, o'liklar chati...): premium emoji saqlanadi, oddiy emoji almashtirilmaydi."""
    from aiogram.types import MessageEntity
    from mafia_zone import texts
    u16 = lambda s: len(s.encode("utf-16-le")) // 2  # Telegram ofsetlari UTF-16 da
    text = "xayr 💣 do'stlar 😎"
    at = u16(text[:text.index("😎")])
    ents = [MessageEntity(type="custom_emoji", offset=at, length=2, custom_emoji_id="999"),
            MessageEntity(type="bold", offset=0, length=4)]  # boshqa formatlash o'tmaydi
    said = texts.said(text, ents)
    assert '<tg-emoji emoji-id="999">😎</tg-emoji>' in said and "<b>" not in said
    out = emoji.premiumize("💣 " + texts.ghost("Ali", said))
    assert out.startswith('<tg-emoji emoji-id="777">💣</tg-emoji>')  # botning o'z matni - almashtiriladi
    assert "xayr 💣 do'stlar" in out and 'emoji-id="999"' in out and texts.USER_MARK not in out
    assert texts.USER_MARK not in emoji.premiumize(texts.said("salom"))
    assert texts.said("<b>x</b>") == f"{texts.USER_MARK}&lt;b&gt;x&lt;/b&gt;{texts.USER_MARK}"
    cut = texts.said("+  " + text, [MessageEntity(type="custom_emoji", offset=3 + at, length=2, custom_emoji_id="999")],
                     skip=3)  # "+" va bo'shliq olib tashlanadi
    assert cut.startswith(texts.USER_MARK + "xayr") and 'emoji-id="999">😎<' in cut
