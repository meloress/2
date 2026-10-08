"""/send: o'tkazish va tarqatish. Pul hech qachon yo'qolmasin, ikki marta berilmasin."""
import asyncio
from types import SimpleNamespace

from mafia_zone import config, db, handlers, runner, texts

runner.GLOBAL_INTERVAL = 0
runner.GROUP_PER_MIN = 10 ** 9
BASE = 7_000_000


async def mkuser(uid: int, dollars: int) -> None:
    await db.upsert_user(uid, f"u{uid}", None)
    u = await db.get_user(uid)
    await db.add_balance(uid, dollars - u.dollars)


async def set_games(uid: int, games: int) -> None:
    from sqlalchemy import update
    async with db.Session.begin() as s:
        await s.execute(update(db.User).where(db.User.telegram_id == uid).values(games=games))


async def bal(uid: int) -> int:
    return (await db.get_user(uid)).dollars


def run(coro):
    async def go():
        await db.init()
        return await coro
    return asyncio.run(go())


def test_transfer():
    async def t():
        a, b = BASE + 1, BASE + 2
        await mkuser(a, 150)
        await mkuser(b, 0)
        assert await db.transfer(a, b, 100)
        assert (await bal(a), await bal(b)) == (50, 100)
        assert not await db.transfer(a, b, 51)  # yetmaydi
        assert not await db.transfer(a, a, 10)  # o'ziga
        assert not await db.transfer(a, BASE + 999, 10)  # qabul qiluvchi yo'q
        assert await bal(a) == 50  # hech narsa yo'qolmadi
    run(t())


def test_giveaway_claims_and_concurrency():
    async def t():
        s = BASE + 10
        await mkuser(s, 100)
        assert await db.create_giveaway(-1, s, 10, 11) is None  # 110 > 100
        gid = await db.create_giveaway(-1, s, 10, 10)
        assert await bal(s) == 0
        assert await db.claim(gid, s) is None  # o'zi ololmaydi
        users = [BASE + 100 + i for i in range(50)]
        for u in users:
            await mkuser(u, 0)
        res = await asyncio.gather(*(db.claim(gid, u) for u in users + users))  # har biri 2 marta
        assert sum(r is not None for r in res) == 10
        assert sum([await bal(u) for u in users]) == 100  # jami taqsimlangan = yechilgan
        assert all(b in (0, 10) for b in [await bal(u) for u in users])
        assert (await db.get_giveaway(gid)).left == 0
        takers = await db.giveaway_takers(gid)
        got = [u for u, r in zip(users + users, res) if r is not None]
        assert len(takers) == 10 and {u for u, _ in takers} == set(got)
        text = texts.giveaway("Ali", s, 10, 10, takers)
        assert "100</b> 💵 ulashmoqda" in text and "10. " in text and "- 10💵" in text
    run(t())


def test_group_commands_deleted():
    async def t():
        me = SimpleNamespace(username="MafiaZoneBot")
        bot = SimpleNamespace(me=lambda: asyncio.sleep(0, me))
        async def handler(m, d):
            return "ok"
        for text, chat, gone in [("/game", "group", True), ("/game@mafiazonebot x", "supergroup", True),
                                 ("/start@OtherBot", "group", False), ("salom", "group", False),
                                 ("/profile", "private", False)]:
            deleted = []
            async def delete():
                deleted.append(1)
            m = SimpleNamespace(text=text, chat=SimpleNamespace(type=chat), delete=delete)
            assert await handlers.drop_commands(handler, m, {"bot": bot}) == "ok"
            assert bool(deleted) == gone, text
    run(t())


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append(text)
        return SimpleNamespace(message_id=1)

    async def pin_chat_message(self, chat_id, message_id, **kw):
        self.pinned = getattr(self, "pinned", []) + [message_id]

    async def unpin_chat_message(self, chat_id, message_id=None):
        self.unpinned = getattr(self, "unpinned", []) + [message_id]


def fake_msg(uid, reply_uid=None):
    deleted = []

    async def delete():
        deleted.append(True)

    user = lambda i: SimpleNamespace(id=i, full_name=f"u{i}", username=None, is_bot=False)
    reply = SimpleNamespace(from_user=user(reply_uid)) if reply_uid else None
    return SimpleNamespace(from_user=user(uid), chat=SimpleNamespace(id=-5), reply_to_message=reply,
                           delete=delete), deleted


