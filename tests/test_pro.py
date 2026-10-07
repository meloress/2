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
    for bad in ("a", "x" * 21, "@ali", "t.me/x", "http://a", "www.a", "ADMIN", "my bot"):
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


def test_pro_perks_reward_and_shop():
    async def t():
        await db.init()
        p, o = 8_200_010, 8_200_011
        for u in (p, o):
            await db.upsert_user(u, f"u{u}", None)
        await db.set_pro(p, 7)
        gid = await db.create_game(-1990, {})
        await db.finish_game(gid, -1990, "finished", "town",
                             [(p, "tinch", "town", True, True), (o, "tinch", "town", True, True)])
        assert (await db.get_user(p)).dollars == config.REWARD_WIN * 3 // 2
        assert (await db.get_user(o)).dollars == config.REWARD_WIN
        await db.add_balance(p, 1000)
        before = (await db.get_user(p)).dollars
        assert await db.buy(p, "shield")
        assert before - (await db.get_user(p)).dollars == config.SHOP["shield"] * 3 // 4
        shop = texts.shop(500, p)
        assert f"<s>{config.SHOP['shield']}</s>" in shop and "-25%" in shop
        assert "<s>" not in texts.shop(500, o)
    asyncio.run(t())


def test_pro_spectator_writes_only_by_day():
    from mafia_zone import handlers
    from mafia_zone.engine.game import DAY, NIGHT, Game, Player
    pro.set_user(77, db.now() + timedelta(days=1), None)
    g = Game(-1, 1, [Player(1, "a", "tinch"), Player(2, "b", "don", alive=False)], phase=DAY)
    assert handlers.may_write(g, 77, "salom", False)          # PRO tomoshabin kunduzi
    assert not handlers.may_write(g, 78, "salom", False)      # oddiy tomoshabin
    pro.set_user(2, db.now() + timedelta(days=1), None)
    assert not handlers.may_write(g, 2, "salom", False)       # o'lgan PRO ham yo'q
    g.phase = NIGHT
    assert not handlers.may_write(g, 77, "salom", False)      # tunda yo'q


def test_pro_buttons_profile_and_lobby_name():
    from mafia_zone import runner
    from mafia_zone.engine.game import Game, Player
    pro.set_user(5, db.now() + timedelta(days=2), "Shoh")
    bot = SimpleNamespace()
    r = runner.Runner(bot, -1991, dict(config.DEFAULT_SETTINGS))
    assert r.join(5, "Ali") == texts.JOINED and r.members[-1] == (5, "Ali")  # nickname ko'rsatishda
    r.game = Game(-1991, 1, [Player(4, "Vali", "don"), Player(5, "Ali", "mafiya"), Player(6, "Hasan", "tinch")],
                  phase="voting")
    r.game_id = 3
    rows = r.vote_kb(4).inline_keyboard
    b = rows[0][0]
    assert b.text == "🤵🏼 PRO Shoh" and b.icon_custom_emoji_id == pro.BADGE_ID
    assert rows[1][0].text == "Hasan" and rows[1][0].icon_custom_emoji_id is None
    r.close()
    u = SimpleNamespace(telegram_id=5, full_name="Ali", wins=0, dollars=0, diamonds=0, games=0)
    card = texts.profile_card(u, [])
    assert pro.BADGE_ID in card and "Shoh" in card and "gacha" in card
    assert "gacha" not in texts.profile_card(SimpleNamespace(telegram_id=6, full_name="H", wins=0, dollars=0,
                                                             diamonds=0, games=0), [])


def test_stars_payment_flow():
    from mafia_zone import handlers

    async def t():
        await db.init()
        u = 8_200_020
        await db.upsert_user(u, "Ali", None)
        said, ok = [], []

        async def answer(text=None, **kw):
            said.append(text)

        async def pcq_answer(ok_=None, error_message=None, **kw):
            ok.append(kw.get("ok", ok_))
        for amount, payload in ((100, "pro:7"), (1, "pro:7"), (100, "pro:8"), (100, "xyz")):
            await handlers.on_pre_checkout(SimpleNamespace(invoice_payload=payload, total_amount=amount, currency="XTR",
                                                           from_user=SimpleNamespace(id=u), answer=pcq_answer))
        assert ok == [True, False, False, False]
        pay = SimpleNamespace(invoice_payload="pro:7", total_amount=100, currency="XTR", telegram_payment_charge_id="c9")
        m = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), successful_payment=pay,
                            answer=answer)
        await handlers.on_paid(m)
        await handlers.on_paid(m)  # Telegram takror yuborsa - ikkinchi marta hisoblanmaydi
        assert pro.is_pro(u) and len(said) == 1 and "PRO" in said[0]
        assert round((pro.until(u) - db.now()).total_seconds() / 86400) == 7
    asyncio.run(t())


