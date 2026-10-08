import json
import random

import pytest

from mafia_zone.engine.game import DAY, FINISHED, MAX_DAYS, Game, Player
from mafia_zone.engine.roles import MAFIA, ROLES, TOWN
from mafia_zone.engine.setup import deal


def mk(*roles, **items):
    """mk('don', 'doktor', ...) -> uid 1, 2, ... ; items: p3={'shield': 1}"""
    ps = [Player(i + 1, f"p{i + 1}", r, items=items.get(f"p{i + 1}", {})) for i, r in enumerate(roles)]
    return Game(1, 42, ps, afk_limit=0)


def kinds(ev):
    return [e.kind for e in ev]


def night(g, *acts):
    if g.phase == DAY:  # kunni ovozsiz o'tkazib yuborish
        g.start_voting()
        g.resolve_vote()
    for uid, kind, target in acts:
        assert g.submit(uid, kind, target), (uid, kind, target)
    return g.resolve_night()


def vote(g, *pairs):
    g.start_voting()
    for v, t in pairs:
        assert g.cast_vote(v, t), (v, t)
    return g.resolve_vote()


# ---------- taqsimot ----------
@pytest.mark.parametrize("n", range(4, 61))
def test_deal(n):
    for seed in range(30):
        r = deal(n, random.Random(seed))
        assert len(r) == n
        assert r.count("don") == 1 and r.count("komissar") == 1
        assert sum(ROLES[x].team == MAFIA for x in r) == (2 if n == 7 else max(1, n // 4))
        assert ("podshoh" not in r) or "qorovul" in r
        assert ("aka" in r) == ("uka" in r)
        assert all(x in ROLES for x in r)
        # balans: kichik o'yin bir zarbada tugamasin, katta o'yinda bo'sh Tinch kam bo'lsin
        assert n > 7 or not {"afsungar", "suitsid", "podshoh"} & set(r)
        assert n >= 12 or not {"qotil", "gazabkor", "sehrgar", "vampir"} & set(r)
        assert not 30 <= n <= 40 or r.count("tinch") <= 6  # 40+ da takrorlanadiganlar tugaydi
        assert all(r.count(x) == 1 for x in set(r) - {"tinch", "mafiya", "daydi", "kezuvchi", "ovchi", "janob"})


def test_deal_disabled():
    for seed in range(50):
        r = deal(20, random.Random(seed), frozenset({"qotil", "doktor", "aka"}))
        assert not {"qotil", "doktor", "aka", "uka"} & set(r)


# ---------- tun ----------
def test_mafia_kill_and_doctor_save():
    g = mk("don", "doktor", "tinch", "tinch", "tinch")
    ev = night(g, (1, "mafia_kill", 3), (2, "heal", 3))
    assert g.get(3).alive and "saved" in kinds(ev)
    ev = night(g, (1, "mafia_kill", 3))
    assert not g.get(3).alive


def test_doctor_cannot_heal_same_twice():
    g = mk("don", "doktor", "tinch", "tinch", "tinch")
    night(g, (2, "heal", 3))
    assert not g.submit(2, "heal", 3)


def test_kezuvchi_blocks_don():
    g = mk("don", "kezuvchi", "tinch", "tinch", "tinch")
    ev = night(g, (1, "mafia_kill", 3), (2, "block", 1))
    assert g.get(3).alive and "blocked" in kinds(ev)


def test_don_absent_mafia_majority():
    g = mk("don", "mafiya", "mafiya", "tinch", "tinch", "tinch", "tinch", "tinch")
    night(g, (2, "mafia_kill", 4), (3, "mafia_kill", 4))
    assert not g.get(4).alive


def test_afsungar_takes_don_and_mafiya_promoted():
    g = mk("don", "mafiya", "afsungar", "tinch", "tinch", "tinch", "tinch")
    ev = night(g, (1, "mafia_kill", 3))
    assert not g.get(3).alive and not g.get(1).alive
    assert g.get(2).role == "don" and "promoted" in kinds(ev)


def test_suitsid():
    g = mk("don", "mafiya", "suitsid", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 3))
    assert not g.get(1).alive and g.get(3).won


def test_voris_transforms():
    g = mk("don", "voris", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 2))
    assert g.get(2).alive and g.get(2).role == "mafiya"
    g = mk("don", "voris", "komissar", "tinch", "tinch", "tinch")
    night(g, (3, "shoot", 2))
    assert g.get(2).alive and g.get(2).role == "serjant"


def test_sehrgar_immunity():
    g = mk("don", "sehrgar", "komissar", "yollanma", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 2), (3, "shoot", 2))
    assert g.get(2).alive
    night(g, (4, "hit", 2))
    assert not g.get(2).alive


def test_qotil_immune_to_mafia():
    g = mk("don", "qotil", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 2), (2, "kill", 3))
    assert g.get(2).alive and not g.get(3).alive


def test_advokat_and_doc_disguise():
    g = mk("don", "advokat", "komissar", "tinch", "tinch", "tinch", "tinch", p1={"doc": 1})
    ev = night(g, (2, "disguise", 2), (3, "check", 2))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch"]  # niqob: Tinch aholi
    ev = night(g, (3, "check", 1))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch"] and "item_used" in kinds(ev)
    ev = night(g, (3, "check", 1))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["don"]  # aniq rol


def test_sotqin_looks_town():
    g = mk("don", "sotqin", "komissar", "tinch", "tinch")
    ev = night(g, (3, "check", 2))
    assert ev[0].data["result"] == "tinch"


