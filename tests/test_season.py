"""Reyting: ban qilinganlar chiqmaydi, o'z o'rni, oylik mavsum va top-3 mukofoti."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import update

from mafia_zone import config, db, texts

B = 6_100_000


async def game(month_day: str, results: list[tuple[int, bool]], chat: int = -61) -> None:
    """month_day: "2026-09-15" (Toshkent kuni, tushdan keyin) da tugagan o'yin; results: [(uid, yutdimi)]."""
    gid = await db.create_game(chat, {})
    await db.finish_game(gid, chat, "finished", "town", [(u, "tinch", "town", True, w) for u, w in results])
    y, m, d = map(int, month_day.split("-"))
    async with db.Session.begin() as s:
        await s.execute(update(db.GameRow).where(db.GameRow.id == gid)
                        .values(finished_at=datetime(y, m, d, 9, tzinfo=timezone.utc)))


async def users(*uids):
    for u in uids:
        await db.upsert_user(u, f"u{u}", None)


def test_leaderboards_place_ban_and_season_payout():
    async def t():
        await db.init()
        a, b, c, d = B + 1, B + 2, B + 3, B + 4
        await users(a, b, c, d)
        await game("2026-09-10", [(a, True), (b, False), (c, True)])
        await game("2026-09-20", [(a, True), (b, True), (c, False), (d, False)])
        await game("2026-08-31", [(d, True)])  # avgust - sentabr mavsumiga kirmaydi

        rows = await db.top(month="2026-09")
        ours = [r for r in rows if r[0] in (a, b, c, d)]
        assert [r[0] for r in ours] == [a, b, c, d]  # a: 2 g'alaba; b, c: 1 dan (teng - uid bo'yicha); d: 0
        assert ours[0][2:] == (2, 2)
        assert await db.place(a, month="2026-09") == (1, 2, 2)
        assert await db.place(d, month="2026-09") == (4, 0, 1)
        assert await db.place(B + 99, month="2026-09") is None  # bu oy o'ynamagan

        await db.set_banned(a, True)  # ban - reytingdan chiqadi (umumiy, oylik, guruh)
        assert a not in [r[0] for r in await db.top()]
        assert a not in [r[0] for r in await db.top(month="2026-09")]
        assert a not in [r[0] for r in await db.top(-61)]
        assert await db.place(a) is None
        await db.set_banned(a, False)

        before = {u: (await db.get_user(u)).diamonds for u in (a, b, c)}
        paid = await db.pay_season("2026-09")
        assert paid == [(a, 1, config.SEASON_PRIZES[0]), (b, 2, config.SEASON_PRIZES[1]), (c, 3, config.SEASON_PRIZES[2])]
        assert (await db.get_user(a)).diamonds == before[a] + config.SEASON_PRIZES[0]
        assert await db.pay_season("2026-09") == []  # ikkinchi marta to'lanmaydi
        assert await db.pay_season("2026-07") == []  # hech kim o'ynamagan oy
    asyncio.run(t())


def test_month_helpers_use_tashkent_time():
    # 30-sentabr 20:00 UTC = 1-oktabr 01:00 Toshkent
    assert db.month_key(datetime(2026, 9, 30, 20, tzinfo=timezone.utc)) == "2026-10"
    assert db.prev_month("2026-01") == "2025-12"
    start, end = db.month_range("2026-10")
    assert start == datetime(2026, 9, 30, 19, tzinfo=timezone.utc) and end == datetime(2026, 10, 31, 19, tzinfo=timezone.utc)


def test_top_text_shows_my_place_and_season_header():
    rows = [(1, "Ali", 5, 9)]
    text = texts.top(rows, "Oylik reyting", me=(37, 4, 12))
    assert "📍 Siz: 37-o'rin · 🏆 4 · 🎮 12" in text
    assert "📍 Siz hali reytingda yo'qsiz" in texts.top(rows, "X", me=None, show_me=True)
    assert texts.top(rows, "X", head="HEAD").startswith(f"🏆 <b>{texts.bold('X')}</b>\nHEAD\n\n")
    assert "📍" not in texts.top(rows, "X")  # guruhdagi /top - shaxsiy qator yo'q
    head = texts.season_head("2026-10", days_left=22)
    assert "Oktabr" in head and "22 kun" in head and f"{config.SEASON_PRIZES[0]}💎" in head


def test_bot_top_view_monthly_and_all_time():
    from mafia_zone import handlers

    async def t():
        await db.init()
        u = B + 50
        await users(u)
        gid = await db.create_game(-62, {})
        await db.finish_game(gid, -62, "finished", "town", [(u, "tinch", "town", True, True)])  # shu oy
        text, kb = await handlers.top_view(u)
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert "m:top" in cbs and "m:topall" in cbs and "m:home" in cbs
        assert "mavsumi" in text and "📍 Siz:" in text
        assert kb.inline_keyboard[0][0].text.startswith("✅")
        text, kb = await handlers.top_view(u, monthly=False)
        assert "mavsumi" not in text and "📍 Siz:" in text and kb.inline_keyboard[0][1].text.startswith("✅")
    asyncio.run(t())