def test_send_command():
    async def t():
        a, b = BASE + 500, BASE + 501
        await mkuser(a, 100)
        await set_games(a, config.SEND_GAMES)
        bot = FakeBot()
        cmd = lambda args: SimpleNamespace(args=args)

        m, deleted = fake_msg(a, reply_uid=b)  # reply + /send 30
        await handlers.cmd_send(m, bot, cmd("30"))
        assert not deleted and await bal(a) == 70 and await bal(b) == 30

        n = len(bot.sent)
        for args in ("500", "abc", "0", "-5", "", "1 2 3"):  # yetmaydi yoki noto'g'ri: jim (buyruqni middleware o'chiradi)
            m, _ = fake_msg(a, reply_uid=b)
            await handlers.cmd_send(m, bot, cmd(args))
            assert len(bot.sent) == n and await bal(a) == 70, args
        m, deleted = fake_msg(a)  # reply'siz bitta son: bitta kishi hammasini oladi
        await handlers.cmd_send(m, bot, cmd("10"))
        assert not deleted and await bal(a) == 60 and "10</b> 💵 ulashmoqda" in bot.sent[-1]
        assert bot.pinned  # tarqatma qadaldi

        n = len(bot.sent)
        m, deleted = fake_msg(a)  # /send 60 6 -> 10 ulush
        await handlers.cmd_send(m, bot, cmd("60 6"))
        assert not deleted and await bal(a) == 0 and len(bot.sent) == n + 1 and "60</b>" in bot.sent[-1]

        m, deleted = fake_msg(a)  # endi pul yo'q
        await handlers.cmd_send(m, bot, cmd("10 1"))
        assert len(bot.sent) == n + 1
    run(t())


def test_couple_flow():
    async def t():
        a, b, c = BASE + 700, BASE + 701, BASE + 702
        for u in (a, b, c):
            await mkuser(u, 0)
        await db.upsert_user(b, "Bek", "BekUZ")
        bot = FakeBot()
        bot.edited = []

        async def edit_message_text(text, chat_id, message_id, **kw):
            bot.edited.append(text)
        bot.edit_message_text = edit_message_text
        cmd = lambda args=None: SimpleNamespace(args=args)

        m, _ = fake_msg(a)
        replies = []

        async def reply(text, **kw):
            replies.append(text)
        m.reply, m.entities = reply, None
        await handlers.cmd_couple(m, bot, cmd())  # nishonsiz
        assert replies[-1] == texts.COUPLE_HOW
        await handlers.cmd_couple(m, bot, cmd("@bekuz"))  # username bo'yicha
        assert "para bo'lish so'rovini" in bot.sent[-1]

        def cq(uid, yes):
            answers = []

            async def answer(text=None, **kw):
                answers.append(text)
            return SimpleNamespace(data=f"cp:{a}:{b}:{yes}", from_user=SimpleNamespace(
                id=uid, full_name=f"u{uid}", username=None), message=SimpleNamespace(
                chat=SimpleNamespace(id=-5), message_id=1), answer=answer), answers

        q, ans = cq(c, 1)  # begona bosa olmaydi
        await handlers.cb_couple(q, bot)
        assert ans == [texts.COUPLE_NOT_YOU] and await db.partner(a) is None
        q, _ = cq(b, 0)
        await handlers.cb_couple(q, bot)
        assert "rad etdi" in bot.edited[-1] and await db.partner(a) is None
        q, _ = cq(b, 1)
        await handlers.cb_couple(q, bot)
        assert "endi para" in bot.edited[-1] and await db.partner(a) == b and await db.partner(b) == a
        assert not await db.make_couple(c, b)  # b band
        await handlers.cmd_mycouple(m)
        assert replies[-1].count("❤️") == 2
        await handlers.cmd_uncouple(m)
        assert "bekor qilindi" in replies[-1] and await db.partner(b) is None
        await handlers.cmd_uncouple(m)
        assert replies[-1] == texts.COUPLE_NONE
    run(t())


