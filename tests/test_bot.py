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
    assert "60 sekund" in texts.death_pm(False) and "osib" in texts.death_pm(True)


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
        assert bot.sent[-1][0] == -4242 and "vaqtida" in bot.sent[-1][1]  # guruhga
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