def test_aka_uka_pair_and_link():
    g = mk("don", "aka", "uka", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch")
    night(g, (2, "pair", 5), (3, "pair", 5))
    assert not g.get(5).alive
    night(g, (2, "pair", 6), (3, "pair", 7))
    assert g.get(6).alive and g.get(7).alive
    vote(g, (4, 2), (6, 2), (7, 2))
    assert not g.get(2).alive and not g.get(3).alive


def test_vampir_and_verbena():
    g = mk("don", "vampir", "tinch", "tinch", "tinch", "tinch", p3={"verbena": 1})
    night(g, (2, "bite", 3))
    assert g.get(3).alive
    night(g, (2, "bite", 3))
    assert not g.get(3).alive


def test_shield():
    g = mk("don", "tinch", "tinch", "tinch", "tinch", p2={"shield": 1})
    night(g, (1, "mafia_kill", 2))
    assert g.get(2).alive and g.get(2).items["shield"] == 0


def test_aferist_steals_kill_and_check():
    g = mk("don", "aferist", "tinch", "tinch", "tinch", "tinch", "komissar", "tinch")
    ev = night(g, (1, "mafia_kill", 3), (2, "steal", 1))
    assert not g.get(3).alive and "stolen" in kinds(ev)
    ev = night(g, (7, "check", 1), (2, "steal", 7))
    checked = [e for e in ev if e.kind == "checked"]
    assert checked[0].uid == 2 and checked[0].data["result"] == "don"


def test_ovchi_penalty():
    g = mk("don", "ovchi", "tinch", "tinch", "tinch", "tinch")
    ev = night(g, (2, "shoot", 3))
    assert not g.get(3).alive and g.get(2).role == "tinch" and "penalty" in kinds(ev)


def test_ovchi_shooting_komissar_shows_ovchi_not_tinch():
    """Xato: jarimadan keyin "unikiga Tinch aholi kelgan" deb chiqardi."""
    from mafia_zone import texts
    g = mk("don", "ovchi", "komissar", "daydi", "tinch", "tinch", "tinch")
    ev = night(g, (2, "shoot", 3), (4, "visit", 3))
    killed = next(e for e in ev if e.kind == "killed")
    assert killed.data["killer_roles"] == ["ovchi"] and killed.data["role"] == "komissar"
    assert next(e for e in ev if e.kind == "witness").data["killer_roles"] == ["ovchi"]
    pub, _ = texts.morning(g, ev)
    text = next(t for t in pub if "kelgan" in t)
    assert texts.role("ovchi") in text and texts.role("tinch") not in text and texts.role("komissar") in text


def test_skip_night_action():
    g = Game(1, 42, [Player(i + 1, f"p{i + 1}", r) for i, r in enumerate(
        ["don", "mafiya", "doktor", "komissar", "tinch", "tinch", "tinch", "tinch"])], afk_limit=1)
    for uid, kind in [(1, "skip"), (2, "mafia_kill"), (3, "skip"), (4, "skip")]:
        assert g.submit(uid, kind, 5 if kind == "mafia_kill" else None)
    assert not g.submit(5, "skip", None)  # Tinchda tungi harakat yo'q
    assert g.all_acted()
    ev = g.resolve_night()
    assert all(p.alive for p in g.players)  # Don "hech kim" dedi: mafiya ovozi hisobga olinmaydi
    assert "mafia_idle" in kinds(ev) and "afk" not in kinds(ev)  # skip AFK emas
    g.afk_limit = 0  # quyidagi ovozsiz kun AFK sanalmasin
    g.start_voting(); g.resolve_vote()
    assert g.submit(2, "skip", None) and g.submit(1, "mafia_kill", 6)  # mafiyachi skip, Don tanladi
    g.resolve_night()
    assert not g.get(6).alive


def test_gazabkor_sacrifice():
    g = mk("don", "gazabkor", *["tinch"] * 10)
    for t in (3, 4, 5):
        night(g, (2, "rage", t))
    assert g.get(2).kills == 3
    night(g, (2, "sacrifice", None))
    assert not g.get(2).alive and g.get(2).won


def test_serjant_promoted():
    g = mk("don", "komissar", "serjant", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 2))
    assert g.get(3).role == "komissar"


def test_daydi_and_jurnalist():
    g = mk("don", "jurnalist", "daydi", "tinch", "tinch", "doktor", "tinch", "tinch")
    ev = night(g, (1, "mafia_kill", 4), (3, "visit", 4), (6, "heal", 5), (2, "interview", 5))
    assert next(e for e in ev if e.kind == "witness").data["killers"] == [1]
    assert next(e for e in ev if e.kind == "interview").data["visitors"] == [6]


def test_konchi_dig():
    from mafia_zone import texts
    g = mk("don", "konchi", "tinch", "tinch", "tinch")
    ev = night(g, (2, "dig", None))
    d = next(e for e in ev if e.kind == "dug").data
    assert 10 <= d["dollars"] <= 2000 and 0 <= d["diamonds"] <= 3
    pub, priv = texts.morning(g, ev)
    assert any(f"{d['dollars']} 💵" in x and "topdi" in x for x in pub)  # guruhga ham
    assert "10 dan 2000" in texts.role_card(g, 2) and "%" not in texts.role_card(g, 2)


def test_konchi_dig_distribution():
    from mafia_zone.engine.game import dig_loot
    import random as _r
    rng = _r.Random(1)
    loot = [dig_loot(rng) for _ in range(100_000)]
    dollars = [x for x, _ in loot]
    gems = [y for _, y in loot]
    assert min(dollars) >= 10 and max(dollars) <= 2000 and max(dollars) > 1000
    assert 0.003 < sum(x > 500 for x in dollars) / len(loot) < 0.02  # 500 dan tepasi - ~1%
    assert 0.55 < sum(x <= 50 for x in dollars) / len(loot) < 0.65
    assert set(gems) <= {0, 1, 2, 3} and 0.92 < gems.count(0) / len(loot) < 0.96 and gems.count(3) < gems.count(2)


