"""Bot qatlami: soxta Bot + vaqtinchalik SQLite bilan to'liq o'yinlar."""
import asyncio
import os
import random
import tempfile
import time
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")

from mafia_zone import db, pro, runner, texts  # noqa: E402
from mafia_zone.engine.game import CONFIRM, FINISHED, NIGHT, VOTING  # noqa: E402
from mafia_zone.engine.roles import ROLES  # noqa: E402

from test_engine import play_random  # noqa: E402

runner.GLOBAL_INTERVAL = 0
runner.GROUP_PER_MIN = 10 ** 9


class FakeBot:
    def __init__(self):
        self.sent, self._id = [], 0

    async def send_message(self, chat_id, text, **kw):
        self._id += 1
        if e := kw.get("ephemeral_message_parameters"):  # guruhda faqat bitta odamga ko'rinadi - alohida yoziladi
            self.eph = getattr(self, "eph", []) + [(chat_id, e.receiver_user_id, text)]
            return SimpleNamespace(message_id=0, ephemeral_message_id=self._id)
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=self._id)

    async def delete_ephemeral_message(self, chat_id, receiver_user_id, ephemeral_message_id):
        self.eph_deleted = getattr(self, "eph_deleted", []) + [(chat_id, receiver_user_id, ephemeral_message_id)]
        return True

    async def edit_message_text(self, text, chat_id, message_id, **kw):
        self.sent.append((chat_id, text))
        return True

    async def delete_message(self, chat_id, message_id):
        self.deleted = getattr(self, "deleted", []) + [(chat_id, message_id)]
        return True

    async def send_animation(self, chat_id, animation, caption=None, **kw):
        self._id += 1
        self.sent.append((chat_id, caption))
        self.gifs = getattr(self, "gifs", []) + [animation]
        return SimpleNamespace(message_id=self._id, animation=SimpleNamespace(file_id="gif-id"), video=None,
                               document=None)


class AutoRunner(runner.Runner):
    """Har faza boshida o'yinchilar tasodifiy harakat qiladi."""
    rng = random.Random(1)

    async def _intro(self, ph, secs):
        await super()._intro(ph, secs)
        g = self.game
        for p in list(g.alive()):
            if ph == NIGHT:
                acts = g.available_actions(p.uid)
                if acts:
                    k = self.rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    await self.on_action(p.uid, g.day, k, self.rng.choice(ts) if ts else 0)
            elif ph == VOTING and g.can_vote(p.uid):
                alive = [x.uid for x in g.alive() if x.uid != p.uid]
                await self.on_vote(p.uid, g.day, self.rng.choice(alive + [0]))
            elif ph == CONFIRM and g.can_confirm(p.uid):
                await self.on_confirm(p.uid, g.day, self.rng.random() < 0.6)


def test_game_over_texts():
    known = set()
    for seed in range(1500):
        g = play_random(seed)
        known.add(g.winner)
        assert texts.game_over(g)
    assert set(texts.WINNER) >= known


def test_full_games_through_runner():
    async def go():
        await db.init()
        bot = FakeBot()
        await db.upsert_user(2, "o'yinchi 2", None)
        u0 = await db.get_user(2)  # boshqa testlar ham shu bazani ishlatadi: farqni tekshiramiz
        settings = {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": True, "disabled": []}
        for chat in range(-1, -21, -1):
            n = 4 + (-chat) % 27
            for uid in range(1, n + 1):
                await db.upsert_user(uid, f"o'yinchi {uid}", None)
            await db.add_balance(1, 500)
            await db.buy(1, "shield")
            r = AutoRunner(bot, chat, settings)
            for uid in range(1, n + 1):
                runner.PLAYING.pop(uid, None)
                assert r.join(uid, f"o'yinchi {uid}") == texts.JOINED
            await r._start_game()
            assert r.game.phase == FINISHED, chat
            assert chat not in runner.RUNNERS
        rows = await db.running_games()
        assert rows == []
        for _, text in bot.sent:
            assert_telegram_html(text)
        assert any("Rostdan ham" in t for _, t in bot.sent)  # ikki bosqichli osish ishladi
        u = await db.get_user(2)
        assert u.games - u0.games == 20  # pul: Qaroqchi o'g'irlashi mumkin, shuning uchun mukofot test_money'da
        assert await db.top(-1)

    asyncio.run(go())


def test_morning_renders_every_event_kind():
    """Dvijok chiqaradigan har bir hodisa matnga aylanadi (xatosiz)."""
    import json
    from mafia_zone.engine.game import Game

    seen = set()
    for seed in range(3000):
        rng = random.Random(seed)
        n = rng.randint(4, 30)
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed,
                        items={i: {"shield": 1, "doc": 1, "verbena": 1} for i in range(1, n + 1)})
        while g.phase != FINISHED:
            for p in g.alive():
                acts = g.available_actions(p.uid)
                if acts:
                    k = rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    g.submit(p.uid, k, rng.choice(ts) if ts else None)
            ev = g.resolve_night()
            texts.morning(g, ev)
            seen |= {e.kind for e in ev}
            for u, t in list(g.hunt):  # Ovchi kunduzi: ba'zan o'ldiradi, ba'zan rahm qiladi
                texts.hunt_pm(g, t, g.get(t).role)
                if rng.random() < 0.6 and (hev := g.hunter_kill(u)):
                    texts.morning(g, hev)
                    seen |= {e.kind for e in hev}
            if g.phase == FINISHED:
                break
            g.start_voting()
            for p in g.alive():
                if g.can_vote(p.uid):
                    g.cast_vote(p.uid, rng.choice([None] + [x.uid for x in g.alive() if x.uid != p.uid]))
            ev = g.resolve_vote()
            texts.morning(g, ev)
            seen |= {e.kind for e in ev}
        json.dumps(g.to_dict())
    expected = {"blocked", "stolen", "steal_empty", "robbed", "checked", "interview", "dug", "saved", "item_used",
                "killed", "revenge", "linked", "transformed", "promoted", "hunted", "witness",
                "hanged", "no_hang", "guard_saved", "tulki", "game_over"}
    assert expected <= seen, expected - seen


def assert_telegram_html(text):
    from html.parser import HTMLParser

    stack = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag in ("b", "i", "a", "code", "u", "s", "tg-spoiler", "pre", "blockquote"), (tag, text)
            stack.append(tag)

        def handle_endtag(self, tag):
            assert stack and stack.pop() == tag, text

    P().feed(text)
    assert not stack, text
    assert len(text) <= 4096


def test_sent_messages_are_valid_html_and_restore_works():
    async def go():
        await db.init()
        bot = FakeBot()
        chat = -999
        await db.group_settings(chat, "test")
        await db.save_group_settings(chat, {"lobby": 0, "night": 0, "day": 0, "vote": 0})
        r = AutoRunner(bot, chat, await db.group_settings(chat))
        for uid in range(101, 131):
            await db.upsert_user(uid, f"<Ali & {uid}>", None)
            runner.PLAYING.pop(uid, None)
            r.join(uid, f"<Ali & {uid}>")

        async def no_loop():  # "qulash": o'yin yaratildi, sikl boshlanmadi
            pass

        r._loop = no_loop
        await r._start_game()
        gid = r.game_id
        r.close()
        await runner.restore(bot)
        restored = runner.RUNNERS[chat]
        assert restored.game_id == gid
        await restored.task
        assert restored.game.phase == FINISHED
        assert (await db.running_games()) == []
        for _, text in bot.sent:
            assert_telegram_html(text)

    asyncio.run(go())