def test_game_reward_win_40_lose_0():
    async def t():
        w, l = BASE + 950, BASE + 951
        await mkuser(w, 0)
        await mkuser(l, 0)
        gid = await db.create_game(-950, {})
        await db.finish_game(gid, -950, "finished", "town", [(w, "tinch", "town", True, True),
                                                               (l, "don", "mafia", False, False)])
        assert await bal(w) == 40 and await bal(l) == 0
    run(t())


def test_concurrent_buys_and_new_users():
    async def t():
        u = BASE + 800
        await mkuser(u, 10 * config.SHOP["shield"])
        res = await asyncio.gather(*(db.buy(u, "shield") for _ in range(15)))
        inv = {i.item: i.qty for i in await db.inventory(u)}
        assert sum(res) == 10 and inv["shield"] == 10 and await bal(u) == 0  # 10 ta narxi
        await db.change_item(u, "shield", -50)  # manfiyga tushmaydi
        assert {i.item: i.qty for i in await db.inventory(u)}["shield"] == 10
        await asyncio.gather(*(db.upsert_user(BASE + 900, "yangi", None) for _ in range(10)))  # xatosiz
        assert await db.get_user(BASE + 900)
        await asyncio.gather(*(db.group_settings(-424242, "g") for _ in range(10)))
    run(t())


def test_begin_allowed_for_admins_and_opener():
    async def t():
        started, said = [], []
        r = SimpleNamespace(game=None, opener=BASE + 900, force_start=lambda: started.append(1))
        bot = SimpleNamespace(get_chat_member=lambda c, u: asyncio.sleep(0, SimpleNamespace(
            status="administrator" if u == BASE + 901 else "member")))
        handlers.RUNNERS[-77] = r
        try:
            for uid, ok in ((BASE + 900, True), (BASE + 901, True), (BASE + 902, False)):
                async def answer(text):
                    said.append(text)
                m = SimpleNamespace(chat=SimpleNamespace(id=-77), from_user=SimpleNamespace(id=uid), answer=answer)
                n = len(started)
                await handlers.cmd_begin(m, bot)
                assert (len(started) > n) == ok, uid
            assert said == [texts.ONLY_STARTER]
        finally:
            handlers.RUNNERS.pop(-77, None)
    run(t())


def test_menu_sections_have_back_button():
    async def t():
        edits = []
        async def edit_text(text, reply_markup=None):
            edits.append((text, reply_markup))
        async def answer(*a, **kw):
            pass
        runner.BOT_USERNAME = "AdmiralMafiaBot"
        for what in ("rules", "top", "shop", "profile", "home"):
            u = SimpleNamespace(id=BASE + 950, full_name="Ali", username=None, is_bot=False)
            cq = SimpleNamespace(data=f"m:{what}", from_user=u, message=SimpleNamespace(edit_text=edit_text), answer=answer)
            await handlers.cb_menu(cq)
            rows = edits[-1][1].inline_keyboard
            cbs = [b.callback_data for row in rows for b in row]
            assert ("m:home" in cbs) == (what != "home"), what
    run(t())


def test_extend_default_custom_cap_and_rights():
    import time as _t

    async def t():
        said = []

        async def answer(text):
            said.append(text)
        base = _t.time()
        r = SimpleNamespace(game=None, lobby_deadline=base, lobby_dirty=False, opener=BASE + 1200)
        r.extend = lambda secs=30: setattr(r, "lobby_deadline", r.lobby_deadline + secs)
        bot = SimpleNamespace(get_chat_member=lambda c, u: asyncio.sleep(0, SimpleNamespace(status="member")))
        handlers.RUNNERS[-78] = r
        msg = lambda uid: SimpleNamespace(chat=SimpleNamespace(id=-78), from_user=SimpleNamespace(id=uid),
                                          sender_chat=None, answer=answer)
        try:
            await handlers.cmd_extend(msg(BASE + 1201), bot, SimpleNamespace(args="60"))  # begona: ruxsat yo'q
            assert r.lobby_deadline == base and said[-1] == texts.ONLY_STARTER_EXTEND
            for args, added in ((None, 30), ("60", 90), ("abc", 120)):
                await handlers.cmd_extend(msg(BASE + 1200), bot, SimpleNamespace(args=args))
                assert abs(r.lobby_deadline - base - added) < 2, args
            await handlers.cmd_extend(msg(BASE + 1200), bot, SimpleNamespace(args="99999"))
            assert r.lobby_deadline - _t.time() <= 601  # ko'pi bilan 10 daqiqa oldinga
            await handlers.cmd_extend(msg(BASE + 1200), bot, SimpleNamespace(args="30"))
            assert said[-1] == texts.EXTEND_MAX
        finally:
            handlers.RUNNERS.pop(-78, None)
        assert "60 soniya" in said[2]
    run(t())


