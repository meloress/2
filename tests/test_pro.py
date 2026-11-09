"""Pro obuna (1/2/3-daraja, toifa): kesh, belgi, imkoniyatlar, xarid."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from mafia_zone import config, db, emoji, pro, texts

U = lambda s: s.replace(emoji.USER, "")  # ismlar USER belgisi bilan o'ralgan (premium emojiga almashmasin)
F = pro.fancy  # Pro ismi qalin kursiv


def setup_function():
    pro.CACHE.clear()
    emoji.DISABLED = False


def test_game_emoji_plain_but_pro_badge_premium():
    """O'yin matnlari animatsion emoji'siz (to'plam o'chiq), PRO tarif belgisi esa premium qoladi."""
    from mafia_zone import runner
    assert config.EMOJI_PACK == ""
    assert "<tg-emoji" in pro.badge() and "<tg-emoji" in pro.tail()
    assert runner.pro_btn().icon_custom_emoji_id == pro.BADGE_ID


def test_badge_name_and_expiry():
    pro.set_user(1, db.now() + timedelta(days=3), "Shoh<1>")  # daraja None - eski PRO = Pro 3
    assert pro.is_pro(1) and pro.tier(1) == 3 and U(pro.name(1, "Ali")) == F("Shoh<1>")
    m = texts.mention(1, "Ali")
    assert pro.BADGE_ID in m and pro.PRO_TAG in m and F("Shoh") + "&lt;1&gt;" in m and "tg://user?id=1" in m
    # 🌟 Pro <nickname> 🔥
    assert m.index(pro.BADGE_ID) < m.index(pro.PRO_TAG) < m.index(F("Shoh")) < m.index(pro.TAIL_ID)
    pro.set_user(1, db.now() - timedelta(seconds=1), "Shoh")
    assert not pro.is_pro(1) and U(texts.mention(1, "Ali")) == '<a href="tg://user?id=1">Ali</a>'


def test_perks_numbers():
    pro.set_user(2, db.now() + timedelta(days=1), None)  # eski PRO: muddati tugaguncha -25%, x1.5
    assert pro.price(2, 100) == 75 and pro.price(3, 100) == 100
    assert pro.win_reward(2) == config.REWARD_WIN * 3 // 2 and pro.win_reward(3) == config.REWARD_WIN
    assert [(U(t), i) for t, i in (pro.label(2, "Ali"), pro.label(3, "Ali"))] == [(pro.PRO_TAG + " " + F("Ali"), pro.BADGE_ID),
                                                                                    ("Ali", None)]
    w = config.REWARD_WIN
    for lv, price, win, icon in ((1, 95, w, None), (2, 90, w * 125 // 100, pro.BADGE_ID), (3, 85, w * 3 // 2, pro.BADGE_ID)):
        pro.set_user(4, db.now() + timedelta(days=1), "Shoh", lv)
        assert pro.tier(4) == lv and pro.price(4, 100) == price and pro.win_reward(4) == win, lv
        text = pro.PRO_TAG + " " + F("Shoh") if lv == 3 else F("Ali")  # nickname faqat Pro 3 da
        assert (U(pro.label(4, "Ali")[0]), pro.label(4, "Ali")[1]) == (text, icon)
        m = texts.mention(4, "Ali")  # belgi Pro 2 dan; "Pro" yozuvi Pro 3 da
        assert (F("Shoh") in m) == (lv == 3) and (pro.BADGE_ID in m) == (lv >= 2) and (pro.PRO_TAG in m) == (lv == 3)
        assert "PRO" not in m


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
    assert calls[-1].text == f"{pro.BADGE_FALLBACK} <b>PRO</b> Ali"
    assert calls[-1].reply_markup.inline_keyboard[0][0].icon_custom_emoji_id is None
    n = len(calls)  # bir marta rad etilgach: keyingilari darhol oddiy yuboriladi
    assert asyncio.run(emoji.PremiumEmoji()(make_request, None, m)) == "ok" and len(calls) == n + 1


def test_pro_purchase_db():
    async def t():
        await db.init()
        u = 8_200_001
        await db.upsert_user(u, "Ali", None)
        await db.add_balance(u, 0, 40)
        until1 = await db.buy_pro_diamonds(u, 3)
        assert until1 and pro.tier(u) == 3 and (await db.get_user(u)).diamonds == 11
        assert round((until1 - db.now()).total_seconds() / 86400) == pro.DAYS
        assert await db.buy_pro_diamonds(u, 3) is None and (await db.get_user(u)).diamonds == 11  # yetmaydi
        assert await db.buy_pro_diamonds(u, 4) is None  # bunday daraja yo'q
        until2 = await db.add_pro(u, 15, "stars", 150, "ch-1", 3)
        assert round((until2 - until1).total_seconds() / 86400) == 15  # o'sha daraja - ustiga qo'shiladi
        assert await db.add_pro(u, 15, "stars", 150, "ch-1", 3) is None  # takror to'lov
        await db.set_nickname(u, "Shoh")
        pro.CACHE.clear()
        await db.load_pro()
        assert U(pro.name(u, "Ali")) == F("Shoh") and pro.tier(u) == 3
        # Pro 3 (22 kun qolgan) -> Pro 1: qolgan kunlar narx bo'yicha (29/9) + 7 kun; nickname Pro 1 da ko'rinmaydi
        left = (pro.until(u) - db.now()).total_seconds() / 86400
        until3 = await db.buy_pro_diamonds(u, 1)
        assert pro.tier(u) == 1 and abs((until3 - db.now()).total_seconds() / 86400 - (left * 29 / 9 + 7)) < 0.01
        assert U(pro.name(u, "Ali")) == F("Ali")
        assert await db.pro_expiring(24 * 200) == [u] and await db.pro_expiring(24 * 200) == []  # bir marta
        await db.set_pro(u, 0)
        assert not pro.is_pro(u) and (await db.get_user(u)).pro_until is None
        await db.set_pro(u, 3)
        assert pro.tier(u) == 3 and U(pro.name(u, "Ali")) == F("Shoh")
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
        assert before - (await db.get_user(p)).dollars == config.SHOP["shield"] * 85 // 100  # Pro 3: -15%
        assert "-15%" in texts.shop(500, p) and "-15%" not in texts.shop(500, o)
        from mafia_zone import handlers
        label = lambda uid: next(b.text for r in handlers.shop_kb(uid).inline_keyboard for b in r
                                 if b.callback_data == "b:shield")  # narx tugmada
        assert f"({config.SHOP['shield'] * 85 // 100}💵)" in label(p) and f"({config.SHOP['shield']}💵)" in label(o)
    asyncio.run(t())


def test_pro_spectator_and_dead_write_only_by_day():
    from mafia_zone import handlers
    from mafia_zone.engine.game import DAY, NIGHT, Game, Player
    pro.set_user(77, db.now() + timedelta(days=1), None)
    g = Game(-1, 1, [Player(1, "a", "tinch"), Player(2, "b", "don", alive=False)], phase=DAY)
    assert handlers.may_write(g, 77, "salom", False)          # Pro tomoshabin kunduzi
    assert not handlers.may_write(g, 78, "salom", False)      # oddiy tomoshabin
    assert not handlers.may_write(g, 2, "salom", False)       # o'lgan oddiy o'yinchi
    pro.set_user(2, db.now() + timedelta(days=1), None, 1)
    assert handlers.may_write(g, 2, "salom", False)           # o'lgan Pro (1-daraja ham) - kunduzi yozadi
    g.phase = NIGHT
    assert not handlers.may_write(g, 77, "salom", False) and not handlers.may_write(g, 2, "salom", False)  # tunda yo'q


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
    assert U(b.text) == "2. 🤵🏼 " + pro.PRO_TAG + " " + F("Shoh") and b.icon_custom_emoji_id == pro.BADGE_ID
    assert U(rows[1][0].text) == "3. Hasan" and rows[1][0].icon_custom_emoji_id is None
    r.close()
    u = SimpleNamespace(telegram_id=5, full_name="Ali", wins=0, dollars=0, diamonds=0, games=0)
    card = texts.profile_card(u, [])
    assert pro.BADGE_ID in card and F("Shoh") in card and "Pro 3" in card and "gacha" in card
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
        for amount, payload in ((150, "pro:3:7"), (50, "pro:1:7"), (1, "pro:3:7"), (150, "pro:4:7"), (150, "pro:3:30"),
                                (100, "pro:7"), (150, "xyz")):  # "pro:7" - eski (darajasiz) hisob-faktura
            await handlers.on_pre_checkout(SimpleNamespace(invoice_payload=payload, total_amount=amount, currency="XTR",
                                                           from_user=SimpleNamespace(id=u), answer=pcq_answer))
        assert ok == [True, True, False, False, False, False, False]
        pay = SimpleNamespace(invoice_payload="pro:3:7", total_amount=150, currency="XTR", telegram_payment_charge_id="c9")
        m = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), successful_payment=pay,
                            answer=answer)
        await handlers.on_paid(m)
        await handlers.on_paid(m)  # Telegram takror yuborsa - ikkinchi marta hisoblanmaydi
        assert pro.tier(u) == 3 and len(said) == 1 and "Pro 3" in said[0]
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
        assert "Pro AKKAUNT" in text and "darajani tanlang" in text
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert cbs == ["pt:1", "pt:2", "pt:3", "pt:title", "m:home"]
        for lv in (1, 2, 3):
            await handlers.cb_pro_tier(cq(f"pt:{lv}"))
            text, kb = shown[-1]
            assert f"Pro {lv}" in text and F("Ali") in text and f"({pro.DISCOUNT[lv]}%)" in text and "/leave" in text
            assert ("/nickname" in text) == (lv == 3) and ("x1.5" in text) == (lv == 3) and ("x1.25" in text) == (lv == 2)
            assert (pro.PRO_TAG in text) == (lv == 3) and (pro.BADGE_ID in text) == (lv >= 2) and "PRO" not in text
            cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
            assert [c for c in cbs if c] == [f"pro:d:{lv}", f"pro:s:{lv}", "m:pro"]
            assert kb.inline_keyboard[0][0].text == f"💎 7 kun — {pro.PACKS[lv][0]}"
        await handlers.cb_pro(cq("pro:d:3"))  # olmos yo'q
        assert alerts[-1] == texts.PRO_NO_DIAMONDS and not pro.is_pro(u)
        await db.add_balance(u, 0, 29)
        await handlers.cb_pro(cq("pro:d:3"))
        assert pro.is_pro(u) and (await db.get_user(u)).diamonds == 0
        said = []

        async def answer(text=None, **kw):
            said.append(text)
        nick = lambda args: handlers.cmd_nickname(
            SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), answer=answer),
            SimpleNamespace(args=args))
        await nick("@shoh")
        assert "❌" in said[-1] and U(pro.name(u, "Ali")) == F("Ali")
        await nick("Shoh")
        assert U(pro.name(u, "Ali")) == F("Shoh") and (await db.get_user(u)).nickname == "Shoh"
        await nick(None)
        assert U(pro.name(u, "Ali")) == F("Ali")
        await db.set_pro(u, 7, 2)  # Pro 2: laqab yo'q
        await nick("Shoh")
        assert said[-1] == texts.NICK_ONLY_PRO
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
    assert U(texts.nm(g, 9)) == F("Shoh") and F("Shoh") in texts.role_card(g, 10)
    pro.set_user(9, db.now() - timedelta(seconds=1), "Shoh")  # Pro tugadi
    assert U(texts.nm(g, 9)) == "Ali" and F("Shoh") not in texts.role_card(g, 10)
    assert "Shoh" not in texts.role_alert(g, 10)


def test_fix_non_pro_cannot_fake_badge():
    assert U(texts.mention(11, "✅ PRO Ali")) == '<a href="tg://user?id=11">Ali</a>'
    assert pro.label(11, "PRO Ali") == (pro.short("Ali"), None)
    assert U(texts.mention(11, "PRO")) == '<a href="tg://user?id=11">PRO</a>'  # faqat "PRO" bo'lsa - qoladi
    assert U(texts.mention(11, "Prohor")) == '<a href="tg://user?id=11">Prohor</a>'


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
            pay = SimpleNamespace(invoice_payload="pro:3:7", total_amount=150, currency="XTR", telegram_payment_charge_id="c77")
            m = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None), successful_payment=pay,
                                answer=answer, bot=SimpleNamespace(refund_star_payment=refund))
            await handlers.on_paid(m)
        finally:
            db.add_pro = orig
        assert refunds == [(u, "c77")] and "qaytarildi" in said[-1] and not pro.is_pro(u)
        await handlers.cmd_paysupport(SimpleNamespace(answer=answer))
        assert "/paysupport" not in said[-1] and "To'lov" in said[-1]
    asyncio.run(t())


def test_long_and_weird_names_are_shortened_everywhere():
    """Juda uzun / g'alati belgili ismlar menyuni to'ldirmasin: bitta joyda (pro.name) qisqaradi."""
    from mafia_zone import pro, texts
    long = "𝓐𝓵𝓲" * 30
    assert U(pro.short(long)) == long[:pro.NAME_MAX - 1] + "…"
    assert U(pro.short("Ali")) == "Ali"
    zalgo = "A" + "́" * 50 + "li"  # ustma-ust urg'u belgilari qatorni bo'yiga cho'zadi
    assert pro.short(zalgo).count("́") <= 2
    assert U(pro.short("Ali‮ilA​")) == "AliilA"  # yo'nalish/ko'rinmas belgilar olib tashlanadi
    assert U(pro.short("👨‍👩‍👧 Oila")) == "👨‍👩‍👧 Oila"  # emoji (ZWJ) buzilmaydi
    assert U(pro.short("​‮")) == "?"
    uid = 77_123_001
    assert long not in texts.mention(uid, long) and "…" in texts.mention(uid, long)
    assert pro.label(uid, long)[0] == pro.short(long)
    assert long not in texts.ref_bonus(long)


def test_owner_badge_only_for_bot_owner():
    """Bot egasi (ADMIN_IDS): "👑 Creator nickname ✅" (PRO o'rniga, tugmada ham); boshqalar "Creator" deb yozib ololmaydi."""
    owner, other = 77_500_001, 77_500_002
    old = set(config.ADMIN_IDS)
    config.ADMIN_IDS.clear(), config.ADMIN_IDS.add(owner)
    try:
        pro.set_user(owner, db.now() + timedelta(days=1), "Shoh")
        m = texts.mention(owner, "Ali")
        assert pro.OWNER_ID in m and pro.OWNER_TAIL_ID in m and pro.CREATOR_TAG in m and F("Shoh") in m
        assert pro.BADGE_ID not in m and pro.PRO_TAG not in m
        assert pro.label(owner, "Ali") == (pro.CREATOR_TAG + " " + pro.short(F("Shoh")), pro.OWNER_ID)
        pro.set_user(owner, None, None)  # PRO tugasa ham egasi Creator
        assert pro.CREATOR_TAG in texts.mention(owner, "Ali")
        assert U(texts.mention(other, "👑 OWNER Vali 👍")) == '<a href="tg://user?id=77500002">Vali</a>'
        assert U(texts.mention(other, "👑 Creator Vali 👍")) == '<a href="tg://user?id=77500002">Vali</a>'
        assert pro._BAD_NICK.search("Creator")  # PRO nickname ham "Creator" bo'lolmaydi
    finally:
        config.ADMIN_IDS.clear(), config.ADMIN_IDS.update(old)
        pro.set_user(owner, None, None)


def test_group_owner_title():
    """Toifa: faol katta guruh egasi -> cheksiz Pro 3 + "<guruh> Owner"; Pro xaridi uni buzmaydi."""
    from mafia_zone import handlers

    async def t():
        await db.init()
        u, chat = 8_200_050, -100_777
        await db.upsert_user(u, "Ali", None)
        await db.group_settings(chat, "Shahar Mafia 🌟")
        for _ in range(config.TITLE_GAMES - 1):
            await db.finish_game(await db.create_game(chat, {}), chat, "finished", "town", [])
        status, members = ["creator"], [config.TITLE_MEMBERS]

        async def get_chat_member(chat_id, user_id):
            return SimpleNamespace(status=status[0])

        async def get_chat_member_count(chat_id):
            return members[0]
        bot = SimpleNamespace(get_chat_member=get_chat_member, get_chat_member_count=get_chat_member_count)
        assert await handlers.find_title(bot, u) is None  # o'yin yetmaydi
        await db.finish_game(await db.create_game(chat, {}), chat, "finished", "town", [])
        title = await handlers.find_title(bot, u)
        assert U(title) == "Shahar Mafia 🌟 Owner"
        members[0] -= 1
        assert await handlers.find_title(bot, u) is None  # a'zo kam
        members[0], status[0] = config.TITLE_MEMBERS, "administrator"
        assert await handlers.find_title(bot, u) is None  # egasi emas
        await db.grant_title(u, title)
        pro.CACHE.clear()
        await db.load_pro()
        assert pro.tier(u) == 3 and pro.title(u) == title and pro.until(u) == pro.FOREVER
        m = texts.mention(u, "Ali")
        # pro boshi + Vip + ism + qora (Vip) galochka; guruh nomi ko'rinmaydi
        assert m.startswith(pro.badge() + f" {pro.VIP_TAG} ") and m.endswith(pro.vip_tail())
        assert "Shahar" not in m and pro.PRO_TAG not in m and pro.TAIL_ID not in m
        assert U(pro.label(u, "Ali")[0]) == pro.VIP_TAG + " " + F("Ali")
        assert await db.add_pro(u, 7, "admin", 0, tier=1) == pro.FOREVER and pro.tier(u) == 3  # toifa tegilmaydi
        alerts = []

        async def cq_answer(text=None, show_alert=False):
            alerts.append(text)
        cq = SimpleNamespace(data="pro:d:1", from_user=SimpleNamespace(id=u, full_name="Ali", username=None),
                             answer=cq_answer, bot=None)
        await handlers.cb_pro(cq)
        assert alerts[-1] == texts.TITLE_HAVE
        card = texts.profile_card(SimpleNamespace(telegram_id=u, full_name="Ali", wins=0, dollars=0, diamonds=0,
                                                  games=0), [])
        assert "cheksiz" in card and "2100" not in card
        await db.set_pro(u, 0)
        assert not pro.is_pro(u) and (await db.get_user(u)).title is None
    asyncio.run(t())


def test_name_lock_prank():
    """settings "name_lock" = {"uid": "ism"}: hamma joyda shu ism (laqab va haqiqiy ism o'rniga), /nickname qulf."""
    from mafia_zone import handlers

    async def t():
        await db.init()
        u = 8_200_060
        await db.upsert_user(u, "Ali", None)
        await db.save_settings({"name_lock": {str(u): "Creator's"}})
        try:
            await db.load_settings()
            assert U(pro.name(u, "Ali")) == "Creator's" and "Creator&#x27;s" in texts.mention(u, "Ali")
            pro.set_user(u, db.now() + timedelta(days=1), "Shoh", 3)
            assert U(pro.name(u, "Ali")) == F("Creator's") and U(pro.label(u, "Ali")[0]) == pro.PRO_TAG + " " + F("Creator's")
            said = []

            async def answer(text=None, **kw):
                said.append(text)
            await handlers.cmd_nickname(SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="Ali", username=None),
                                                        answer=answer), SimpleNamespace(args="Boshqa"))
            assert said[-1] == texts.NICK_LOCKED and (await db.get_user(u)).nickname is None
        finally:
            await db.save_settings({"name_lock": {}})
            await db.load_settings()
        assert U(pro.name(u, "Ali")) == F("Shoh")
    asyncio.run(t())
