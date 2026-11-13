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
    async def edit_text(text, reply_markup=None, **kw):
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
    assert config.DIAMOND_STARS == {1: 6, 7: 39, 15: 83, 30: 160, 55: 285, 100: 500, 250: 1200, 500: 2313, 1000: 4450}
    assert config.DIAMOND_SUM == {1: 1150, 7: 7850, 15: 16500, 30: 32000, 55: 57000, 100: 100000, 250: 240000,
                                  500: 462500, 1000: 890000}
    assert set(config.DIAMOND_SUM) == set(config.DIAMOND_STARS)  # karta va Stars paketlari bir xil
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
        for amount, payload in ((39, "dm:7:0"), (38, "dm:7:0"), (6, f"dm:1:{friend}"), (6, "dm:1:999"), (6, "dm:2:0")):
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
        await handlers.on_paid(paid("dm:7:0", 39, "dmc1"))
        await handlers.on_paid(paid("dm:7:0", 39, "dmc1"))  # takror - hisoblanmaydi
        assert await gems(payer) == g0 + 7 and len(said) == 1
        await handlers.on_paid(paid("dm:5:0", 35, "dmc-old"))  # eski paket (deploy payti to'langan) - baribir tushadi
        g0 += 5
        assert await gems(payer) == g0 + 7
        runner.BOT = None
        sent = []

        async def fake_send(bot, chat_id, text, *a, **kw):
            sent.append((chat_id, text))
        old, handlers.send = handlers.send, fake_send
        try:
            await handlers.on_paid(paid(f"dm:15:{friend}", 83, "dmc2"))
        finally:
            handlers.send = old
        assert await gems(friend) == f0 + 15 and await gems(payer) == g0 + 7
        assert any(c == friend for c, _ in sent)  # do'stga sovg'a xabari
    run(t())


def test_gift_asks_recipient_then_shows_shop():
    async def t():
        payer, friend = U + 20, U + 21
        await mkuser(payer, 0)
        await db.upsert_user(friend, "Do'st", "dost_gift")
        log = []
        await handlers.cb_wallet(cq(payer, "gm:to", log))
        assert handlers.ASK[payer] == "to"
        await handlers.on_private_text(msg(payer, "@dost_gift", log))
        kb = log[-1][2]
        assert f"gc:15:{friend}" in cbs(kb) and f"gx:{friend}" in cbs(kb) and payer not in handlers.ASK
        await handlers.cb_card(cq(payer, f"gx:{friend}", log))  # Stars paketlari ham do'stga
        assert f"gs:7:{friend}" in cbs(log[-2][2]) and f"gp:{friend}" in cbs(log[-2][2])
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
        assert texts.ask_send("dollars") in [x[1] for x in log]  # yangi profil ham yubora oladi
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
        assert "gc:1000:0" in cbs(edits[-1][2]) and "gx:0" in cbs(edits[-1][2])  # karta paketlari + Stars
    run(t())


def test_top_groups():
    async def t():
        await db.group_settings(-100777, "Admiral guruh")
        gid = await db.create_game(-100777, {})
        await db.finish_game(gid, -100777, "finished", "town", [])
        for _ in range(3):
            gid = await db.create_game(-100777, {})
            await db.finish_game(gid, -100777, "finished", "town", [])
        rows = await db.top_groups(None)  # 4 o'yin = 1 ball
        assert any(r["title"] == "Admiral guruh" and r["games"] >= 4 and r["points"] >= 1 for r in rows)
        assert "Admiral guruh" in texts.top_groups(rows)
    run(t())


def test_start_menu_shows_only_featured_groups():
    """/start menyusida faqat qo'lda tanlangan guruh(lar): avtomatik "eng faol guruhlar" yo'q."""
    async def t():
        await db.group_settings(-100881, "Begona guruh", "begona_mafia")
        gid = await db.create_game(-100881, {})
        await db.finish_game(gid, -100881, "finished", "town", [])
        kb = handlers.start_kb(U)
        urls = {b.url: b.text for row in kb.inline_keyboard for b in row if b.url}
        assert urls["https://t.me/+OVoKusV3WqphZWUy"] == "𝐒𝐊𝐀𝐑𝐅𝐀𝐂𝐄 𝐌𝐀𝐅𝐈𝐀 🥷🏻"
        assert not any("begona_mafia" in u for u in urls)
    run(t())


