"""/send: o'tkazish va tarqatish. Pul hech qachon yo'qolmasin, ikki marta berilmasin."""
import asyncio
from types import SimpleNamespace

from mafia_zone import db, handlers, runner, texts

runner.GLOBAL_INTERVAL = 0
runner.GROUP_PER_MIN = 10 ** 9
BASE = 7_000_000


async def mkuser(uid: int, dollars: int) -> None:
    await db.upsert_user(uid, f"u{uid}", None)
    u = await db.get_user(uid)
    await db.add_balance(uid, dollars - u.dollars)


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
        await mkuser(u, 1000)
        res = await asyncio.gather(*(db.buy(u, "shield") for _ in range(15)))
        inv = {i.item: i.qty for i in await db.inventory(u)}
        assert sum(res) == 10 and inv["shield"] == 10 and await bal(u) == 0  # 1000/100
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


def test_extend_default_and_custom():
    async def t():
        said = []
        async def answer(text):
            said.append(text)
        r = SimpleNamespace(game=None, lobby_deadline=100.0, lobby_dirty=False)
        r.extend = lambda secs=30: setattr(r, "lobby_deadline", r.lobby_deadline + secs)
        handlers.RUNNERS[-78] = r
        try:
            for args, total in ((None, 130), ("60", 190), ("abc", 220), ("99999", 820)):
                await handlers.cmd_extend(SimpleNamespace(chat=SimpleNamespace(id=-78), answer=answer),
                                          SimpleNamespace(args=args))
                assert r.lobby_deadline == total, args
        finally:
            handlers.RUNNERS.pop(-78, None)
        assert "60 soniya" in said[1] and "600 soniya" in said[3]
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
