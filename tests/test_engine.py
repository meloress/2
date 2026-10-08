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
    assert [e.data["result"] for e in ev if e.kind == "checked"] == [TOWN]
    ev = night(g, (3, "check", 1))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == [TOWN] and "item_used" in kinds(ev)
    ev = night(g, (3, "check", 1))
    assert [e.data["result"] for e in ev if e.kind == "checked"] == [MAFIA]


def test_sotqin_looks_town():
    g = mk("don", "sotqin", "komissar", "tinch", "tinch")
    ev = night(g, (3, "check", 2))
    assert ev[0].data["result"] == TOWN


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
    assert checked[0].uid == 2 and checked[0].data["result"] == MAFIA


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
    g = mk("don", "konchi", "tinch", "tinch", "tinch")
    ev = night(g, (2, "dig", None))
    assert 10 <= next(e for e in ev if e.kind == "dug").data["dollars"] <= 30


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
