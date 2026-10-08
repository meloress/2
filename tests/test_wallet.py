"""Profil hamyoni: olmosga dollar, Stars bilan olmos (o'zim/birov uchun), shaxsiy chatda pul/olmos yuborish, top guruhlar."""
import asyncio
from types import SimpleNamespace

from mafia_zone import config, db, handlers, pro, runner, texts
from tests.test_money import BASE, bal, mkuser, set_games

U = BASE + 5000


def run(coro):
    async def go():
        await db.init()
        return await coro
    return asyncio.run(go())


async def gems(uid: int) -> int:
    return (await db.get_user(uid)).diamonds


def cq(uid: int, data: str, log: list):
    async def edit_text(text, reply_markup=None):
        log.append(("edit", text, reply_markup))

    async def answer(text=None, show_alert=False, **kw):
        log.append(("alert", text))

    async def m_answer(text=None, reply_markup=None, **kw):
        log.append(("msg", text, reply_markup))
    u = SimpleNamespace(id=uid, full_name=f"u{uid}", username=None, is_bot=False)
    return SimpleNamespace(data=data, from_user=u, answer=answer,
                           message=SimpleNamespace(edit_text=edit_text, answer=m_answer, chat=SimpleNamespace(id=uid)))


def msg(uid: int, text: str, log: list):
    async def answer(t=None, reply_markup=None, **kw):
        log.append(("msg", t, reply_markup))
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=uid, full_name=f"u{uid}", username=None),
                           chat=SimpleNamespace(id=uid), answer=answer, bot=None)


def cbs(kb) -> list[str]:
    return [b.callback_data or b.url for row in kb.inline_keyboard for b in row]


def test_packs_match_screenshot():
    assert config.DOLLAR_PACKS == {1: 300, 2: 600, 3: 800, 4: 1500, 15: 5000, 30: 10000}
    assert config.DIAMOND_STARS == {1: 7, 5: 35, 10: 66, 15: 101, 30: 202, 50: 342, 200: 1388, 500: 3488,
                                    1000: 6984, 2000: 13984}
    assert config.DIAMOND_RATE == 300


def test_buy_dollars_atomic():
    async def t():
        await mkuser(U, 0)
        await db.add_balance(U, 0, 3 - await gems(U))
        assert await db.buy_dollars(U, 2) and await bal(U) == 600 and await gems(U) == 1
        assert not await db.buy_dollars(U, 2) and await bal(U) == 600  # yetmaydi - hech narsa o'zgarmaydi
        assert not await db.buy_dollars(U, 7)  # bunday paket yo'q
        log = []
        await handlers.cb_wallet(cq(U, "xd:1", log))
        assert await bal(U) == 900 and await gems(U) == 0
    run(t())


def test_transfer_diamonds():
    async def t():
        a, b = U + 1, U + 2
        await mkuser(a, 0)
        await mkuser(b, 0)
        await db.add_balance(a, 0, 5 - await gems(a))
        assert await db.transfer(a, b, 3, "diamonds") and await gems(a) == 2 and await gems(b) >= 3
        assert not await db.transfer(a, b, 3, "diamonds") and await gems(a) == 2
    run(t())


def test_stars_diamonds_self_and_gift():
    async def t():
        payer, friend = U + 10, U + 11
        await mkuser(payer, 0)
        await db.upsert_user(friend, "Do'st", "dost_uz")
        g0, f0 = await gems(payer), await gems(friend)
        ok = []

        async def pcq_answer(ok_=None, error_message=None, **kw):
            ok.append(kw.get("ok", ok_))
        for amount, payload in ((35, "dm:5:0"), (34, "dm:5:0"), (7, f"dm:1:{friend}"), (7, "dm:1:999"), (7, "dm:2:0")):
            await handlers.on_pre_checkout(SimpleNamespace(invoice_payload=payload, total_amount=amount, currency="XTR",
                                                           from_user=SimpleNamespace(id=payer), answer=pcq_answer))
        assert ok == [True, False, True, False, False]
        said = []

        async def answer(text=None, **kw):
            said.append(text)

        def paid(payload, amount, charge):
            pay = SimpleNamespace(invoice_payload=payload, total_amount=amount, currency="XTR",
                                  telegram_payment_charge_id=charge)
            return SimpleNamespace(from_user=SimpleNamespace(id=payer, full_name="P", username=None),
                                   successful_payment=pay, answer=answer, bot=None)
        await handlers.on_paid(paid("dm:5:0", 35, "dmc1"))
        await handlers.on_paid(paid("dm:5:0", 35, "dmc1"))  # takror - hisoblanmaydi
        assert await gems(payer) == g0 + 5 and len(said) == 1
        runner.BOT = None
        sent = []

        async def fake_send(bot, chat_id, text, *a, **kw):
            sent.append((chat_id, text))
        old, handlers.send = handlers.send, fake_send
        try:
            await handlers.on_paid(paid(f"dm:10:{friend}", 66, "dmc2"))
        finally:
            handlers.send = old
        assert await gems(friend) == f0 + 10 and await gems(payer) == g0 + 5
        assert any(c == friend for c, _ in sent)  # do'stga sovg'a xabari
    run(t())