def test_group_rate_limit(monkeypatch):
    clock = [1000.0]
    slept = []

    async def fake_sleep(s):
        slept.append(s)
        clock[0] += s

    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "GROUP_PER_MIN", 3)

    async def go():
        for _ in range(3):
            await runner._group_slot(-555)
        assert slept == []
        await runner._group_slot(-555)  # 4-xabar daqiqa o'tishini kutadi
        assert len(slept) == 1 and 60 <= slept[0] <= 61
        await runner._group_slot(42)  # shaxsiy chat cheklanmaydi
        assert len(slept) == 1

    asyncio.run(go())


def test_testgame_bots_play_to_the_end():
    async def go():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -777, {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": False,
                                       "afk": True, "disabled": []})
        r.add_bots(12)
        await r._start_game()
        assert r.game.phase == FINISHED
        assert all(chat < runner.FAKE_BASE for chat, _ in bot.sent)  # botlarga xabar ketmaydi
        group = [t for c, t in bot.sent if c == -777]
        assert any(t.endswith("ga ovoz berdi") or t.endswith("ovoz bermadi") for t in group)  # har ovoz alohida
        assert any(t.endswith("...") and "\n" not in t for t in group)  # har tungi harakat alohida xabar
        merged = [t for t in group if "\n" in t and all(x.endswith("...") for x in t.split("\n"))]
        assert not merged  # lenta qatorlari hech qachon bitta xabarga birlashmaydi
        assert bot.gifs.count("gif-id") >= 1  # GIF bir marta yuklanib, keyin file_id bilan
        for t in group:
            assert_telegram_html(t)
        # o'yin boshi tartibi: O'YIN BOSHLANDI -> Tun GIF -> tirik o'yinchilar + tarkib
        start, night = group.index(texts.GAME_STARTED), group.index(texts.NIGHT_CAPTION)
        roster = group[night + 1]
        assert start < night and roster.startswith("<b>Tirik o'yinchilar:</b>\n1. ") and "Jami: 12" in roster
        assert sum(t.startswith("<b>Tirik o'yinchilar:</b>") for t in group[:night + 2]) == 1
        p = r.game.players[0]  # "🎭 Sizning rolingiz" - faqat rol nomi, vazifasiz
        assert texts.role_alert(r.game, p.uid) == f"Sizning rolingiz: {ROLES[p.role].name}"

    asyncio.run(go())


def test_split_text():
    text = "\n".join(f"<b>qator {i}</b> " + "x" * 50 for i in range(300))
    parts = runner.split_text(text)
    assert len(parts) > 1 and all(len(p) <= runner.MAX_TEXT for p in parts)
    assert "\n".join(parts) == text
    for p in parts:
        assert_telegram_html(p)
    assert runner.split_text("y" * 9000) == ["y" * 3800, "y" * 3800, "y" * 1400]


def test_sixty_players_game():
    class BigBot(FakeBot):
        async def send_message(self, chat_id, text, reply_markup=None, **kw):
            assert len(text) <= 4096
            if reply_markup:
                assert sum(len(r) for r in reply_markup.inline_keyboard) <= 100
            return await super().send_message(chat_id, text, **kw)

    async def go():
        await db.init()
        bot = BigBot()
        r = runner.Runner(bot, -6060, {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": False,
                                        "afk": True, "confirm": True, "disabled": []})
        r.add_bots(60)
        assert len(r.members) == 60
        assert r.join(123, "ortiqcha") == texts.LOBBY_FULL and 123 in runner.NEXT[-6060]
        await r._start_game()
        assert r.game.phase == FINISHED and r.game.max_days == 60

    asyncio.run(go())


def test_last_words_for_every_death_kind():
    from mafia_zone.engine.game import Event
    ev = [Event("killed", target=1), Event("hanged", target=2), Event("revenge", 5, 3), Event("linked", target=4),
          Event("tulki", 2, 6), Event("afk", target=7), Event("left", target=8), Event("killed", target=1)]
    assert texts.victims(ev) == [1, 2, 3, 4, 6]  # AFK/chiqib ketgan yo'q, takror yo'q
    assert "<b>60</b> soniya" in texts.death_pm(False) and "osib" in texts.death_pm(True)


def test_late_confirm_click_does_not_crash_next_phase():
    """Tasdiq tugashidan oldin bosilgan 👍 belgisi keyingi tunda eski xabarni tahrirlab o'yinni yiqitmasin."""
    from mafia_zone.engine.game import Game

    async def go():
        bot = FakeBot()
        r = runner.Runner(bot, -4343, {"vote": 10})
        r.game = Game.create(-4343, [(i, f"p{i}") for i in range(1, 7)], 3)
        g = r.game
        g.phase, g.candidate, r.meta["confirm_msg"] = CONFIRM, 1, 77
        r.confirm_dirty = True
        g.resolve_confirm()  # tasdiq tugadi, nomzod yo'q, faza o'zgardi
        n = len(bot.sent)
        await r._edit_confirm(final=False)
        assert not r.confirm_dirty and len(bot.sent) == n
        assert texts.nm(g, None) == "?" and texts.nm(g, 999) == "?"
        r.close()

    asyncio.run(go())


def test_last_words_late_goes_nowhere():
    from mafia_zone.engine.game import Game, Player
    import time as _t

    async def go():
        bot = FakeBot()
        r = runner.Runner(bot, -4242, {})
        r.game = Game(-4242, 1, [Player(1, "a", "tinch", alive=False), Player(2, "b", "tinch", alive=False),
                                 Player(3, "c", "don")], phase="day")
        r.last_words = {1: _t.time() + 60, 2: _t.time() - 1}
        assert await r.on_private_text(1, "vaqtida")
        assert bot.sent[-2][0] == -4242 and "vaqtida" in bot.sent[-2][1]  # guruhga
        assert bot.sent[-1] == (1, texts.LAST_WORDS_SENT)  # o'ziga: yetkazildi
        n = len(bot.sent)
        assert await r.on_private_text(2, "kech")
        assert bot.sent[n:] == [(2, texts.LAST_WORDS_LATE)]  # faqat o'ziga ogohlantirish
        assert await r.on_private_text(2, "keyingi")
        assert bot.sent[-1][0] == 1 and "keyingi" in bot.sent[-1][1]  # endi o'liklar chatiga
        r.close()

    asyncio.run(go())


def test_game_again_reposts_lobby_with_same_players():
    async def t():
        bot = FakeBot()
        deleted, pinned = [], []
        async def delete_message(chat_id, message_id):
            deleted.append(message_id)
        async def pin_chat_message(chat_id, message_id, **kw):
            pinned.append(message_id)
        bot.delete_message, bot.pin_chat_message = delete_message, pin_chat_message
        r = runner.Runner(bot, -991, dict(runner.config.DEFAULT_SETTINGS, lobby=600))
        r.members = [(1, "Ali"), (2, "Vali")]
        await r.open_lobby()
        first = r.lobby_msg
        await r.repost_lobby()
        assert r.lobby_msg != first and deleted == [first] and pinned[-1] == r.lobby_msg
        assert "Ali" in bot.sent[-1][1] and "Vali" in bot.sent[-1][1]
        r.task.cancel()
        r.close()
    asyncio.run(t())


def test_hanged_afsungar_gets_night_buttons():
    from mafia_zone.engine.game import Game, Player

    async def go():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -4446, {"night": 10})
        r.game, r.game_id = Game(-4446, 1, [Player(1, "a", "don"), Player(2, "b", "afsungar", alive=False),
                                            Player(3, "c", "tinch"), Player(4, "d", "tinch")]), 57
        r.game.bomb = 2
        try:
            await r._intro(NIGHT, 10)
            pm = [t for c, t in bot.sent if c == 2]
            assert pm and texts.ROLE_PROMPT["afsungar"] in pm[0]
            assert r.night_kb(2).inline_keyboard[0][0].callback_data.startswith("a:57:1:blast:")
            assert await r.on_action(2, 1, "blast", 1) and r.live_lines == []  # guruhga yozilmaydi
        finally:
            r.close()

    asyncio.run(go())


