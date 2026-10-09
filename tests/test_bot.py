"""Bot qatlami: soxta Bot + vaqtinchalik SQLite bilan to'liq o'yinlar."""
import asyncio
import os
import random
import tempfile
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")

from mafia_zone import db, runner, texts  # noqa: E402
from mafia_zone.engine.game import CONFIRM, FINISHED, NIGHT, VOTING  # noqa: E402

from test_engine import play_random  # noqa: E402

runner.GLOBAL_INTERVAL = 0
runner.GROUP_PER_MIN = 10 ** 9


class FakeBot:
    def __init__(self):
        self.sent, self._id = [], 0

    async def send_message(self, chat_id, text, **kw):
        self._id += 1
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=self._id)

    async def edit_message_text(self, text, chat_id, message_id, **kw):
        self.sent.append((chat_id, text))
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
    expected = {"blocked", "stolen", "saw_role", "robbed", "checked", "interview", "dug", "saved", "item_used",
                "killed", "revenge", "linked", "transformed", "promoted", "penalty", "witness",
                "hanged", "no_hang", "guard_saved", "tulki", "game_over"}
    assert expected <= seen, expected - seen


def assert_telegram_html(text):
    from html.parser import HTMLParser

    stack = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag in ("b", "i", "a", "code"), (tag, text)
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
        assert bot.gifs.count("gif-id") >= 1  # GIF bir marta yuklanib, keyin file_id bilan
        for t in group:
            assert_telegram_html(t)

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
    assert "<b>60</b> sekund" in texts.death_pm(False) and "osib" in texts.death_pm(True)


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
        assert rows[0][0].text == "2. 🤵🏼 b" and rows[1][0].text == "3. c"
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
            assert r._lobby_kb().inline_keyboard[0][0].style == "danger"
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
    assert texts_[:4] == ["3. p3", "4. p4", "6. p6", "7. p7"]
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


def test_locked_couple_cannot_uncouple():
    """config.LOCKED_COUPLE: bot egasi bergan ikki ID majburan para; /uncouple - egasining matni, para qoladi."""
    from mafia_zone import config, handlers

    async def go():
        await db.init()
        a, b, c = 8_805_001, 8_805_002, 8_805_003
        for u in (a, b, c):
            await db.upsert_user(u, f"u{u}", None)
        await db.make_couple(b, c)  # b ning boshqa parasi bor edi
        old = config.LOCKED_COUPLE, config.LOCKED_COUPLE_TEXT
        config.LOCKED_COUPLE, config.LOCKED_COUPLE_TEXT = (a, b), "Qochib qutulolmaysan 😏"
        try:
            await db.ensure_locked_couple()
            assert await db.partner(a) == b and await db.partner(b) == a and await db.partner(c) is None
            for u in (a, b):
                replies = []
                msg = SimpleNamespace(from_user=SimpleNamespace(id=u, full_name="x", username=None),
                                      reply=lambda t, **k: asyncio.sleep(0, replies.append(t)))
                await handlers.cmd_uncouple(msg)
                assert replies == ["Qochib qutulolmaysan 😏"] and await db.partner(u) is not None
            config.LOCKED_COUPLE = None  # qulf olib tashlandi - oddiy holat
            await db.ensure_locked_couple()
            assert await db.break_couple(a) == b
        finally:
            config.LOCKED_COUPLE, config.LOCKED_COUPLE_TEXT = old
    asyncio.run(go())