def test_gift_asks_recipient_then_shows_stars():
    async def t():
        payer, friend = U + 20, U + 21
        await mkuser(payer, 0)
        await db.upsert_user(friend, "Do'st", "dost_gift")
        log = []
        await handlers.cb_wallet(cq(payer, "gm:to", log))
        assert handlers.ASK[payer] == "to"
        await handlers.on_private_text(msg(payer, "@dost_gift", log))
        kb = log[-1][2]
        assert f"gs:5:{friend}" in cbs(kb) and payer not in handlers.ASK
        await handlers.cb_wallet(cq(payer, "gm:to", log))
        await handlers.on_private_text(msg(payer, "@yoq_odam", log))
        assert log[-1][1] == texts.WALLET_NO_USER
    run(t())


def test_private_send_money_and_diamonds():
    async def t():
        a, b = U + 30, U + 31
        await mkuser(a, 500)
        await mkuser(b, 0)
        await db.add_balance(a, 0, 4 - await gems(a))
        b0, bg0 = await bal(b), await gems(b)
        log = []
        await set_games(a, 0)
        await handlers.cb_menu(cq(a, "m:pay", log))
        assert texts.send_locked(0) in [x[1] for x in log]  # yangi profil yubora olmaydi
        await set_games(a, config.SEND_GAMES)
        sent = []

        async def fake_send(bot, chat_id, text, *a_, **kw):
            sent.append(chat_id)
        old, handlers.send = handlers.send, fake_send
        try:
            await handlers.cb_menu(cq(a, "m:pay", log))
            await handlers.on_private_text(msg(a, f"{b} 200", log))
            assert await bal(a) == 300 and await bal(b) == b0 + 200 and b in sent
            await handlers.cb_menu(cq(a, "m:gift", log))
            await handlers.on_private_text(msg(a, f"{b} 9", log))  # yetmaydi
            assert await gems(a) == 4 and log[-1][1] == texts.NO_DIAMONDS
            await handlers.cb_menu(cq(a, "m:gift", log))
            await handlers.on_private_text(msg(a, f"{b} 3", log))
            assert await gems(a) == 1 and await gems(b) == bg0 + 3
            await handlers.cb_menu(cq(a, "m:pay", log))
            await handlers.on_private_text(msg(a, "salom", log))  # noto'g'ri format - hech narsa o'tmaydi
            assert await bal(a) == 300 and log[-1][1] == texts.WALLET_FORMAT
            await handlers.cb_menu(cq(a, "m:pay", log))
            await handlers.on_private_text(msg(a, f"{a} 10", log))  # o'ziga - yo'q
            assert await bal(a) == 300
        finally:
            handlers.send = old
    run(t())


def test_profile_kb_layout_and_sections():
    async def t():
        await mkuser(U + 40, 0)
        kb = runner.profile_kb([], U + 40)
        c = cbs(kb)
        for d in ("m:pro", "m:buy", "m:gem", "m:pay", "m:gift", "m:groups", "shop", "m:home"):
            assert d in c, d
        assert "x" not in c  # Exchange tugmasi yo'q: dollar Xarid orqali olinadi
        log = []
        for what in ("buy", "gem", "groups"):
            await handlers.cb_menu(cq(U + 40, f"m:{what}", log))
            assert "m:profile" in cbs(log[-2][2] if log[-1][0] == "alert" else log[-1][2]), what
        await handlers.cb_wallet(cq(U + 40, "gm:me", log))
        edits = [x for x in log if x[0] == "edit"]
        assert "gs:2000:0" in cbs(edits[-1][2])
    run(t())


def test_top_groups():
    async def t():
        await db.group_settings(-100777, "Admiral guruh")
        gid = await db.create_game(-100777, {})
        await db.finish_game(gid, -100777, "finished", "town", [])
        rows = await db.top_groups()
        assert any(title == "Admiral guruh" and n >= 1 for title, n in rows)
        assert "Admiral guruh" in texts.top_groups(rows)
    run(t())