def test_back_to_group_button_on_game_pms():
    """O'yin paytida botdagi har xabar oxirida "Guruhga qaytish" (guruhdagi oxirgi bot xabariga)."""
    from aiogram.methods import EditMessageText, SendMessage
    from aiogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
    from mafia_zone.engine.game import Game

    async def go():
        chat = -1001234567890
        r = runner.Runner(FakeBot(), chat, {})
        r.game = Game.create(chat, [(i, f"p{i}") for i in range(1, 5)], 3)
        runner.PLAYING[1] = r
        calls = []

        async def make_request(bot, method):
            calls.append(method)
            return SimpleNamespace(message_id=41)
        mw = runner.BackToGroup()
        try:
            await mw(make_request, None, SendMessage(chat_id=chat, text="guruhga"))  # guruh xabari: tugmasiz
            assert calls[-1].reply_markup is None
            url = "https://t.me/c/1234567890/41"
            await mw(make_request, None, SendMessage(chat_id=1, text="rol"))
            assert [[b.url for b in row] for row in calls[-1].reply_markup.inline_keyboard] == [[url]]
            assert calls[-1].reply_markup.inline_keyboard[0][0].text == texts.BACK_TO_GROUP
            kb = Kb(inline_keyboard=[[Btn(text="1. Ali", callback_data="a")]])
            await mw(make_request, None, EditMessageText(chat_id=1, message_id=3, text="x", reply_markup=kb))
            assert calls[-1].reply_markup.inline_keyboard == kb.inline_keyboard  # tanlov tugmalari: qaytish yo'q
            await mw(make_request, None, EditMessageText(chat_id=1, message_id=3, text="Siz Alini tanladingiz"))
            assert calls[-1].reply_markup.inline_keyboard[-1][0].url == url  # tanlovdan keyin chiqadi
            link = Kb(inline_keyboard=[[Btn(text="Kanal", url="https://t.me/x")]])
            await mw(make_request, None, SendMessage(chat_id=1, text="x", reply_markup=link))
            await mw(make_request, None, EditMessageText(chat_id=1, message_id=3, text="x",
                                                         reply_markup=calls[-1].reply_markup))
            assert len(calls[-1].reply_markup.inline_keyboard) == 2  # ikki marta qo'shilmaydi
            await mw(make_request, None, SendMessage(chat_id=2, text="o'yinda emas"))
            assert calls[-1].reply_markup is None
        finally:
            runner.PLAYING.pop(1, None)
            r.close()

    asyncio.run(go())


def test_double_game_press_leaves_one_lobby():
    """/game ni ikki kishi bir vaqtda bossa: guruhda bitta ro'yxat qoladi."""
    async def t():
        bot = FakeBot()
        deleted = []
        slow = bot.send_message

        async def send_message(chat_id, text, **kw):
            await asyncio.sleep(0.05)  # Telegram javobi kechikadi - shu orada ikkinchi /game keladi
            return await slow(chat_id, text, **kw)

        async def delete_message(chat_id, message_id):
            deleted.append(message_id)

        async def pin_chat_message(*a, **kw):
            pass
        bot.send_message, bot.delete_message, bot.pin_chat_message = send_message, delete_message, pin_chat_message
        await db.init()
        r = runner.Runner(bot, -992, dict(runner.config.DEFAULT_SETTINGS, lobby=600))
        try:
            await asyncio.gather(r.open_lobby(), r.repost_lobby(), r.repost_lobby())
            lobbies = [i + 1 for i, (c, _) in enumerate(bot.sent) if c == -992]
            assert [m for m in lobbies if m not in deleted] == [r.lobby_msg]
        finally:
            if r.task:
                r.task.cancel()
            r.close()
    asyncio.run(t())


def test_cancelled_lobby_is_unpinned_and_deleted():
    async def t():
        bot = FakeBot()
        log = []
        async def delete_message(chat_id, message_id):
            log.append(("del", message_id))
        async def unpin_chat_message(chat_id, message_id=None):
            log.append(("unpin", message_id))
        async def pin_chat_message(chat_id, message_id, **kw):
            pass
        bot.delete_message, bot.unpin_chat_message, bot.pin_chat_message = delete_message, unpin_chat_message, pin_chat_message
        for how in ("stop", "few"):
            log.clear()
            r = runner.Runner(bot, -992, dict(runner.config.DEFAULT_SETTINGS, lobby=600))
            r.members = [(1, "Ali")]
            await r.open_lobby()
            lobby = r.lobby_msg
            if how == "stop":
                await r.abort()
            else:
                r.task.cancel()
                await r._start_game()
            assert log == [("unpin", lobby), ("del", lobby)], how
            assert -992 not in runner.RUNNERS
    asyncio.run(t())


def test_role_button_shows_own_role_only():
    from mafia_zone import handlers
    from mafia_zone.engine.game import Game, Player
    async def t():
        g = Game(-993, 1, [Player(1, "A" * 60, "don"), Player(2, "B" * 60, "mafiya"), Player(3, "C" * 60, "yollanma"),
                           Player(4, "Vali", "tinch")])
        r = SimpleNamespace(game=g, game_id=77)
        said = []
        async def answer(text=None, show_alert=False):
            said.append((text, show_alert))
        handlers.PLAYING.update({1: r, 4: r})
        try:
            for uid, data in ((1, "r:77"), (4, "r:77"), (5, "r:77"), (4, "r:76")):
                await handlers.cb_role(SimpleNamespace(data=data, from_user=SimpleNamespace(id=uid), answer=answer))
        finally:
            handlers.PLAYING.pop(1, None); handlers.PLAYING.pop(4, None)
        assert "Don" in said[0][0] and "Sheriklar" not in said[0][0] and len(said[0][0]) <= 200  # sheriklar - faqat botda
        assert "Tinch aholi" in said[1][0]
        assert said[2][0] == said[3][0] == texts.NOT_IN_GAME and all(a for _, a in said)
    asyncio.run(t())


def test_last_words_timeout_notifies_and_vote_kb_marks_mates():
    from mafia_zone.engine.game import Game, Player
    import time as _t

    async def go():
        bot = FakeBot()
        r = runner.Runner(bot, -4243, {})
        r.game_id = 5
        r.game = Game(-4243, 1, [Player(1, "a", "don"), Player(2, "b", "mafiya"), Player(3, "c", "tinch"),
                                 Player(4, "d", "tinch", alive=False)], phase="voting")
        rows = r.vote_kb(1).inline_keyboard
        assert all(len(row) == 1 for row in rows)  # bir ustun
        assert [rows[0][0].text, rows[1][0].text] == ["2. 🤵🏼 " + pro.short("b"), "3. " + pro.short("c")]
        r.last_words = {4: _t.time() + 0.05}
        await r._last_words_timeout(4, r.last_words[4])
        assert bot.sent[-1] == (4, texts.LAST_WORDS_TIMEOUT) and 4 not in r.last_words
        r.close()
    asyncio.run(go())


class CleanBot(FakeBot):
    """FakeBot + pin/unpin/delete jurnali."""
    def __init__(self):
        super().__init__()
        self.log = []

    async def pin_chat_message(self, chat_id, message_id, **kw):
        self.log.append(("pin", chat_id, message_id))

    async def unpin_chat_message(self, chat_id, message_id=None):
        self.log.append(("unpin", chat_id, message_id))

    async def delete_message(self, chat_id, message_id):
        self.log.append(("del", chat_id, message_id))


