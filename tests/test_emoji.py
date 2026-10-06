import asyncio

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, MessageEntity

from mafia_zone import emoji


@pytest.fixture(autouse=True)
def mapping():
    emoji.load({"🤵‍♂️": "111", "⚖️": "222", "🕵️‍♂️": "333", "🕵": "444"})
    yield
    emoji.load({})


def test_premiumize_variants_and_longest_match():
    out = emoji.premiumize("🤵‍♂️ Don · ⚖ sud · ⚖️ sud · 🕵️‍♂️ Komissar · 🤵 Mafiya")
    assert '<tg-emoji emoji-id="111">🤵‍♂️</tg-emoji> Don' in out
    assert out.count('emoji-id="222"') == 2
    assert '<tg-emoji emoji-id="333">🕵️‍♂️</tg-emoji>' in out and 'emoji-id="444"' not in out
    assert "🤵 Mafiya" in out  # mos emoji yo'q - tegilmaydi


def test_premiumize_empty_mapping():
    emoji.load({})
    assert emoji.premiumize("🤵‍♂️ Don") == "🤵‍♂️ Don"


def test_iconize_buttons():
    kb = emoji.iconize(Kb(inline_keyboard=[[Btn(text="🤵‍♂️ Don", callback_data="x"),
                                            Btn(text="🤵‍♂️", callback_data="y"),
                                            Btn(text="Ali", callback_data="z", style="danger")]]))
    a, b, c = kb.inline_keyboard[0]
    assert (a.text, a.icon_custom_emoji_id) == ("Don", "111")
    assert b.icon_custom_emoji_id is None  # faqat emoji bo'lsa, matn bo'sh qolmasin
    assert c.text == "Ali" and c.style == "danger"


def test_middleware_falls_back_on_reject():
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
    assert calls[1].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id is None


def test_extract_from_owner_message():
    text = "🤵‍♂️ va ⚖️"
    ents = [MessageEntity(type="custom_emoji", offset=0, length=len("🤵‍♂️".encode("utf-16-le")) // 2,
                          custom_emoji_id="999")]
    assert emoji.extract(text, ents) == [("🤵‍♂️", "999")]


def test_catalog_unique_and_covers_roles():
    chars = [emoji.norm(c) for c, _ in emoji.CATALOG]
    assert len(chars) == len(set(chars))
    assert emoji.norm("🤵‍♂️") in chars and emoji.norm("🧛") in chars


def test_emoji_pack_upload_flow(monkeypatch):
    from types import SimpleNamespace
    from mafia_zone import emoji_pack

    icons = [(c, b"png") for c, _ in emoji.CATALOG]
    monkeypatch.setattr(emoji_pack, "build", lambda: icons)
    calls = []

    class Bot:
        async def delete_sticker_set(self, name):
            raise RuntimeError("yo'q")  # birinchi marta - to'plam yo'q

        async def create_new_sticker_set(self, user_id, name, title, stickers, sticker_type):
            assert len(stickers) == 50 and sticker_type == "custom_emoji" and name == "mafiazone_by_testbot"
            calls.extend(stickers)

        async def add_sticker_to_set(self, user_id, name, sticker):
            calls.append(sticker)

        async def get_sticker_set(self, name):
            return SimpleNamespace(stickers=[SimpleNamespace(custom_emoji_id=str(i)) for i in range(len(calls))])

    ids = asyncio.run(emoji_pack.upload(Bot(), 42, "testbot"))
    assert len(calls) == len(icons) and len(ids) == len(icons)
    assert ids[emoji.norm(icons[0][0])] == "0" and ids[emoji.norm(icons[-1][0])] == str(len(icons) - 1)
    assert all(s.emoji_list == [c] for s, (c, _) in zip(calls, icons))


def test_badge_is_100px_png():
    from io import BytesIO
    from PIL import Image
    from mafia_zone import emoji_pack

    png = emoji_pack.badge(Image.new("RGBA", (72, 72), (255, 0, 0, 255)), (200, 30, 45))
    im = Image.open(BytesIO(png))
    assert im.size == (100, 100) and im.format == "PNG"