def test_pro_menu_diamonds_and_nickname():
    from mafia_zone import handlers

    async def t():
        await db.init()
        u = 8_200_030
        await db.upsert_user(u, "Ali", None)
        alerts, shown = [], []

        async def cq_answer(text=None, show_alert=False):
            alerts.append(text)

        async def edit_text(text, reply_markup=None):
            shown.append((text, reply_markup))
        cq = lambda data: SimpleNamespace(data=data, from_user=SimpleNamespace(id=u, full_name="Ali", username=None),
                                          message=SimpleNamespace(edit_text=edit_text), answer=cq_answer, bot=None)
        await handlers.cb_menu(cq("m:pro"))
        text, kb = shown[-1]
        assert "PRO AKKAUNT" in text and "x1.5" in text
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert {"pro:d:7", "pro:s:7", "pro:d:30", "pro:s:30", "m:home"} <= set(cbs)
        await handlers.cb_pro(cq("pro:d:7"))  # olmos yo'q
        assert alerts[-1] == texts.PRO_NO_DIAMONDS and not pro.is_pro(u)
        await db.add_balance(u, 0, 30)
        await handlers.cb_pro(cq("pro:d:7"))
        assert pro.is_pro(u) and (await db.get_user(u)).diamonds == 0
        said = []

        async def answer(text=None, **kw):
            said.append(text)
        nick = lambda args: handlers.cmd_nickname(
            SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), answer=answer),
            SimpleNamespace(args=args))
        await nick("@shoh")
        assert "❌" in said[-1] and pro.name(u, "Ali") == "Ali"
        await nick("Shoh")
        assert pro.name(u, "Ali") == "Shoh" and (await db.get_user(u)).nickname == "Shoh"
        await nick(None)
        assert pro.name(u, "Ali") == "Ali"
        await db.set_pro(u, 0)
        await nick("Shoh")
        assert said[-1] == texts.NICK_ONLY_PRO
    asyncio.run(t())


def test_fix_nickname_not_frozen_into_game():
    from mafia_zone import runner
    from mafia_zone.engine.game import Game, Player
    pro.set_user(9, db.now() + timedelta(days=1), "Shoh")
    r = runner.Runner(SimpleNamespace(), -1992, dict(config.DEFAULT_SETTINGS))
    r.join(9, "Ali")
    assert r.members[-1] == (9, "Ali")  # haqiqiy ism saqlanadi, nickname ko'rsatishda qo'yiladi
    r.close()
    g = Game(-1, 1, [Player(9, "Ali", "don"), Player(10, "Vali", "mafiya")])
    assert texts.nm(g, 9) == "Shoh" and "Shoh" in texts.role_card(g, 10)
    pro.set_user(9, db.now() - timedelta(seconds=1), "Shoh")  # PRO tugadi
    assert texts.nm(g, 9) == "Ali" and "Shoh" not in texts.role_card(g, 10)
    assert "Shoh" not in texts.role_alert(g, 10)


def test_fix_non_pro_cannot_fake_badge():
    assert texts.mention(11, "✅ PRO Ali") == '<a href="tg://user?id=11">Ali</a>'
    assert pro.label(11, "PRO Ali") == ("Ali", None)
    assert texts.mention(11, "PRO") == '<a href="tg://user?id=11">PRO</a>'  # faqat "PRO" bo'lsa - qoladi
    assert texts.mention(11, "Prohor") == '<a href="tg://user?id=11">Prohor</a>'


def test_fix_nick_filter_words_and_control_chars():
    for ok in ("Botir", "Badminton", "Admiral"):
        assert pro.check_nick(ok) is None, ok
    for bad in ("bot", "Admin Ali", "Ali‮ilA", "A​dmin"):
        assert pro.check_nick(bad), bad


def test_fix_paid_db_failure_refunds_and_paysupport():
    from mafia_zone import handlers

    async def t():
        await db.init()
        u = 8_200_040
        await db.upsert_user(u, "Ali", None)
        said, refunds = [], []

        async def answer(text=None, **kw):
            said.append(text)

        async def refund(user_id, telegram_payment_charge_id):
            refunds.append((user_id, telegram_payment_charge_id))
        orig = db.add_pro

        async def boom(*a, **k):
            raise RuntimeError("db down")
        db.add_pro = boom
        try:
            pay = SimpleNamespace(invoice_payload="pro:7", total_amount=100, currency="XTR", telegram_payment_charge_id="c77")
            m = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), successful_payment=pay,
                                answer=answer, bot=SimpleNamespace(refund_star_payment=refund))
            await handlers.on_paid(m)
        finally:
            db.add_pro = orig
        assert refunds == [(u, "c77")] and "qaytarildi" in said[-1] and not pro.is_pro(u)
        await handlers.cmd_paysupport(SimpleNamespace(answer=answer))
        assert "/paysupport" not in said[-1] and "To'lov" in said[-1]
    asyncio.run(t())