def test_giveaway_expires_and_refunds():
    from mafia_zone import handlers

    async def t():
        await db.init()
        a, b = 8_100_001, 8_100_002
        for u in (a, b):
            await db.upsert_user(u, f"u{u}", None)
        await db.add_balance(a, 100)
        gid = await db.create_giveaway(-994, a, 10, 10)
        await db.set_giveaway_msg(gid, 55)
        assert await db.claim(gid, b)
        bot = CleanBot()
        await handlers.expire_giveaway(bot, gid, 0)
        assert (await db.get_user(a)).dollars == 90  # 9 ulush qaytdi
        assert ("unpin", -994, 55) in bot.log and "Vaqt tugadi" in bot.sent[0][1] and bot.sent[-1][0] == a
        n = len(bot.sent)
        await handlers.expire_giveaway(bot, gid, 0)  # ikkinchi marta: hech narsa
        assert len(bot.sent) == n and (await db.get_user(a)).dollars == 90
    asyncio.run(t())


def test_leave_frees_player_and_repeat_action_is_quiet():
    from mafia_zone.engine.game import Game, Player

    async def t():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -995, dict(runner.config.DEFAULT_SETTINGS))
        r.game = Game(-995, 1, [Player(1, "a", "komissar"), Player(2, "b", "tinch"), Player(3, "c", "don"),
                                Player(4, "d", "tinch")])
        r.game_id = 9
        for p in r.game.players:
            runner.PLAYING[p.uid] = r
        await r.on_action(1, 1, "check", 2)
        await r.on_action(1, 1, "check", 3)  # tanlovni almashtirdi
        assert len(r.live_lines) == 1
        await r.leave(2)
        assert 2 not in runner.PLAYING and not r.game.get(2).alive
        r.close()
    asyncio.run(t())


def test_restart_cleans_lost_lobbies_and_move_chat():
    async def t():
        await db.init()
        await db.save_lobby(-996, 77)
        bot = CleanBot()
        await runner.restore(bot)
        assert ("unpin", -996, 77) in bot.log and ("del", -996, 77) in bot.log
        assert bot.sent[-1] == (-996, texts.LOBBY_LOST) and not await db.lobbies()
        r = runner.Runner(bot, -997, dict(runner.config.DEFAULT_SETTINGS))
        await r.move(-1000997)
        assert runner.RUNNERS.get(-1000997) is r and -997 not in runner.RUNNERS and r.chat_id == -1000997
        r.close()
    asyncio.run(t())


def test_bot_removed_aborts_game():
    from mafia_zone import handlers

    async def t():
        await db.init()
        bot = CleanBot()
        r = runner.Runner(bot, -998, dict(runner.config.DEFAULT_SETTINGS))
        upd = SimpleNamespace(chat=SimpleNamespace(id=-998), new_chat_member=SimpleNamespace(status="kicked"))
        await handlers.on_bot_removed(upd)
        assert -998 not in runner.RUNNERS
    asyncio.run(t())


def test_phase_timer_starts_after_buttons_are_sent():
    """Guruh limiti to'lib 👍/👎 xabari kechiksa ham, vaqt tugmalar chiqqandan keyin boshlanadi."""
    from mafia_zone.engine.game import Game

    async def go():
        await db.init()
        r = runner.Runner(FakeBot(), -4445, {"vote": 10})
        r.game, r.game_id = Game.create(-4445, [(i, f"p{i}") for i in range(1, 7)], 3), 56
        g = r.game
        g.phase, g.candidate = CONFIRM, 1
        seen = []

        async def slow_intro(ph, secs):  # guruh limiti: xabar navbatda kutdi
            seen.append("deadline" in r.meta)
            for p in g.alive():
                if g.can_confirm(p.uid):
                    g.cast_confirm(p.uid, False)
        r._intro = slow_intro
        try:
            await r._step()
            assert seen == [False]
        finally:
            r.close()

    asyncio.run(go())


def test_feed_lines_separate_and_phase_not_delayed_by_group_limit():
    """Guruh limiti to'lib yuborish kutib tursa ham: faza o'z vaqtida hal bo'ladi, har qator alohida xabar,
    tartib saqlanadi va natija (e'lon) hamma qatorlardan keyin chiqadi."""
    from mafia_zone.engine.game import Game

    async def go():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -4848, {"vote": 10})
        r.game, r.game_id = Game.create(-4848, [(i, f"p{i}") for i in range(1, 7)], 3), 80
        r.game.phase = VOTING
        r.meta["deadline"] = time.time() + 1.5
        gate, out, orig = asyncio.Event(), [], runner.send

        async def slow_send(b, chat_id, text, kb=None, **kw):
            if chat_id < 0:
                await gate.wait()  # guruh limiti: Telegram ruxsat berguncha kutadi
                out.append(text)
            return SimpleNamespace(message_id=1)
        runner.send = slow_send
        try:
            for v in (1, 2, 3):
                assert await r.on_vote(v, r.game.day, 0)
            step = asyncio.create_task(r._step())
            await asyncio.sleep(3)
            assert r.game.phase != VOTING and "deadline" not in r.meta  # vaqtida hal bo'ldi
            assert not step.done() and not out  # e'lon lenta qatorlarini kutyapti
            gate.set()
            await step
        finally:
            runner.send = orig
            r.close()
        feed = [t for t in out if t.endswith("ovoz bermadi")]
        assert len(feed) == 3 and out[:3] == feed  # alohida, birinchi; natija keyin
    asyncio.run(go())


def test_ovchi_hunt_button_kills_by_day_and_pays_fine_to_victim():
    from mafia_zone import handlers
    from mafia_zone.engine.game import DAY, HUNT_FINE, Game, Player

    async def go():
        await db.init()
        ids = [9_100_000 + i for i in range(1, 8)]
        for u in ids:
            await db.upsert_user(u, f"p{u}", None)
        await db.add_balance(ids[1], 1000)  # Ovchi
        o0, v0 = (await db.get_user(ids[1])).dollars, (await db.get_user(ids[2])).dollars
        bot = FakeBot()
        r = runner.Runner(bot, -4949, {"night": 60, "day": 60, "vote": 60})
        roles = ["don", "ovchi", "tinch", "tinch", "tinch", "tinch", "tinch"]
        r.game, r.game_id = Game(-4949, 5, [Player(u, f"p{u}", x) for u, x in zip(ids, roles)], afk_limit=0), 81
        for u in ids:
            handlers.PLAYING[u] = r
        try:
            assert await r.on_action(ids[1], 1, "check", ids[2])
            r.meta["deadline"] = 0
            await r._step()  # tun hal bo'ldi, tong e'lon qilindi
            assert r.game.phase == DAY and r.game.hunt == [[ids[1], ids[2]]]
            assert any(c == ids[1] and "rahm" in t for c, t in bot.sent)  # rol + o'ldirish tugmasi
            said = []

            async def answer(text=None, **kw):
                said.append(text)

            async def edit_reply_markup(**kw):
                pass
            cq = lambda uid: SimpleNamespace(data=f"h:81:{r.game.day}", from_user=SimpleNamespace(id=uid),
                                             answer=answer, message=SimpleNamespace(edit_reply_markup=edit_reply_markup))
            await handlers.cb_hunt(cq(ids[3]))  # Ovchi emas
            assert r.game.get(ids[2]).alive and said[-1] == texts.HUNT_NO
            await handlers.cb_hunt(cq(ids[1]))
            assert not r.game.get(ids[2]).alive
            group = [t for c, t in bot.sent if c == -4949]
            assert any("murdasi topildi" in t for t in group) and any("jarima" in t for t in group)
            assert any(c == ids[2] and "joningizni oldi" in t for c, t in bot.sent)  # so'nggi so'z
            fine = (await db.get_user(ids[2])).dollars - v0  # jarima o'ldirilganga o'tdi
            assert HUNT_FINE[0] <= fine <= HUNT_FINE[1] and (await db.get_user(ids[1])).dollars == o0 - fine
            await handlers.cb_hunt(cq(ids[1]))  # ikkinchi marta - yo'q
            assert said[-1] == texts.HUNT_NO
            r.game.start_voting()
            await handlers.cb_hunt(cq(ids[1]))  # ovoz berish boshlandi - kech
            assert said[-1] == texts.HUNT_LATE
        finally:
            for u in ids:
                handlers.PLAYING.pop(u, None)
            r.close()
    asyncio.run(go())


