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
    from mafia_zone.engine.roles import ROLES
    assert set(config.ROLE_PICKS) == set(ROLES) - {"tinch"}  # Tinchdan boshqa hamma rol sotiladi
    assert all(1 <= p <= 4 for p in config.ROLE_PICKS.values())
    assert config.ROLE_PICKS["komissar"] == config.ROLE_PICKS["don"] == 3 and config.ROLE_PICKS["konchi"] == 4
    for c in config.ROLE_PICKS:
        assert f"r_{c}" in texts.ITEMS and len(f"r_{c}") <= 16  # Inventory.item String(16)


def test_profile_strikes_off_items_and_shows_role_picks():
    """Profil: OFF buyum ustidan chiziladi (o'yinga olinmaydi), ON - oddiy; sotib olingan rollar alohida qatorda."""
    inv = [SimpleNamespace(item="shield", qty=2, enabled=True), SimpleNamespace(item="doc", qty=1, enabled=False),
           SimpleNamespace(item="r_don", qty=1, enabled=True), SimpleNamespace(item="r_komissar", qty=2, enabled=False)]
    u = SimpleNamespace(telegram_id=U + 900, full_name="Ali", wins=1, games=3, dollars=10, diamonds=2)
    card = texts.profile_card(u, inv)
    assert f"{texts.bold('Qalqon')}: 2 ta" in card and f"<s>{texts.bold('Hujjat')}: 1 ta</s>" in card
    assert f"<s>{texts.bold('Qalqon')}" not in card
    line = next(x for x in card.split("\n") if x.startswith("🃏"))
    assert texts.role("don") in line and f"<s>{texts.role('komissar')} ×2</s>" in line
    assert "Komissar Katani roli" not in card  # rol buyum ro'yxatida takrorlanmaydi
    empty = texts.profile_card(u, [])
    assert next(x for x in empty.split("\n") if x.startswith("🃏")).endswith("—")


def test_every_role_pick_lands_when_role_dealt():
    """Har bir sotiladigan rol: o'yinda bo'lsa xaridorga tushadi, tarkib o'zgarmaydi."""
    for c in config.ROLE_PICKS:
        for seed in range(30):
            g = Game.create(1, [(i, f"p{i}") for i in range(1, 41)], seed, items={7: {f"r_{c}": 1}})
            before = sorted(p.role for p in g.players)
            dealt = c in before
            g.use_role_picks()
            assert (g.get(7).role == c) == dealt, (c, seed)
            assert sorted(p.role for p in g.players) == before


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
    g.phase = "day"  # 3 ta bo'lsa ham bir o'yinda bir marta
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