# ---------- kun ----------
def test_janob_double_vote():
    g = mk("don", "janob", "tinch", "tinch", "tinch")
    night(g)
    vote(g, (2, 1), (3, 4))
    assert not g.get(1).alive


def test_tie_no_hang():
    g = mk("don", "tinch", "tinch", "tinch", "tinch")
    night(g)
    ev = vote(g, (2, 1), (3, 4))
    assert "no_hang" in kinds(ev)


def test_qorovul_and_podshoh():
    g = mk("don", "mafiya", "qorovul", "podshoh", *["tinch"] * 5)
    night(g, (3, "guard", 4))
    ev = vote(g, (1, 4), (2, 4))
    assert g.get(4).alive and "guard_saved" in kinds(ev)
    night(g)
    vote(g, (1, 4), (2, 4))
    assert g.phase == FINISHED and g.winner == MAFIA


def test_tulki_takes_first_voter():
    g = mk("don", "tulki", "tinch", "tinch", "tinch", "tinch", "tinch")
    night(g)
    vote(g, (3, 2), (4, 2), (5, 2))
    assert not g.get(3).alive and g.get(2).won and g.get(4).alive


def test_qaroqchi_vote_steal():
    g = mk("don", "qaroqchi", "tinch", "tinch", "tinch", "tinch")
    for seed in range(100):
        g.seed = seed
        ev = night(g, (2, "rob", 3))
        if ev[0].data["what"] == "vote":
            g.start_voting()
            assert not g.can_vote(3)
            return
    pytest.fail("vote o'g'irlash hech chiqmadi")


# ---------- g'alaba ----------
def test_town_wins():
    g = mk("don", "tinch", "tinch", "tinch", "tinch")
    night(g)
    vote(g, (2, 1), (3, 1))
    assert g.winner == TOWN and g.get(2).won and not g.get(1).won


def test_only_alive_teammates_win():
    # 1-tun: Don Komissarni o'ldiradi; kunduzi Donni osishadi -> Tinchlar yutadi, lekin o'lgan Komissar emas
    g = mk("don", "komissar", "suitsid", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 2))
    vote(g, (3, 1), (4, 1), (5, 1))
    assert g.winner == TOWN and not g.get(2).won and g.get(3).won and g.get(4).won and not g.get(1).won
    # Suitsid o'lib yutadi - o'yin oxirida ham g'olib qoladi
    g = mk("don", "mafiya", "suitsid", "tinch", "tinch", "tinch", "tinch")
    night(g, (1, "mafia_kill", 3))
    vote(g, (4, 2), (5, 2), (6, 2))
    assert g.winner == TOWN and g.get(3).won and not g.get(3).alive


def test_mafia_wins_parity_and_sotqin():
    g = mk("don", "sotqin", "tinch", "tinch")
    night(g, (1, "mafia_kill", 3))
    vote(g, (1, 4), (2, 4))
    assert g.winner == MAFIA and g.get(2).won


def test_qotil_solo():
    g = mk("don", "qotil", "tinch")
    night(g, (1, "mafia_kill", 3))
    assert g.winner == "qotil" and g.get(2).won


# ---------- saqlash ----------
def test_roundtrip_json():
    g = mk("don", "doktor", "tinch", "tinch", "tinch")
    g.submit(1, "mafia_kill", 3)
    g.submit(2, "heal", 4)
    g2 = Game.from_dict(json.loads(json.dumps(g.to_dict())))
    assert g2 == g


# ---------- simulyator ----------
def play_random(seed: int) -> Game:
    rng = random.Random(seed)
    n = rng.randint(4, 60)
    g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed,
                    items={i: {"shield": rng.randint(0, 1), "doc": rng.randint(0, 1)} for i in range(1, n + 1)})
    for _ in range(g.max_days + 2):
        for p in g.alive():
            acts = g.available_actions(p.uid)
            if not acts or rng.random() < 0.1:
                continue
            k = rng.choice(acts)
            ts = g.targets(p.uid, k)
            if ts or k in ("dig", "sacrifice"):
                assert g.submit(p.uid, k, rng.choice(ts) if ts else None)
        g = Game.from_dict(json.loads(json.dumps(g.to_dict())))
        g.resolve_night()
        if g.phase == FINISHED:
            return g
        g.start_voting()
        alive = [p.uid for p in g.alive()]
        for u in alive:
            if g.can_vote(u):
                g.cast_vote(u, rng.choice([None] + [x for x in alive if x != u]))
        g.resolve_vote()
        if g.phase == FINISHED:
            return g
    raise AssertionError(f"seed {seed}: o'yin tugamadi")


def test_simulate_many():
    for seed in range(10_000):
        g = play_random(seed)
        assert g.winner is not None
        assert g.day <= g.max_days + 1
        # o'lgan o'yinchi faqat o'limi bilan yutadigan rollarda g'olib bo'ladi
        assert all(p.alive or p.role in ("suitsid", "tulki", "gazabkor") for p in g.players if p.won), seed
        if g.winner in (TOWN, MAFIA):
            assert all(p.won for p in g.alive() if p.team == g.winner), seed