def test_night_submenu_has_back_button():
    """Komissar "Otish"ni adashib bossa - ⬅️ Orqaga bilan harakat tanlashga qaytadi. Bitta harakatli rolda yo'q."""
    from mafia_zone.engine.game import Game, Player
    r = runner.Runner(FakeBot(), -4747, {})
    r.game = Game(-4747, 1, [Player(1, "a", "komissar"), Player(2, "b", "doktor"), Player(3, "c", "don"),
                             Player(4, "d", "tinch")])
    r.game_id = 79
    cbs = lambda kb: [b.callback_data for row in kb.inline_keyboard for b in row]
    menu = cbs(r.night_kb(1))
    assert f"k:79:{r.game.day}:shoot" in menu and not any(c.endswith(":menu") for c in menu)
    assert len(r.night_kb(1).inline_keyboard[0]) == 2  # Tekshirish | Otish - bitta qatorda
    sub = r.night_kb(1, "shoot")
    assert cbs(sub)[-1] == f"k:79:{r.game.day}:menu" and sub.inline_keyboard[-1][0].text == texts.BACK_BTN
    assert cbs(r.night_kb(1, None)) == menu  # "menu" -> qayta harakat tanlash
    assert not any(c.endswith(":menu") for c in cbs(r.night_kb(2)))  # Doktor: bitta harakat
    r.close()


def test_unanswered_prompts_deleted_when_phase_ends():
    """Ovoz berish tugadi: javob bermaganlarning tugmali xabari o'chadi, ovoz berganniki ("Ovozingiz: ...") qoladi."""
    from mafia_zone.engine.game import Game

    async def go():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -4646, {"vote": 10})
        r.game, r.game_id = Game.create(-4646, [(i, f"p{i}") for i in range(1, 7)], 3), 78
        r.game.phase = VOTING
        await r._intro(VOTING, 10)
        sent = dict(r.prompts)
        assert set(sent) == {p.uid for p in r.game.alive() if r.game.can_vote(p.uid)}
        assert await r.on_vote(1, r.game.day, 0)
        r.meta["deadline"] = 0  # vaqt tugadi
        await r._step()
        await asyncio.sleep(0.2)  # fondagi o'chirish
        assert sorted(bot.deleted) == sorted((u, m) for u, m in sent.items() if u != 1) and not r.prompts
        r.close()
    asyncio.run(go())


def test_group_ephemeral_prompts_mirror_private_ones():
    """Ovoz tugmalari guruhda ham chiqadi, faqat egasiga (ephemeral). Guruhdagisi bosilsa - shaxsiy chatdagi o'chadi;
    shaxsiydagisi bosilsa - guruhdagi o'chadi; faza oxirida guruhdagilarning hammasi o'chadi."""
    from mafia_zone.engine.game import Game

    async def go():
        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -4647, {"vote": 10})
        r.game, r.game_id = Game.create(-4647, [(i, f"p{i}") for i in range(1, 7)], 3), 79
        r.game.phase = VOTING
        await r._intro(VOTING, 10)
        voters = {p.uid for p in r.game.alive() if r.game.can_vote(p.uid)}
        assert {u for c, u, _ in bot.eph if c == -4647} == voters == set(r.eph)  # guruh lentasiga tushmaydi
        pm1, e2 = r.prompts[1], r.eph[2]
        assert await r.on_vote(1, r.game.day, 0)
        await r.drop_prompt(1, via_eph=True)  # 1 - guruhdagi tugmani bosdi: shaxsiydagi o'chadi
        assert (1, pm1) in bot.deleted
        assert await r.on_vote(2, r.game.day, 0)
        await r.drop_prompt(2, via_eph=False)  # 2 - shaxsiydagini bosdi: guruhdagi o'chadi
        assert (-4647, 2, e2) in bot.eph_deleted and 2 not in r.eph
        r.meta["deadline"] = 0
        await r._step()
        await asyncio.sleep(0.2)
        assert {u for _, u, _ in bot.eph_deleted} == voters and not r.eph
        r.close()
    asyncio.run(go())


def test_late_button_answers_and_deletes_private_prompt():
    """Vaqt o'tgan ovoz/tun tugmasi: tepada "kechikdingiz", shaxsiy chatdagi so'rov o'chadi, guruhdagisi qoladi."""
    from mafia_zone import handlers
    from mafia_zone.engine.game import Game

    async def go():
        r = runner.Runner(FakeBot(), -4545, {})
        r.game, r.game_id = Game.create(-4545, [(i, f"p{i}") for i in range(1, 7)], 3), 77
        handlers.PLAYING[1] = r
        try:
            for data, chat, late in [(f"v:77:{r.game.day}:2", 1, texts.LATE_VOTE),  # tun: ovoz eski
                                     (f"a:77:{r.game.day - 1}:kill:2", 1, texts.LATE_NIGHT),  # o'tgan tun
                                     (f"v:76:{r.game.day}:2", 1, texts.LATE_VOTE),  # eski o'yin
                                     (f"c:77:{r.game.day}:1", -4545, texts.LATE_VOTE)]:  # guruh: o'chirilmaydi
                said, deleted = [], []

                async def answer(text=None, **kw):
                    said.append(text)

                async def delete():
                    deleted.append(1)
                cq = SimpleNamespace(data=data, from_user=SimpleNamespace(id=1), answer=answer,
                                     message=SimpleNamespace(chat=SimpleNamespace(id=chat), delete=delete))
                cb = {"v": handlers.cb_vote, "a": handlers.cb_action, "c": handlers.cb_confirm}[data[0]]
                await cb(cq)
                assert said == [late] and deleted == ([1] if chat > 0 else []), data
        finally:
            handlers.PLAYING.pop(1, None)
            r.close()
    asyncio.run(go())


