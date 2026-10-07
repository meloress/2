"""PRO obuna: kesh, belgi, imkoniyatlar, xarid."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from mafia_zone import config, db, emoji, pro, texts


def setup_function():
    pro.CACHE.clear()
    emoji.DISABLED = False


def test_badge_name_and_expiry():
    pro.set_user(1, db.now() + timedelta(days=3), "Shoh<b>")
    assert pro.is_pro(1) and pro.name(1, "Ali") == "Shoh<b>"
    m = texts.mention(1, "Ali")
    assert pro.BADGE_ID in m and "<b>PRO</b>" in m and "Shoh&lt;b&gt;" in m and "tg://user?id=1" in m
    pro.set_user(1, db.now() - timedelta(seconds=1), "Shoh")
    assert not pro.is_pro(1) and texts.mention(1, "Ali") == '<a href="tg://user?id=1">Ali</a>'


def test_perks_numbers():
    pro.set_user(2, db.now() + timedelta(days=1), None)
    assert pro.price(2, 100) == 75 and pro.price(3, 100) == 100
    assert pro.leave_free(2) == 5 and pro.leave_free(3) == config.LEAVE_FREE
    assert pro.win_reward(2) == config.REWARD_WIN * 3 // 2 and pro.win_reward(3) == config.REWARD_WIN
    assert pro.label(2, "Ali") == ("PRO Ali", pro.BADGE_ID) and pro.label(3, "Ali") == ("Ali", None)


def test_check_nick():
    assert pro.check_nick("Shoh") is None
    for bad in ("a", "x" * 21, "@ali", "t.me/x", "http://a", "www.a", "ADMIN", "mybot"):
        assert pro.check_nick(bad), bad


def test_custom_emoji_rejected_falls_back_to_plain():
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        icons = any(b.icon_custom_emoji_id for r in method.reply_markup.inline_keyboard for b in r)
        if "tg-emoji" in method.text or icons:
            raise TelegramBadRequest(method=method, message="Bad Request: custom emoji not allowed")
        return "ok"

    emoji.load({})  # to'plam bo'sh bo'lsa ham matndagi PRO belgisi tozalanadi
    m = SendMessage(chat_id=1, text=f"{pro.badge()} <b>PRO</b> Ali",
                    reply_markup=Kb(inline_keyboard=[[Btn(text="PRO Ali", callback_data="x",
                                                          icon_custom_emoji_id=pro.BADGE_ID)]]))
    assert asyncio.run(emoji.PremiumEmoji()(make_request, None, m)) == "ok"
    assert calls[-1].text == "✅ <b>PRO</b> Ali"
    assert calls[-1].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id is None
    n = len(calls)  # bir marta rad etilgach: keyingilari darhol oddiy yuboriladi
    assert asyncio.run(emoji.PremiumEmoji()(make_request, None, m)) == "ok" and len(calls) == n + 1


def test_pro_purchase_db():
    async def t():
        await db.init()
        u = 8_200_001
        await db.upsert_user(u, "Ali", None)
        await db.add_balance(u, 0, 40)
        until1 = await db.buy_pro_diamonds(u, 7)
        assert until1 and pro.is_pro(u) and (await db.get_user(u)).diamonds == 10
        assert await db.buy_pro_diamonds(u, 7) is None and (await db.get_user(u)).diamonds == 10  # yetmaydi
        assert await db.buy_pro_diamonds(u, 8) is None  # bunday paket yo'q
        until2 = await db.add_pro(u, 15, "stars", 150, "ch-1")
        assert round((until2 - until1).total_seconds() / 86400) == 15  # ustiga qo'shiladi
        assert await db.add_pro(u, 15, "stars", 150, "ch-1") is None  # takror to'lov
        await db.set_nickname(u, "Shoh")
        pro.CACHE.clear()
        await db.load_pro()
        assert pro.name(u, "Ali") == "Shoh"
        assert await db.pro_expiring(24 * 30) == [u] and await db.pro_expiring(24 * 30) == []  # bir marta
        await db.set_pro(u, 0)
        assert not pro.is_pro(u) and (await db.get_user(u)).pro_until is None
        await db.set_pro(u, 3)
        assert pro.is_pro(u) and pro.name(u, "Ali") == "Shoh"
    asyncio.run(t())