def test_afk_kicked():
    g = mk("don", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch")
    g.afk_limit = 3
    for _ in range(2):
        night(g, (1, "mafia_kill", 8) if g.get(8).alive else (1, "mafia_kill", 7))
        vote(g, (1, None), (2, None), (3, None), (4, None), (5, None))
    # 6-o'yinchi 2 kun ovoz bermadi; 3-chisida chiqariladi, faol 2-o'yinchi qoladi
    night(g, (1, "mafia_kill", 2))
    assert g.get(6).alive
    ev = vote(g, (1, None), (3, None))
    assert not g.get(6).alive and "afk" in kinds(ev)
    assert g.get(3).alive


# ---------- ikki bosqichli osish ----------
def nominate(g, *pairs):
    g.start_voting()
    for v, t in pairs:
        assert g.cast_vote(v, t)
    return g.resolve_vote()


def test_confirm_yes_hangs():
    g = mk("don", "tinch", "tinch", "tinch", "tinch", "tinch")
    g.confirm = True
    night(g)
    ev = nominate(g, (2, 1), (3, 1))
    assert g.phase == "confirm" and g.candidate == 1 and "candidate" in kinds(ev)
    assert not g.cast_confirm(1, False)  # nomzod o'zi ovoz bermaydi
    for u in (2, 3, 4):
        assert g.cast_confirm(u, True)
    g.cast_confirm(5, False)
    ev = g.resolve_confirm()
    assert not g.get(1).alive and g.winner == TOWN


def test_confirm_no_spares_and_janob_weight():
    g = mk("don", "janob", "tinch", "tinch", "tinch", "tinch")
    g.confirm = True
    night(g)
    nominate(g, (1, 3), (4, 3))
    g.cast_confirm(1, True)
    g.cast_confirm(4, True)
    g.cast_confirm(2, False)  # Janob: 2 ovoz -> 2:2, rahm
    ev = g.resolve_confirm()
    assert g.get(3).alive and "spared" in kinds(ev) and g.phase == "night" and g.day == 2


def test_ticket_gives_active_role():
    for seed in range(50):
        g = Game.create(1, [(i, f"p{i}") for i in range(1, 11)], seed, items={i: {"ticket": 1} for i in (1, 2)})
        before = {p.uid: p.role for p in g.players}
        used = g.use_tickets()
        for uid in (1, 2):
            assert g.get(uid).role != "tinch"
            assert (uid in used) == (before[uid] == "tinch")
        assert sorted(before.values()) == sorted(p.role for p in g.players)  # tarkib o'zgarmaydi


def test_simulate_with_confirm():
    for seed in range(3000):
        rng = random.Random(seed)
        n = rng.randint(4, 60)
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed, confirm=True)
        for _ in range(g.max_days + 2):
            for p in g.alive():
                acts = g.available_actions(p.uid)
                if acts:
                    k = rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    g.submit(p.uid, k, rng.choice(ts) if ts else None)
            g.resolve_night()
            if g.phase == FINISHED:
                break
            g.start_voting()
            alive = [p.uid for p in g.alive()]
            for u in alive:
                if g.can_vote(u):
                    g.cast_vote(u, rng.choice([None] + [x for x in alive if x != u]))
            g.resolve_vote()
            if g.phase == "confirm":
                for u in alive:
                    if g.can_confirm(u):
                        g.cast_confirm(u, rng.random() < 0.6)
                g = Game.from_dict(json.loads(json.dumps(g.to_dict())))
                g.resolve_confirm()
            if g.phase == FINISHED:
                break
        assert g.phase == FINISHED, seed


# ---------- yashirin hissa balli (g'oliblar tartibi) ----------
def test_hidden_score_orders_winners():
    from mafia_zone import texts
    # ro'yxatda komissar va doktor oxirida: tartib qo'shilish navbatiga emas, o'yinga qarab bo'lishi kerak
    g = mk("don", "tinch", "tinch", "tinch", "doktor", "komissar")
    night(g, (1, "mafia_kill", 2), (5, "heal", 4), (6, "check", 1))  # tinch o'ldi, komissar Donni topdi
    assert g.get(1).score == 3 and g.get(6).score == 3 and g.get(5).score == 0
    s5 = g.get(5).score + 1  # +1 - kunduzgi kun omon qoldi
    night(g, (1, "mafia_kill", 3), (5, "heal", 3), (6, "check", 1))  # doktor qutqardi
    assert g.get(3).alive and g.get(5).score == s5 + 3
    g2 = Game.from_dict(json.loads(json.dumps(g.to_dict())))  # ball saqlanadi
    assert [p.score for p in g2.players] == [p.score for p in g.players]
    vote(g, (3, 1), (4, 1), (5, 1), (6, 1))  # Don osildi - tinch aholi yutdi
    assert g.phase == FINISHED and g.get(4).score < g.get(5).score < g.get(6).score
    text = texts.game_over(g)
    won = text.split("G'oliblar")[1].split("Qolgan")[0]
    assert won.index("p6") < won.index("p5") < won.index("p3")
    assert "ball" not in text.lower() and "ochko" not in text.lower()  # foydalanuvchiga ko'rsatilmaydi


def test_score_penalties():
    g = mk("don", "mafiya", "tinch", "tinch", "tinch", "tinch", "tinch")
    vote(g, (1, 2), (3, 4))  # durang - hech kim osilmaydi: faqat kun omon qolgani uchun
    assert g.get(1).score == g.get(3).score == 1
    vote(g, (1, 2), (3, 2), (4, 2))  # mafiya osildi: tinchlar +2, Don (sherigini osdi) -1
    assert g.get(3).score > 0 and g.get(1).score < g.get(3).score


# ---------- tungi natija xabarlari ----------
def _results(ev):
    return {(e.uid, e.data["kind"]): e.data["ok"] for e in ev if e.kind == "result"}