def test_confirm_cannot_be_killed_by_deleting_group_message():
    """Admin guruhdagi 👍/👎 xabarini o'chirsa ham: tugmalar botda ham bor, xabar qayta yuboriladi."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText
    from mafia_zone import handlers
    from mafia_zone.engine.game import Game

    class DeletedBot(FakeBot):
        async def edit_message_text(self, text, chat_id, message_id, **kw):
            raise TelegramBadRequest(EditMessageText(text=text), "Bad Request: message to edit not found")

    async def go():
        await db.init()
        bot, chat = DeletedBot(), -4444
        r = runner.Runner(bot, chat, {"vote": 10})
        r.game, r.game_id = Game.create(chat, [(i, f"p{i}") for i in range(1, 7)], 3), 55
        g = r.game
        g.phase, g.candidate = CONFIRM, 1
        handlers.RUNNERS[chat] = r
        for p in g.players:
            handlers.PLAYING[p.uid] = r
        try:
            await r._intro(CONFIRM, 10)
            pms = {c for c, _ in bot.sent if c > 0}
            assert pms == {p.uid for p in g.alive() if g.can_confirm(p.uid)}  # har kimga botda tugmalar
            said = []

            async def answer(text=None, **kw):
                said.append(text)

            async def edit_text(*a, **kw):
                pass
            cq = SimpleNamespace(data=f"c:55:{g.day}:1", from_user=SimpleNamespace(id=2), answer=answer,
                                 message=SimpleNamespace(chat=SimpleNamespace(id=2), edit_text=edit_text))
            await handlers.cb_confirm(cq)  # botning shaxsiy chatidan
            assert g.confirms.get(2) is True
            old, n = r.meta["confirm_msg"], len(bot.sent)
            await r._edit_confirm(final=False)  # guruh xabari o'chirilgan - qayta yuboriladi
            assert r.meta["confirm_msg"] != old and bot.sent[n][0] == chat
            n = len(bot.sent)
            await r._edit_confirm(final=True)
            assert bot.sent[n][0] == chat and "vaqt tugadi" in bot.sent[n][1]  # natija yangi xabar bo'lib chiqadi
        finally:
            handlers.RUNNERS.pop(chat, None)
            for p in g.players:
                handlers.PLAYING.pop(p.uid, None)
            r.close()

    asyncio.run(go())


def test_deleted_lobby_is_reposted():
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText

    class DeletedBot(FakeBot):
        async def edit_message_text(self, text, chat_id, message_id, **kw):
            raise TelegramBadRequest(EditMessageText(text=text), "Bad Request: message to edit not found")

        async def delete_message(self, *a, **kw):
            return True

        async def pin_chat_message(self, *a, **kw):
            return True

    async def go():
        await db.init()
        bot, chat = DeletedBot(), -4545
        r = runner.Runner(bot, chat, {"lobby": 60})
        runner.RUNNERS[chat] = r
        try:
            r.lobby_msg, r.lobby_deadline = 5, __import__("time").time() + 60
            await r._refresh_lobby()  # admin ro'yxatni o'chirgan - qayta chiqadi
            assert r.lobby_msg != 5 and bot.sent[-1][0] == chat
        finally:
            runner.RUNNERS.pop(chat, None)
            r.close()

    asyncio.run(go())


def test_couple_game_through_runner():
    """/couplegame: faqat juftlar qo'shiladi, jufti kelmaganlar chiqariladi, oxirgi tirik juft yutadi."""
    from mafia_zone import handlers

    async def go():
        await db.init()
        bot, base = CleanBot(), 9_100_000
        runner.BOT_USERNAME = "AdmiralMafiaBot"
        for chat in range(-51, -59, -1):
            k = 2 + (-chat) % 5  # 2..6 para
            uids = [base + chat * -100 + i for i in range(1, 2 * k + 3)]
            for u in uids:
                await db.upsert_user(u, f"o'yinchi {u}", None)
            for a, b in zip(uids[:2 * k:2], uids[1:2 * k:2]):
                assert await db.make_couple(a, b)
            assert await db.make_couple(uids[-2], uids[-1])  # bu juftning faqat biri qo'shiladi
            settings = {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": True, "disabled": []}
            r = AutoRunner(bot, chat, settings, couple=True)
            said = []

            async def answer(text=None, **kw):
                said.append(text)
            for u in uids[:-1] + [base + 99_999]:  # oxirgisi - umuman jufti yo'q
                runner.PLAYING.pop(u, None)
                await db.upsert_user(u, f"o'yinchi {u}", None)
                m = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name=f"o'yinchi {u}", username=None),
                                    answer=answer)
                await handlers.cmd_start(m, bot, SimpleNamespace(args=f"join{chat}"))
            assert said[-1] == texts.NO_COUPLE_JOIN and base + 99_999 not in dict(r.members)
            lobby = r._lobby_text()
            assert "PARALAR" in lobby and "❤️" in lobby and "jufti kutilmoqda" in lobby and "💞" not in lobby
            assert "Faqat /couple" not in lobby and "\n1. ❤️ " in lobby  # har para yangi qatorda
            assert r._lobby_kb().inline_keyboard[0][0].style is None  # tugmalar rangsiz (faqat profil ON/OFF rangli)
            r.lobby_msg = 1
            await r._start_game()
            g = r.game
            assert g.couple_mode and g.phase == FINISHED and uids[-2] not in g.pairs and len(g.players) == 2 * k
            won = {p.uid for p in g.players if p.won}
            assert g.winner == "draw" and not won or len(won) == 2 and g.pairs[min(won)] == max(won)
        for _, text in bot.sent:
            assert_telegram_html(text)
        assert any("PARALAR O'YINI BOSHLANDI" in t for _, t in bot.sent)
        assert any("juftingiz" in t for _, t in bot.sent)

    asyncio.run(go())


def test_partner_chat_with_plus():
    from mafia_zone.engine.game import Game

    async def go():
        bot = FakeBot()
        r = runner.Runner(bot, -4646, {})
        r.game = Game.create(-4646, [(i, f"p{i}") for i in range(1, 7)], 3)
        r.game.pairs = {1: 2, 2: 1}
        assert await r.on_private_text(1, "+salom jonim")
        assert any(c == 2 and "salom jonim" in t for c, t in bot.sent) and any(c == 1 for c, _ in bot.sent)
        n = len(bot.sent)
        assert await r.on_private_text(3, "+salom")  # juft yo'q
        assert bot.sent[n:] == [(3, texts.NO_PARTNER)]
        r.close()

    asyncio.run(go())


def test_player_numbers_stay_the_same():
    """O'yin boshidagi raqam saqlanadi: 5-o'yinchi chiqsa, ro'yxatda 5 bo'lmaydi; tugmalarda ham shu raqam."""
    from mafia_zone.engine.game import Game

    g = Game.create(-4747, [(i, f"p{i}") for i in range(1, 8)], 3)
    g.get(2).alive = g.get(5).alive = False
    lines = texts.alive_list(g).split("\n")[1:]
    assert [ln.split(".")[0] for ln in lines] == ["1", "3", "4", "6", "7"]
    r = runner.Runner(FakeBot(), -4747, {})
    r.game, r.game_id = g, 1
    g.start_voting()
    texts_ = [b.text for row in r.vote_kb(1).inline_keyboard for b in row]
    assert [t.replace(texts.USER_MARK, "") for t in texts_[:4]] == ["3. p3", "4. p4", "6. p6", "7. p7"]
    r.close()


def test_items_not_spent_when_game_not_created():
    """Guruhda o'yin allaqachon bor (create_game -> None): maska yechilmasin."""
    async def go():
        await db.init()
        u = 8_800_001
        await db.upsert_user(u, "Ali", None)
        await db.change_item(u, "mask", 1)
        r = runner.Runner(FakeBot(), -8801, {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": True,
                                              "afk": True, "disabled": []})
        r.members = [(u, "Ali")]
        r.add_bots(5)
        orig, db.create_game = db.create_game, lambda *a: asyncio.sleep(0, None)
        try:
            await r._start_game()
        finally:
            db.create_game = orig
        assert {i.item: i.qty for i in await db.inventory(u)}["mask"] == 1
    asyncio.run(go())


def _night_runner(roles):
    from mafia_zone.engine.game import Game, Player
    bot = FakeBot()
    r = runner.Runner(bot, -8802, {"lobby": 0, "night": 60, "day": 0, "vote": 0, "items": False,
                                    "afk": True, "disabled": []})
    r.game = Game(-8802, 1, [Player(8_802_000 + i, f"p{i}", c) for i, c in enumerate(roles)], afk_limit=0)
    r.game_id = 1
    return r, bot, [p.uid for p in r.game.players]


def test_donishmand_overhears_mafia_and_komissar_at_night():
    async def go():
        r, bot, (don, maf, kom, ser, dsh, tin) = _night_runner(["don", "mafiya", "komissar", "serjant",
                                                                 "donishmand", "tinch"])
        assert await r.on_private_text(don, "3-ni olamiz")
        got = {c: t for c, t in bot.sent}
        assert "3-ni olamiz" in got[maf] and "3-ni olamiz" in got[dsh] and "p0" not in got[dsh]  # ismsiz
        bot.sent.clear()
        assert await r.on_private_text(kom, "2 shubhali")
        got = {c: t for c, t in bot.sent}
        assert "2 shubhali" in got[ser] and "2 shubhali" in got[dsh] and don not in got
        bot.sent.clear()
        assert not await r.on_private_text(tin, "salom")  # tinch aholi yozishmasi eshitilmaydi
        assert not bot.sent
        r.close()
    asyncio.run(go())


