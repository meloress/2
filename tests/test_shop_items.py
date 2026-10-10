"""Do'kon: yangi narxlar, olmosli buyumlar (Maska, Ovoz himoyasi), rolni tanlab olish."""
import asyncio
from types import SimpleNamespace

from mafia_zone import config, db, handlers, pro, texts
from mafia_zone.engine.game import Game
from tests.test_engine import mk, night, vote

U = 7_600_000


def test_prices_and_catalog():
    assert config.SHOP == {"shield": 140, "verbena": 145, "doc": 190}  # tasodifiy "ticket" endi sotilmaydi
    assert config.SHOP_GEMS == {"mask": 1, "votesave": 2}
    assert config.ROLE_PICKS == {"komissar": 3, "don": 3, "doktor": 2, "kezuvchi": 2}
    for c in config.ROLE_PICKS:
        assert f"r_{c}" in texts.ITEMS and len(f"r_{c}") <= 16  # Inventory.item String(16)


def test_mask_hides_role_everywhere_public():
    g = mk("don", "komissar", "tinch", "tinch", "tinch", "tinch", p2={"mask": 1})
    comp = texts.alive_composition(g)
    kom, don = texts.role("komissar"), texts.role("don")
    assert kom not in comp and "🎭" in comp and "Jami: 6" in comp
    ev = night(g, (1, "mafia_kill", 2))
    pub, _ = texts.morning(g, ev)
    assert kom not in "".join(pub) and "🎭" in "".join(pub)
    assert kom not in texts.who(g, 2)
    g = mk("don", "mafiya", "tinch", "tinch", "tinch", "tinch", "tinch", p1={"mask": 1})
    ev = vote(g, (3, 1), (4, 1))  # o'yin davom etadi (Mafiya Don bo'ladi)
    pub, _ = texts.morning(g, ev)
    assert g.phase != "finished" and don not in "".join(pub) and "🎭" in "".join(pub)
    g.phase = "finished"
    assert don in texts.game_over(g)  # o'yin oxirida haqiqiy rollar ko'rinadi


def test_rob_never_takes_mask():
    for seed in range(40):
        g = mk("don", "qaroqchi", "tinch", "tinch", "tinch", "tinch", p3={"mask": 1})
        g.seed = seed
        ev = night(g, (2, "rob", 3))
        assert g.get(3).items["mask"] == 1
        assert all(e.data.get("item") != "mask" for e in ev if e.kind == "robbed")


def test_votesave_once_per_game():
    g = Game.create(1, [(i, f"p{i}") for i in range(1, 9)], 5, items={1: {"votesave": 3}})
    assert g.get(1).items["votesave"] == 1  # bir o'yinda bir martadan ko'p emas
    g.phase = "day"
    voters = [p.uid for p in g.players if p.uid != 1]
    ev = vote(g, *[(v, 1) for v in voters])
    assert g.get(1).alive and "vote_saved" in [e.kind for e in ev] and "item_used" in [e.kind for e in ev]
    pub, _ = texts.morning(g, ev)
    assert any("Ovoz himoyasi" in x for x in pub)
    if g.phase != "finished":
        g.phase = "day"
        ev = vote(g, *[(v, 1) for v in voters if g.get(v).alive])
        assert not g.get(1).alive


def test_role_pick_swaps_and_keeps_token_if_role_absent():
    for seed in range(40):
        g = Game.create(1, [(i, f"p{i}") for i in range(1, 11)], seed,
                        items={1: {"r_komissar": 1}, 2: {"r_don": 1}, 3: {"ticket": 1}})
        before = sorted(p.role for p in g.players)
        had = {p.uid: p.role for p in g.players}
        used = g.use_role_picks()
        g.use_tickets()
        assert g.get(1).role == "komissar" and g.get(2).role == "don"
        assert ((1, "r_komissar") in used) == (had[1] != "komissar")
        assert sorted(p.role for p in g.players) == before  # tarkib o'zgarmaydi
    g = Game.create(1, [(i, f"p{i}") for i in range(1, 5)], 1, items={1: {"r_kezuvchi": 1}})
    if "kezuvchi" not in [p.role for p in g.players]:
        assert g.use_role_picks() == []  # rol bu o'yinda yo'q - token keyingi o'yinga qoladi


def test_buy_with_diamonds_no_pro_discount():
    async def t():
        await db.init()
        await db.upsert_user(U, "Ali", None)
        u = await db.get_user(U)
        await db.add_balance(U, 0, 10 - u.diamonds)
        pro.set_user(U, db.now().replace(year=2100), None)
        try:
            assert await db.buy(U, "votesave") and (await db.get_user(U)).diamonds == 8
            assert await db.buy(U, "r_don") and (await db.get_user(U)).diamonds == 5
            assert await db.buy(U, "mask") and (await db.get_user(U)).diamonds == 4
            assert not await db.buy(U, "r_tinch") and not await db.buy(U, "ticket")
            await db.add_balance(U, 0, -4)
            assert not await db.buy(U, "mask")
            inv = {i.item: i.qty for i in await db.inventory(U)}
            assert inv["votesave"] == 1 and inv["r_don"] == 1 and inv["mask"] == 1
        finally:
            pro.CACHE.pop(U, None)
    asyncio.run(t())


def test_shop_menu_buttons():
    kb = handlers.shop_kb(U)
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert {"b:shield", "b:mask", "b:votesave", "shoproles", "m:home"} <= set(cbs) and "b:ticket" not in cbs
    rk = handlers.roles_shop_kb()
    rcbs = [b.callback_data for row in rk.inline_keyboard for b in row]
    assert {"b:r_komissar", "b:r_don", "shop"} <= set(rcbs)
    text = texts.shop(500, U, 3)
    assert "💎" in text and "Maska" in text


def test_buying_turns_item_on():
    """OFF qilingan buyumni yana sotib olsa - ON bo'ladi va keyingi o'yinga olinadi."""
    async def t():
        await db.init()
        u = U + 500
        await db.upsert_user(u, "Vali", None)
        await db.add_balance(u, 1000)
        assert await db.buy(u, "shield")
        await db.toggle_item(u, "shield")
        assert (await db.game_items([u])).get(u, {}).get("shield") is None  # OFF - o'yinga olinmaydi
        assert await db.buy(u, "shield")
        inv = {i.item: i for i in await db.inventory(u)}
        assert inv["shield"].enabled and inv["shield"].qty == 2
        assert (await db.game_items([u]))[u]["shield"] == 2
    asyncio.run(t())