def test_pro_screen_offers_card_payment_via_admin():
    """Pro daraja ekranida pastda: karta orqali - admin bilan bog'lanish tugmasi. Olmosda karta o'z oqimi bilan."""
    url = f"https://t.me/{config.CARD_ADMIN}"
    for lv in (1, 2, 3):
        rows = handlers.tier_kb(lv).inline_keyboard
        assert rows[-2][0].url == url and rows[-2][0].text == texts.CARD_BTN  # orqaga tugmasidan oldin
        assert texts.CARD_NOTE in texts.pro_tier(1, lv, "Ali") and "@" + config.CARD_ADMIN in texts.pro_tier(1, lv, "Ali")
    assert cbs(handlers.stars_kb(5))[-1] == "gp:5"  # Stars -> orqaga karta paketlariga


def test_card_order_check_photo_to_admin_approves_once():
    """Karta: paket -> to'lov ekrani -> chek rasmi -> adminga ma'lumot bilan; tasdiq bir marta, sabab bilan rad."""
    async def t():
        payer, friend = U + 60, U + 61
        for u in (payer, friend):
            await mkuser(u, 0)
        admin = next(iter(config.ADMIN_IDS), 1)
        sent, photos = [], []
        old_send, old_card, old_admins = handlers.send, config.CARD_NUMBER, config.ADMIN_IDS

        async def fake_send(bot, chat_id, text, kb=None, **kw):
            sent.append((chat_id, text, kb))

        reach = [True]  # False - bot adminga yoza olmaydi

        async def send_photo(chat_id, photo, caption=None, reply_markup=None, **kw):
            photos.append((chat_id, photo, caption, reply_markup))
            return SimpleNamespace(message_id=1) if reach[0] else None

        def c(uid, data, log):
            q = cq(uid, data, log)
            q.bot = None

            async def edit_caption(caption=None, **kw):
                log.append(("caption", caption))
            q.message.html_text, q.message.edit_caption = "💳 chek", edit_caption
            return q

        def photo(uid, log, text=None, same="U1"):
            async def answer(t=None, reply_markup=None, **kw):
                log.append(("msg", t, reply_markup))
            return SimpleNamespace(from_user=SimpleNamespace(id=uid, full_name=f"u{uid}", username="pul_uz"),
                                   photo=[SimpleNamespace(file_id="small", file_unique_id="s"),
                                          SimpleNamespace(file_id="CHEK1", file_unique_id=same)],
                                   document=None, text=text, answer=answer,
                                   bot=SimpleNamespace(send_photo=send_photo, send_document=send_photo))

        def order_id(kb) -> int:
            return int(next(x for x in cbs(kb) if x and x.startswith("ox:"))[3:])
        handlers.send, config.ADMIN_IDS = fake_send, {admin}
        try:
            log = []
            config.CARD_NUMBER = ""
            await handlers.cb_card(c(payer, "gc:15:0", log))
            assert log[-1] == ("alert", texts.card_off())  # karta sozlanmagan
            config.CARD_NUMBER = "5614684605535200"
            await handlers.cb_card(c(payer, f"gc:15:{friend}", log))
            text, kb = log[-2][1], log[-2][2]
            assert "5614 6846 0553 5200" in text and "16 500 so'm" in text and "TOP-" in text and "chek" in text
            assert kb.inline_keyboard[0][0].copy_text.text == "5614684605535200"
            oid = order_id(kb)
            await handlers.on_private_text(msg(payer, "to'ladim", log))  # matn - chek emas, hali kutiladi
            assert log[-1][1] == texts.CHECK_NEED_PHOTO and handlers.ASK[payer] == f"chek:{oid}"
            await handlers.on_check(photo(payer, log))
            o = await db.get_card_order(oid)
            assert o.status == "paid" and o.check_file == "CHEK1" and payer not in handlers.ASK
            to, file_id, caption, akb = photos[-1]
            assert to == admin and file_id == "CHEK1" and f"#TOP-{oid}" in caption and "@pul_uz" in caption
            assert "16 500 so'm" in caption and "···· 5200" in caption and str(payer) in caption
            assert cbs(akb) == [f"oa:{oid}:1", f"oa:{oid}:n", f"oa:{oid}:s", f"oa:{oid}:c"]
            await handlers.on_check(photo(payer, log))  # ikkinchi rasm - kutilmagan, e'tiborsiz
            assert len(photos) == 1
            g0 = await gems(friend)
            await handlers.cb_order_admin(c(admin, f"oa:{oid}:1", log))
            await handlers.cb_order_admin(c(admin, f"oa:{oid}:1", log))  # ikkinchi bosish - hech narsa
            assert await gems(friend) == g0 + 15 and log[-1] == ("alert", texts.ORDER_DONE_ALREADY)
            assert any(x[0] == "caption" and "Tasdiqlandi" in x[1] for x in log)
            assert {u for u, *_ in sent[-2:]} == {payer, friend}
            # rad etish (summa boshqa): olmos tushmaydi, to'lovchiga sabab.
            # Shu orada bot qayta ishga tushdi (ASK xotirada yo'qoldi) va o'sha chek qayta yuborildi
            await handlers.cb_card(c(payer, "gc:1:0", log))
            oid2 = order_id(log[-2][2])
            handlers.ASK.clear()
            await handlers.on_check(photo(payer, log))
            assert (await db.get_card_order(oid2)).status == "paid"  # restartdan keyin ham qabul qilindi
            assert f"avval #TOP-{oid}" in photos[-1][2]  # bir chek ikki buyurtmada - adminga ogohlantirish
            p0 = await gems(payer)
            await handlers.cb_order_admin(c(admin, f"oa:{oid2}:s", log))
            o2 = await db.get_card_order(oid2)
            assert await gems(payer) == p0 and o2.status == "rejected" and o2.reason == "s"
            assert sent[-1][0] == payer and texts.REJECT_TELL["s"] in sent[-1][1]
            # bekor qilish; 7 daqiqadan keyin kelgan chek adminga bormaydi
            await handlers.cb_card(c(payer, "gc:7:0", log))
            oid3 = order_id(log[-2][2])
            await handlers.cb_card(c(payer, f"ox:{oid3}", log))
            assert (await db.get_card_order(oid3)).status == "cancelled" and payer not in handlers.ASK
            await handlers.cb_card(c(payer, "gc:7:0", log))
            oid4 = order_id(log[-2][2])
            async with db.Session.begin() as s:
                await s.execute(db.update(db.CardOrder).where(db.CardOrder.id == oid4)
                                .values(created_at=db.now() - db.timedelta(minutes=8)))
            n = len(photos)
            await handlers.on_check(photo(payer, log, same="U4"))
            assert (await db.get_card_order(oid4)).status == "expired" and len(photos) == n
            assert texts.order_expired() == log[-1][1]
            # chek hech bir adminga yetmadi - foydalanuvchiga aytiladi, kutib qolmaydi
            reach[0] = False
            await handlers.cb_card(c(payer, "gc:7:0", log))
            oid5 = order_id(log[-2][2])
            await handlers.on_check(photo(payer, log, same="U5"))
            assert log[-1][1] == texts.check_not_delivered(await db.get_card_order(oid5))
            assert "TOP-" not in photos[-1][2].split("Karta to'lovi")[0]  # yangi chek - ogohlantirishsiz
            # /cheklar: cheklar guruhga boradi (shaxsiyga emas); guruhga yetmasa - egalarga shaxsiy
            reach[0] = True
            said = []
            gmsg = SimpleNamespace(chat=SimpleNamespace(id=-5551, type="supergroup"),
                                   answer=lambda t, **kw: asyncio.sleep(0, said.append(t)))
            await handlers.cmd_orders_chat(gmsg)
            assert config.ORDERS_CHAT == -5551 and said[-1] == texts.ORDERS_HERE
            await handlers.cb_card(c(payer, "gc:7:0", log))
            await handlers.on_check(photo(payer, log, same="U6"))
            assert [x[0] for x in photos[-1:]] == [-5551]
            n = len(photos)
            reach[0] = False  # bot guruhdan chiqarilgan
            await handlers.cb_card(c(payer, "gc:7:0", log))
            await handlers.on_check(photo(payer, log, same="U7"))
            assert [x[0] for x in photos[n:]] == [-5551, admin]
            await handlers.cmd_orders_chat(SimpleNamespace(chat=SimpleNamespace(id=admin, type="private"),
                                                           answer=lambda t, **kw: asyncio.sleep(0, said.append(t))))
            assert config.ORDERS_CHAT is None and said[-1] == texts.ORDERS_PM
        finally:
            config.ORDERS_CHAT = None
            handlers.send, config.CARD_NUMBER, config.ADMIN_IDS = old_send, old_card, old_admins
            handlers.ASK.pop(payer, None)
    run(t())