def test_night_chat_is_explained_and_donishmand_is_told_to_listen():
    """O'yinchilar tunda sheriklariga yozish mumkinligini bilmasa, Donishmand hech narsa eshitmaydi."""
    async def go():
        r, bot, (don, maf, kom, ser, dsh, tin) = _night_runner(["don", "mafiya", "komissar", "serjant",
                                                                 "donishmand", "tinch"])
        for uid in (don, maf, kom, ser):
            assert texts.NIGHT_CHAT_HINT in texts.role_card(r.game, uid)
        assert texts.NIGHT_CHAT_HINT not in texts.role_card(r.game, tin)
        await r._intro(NIGHT, 60)
        got = [t for c, t in bot.sent if c == dsh]
        assert any(texts.DONISHMAND_NIGHT in t for t in got)
        assert any(texts.NIGHT_CHAT_HINT in t for c, t in bot.sent if c == don)  # tungi tanlovda ham eslatma
        r.close()
    asyncio.run(go())


def test_double_taps_do_nothing_twice():
    """Tugma ikki marta bosilsa: ikkinchisi e'tiborsiz (xarid, PRO, ovoz...); ovoz va mafiya xabari takrorlanmaydi."""
    from mafia_zone import handlers
    from mafia_zone.engine.game import Game

    async def go():
        calls, answered = [], []

        async def handler(cq, data):
            calls.append(cq.data)

        async def answer(*a, **kw):
            answered.append(a)
        cq = lambda d, u=1: SimpleNamespace(data=d, from_user=SimpleNamespace(id=u), answer=answer)
        await handlers.drop_double_taps(handler, cq("pro:d:30"), {})
        await handlers.drop_double_taps(handler, cq("pro:d:30"), {})  # darhol ikkinchi bosish
        await handlers.drop_double_taps(handler, cq("pro:d:30", u=2), {})  # boshqa odam - o'tadi
        await handlers.drop_double_taps(handler, cq("b:shield"), {})  # boshqa tugma - o'tadi
        assert calls == ["pro:d:30", "pro:d:30", "b:shield"] and len(answered) == 1

        await db.init()
        bot = FakeBot()
        r = runner.Runner(bot, -8811, {})
        r.game, r.game_id = Game.create(-8811, [(i, f"p{i}") for i in range(1, 9)], 3), 59
        g = r.game
        try:
            g.start_voting()
            assert await r.on_vote(1, g.day, 2)
            assert not await r.on_vote(1, g.day, 3)  # ovoz qabul qilingan - o'zgarmaydi, lenta takrorlanmaydi
            assert g.votes[1] == 2 and len(r.live_lines) == 1
            g.phase, r.live_lines = runner.NIGHT, []
            don = g.by_role("don")
            mates = [m.uid for m in g.teammates(don.uid) if m.alive]
            target = next(t for t in g.targets(don.uid, "mafia_kill"))
            n = len(bot.sent)
            assert await r.on_action(don.uid, g.day, "mafia_kill", target)
            assert await r.on_action(don.uid, g.day, "mafia_kill", target)
            assert len([c for c, _ in bot.sent[n:] if c in mates]) == len(mates)  # sheriklarga bir marta
        finally:
            r.close()
    asyncio.run(go())


def test_owner_kicks_player():
    """/kick - faqat bot egasi (ADMIN_IDS): reply yoki raqam bilan; guruh admini/oddiy o'yinchi chiqara olmaydi."""
    from mafia_zone import config, handlers
    from mafia_zone.engine.game import Game

    async def go():
        await db.init()
        owner, chat = 1, -8810
        old, config.ADMIN_IDS = config.ADMIN_IDS, {owner}
        bot = FakeBot()
        r = runner.Runner(bot, chat, {})
        r.game, r.game_id = Game.create(chat, [(i, f"p{i}") for i in range(2, 9)], 3), 58
        for p in r.game.players:
            runner.PLAYING[p.uid] = r
        said = []

        async def answer(text, **kw):
            said.append(text)

        def msg(uid, reply_to=None):
            rep = SimpleNamespace(from_user=SimpleNamespace(id=reply_to)) if reply_to else None
            return SimpleNamespace(chat=SimpleNamespace(id=chat), from_user=SimpleNamespace(id=uid),
                                   reply_to_message=rep, answer=answer, sender_chat=None)
        try:
            await handlers.cmd_kick(msg(2, reply_to=3), SimpleNamespace(args=None))  # o'yinchi - yo'q
            assert r.game.get(3).alive and not said
            await handlers.cmd_kick(msg(owner, reply_to=3), SimpleNamespace(args=None))
            assert not r.game.get(3).alive and 3 not in runner.PLAYING
            assert any("o'yindan chiqarildi" in t for _, t in bot.sent if t)
            await handlers.cmd_kick(msg(owner), SimpleNamespace(args="5"))  # o'yin boshidagi raqam: 5 -> uid 6
            assert not r.game.get(6).alive
            lobby = runner.Runner(bot, chat - 1, {})
            lobby.members = [(20, "a"), (21, "b")]
            runner.PLAYING[21] = lobby
            m = msg(owner, reply_to=21)
            m.chat.id = chat - 1
            await handlers.cmd_kick(m, SimpleNamespace(args=None))
            assert lobby.members == [(20, "a")] and "o'yindan chiqarildi" in said[-1]
            lobby.close()
        finally:
            config.ADMIN_IDS = old
            r.close()
    asyncio.run(go())


def test_couplestop_stops_couple_game():
    """💞 Paralar o'yini /couplestop (va /stop) bilan to'xtaydi; buyruq menyusida ham bor."""
    from mafia_zone import config, handlers
    from mafia_zone.__main__ import GROUP_COMMANDS

    async def go():
        await db.init()
        owner = 1
        old, config.ADMIN_IDS = config.ADMIN_IDS, {owner}
        try:
            r = runner.Runner(FakeBot(), -8803, {}, couple=True)
            msg = SimpleNamespace(chat=SimpleNamespace(id=-8803), from_user=SimpleNamespace(id=owner),
                                  sender_chat=None)
            await handlers.cmd_stop(msg, FakeBot(), SimpleNamespace(command="couplestop"))
            assert -8803 not in runner.RUNNERS
        finally:
            config.ADMIN_IDS = old
    asyncio.run(go())
    assert "couplestop" in [c.command for c in GROUP_COMMANDS]


def test_couplestop_does_not_stop_normal_game():
    from mafia_zone import config, handlers

    async def go():
        await db.init()
        bot = FakeBot()
        owner = 1
        old, config.ADMIN_IDS = config.ADMIN_IDS, {owner}
        try:
            r = runner.Runner(bot, -8804, {})
            msg = SimpleNamespace(chat=SimpleNamespace(id=-8804), from_user=SimpleNamespace(id=owner), sender_chat=None,
                                  answer=lambda text: bot.send_message(-8804, text))
            await handlers.cmd_stop(msg, bot, SimpleNamespace(command="couplestop"))
            assert runner.RUNNERS.get(-8804) is r and texts.NOT_COUPLE_GAME in bot.sent[-1][1]
            r.close()
        finally:
            config.ADMIN_IDS = old
    asyncio.run(go())


def test_owner_couple_can_uncouple():
    """Bot egasining parasi endi qulflanmagan: /uncouple oddiy ishlaydi."""
    from mafia_zone import config, handlers

    async def go():
        await db.init()
        a, b = 2001717965, 7755486947
        for u in (a, b):
            await db.upsert_user(u, f"u{u}", None)
        await db.make_couple(a, b)
        assert not hasattr(config, "LOCKED_COUPLE")
        replies = []
        msg = SimpleNamespace(from_user=SimpleNamespace(id=a, full_name="x", username=None),
                              reply=lambda t, **k: asyncio.sleep(0, replies.append(t)))
        await handlers.cmd_uncouple(msg)
        assert await db.partner(a) is None and await db.partner(b) is None
    asyncio.run(go())