def test_night_results_for_every_actor():
    g = mk("don", "doktor", "komissar", "kezuvchi", "daydi", "qotil", "tinch", "tinch", "tinch", "advokat")
    ev = night(g, (1, "mafia_kill", 7), (2, "heal", 7), (3, "shoot", 8), (4, "block", 9), (5, "visit", 9),
               (6, "kill", 3), (10, "disguise", 1))
    r = _results(ev)
    assert r[(2, "heal")] is True and g.get(7).alive  # doktor qutqardi
    assert r[(3, "shoot")] is True and r[(6, "kill")] is True  # komissar tinchni otdi, qotil komissarni
    assert r[(4, "block")] is True and r[(10, "disguise")] is True and r[(5, "visit")] is False
    from mafia_zone import texts
    _, priv = texts.morning(g, ev)
    to = {}
    for uid, t in priv:
        to.setdefault(uid, []).append(t)
    for uid in (2, 3, 4, 5, 6, 10):
        assert uid in to, uid
    assert any("qutqar" in t for t in to[2]) and any("Doktor" in t for t in to[7])  # hujum qilingan o'zi ham biladi


def test_heal_without_attack_and_failed_attack():
    g = mk("don", "doktor", "komissar", "sehrgar", "tinch", "tinch", "tinch")
    ev = night(g, (2, "heal", 5), (3, "shoot", 4))  # sehrgar komissar o'qidan himoyalangan
    r = _results(ev)
    assert r[(2, "heal")] is False and r[(3, "shoot")] is False and g.get(4).alive


def test_skip_feed_texts():
    from mafia_zone import texts
    assert "dam" in texts.skip_feed("doktor")
    assert texts.skip_feed("don") is None  # ertalab "Don hech kimni tanlamadi" chiqadi
    assert texts.skip_feed("qotil")


def test_blocked_player_cannot_vote_next_day():
    g = mk("don", "kezuvchi", "doktor", "tinch", "tinch", "tinch", "tinch")
    night(g, (2, "block", 3), (3, "heal", 4))
    g.start_voting()
    assert not g.can_vote(3) and g.can_vote(4)  # uxlatilgan - ertangi ovozdan ham mahrum
    g.resolve_vote()  # hech kim osilmaydi, o'yin davom etadi
    night(g)
    g.start_voting()
    assert g.can_vote(3)  # faqat bir kun



def test_check_shows_exact_role():
    from mafia_zone import texts
    g = mk("don", "qotil", "komissar", "tinch", "tinch", "tinch")
    ev = night(g, (3, "check", 2))
    _, priv = texts.morning(g, ev)
    assert any(texts.role("qotil") in t for u, t in priv if u == 3)


def test_doctor_and_patient_both_told():
    from mafia_zone import texts

    def pms(g, ev):
        out = {}
        for uid, t in texts.morning(g, ev)[1]:
            out.setdefault(uid, []).append(t)
        return out
    g = mk("don", "doktor", "tinch", "tinch", "tinch", "tinch")
    to = pms(g, night(g, (1, "mafia_kill", 3), (2, "heal", 3)))
    assert any("yordam bera oldingiz" in t for t in to[2])
    assert len(to[3]) == 1 and "Doktor" in to[3][0] and "qutqar" in to[3][0]  # bitta xabar, takror emas
    g = mk("don", "doktor", "tinch", "tinch", "tinch", "tinch")
    to = pms(g, night(g, (1, "mafia_kill", 3), (2, "heal", 4)))
    assert any("hech kim hujum qilmadi" in t for t in to[2]) and any("Doktor" in t for t in to[4])


# ---------- himoyalar bekorga yonmasin ----------
def test_doc_only_for_mafia_and_neutrals():
    g = mk("don", "komissar", "tinch", "doktor", "tinch", "tinch", p3={"doc": 1}, p4={"doc": 1})
    ev = night(g, (2, "check", 3))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch"] and "item_used" not in kinds(ev)
    assert g.get(3).items["doc"] == 1  # tinch aholida hujjat yonmaydi
    ev = night(g, (2, "check", 4))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["doktor"] and g.get(4).items["doc"] == 1
    g = mk("don", "qotil", "komissar", "tinch", "tinch", "tinch", "tinch", p2={"doc": 1})
    ev = night(g, (3, "check", 2))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch"] and g.get(2).items["doc"] == 0


def test_doc_covers_every_check_that_night():
    g = mk("don", "komissar", "ovchi", "tinch", "tinch", "tinch", "tinch", p1={"doc": 1})
    ev = night(g, (2, "check", 1), (3, "check", 1))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == ["tinch", "tinch"]
    assert kinds(ev).count("item_used") == 1


def test_suitsid_shield_not_used_against_mafia():
    g = mk("don", "suitsid", "tinch", "tinch", "tinch", "tinch", "mafiya", p2={"shield": 1})
    ev = night(g, (1, "mafia_kill", 2))
    assert not g.get(2).alive and g.get(2).won and not g.get(1).alive  # Donni olib ketdi
    assert g.get(2).items["shield"] == 1 and "item_used" not in kinds(ev)


def test_tulki_votesave_not_used():
    g = mk("don", "tulki", "tinch", "tinch", "tinch", "tinch", "mafiya", p2={"votesave": 1})
    ev = vote(g, (3, 2), (4, 2))
    assert not g.get(2).alive and g.get(2).won and g.get(2).items["votesave"] == 1
    assert "vote_saved" not in kinds(ev)