def test_call_survives_network_errors():
    from aiogram.exceptions import TelegramNetworkError
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise TelegramNetworkError(method=None, message="timeout")
        return "ok"

    async def always():
        raise TelegramNetworkError(method=None, message="down")

    async def t():
        assert await runner._call(flaky) == "ok" and len(calls) == 2
        assert await runner._call(always) is None  # o'yinni yiqitmaydi
    run(t())


def test_leave_limit_fine_and_debt_block():
    from mafia_zone.engine.game import Game, Player

    async def t():
        a, other = BASE + 1000, BASE + 1001
        await mkuser(a, 100)
        await mkuser(other, 0)
        sent, answers = [], []

        async def fake_send(bot, chat_id, text, kb=None, **kw):
            sent.append((chat_id, text))
        orig_send, handlers.send = handlers.send, fake_send
        try:
            for round_ in range(5):  # 3 ta bepul, keyin ogohlantirish + tugmalar
                g = Game(-79, 1, [Player(a, "Ali", "don"), Player(other, "Vali", "tinch")], phase="day")
                left = []

                async def leave(uid):
                    left.append(uid)
                    g.get(uid).alive = False
                r = SimpleNamespace(game=g, game_id=500 + round_, chat_id=-79, leave=leave)
                handlers.RUNNERS[-79] = r
                handlers.PLAYING[a] = r

                async def answer(text, reply_markup=None):
                    answers.append((text, reply_markup))
                m = SimpleNamespace(chat=SimpleNamespace(id=-79), from_user=SimpleNamespace(id=a, full_name="Ali"),
                                    answer=answer)
                await handlers.cmd_leave(m)
                if round_ < 3:
                    assert left == [a] and f"{round_ + 1}/3" in answers[-1][0] and await bal(a) == 100
                    continue
                assert not left and answers[-1][1] is not None  # ogohlantirish, hali chiqmadi
                deleted = []

                async def delete():
                    deleted.append(1)
                for who, data in ((other, f"lv:{r.game_id}:{a}:1"), (a, f"lv:{r.game_id}:{a}:{1 if round_ == 4 else 0}")):
                    said = []

                    async def cq_answer(text=None, show_alert=False):
                        said.append(text)
                    cq = SimpleNamespace(data=data, from_user=SimpleNamespace(id=who, full_name="Ali"), bot=None,
                                         message=SimpleNamespace(delete=delete), answer=cq_answer)
                    await handlers.cb_leave(cq)
                    if who == other:
                        assert said == [texts.NOT_YOUR_BTN] and not left
                if round_ == 3:  # "davom ettirish"
                    assert not left and await bal(a) == 100
                else:  # "chiqish": -200, minusga tushadi
                    assert left == [a] and await bal(a) == -100 and "jarima" in sent[-1][1]
        finally:
            handlers.send = orig_send
            handlers.RUNNERS.pop(-79, None)
            handlers.PLAYING.pop(a, None)
        assert await db.leaves_today(a) == 4
        await db.count_leave(a, 1000)  # -1100: o'yinga qo'shila olmaydi
        said = []

        async def answer2(text, reply_markup=None):
            said.append(text)
        m = SimpleNamespace(from_user=SimpleNamespace(id=a, full_name="Ali", username=None), answer=answer2)
        await handlers.cmd_start(m, None, SimpleNamespace(args="join-79"))
        assert "-1100" in said[-1] and "qo'shila olmaydi" in said[-1]
    run(t())


def test_rob_negative_balance_steals_nothing():
    async def t():
        v, th = BASE + 1010, BASE + 1011
        await mkuser(v, -300)
        await mkuser(th, 0)
        assert await db.rob_dollars(v, th) == 0 and await bal(v) == -300 and await bal(th) == 0
    run(t())