def test_settings_and_denials_only_for_caller():
    """/settings guruhda faqat yozgan adminga (ephemeral), ➕ shu xabarni tahrirlaydi; rad javoblari ham faqat yozganga."""
    from mafia_zone import config, handlers

    class Bot(FakeBot):
        async def edit_ephemeral_message_text(self, **kw):
            self.eph_kb = kw
            return True

    async def go():
        await db.init()
        bot, chat, admin = Bot(), -4648, 4_648_001
        config.ADMIN_IDS.add(admin)
        user = SimpleNamespace(id=admin, full_name="A", username=None)
        msg = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=chat, type="supergroup", title="g"), from_user=user,
                              sender_chat=None, answer=None)
        await handlers.cmd_settings(msg, bot)
        assert bot.eph[-1][:2] == (chat, admin) and handlers.SET_EPH[admin][0] == chat
        eid = handlers.SET_EPH[admin][1]
        cq = SimpleNamespace(bot=bot, from_user=user, data="s:lobby:+", answer=lambda *a, **k: asyncio.sleep(0),
                             message=SimpleNamespace(chat=SimpleNamespace(id=chat), ephemeral_message_id=eid))
        before = (await db.group_settings(chat))["lobby"]
        await handlers.cb_settings(cq, bot)
        assert (await db.group_settings(chat))["lobby"] > before and bot.eph_kb["ephemeral_message_id"] == eid
        assert texts.dur(before + 30) in bot.eph_kb["text"]  # qiymat matnda (telefonda tugmaga sig'maydi)
        cq.data = "s:close"
        await handlers.cb_settings(cq, bot)  # ❌ Yopish - xabar o'chadi
        assert bot.eph_deleted[-1] == (chat, admin, eid) and admin not in handlers.SET_EPH
        msg.from_user = SimpleNamespace(id=admin + 1, full_name="B", username=None)
        await handlers.cmd_stop(msg, bot)  # o'yin yo'q - faqat yozganga
        assert bot.eph[-1] == (chat, admin + 1, texts.NO_GAME_HERE)
    try:
        asyncio.run(go())
    finally:
        config.ADMIN_IDS.discard(4_648_001)


def test_bot_pin_notice_deleted():
    """Bot qadagan xabar haqidagi xizmat xabari o'chadi, odam qadagani qoladi."""
    from mafia_zone import handlers
    gone = []

    async def go():
        for who in (42, 7):
            async def delete(who=who):
                gone.append(who)
            msg = SimpleNamespace(bot=SimpleNamespace(id=42), from_user=SimpleNamespace(id=who), delete=delete)
            await handlers.on_pinned(msg)
    asyncio.run(go())
    assert gone == [42]


def test_groupgame_lobby_switch_and_unequal_cancel():
    """⚪⚫ Oq-Qora: jamoa tanlab qo'shiladi, almashtirsa o'tadi; teng bo'lmasa bekor, teng bo'lsa o'ynaladi."""
    settings = {"lobby": 0, "night": 0, "day": 0, "vote": 0, "items": False, "disabled": []}

    async def go():
        await db.init()
        bot = FakeBot()
        r = AutoRunner(bot, -9101, settings, teams=True)
        for uid in range(9101, 9107):
            runner.PLAYING.pop(uid, None)
            await db.upsert_user(uid, f"p{uid}", None)
        assert r.join(9101, "a") == texts.TEAM_PICK and not r.members  # jamoasiz qo'shilib bo'lmaydi
        for uid in range(9101, 9107):
            r.join(uid, f"p{uid}", "oq" if uid < 9104 else "qora")
        r.join(9101, "a", "qora")  # almashtirdi: 2 : 4
        assert len(r.members) == 6 and r.sides[9101] == "qora"
        assert "⚪ Oq (2)" in r._lobby_text() and "⚫ Qora (4)" in r._lobby_text()
        await r._start_game()
        assert r.game is None and bot.sent[-1] == (-9101, texts.teams_unequal(2, 4)) and -9101 not in runner.RUNNERS
        r = AutoRunner(bot, -9102, settings, teams=True)
        for uid in range(9101, 9107):
            runner.PLAYING.pop(uid, None)
            r.join(uid, f"p{uid}", "oq" if uid % 2 else "qora")
        await r._start_game()
        g = r.game
        assert g.phase == FINISHED and set(g.sides.values()) == {"oq", "qora"}
        if g.winner in ("oq", "qora"):
            assert {p.uid for p in g.players if p.won} == {u for u, s in g.sides.items() if s == g.winner}
        for _, text in bot.sent:
            assert_telegram_html(text)
    asyncio.run(go())


def test_top_groups_and_donate():
    """TOP guruhlar: 4 o'yin = 1 ball, 1 💎 = 2 ball; /donate olmosni guruhga o'tkazadi (yetmasa - faqat yozganga);
    guruh nomi havola: ochiq - t.me/username, yopiq - bot yaratgan taklif havolasi (bir marta, bazada saqlanadi)."""
    from mafia_zone import handlers

    class Bot(FakeBot):
        made = 0

        async def create_chat_invite_link(self, chat_id, name=None, **kw):
            Bot.made += 1
            return SimpleNamespace(invite_link=f"https://t.me/+inv{-chat_id}")

    async def go():
        await db.init()
        bot, uid = Bot(), 7_771_001
        await db.upsert_user(uid, "Donor", None)
        await db.add_balance(uid, 0, 5 - (await db.get_user(uid)).diamonds)
        await db.group_settings(-7771, "Ochiq <guruh>", "ochiqguruh")
        await db.group_settings(-7772, "Yopiq guruh", "")
        user = SimpleNamespace(id=uid, full_name="Donor", username=None)
        msg = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=-7772, type="supergroup", title="Yopiq guruh", username=None),
                              from_user=user, sender_chat=None, answer=None)
        replies = []
        msg.reply = lambda text, **kw: asyncio.sleep(0, replies.append(text))
        await handlers.cmd_donate(msg, bot, SimpleNamespace(args="3"))
        assert (await db.get_user(uid)).diamonds == 2 and "3 💎</b> donat qildi!" in bot.sent[-1][1]
        await handlers.cmd_donate(msg, bot, SimpleNamespace(args="3"))  # 2 ta qoldi - yetmaydi
        assert (await db.get_user(uid)).diamonds == 2 and replies[-1] == texts.NO_DIAMONDS  # hammaga ko'rinadi
        await handlers.cmd_donate(msg, bot, SimpleNamespace(args=""))
        assert replies[-1] == texts.DONATE_HOW
        await db.donate(uid, -7771, 1)
        rows = {r["chat_id"]: r for r in await db.top_groups(None)}
        assert rows[-7772]["points"] >= 6 and rows[-7771]["points"] >= 2
        mine = lambda: [r for r in rows.values() if r["chat_id"] in (-7771, -7772)]  # boshqa testlar guruhlari ham bor
        text = texts.top_groups(await handlers._link_groups(bot, mine()))
        rows = {r["chat_id"]: r for r in await db.top_groups(None)}
        await handlers._link_groups(bot, mine())
        assert 'href="https://t.me/ochiqguruh"' in text and "&lt;guruh&gt;" in text
        assert 'href="https://t.me/+inv7772"' in text and Bot.made == 1  # havola bir marta yaratiladi
        assert rows[-7772]["gems"] == 3 and "Donor" not in text and "💎" not in text  # ro'yxatda faqat nom va ball
        assert_telegram_html(text)
    asyncio.run(go())