# ---------- 💞 paralar o'yini ----------
def test_couple_pairs_only_real_couples():
    from mafia_zone.engine.game import couple_pairs
    pairs = couple_pairs([1, 2, 3, 4, 5], {1: 2, 2: 1, 3: 9, 4: 5, 5: 4})  # 3 ning jufti o'yinda yo'q
    assert pairs == {1: 2, 2: 1, 4: 5, 5: 4}


def couple_game(*roles):
    g = mk(*roles)
    g.couple_mode = True
    g.pairs = {u: (u + 1 if u % 2 else u - 1) for u in range(1, len(roles) + 1)}  # 1-2, 3-4, 5-6 ...
    return g


def test_partner_dies_too_and_serializes():
    g = couple_game("don", "tinch", "tinch", "tinch", "tinch", "tinch", "doktor", "mafiya")
    ev = night(g, (1, "mafia_kill", 3))
    assert not g.get(3).alive and not g.get(4).alive
    assert any(e.kind == "heartbreak" and e.target == 4 for e in ev)
    g2 = Game.from_dict(json.loads(json.dumps(g.to_dict())))
    assert g2.pairs == g.pairs and g2.couple_mode


def test_couple_mode_no_teams_anyone_can_be_killed():
    g = couple_game("don", "tinch", "mafiya", "tinch", "tinch", "tinch")
    assert 3 in g.targets(1, "mafia_kill") and 2 not in g.targets(1, "mafia_kill")  # sherik mumkin, jufti - yo'q
    night(g, (1, "mafia_kill", 3))  # Don mafiyani o'ldirdi: 3-4 jufti chiqdi
    assert not g.get(3).alive and not g.get(4).alive and g.phase != FINISHED  # mafiya "yutmaydi"
    vote(g, (1, 5), (2, 5), (5, 1))
    assert g.phase == FINISHED and g.winner == "couple"
    assert {p.uid for p in g.players if p.won} == {1, 2}  # faqat oxirgi tirik juft


def test_couple_mode_ignores_side_wins():
    g = couple_game("don", "tinch", "podshoh", "tinch", "suitsid", "tinch")
    vote(g, (1, 3), (2, 3))  # Podshoh osildi - oddiy o'yindagidek tugamaydi
    assert g.phase != FINISHED and not g.get(4).alive
    night(g, (1, "mafia_kill", 5))  # Suitsid Donni olib ketadi, lekin yutmaydi
    assert g.phase == FINISHED and g.winner == "draw" and not any(p.won for p in g.players)  # hamma o'ldi


def test_simulate_couple_mode():
    from mafia_zone import texts
    from mafia_zone.engine.game import DRAW
    wins = 0
    for seed in range(2000):
        rng = random.Random(seed)
        n = rng.randrange(4, 41, 2)
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed)
        g.couple_mode = True
        g.pairs = {u: (u + 1 if u % 2 else u - 1) for u in range(1, n + 1)}
        for _ in range(g.max_days + 2):
            for p in g.alive():
                acts = g.available_actions(p.uid)
                if acts and rng.random() > 0.1:
                    k = rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    if ts or k in ("dig", "sacrifice"):
                        assert g.submit(p.uid, k, rng.choice(ts) if ts else None)
            texts.morning(g, g.resolve_night())
            if g.phase == FINISHED:
                break
            g.start_voting()
            for p in g.alive():
                if g.can_vote(p.uid):
                    g.cast_vote(p.uid, rng.choice([None] + [x.uid for x in g.alive() if x.uid != p.uid]))
            texts.morning(g, g.resolve_vote())
            if g.phase == FINISHED:
                break
        assert g.phase == FINISHED and g.winner in ("couple", DRAW), (seed, g.winner)
        winners = {p.uid for p in g.players if p.won}
        if g.winner == "couple":
            a = next(iter(winners))
            assert winners == {a, g.pairs[a]}, seed  # har doim bitta juft
            wins += 1
        else:
            assert not winners, seed
        texts.game_over(g)
    assert wins > 1500


def test_healed_player_keeps_shield():
    g = mk("don", "doktor", "tinch", "tinch", "tinch", "tinch", "komissar", p3={"shield": 1, "verbena": 1})
    ev = night(g, (1, "mafia_kill", 3), (7, "shoot", 3), (2, "heal", 3))  # ikki hujum + davolash
    assert g.get(3).alive and g.get(3).items == {"shield": 1, "verbena": 1} and "item_used" not in kinds(ev)


def test_protections_never_double_spent():
    """Tasodifiy o'yinlar: davolangan odamning qalqoni/verbenasi hech qachon yonmaydi."""
    for seed in range(3000):
        rng = random.Random(seed)
        n = rng.randint(6, 30)
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed,
                        items={i: {k: rng.randint(0, 1) for k in ("shield", "verbena", "doc")} for i in range(1, n + 1)})
        for _ in range(5):
            for p in g.alive():
                acts = g.available_actions(p.uid)
                if acts:
                    k = rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    if ts or k in ("dig", "sacrifice"):
                        g.submit(p.uid, k, rng.choice(ts) if ts else None)
            ev = g.resolve_night()
            healed = {e.target for e in ev if e.kind == "result" and e.data["kind"] == "heal"}
            assert not any(e.kind == "item_used" and e.uid in healed and e.data["item"] in ("shield", "verbena")
                           for e in ev), seed
            if g.phase == FINISHED:
                break
            g.start_voting()
            g.resolve_vote()
            if g.phase == FINISHED:
                break


def test_checked_player_is_told():
    from mafia_zone import texts
    g = mk("don", "komissar", "tinch", "tinch", "tinch")
    _, priv = texts.morning(g, night(g, (2, "check", 1)))
    assert (1, texts.CHECKED_YOU) in priv and not any(u == 1 and "Komissar" in t for u, t in priv)  # kim - aytilmaydi


