"""Himoya buyumlari boshidan oxirigacha: do'kon -> inventar -> o'yinga tushishi -> ishlashi -> bazadan yechilishi.
Osishdan himoya tasdiqlash (👍/👎) yoqilgan va o'chirilgan o'yinda, qayta ishga tushirishdan (saqlash/tiklash) keyin ham."""
import asyncio

from mafia_zone import db, runner, texts
from mafia_zone.engine.game import CONFIRM, DAY, VOTING, Game, Player

BASE = 7_300_000


def _game(roles, items, confirm):
    ps = [Player(BASE + i, f"p{i}", r, items=dict(items.get(BASE + i, {}))) for i, r in enumerate(roles)]
    return Game(-1, 7, ps, afk_limit=0, confirm=confirm)


def _hang_vote(g, target):
    g.phase = DAY
    g.start_voting()
    assert g.phase == VOTING
    for p in g.alive():
        if p.uid != target:
            g.cast_vote(p.uid, target)
    ev = g.resolve_vote()
    if g.phase == CONFIRM:
        g = Game.from_dict(g.to_dict())  # 👍/👎 paytida bot qayta ishga tushdi
        for p in g.alive():
            if g.can_confirm(p.uid):
                g.cast_confirm(p.uid, True)
        ev = g.resolve_confirm()
    return g, ev


def test_every_protection_end_to_end():
    async def t():
        await db.init()
        roles = ["don", "mafiya", "komissar", "vampir", "tinch", "tinch", "tinch", "tinch", "doktor", "tinch",
                 "tinch", "tinch"]
        uids = [BASE + i for i in range(len(roles))]
        for u in uids:
            await db.upsert_user(u, f"p{u}", None)
            await db.add_balance(u, 10_000, 50)
        shop = {uids[4]: "votesave", uids[5]: "shield", uids[6]: "verbena", uids[1]: "doc", uids[7]: "votesave"}
        for u, item in shop.items():
            assert await db.buy(u, item), item
        items = await db.game_items(uids)
        assert {u: list(v) for u, v in items.items()} == {u: [i] for u, i in shop.items()}

        for confirm in (True, False):
            g = _game(roles, items, confirm)
            g = Game.from_dict(g.to_dict())  # o'yin boshlanib saqlandi/tiklandi - buyumlar yo'qolmaydi

            # ⚖️ Ovoz himoyasi: osilmaydi, guruhga e'lon, bazadan 1 ta yechiladi
            g, ev = _hang_vote(g, uids[4])
            assert g.get(uids[4]).alive and "vote_saved" in [e.kind for e in ev], (confirm, [e.kind for e in ev])
            pub, priv = texts.morning(g, ev)
            assert any("Ovoz himoyasi" in x for x in pub)
            # ikkinchi marta shu o'yinda - endi osiladi (bir o'yinda bir marta)
            g, ev = _hang_vote(g, uids[4])
            assert not g.get(uids[4]).alive

            # 🛡 Qalqon - mafiya hujumidan, 🌿 Verbena - Vampir tishlashidan, 📄 Hujjat - Komissar tekshiruvidan
            g.phase = DAY
            g.start_voting()
            g.resolve_vote()
            if g.phase == CONFIRM:
                g.resolve_confirm()
            g.submit(uids[0], "mafia_kill", uids[5])
            g.submit(uids[3], "bite", uids[6])
            g.submit(uids[2], "check", uids[1])
            ev = g.resolve_night()
            kinds = [(e.kind, e.uid, e.data.get("item")) for e in ev if e.kind == "item_used"]
            assert ("item_used", uids[5], "shield") in kinds and g.get(uids[5]).alive
            assert ("item_used", uids[6], "verbena") in kinds and g.get(uids[6]).alive
            assert ("item_used", uids[1], "doc") in kinds
            assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch"]

        # bazadan yechilishi (runner._economy - har ishlatilgan buyum uchun -1)
        r = runner.Runner(None, -7301, {})
        await r._economy([e for e in ev if e.kind == "item_used"])
        r.close()
        left = {u: {i.item: i.qty for i in await db.inventory(u)} for u in (uids[5], uids[6], uids[1])}
        assert left[uids[5]].get("shield", 0) == 0 and left[uids[6]].get("verbena", 0) == 0
        assert left[uids[1]].get("doc", 0) == 0
    asyncio.run(t())


def test_items_off_in_group_or_profile_means_no_protection():
    """Guruh sozlamasida 🎒 Buyumlar o'chiq yoki profilda buyum OFF - o'yinga tushmaydi (shuning uchun ishlamaydi)."""
    async def t():
        await db.init()
        u = BASE + 99
        await db.upsert_user(u, "x", None)
        await db.add_balance(u, 0, 10)
        assert await db.buy(u, "votesave")
        assert (await db.game_items([u]))[u] == {"votesave": 1}
        await db.toggle_item(u, "votesave")
        assert u not in await db.game_items([u])
    asyncio.run(t())