def test_new_accounts_cannot_send_or_claim_and_ref_paid_after_games():
    async def t():
        a, b, inviter, friend = BASE + 1100, BASE + 1101, BASE + 1102, BASE + 1103
        await mkuser(a, 100)
        await mkuser(inviter, 0)
        await set_games(a, config.SEND_GAMES - 1)
        bot = FakeBot()
        m, _ = fake_msg(a)
        await handlers.cmd_send(m, bot, SimpleNamespace(args="10"))
        assert await bal(a) == 100 and "🔒" in bot.sent[-1]  # yopiq: pul yechilmadi
        await set_games(a, config.SEND_GAMES)
        await handlers.cmd_send(m, bot, SimpleNamespace(args="10"))
        gid = max(g.id for g in [await db.get_giveaway(i) for i in range(1, 500)] if g)
        await mkuser(b, 0)  # 0 ta o'yin - tarqatmadan ololmaydi
        said = []

        async def answer(text=None, show_alert=False):
            said.append(text)
        cq = SimpleNamespace(data=f"g:{gid}", from_user=SimpleNamespace(id=b, full_name="b", username=None),
                             answer=answer, message=SimpleNamespace(chat=SimpleNamespace(id=-5), message_id=1))
        await handlers.cb_giveaway(cq, bot)
        assert "🔒" in said[-1] and await bal(b) == 0
        # taklif: bonus darhol emas, REF_GAMES ta o'yindan keyin, bir marta
        await mkuser(friend, 0)
        await db.set_referrer(friend, inviter)
        assert await db.pay_referrals([friend]) == [] and await bal(inviter) == 0
        await set_games(friend, config.REF_GAMES)
        assert await db.pay_referrals([friend]) == [(inviter, f"u{friend}")]
        assert await db.pay_referrals([friend]) == [] and await bal(inviter) == config.REF_BONUS
    run(t())


def test_diamond_giveaway():
    """/give: olmos tarqatma - pul tarqatma bilan bir xil, faqat olmosda."""
    async def t():
        s, a, b = BASE + 900, BASE + 901, BASE + 902
        for u in (s, a, b):
            await mkuser(u, 0)
        await db.add_balance(s, 0, 5)
        assert await db.create_giveaway(-1, s, 2, 3, "diamonds") is None  # 6 > 5
        gid = await db.create_giveaway(-1, s, 2, 2, "diamonds")
        assert (await db.get_user(s)).diamonds == 1 and await bal(s) == 0
        assert (await db.claim(gid, a)).currency == "diamonds"
        assert (await db.get_user(a)).diamonds == 2 and await bal(a) == 0
        g, refund = await db.close_giveaway(gid)
        assert refund == 2 and (await db.get_user(s)).diamonds == 3 and await bal(s) == 0
        text = texts.giveaway("Ali", s, 2, 2, await db.giveaway_takers(gid), "diamonds")
        assert "4</b> 💎 ulashmoqda" in text and "- 2💎" in text
        assert await db.transfer(a, b, 2, "diamonds")
    run(t())


def test_give_command_diamonds():
    """Guruhda /give - /send bilan bir xil, faqat olmos; dollar tegilmaydi."""
    async def t():
        a, b = BASE + 950, BASE + 951
        await mkuser(a, 100)
        await mkuser(b, 0)
        await db.add_balance(a, 0, 10)
        await set_games(a, config.SEND_GAMES)
        bot = FakeBot()
        cmd = lambda args: SimpleNamespace(args=args, command="give")
        m, _ = fake_msg(a, reply_uid=b)  # reply + /give 3
        await handlers.cmd_send(m, bot, cmd("3"))
        assert (await db.get_user(b)).diamonds == 3 and "3 💎" in bot.sent[-1]
        m, _ = fake_msg(a)  # /give 6 2 -> 3 ulush
        await handlers.cmd_send(m, bot, cmd("6 2"))
        u = await db.get_user(a)
        assert u.diamonds == 1 and u.dollars == 100 and "6</b> 💎 ulashmoqda" in bot.sent[-1]
    run(t())