# ---------- o'yindan chiqqan o'yinchi (/leave, guruhdan chiqish) ----------
def test_left_podshoh_is_not_hanged_and_mafia_does_not_win():
    """Podshoh ovozda yetakchi bo'lib /leave qilsa, o'lik Podshoh "osilib" mafiyaga g'alaba bermasin."""
    g = mk("don", "mafiya", "qorovul", "podshoh", *["tinch"] * 5)
    night(g)
    g.start_voting()
    for v in (1, 2, 5):
        g.cast_vote(v, 4)
    assert "left" in kinds(g.kill_player(4))
    ev = g.resolve_vote()
    assert "hanged" not in kinds(ev) and g.phase != FINISHED and g.winner is None


def test_left_tulki_is_not_hanged():
    g = mk("don", "tulki", "tinch", "tinch", "tinch", "tinch", "tinch")
    night(g)
    g.start_voting()
    for v in (3, 4, 5):
        g.cast_vote(v, 2)
    g.kill_player(2)
    ev = g.resolve_vote()
    assert "hanged" not in kinds(ev) and "tulki" not in kinds(ev)
    assert g.get(3).alive and not g.get(2).won


def test_votes_of_left_players_do_not_count():
    """Chiqib ketganning ovozi hisoblanmaydi: qolganlarning ovozi hal qiladi."""
    g = mk("don", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch")
    night(g)
    g.start_voting()
    g.cast_vote(2, 3), g.cast_vote(4, 3), g.cast_vote(5, 6)
    g.kill_player(2), g.kill_player(4)
    ev = g.resolve_vote()
    assert [e.target for e in ev if e.kind == "hanged"] == [6] and g.get(3).alive


def test_left_candidate_is_not_hanged_in_confirm():
    g = mk("don", "mafiya", "qorovul", "podshoh", *["tinch"] * 5)
    g.confirm = True
    night(g)
    vote(g, (1, 4), (2, 4), (5, 4))
    assert g.candidate == 4
    for v in (1, 2, 5, 6):
        g.cast_confirm(v, True)
    g.kill_player(4)
    ev = g.resolve_confirm()
    assert "hanged" not in kinds(ev) and g.phase != FINISHED


def test_confirms_of_left_players_do_not_count():
    g = mk("don", "tinch", "tinch", "tinch", "tinch", "tinch", "tinch")
    g.confirm = True
    night(g)
    vote(g, (2, 3), (4, 3))
    g.cast_confirm(2, True), g.cast_confirm(4, True), g.cast_confirm(5, False)
    g.kill_player(2), g.kill_player(4)
    assert g.confirm_tally() == (0, 1)
    assert "spared" in kinds(g.resolve_confirm()) and g.get(3).alive


def test_night_actions_on_left_player_are_dropped():
    """Tunda chiqib ketgan o'yinchini tekshirish/o'g'irlash/o'ldirish bekor bo'ladi."""
    g = mk("don", "komissar", "qaroqchi", "jurnalist", "tinch", "tinch", "tinch", "tinch")
    g.submit(1, "mafia_kill", 5)
    g.submit(2, "check", 5)
    g.submit(3, "rob", 5)
    g.submit(4, "interview", 5)
    g.kill_player(5)
    ev = g.resolve_night()
    assert not [e for e in ev if e.target == 5 and e.kind != "result"], [(e.kind, e.target) for e in ev]


def test_don_target_left_falls_back_to_mafia_votes():
    g = mk("don", "mafiya", "tinch", "tinch", "tinch", "tinch", "tinch")
    g.submit(1, "mafia_kill", 3)
    g.submit(2, "mafia_kill", 4)
    g.kill_player(3)
    ev = g.resolve_night()
    assert [e.target for e in ev if e.kind == "killed"] == [4]


def test_simulate_leaves_never_hit_left_players():
    """Har fazada kimdir chiqib ketadi: chiqqan o'yinchi osilmaydi, tekshirilmaydi, o'g'irlanmaydi."""
    from mafia_zone.engine.game import CONFIRM, NIGHT, VOTING
    DEATH = {"killed", "hanged", "tulki", "checked", "interview", "robbed", "saw_role", "stolen", "vote_saved",
             "guard_saved", "candidate", "mafia_result", "afk"}
    bad = []
    for seed in range(1500):
        rng = random.Random(seed)
        n = rng.randint(5, 20)
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed, confirm=rng.random() < .5)
        gone = set()
        for _ in range(60):
            if g.phase == FINISHED:
                break
            if g.alive() and rng.random() < .4:
                u = rng.choice(g.alive()).uid
                g.kill_player(u); gone.add(u)
                if g.phase == FINISHED:
                    break
            if g.phase == NIGHT:
                for p in g.alive():
                    acts = g.available_actions(p.uid)
                    if acts:
                        k = rng.choice(acts); ts = g.targets(p.uid, k)
                        g.submit(p.uid, k, rng.choice(ts) if ts else None)
                if g.alive() and rng.random() < .5:
                    u = rng.choice(g.alive()).uid; g.kill_player(u); gone.add(u)
                    if g.phase == FINISHED: break
                ev = g.resolve_night()
            elif g.phase == DAY:
                g.start_voting(); continue
            elif g.phase == VOTING:
                al = [p.uid for p in g.alive()]
                for v in al:
                    g.cast_vote(v, rng.choice([x for x in al if x != v] + [None]))
                if al and rng.random() < .5:
                    u = rng.choice(al); g.kill_player(u); gone.add(u)
                    if g.phase == FINISHED: break
                ev = g.resolve_vote()
            else:
                for p in g.alive():
                    g.cast_confirm(p.uid, rng.random() < .6)
                if rng.random() < .5 and g.candidate is not None and g.get(g.candidate).alive:
                    g.kill_player(g.candidate); gone.add(g.candidate)
                    if g.phase == FINISHED: break
                ev = g.resolve_confirm()
            for e in ev:
                if e.kind in DEATH and e.target in gone:
                    bad.append((seed, e.kind))
    assert not bad, bad[:10]


# ---------- dvijok auditi (2026-10-09) ----------
def test_blocked_mafiya_vote_does_not_count():
    """Kezuvchi uxlatgan Mafiya bu tun hech narsa qila olmaydi - o'ldirishga ovozi ham hisoblanmaydi."""
    g = mk("don", "mafiya", "kezuvchi", "tinch", "tinch", "tinch", "tinch")
    g.submit(2, "mafia_kill", 4)
    g.submit(3, "block", 2)
    ev = g.resolve_night()
    assert g.get(4).alive and "killed" not in kinds(ev)


def test_aferist_cannot_steal_block():
    """Uxlatish birinchi bajariladi: Aferist uni o'g'irlay olmaydi, Kezuvchiga qarama-qarshi xabar bormaydi."""
    g = mk("don", "kezuvchi", "aferist", "tinch", "tinch", "tinch", "tinch")
    g.submit(2, "block", 4)
    g.submit(3, "steal", 2)
    ev = g.resolve_night()
    assert "stolen" not in kinds(ev) and "saw_role" in kinds(ev)
    assert any(e.kind == "blocked" and e.uid == 4 for e in ev)


def test_aferist_saw_role_respects_disguise_and_sotqin():
    """Aferist ko'rgan rol Komissar tekshiruvi bilan bir xil: niqob va Sotqin - Tinch aholi."""
    g = mk("don", "mafiya", "advokat", "aferist", "sotqin", "tinch", "tinch", "tinch")
    g.submit(3, "disguise", 2)
    g.submit(4, "steal", 2)
    ev = g.resolve_night()
    assert [e.data["role"] for e in ev if e.kind == "saw_role"] == ["tinch"]
    g2 = mk("don", "aferist", "sotqin", "tinch", "tinch", "tinch")
    ev = g2.resolve_night() if not g2.submit(2, "steal", 3) else g2.resolve_night()
    assert [e.data["role"] for e in ev if e.kind == "saw_role"] == ["tinch"]


def test_qotil_immune_to_aka_uka():
    """Qotil: "Mafiya sizga tegolmaydi" - Aka-Uka hujumi ham."""
    g = mk("don", "aka", "uka", "qotil", "tinch", "tinch", "tinch", "tinch")
    g.submit(2, "pair", 4)
    g.submit(3, "pair", 4)
    g.resolve_night()
    assert g.get(4).alive


def test_immune_attacker_is_told_fail_even_if_target_died():
    """Komissar Sehrgarga o'q uzdi (ta'sir qilmaydi), Vampir uni tishlab o'ldirdi: Komissarga "omon qoldi"."""
    g = mk("don", "komissar", "sehrgar", "vampir", *["tinch"] * 9)
    g.submit(2, "shoot", 3)
    g.submit(4, "bite", 3)
    ev = g.resolve_night()
    assert not g.get(3).alive
    res = {e.uid: e.data["ok"] for e in ev if e.kind == "result"}
    assert res[2] is False and res[4] is True


def test_blocked_doctor_can_heal_same_target_next_night():
    """Uxlatilgan Doktor davolamadi - ertasi kuni o'sha odamni davolay oladi."""
    g = mk("don", "doktor", "kezuvchi", "tinch", "tinch", "tinch", "tinch")
    night(g, (2, "heal", 4), (3, "block", 2))
    g.start_voting(), g.resolve_vote()
    assert 4 in g.targets(2, "heal")


def test_promotion_skips_aka_uka_and_mafia_is_told():
    """Don o'lsa Aka/Uka emas, boshqa mafiyadosh Don bo'ladi; jamoa yangi Donni biladi."""
    from mafia_zone import texts
    g = mk("don", "aka", "uka", "jurnalist", *["tinch"] * 8)
    g.get(1).alive = False
    ev = []
    g._after_deaths(ev)
    assert g.get(4).role == "don" and g.get(2).role == "aka"
    _, priv = texts.morning(g, ev)
    assert {u for u, t in priv if "Don" in t or texts.role("don") in t} >= {2, 3, 4}


def test_komissar_check_reaches_serjant_promoted_same_night():
    """Komissar tekshirib, shu tun o'ldirildi: Serjant (endi Komissar) natijani baribir oladi."""
    from mafia_zone import texts
    g = mk("don", "komissar", "serjant", "tinch", "tinch", "tinch", "tinch")
    g.submit(1, "mafia_kill", 2)
    g.submit(2, "check", 1)
    ev = g.resolve_night()
    assert g.get(3).role == "komissar"
    _, priv = texts.morning(g, ev)
    assert any(u == 3 and "Tekshiruv natijasi" in t for u, t in priv)


def test_death_pm_does_not_say_shot():
    """Tunda o'ldirish - har doim ham otish emas (zahar, tishlash, la'nat, Tulki)."""
    from mafia_zone import texts
    assert "otib" not in texts.death_pm(False) and "osib" in texts.death_pm(True)


def test_sehrgar_about_says_curse_kills():
    from mafia_zone.engine.roles import ROLES
    assert "o'ladi" in ROLES["sehrgar"].about
