"""⚪⚫ Oq-Qora rejimi (Game.sides): rollar odatdagidek, g'olib jamoaning hammasi (o'liklar ham) yutadi."""
import json
import random

from mafia_zone.engine.game import DAY, DRAW, FINISHED, Game
from tests.test_engine import mk, night, vote


def teams(g, oq):
    """oq - Oq jamoadagi uid'lar, qolganlari Qora."""
    g.sides = {p.uid: "oq" if p.uid in oq else "qora" for p in g.players}
    return g


def test_team_win_includes_dead():
    g = teams(mk("don", "tinch", "komissar", "tinch"), {1, 2})  # Oq: Don + Tinch, Qora: Komissar + Tinch
    night(g, (1, "mafia_kill", 3))
    assert g.phase == DAY and g.side(3) == "qora"
    vote(g, (1, 4), (2, 4))
    assert g.phase == FINISHED and g.winner == "oq"
    assert [p.uid for p in g.players if p.won] == [1, 2]
    g = teams(mk("don", "tinch", "komissar", "tinch"), {1, 2})
    night(g, (1, "mafia_kill", 2))  # Don o'z jamoasini o'ldirdi - cheklanmaydi
    vote(g, (3, 1), (4, 1))  # Oq tugadi: Qoraning hammasi yutadi
    assert g.winner == "qora" and [p.uid for p in g.players if p.won] == [3, 4]


def test_team_no_personal_wins():
    g = teams(mk("don", "suitsid", "tinch", "tinch", "tinch", "tinch"), {1, 3, 4})
    night(g, (1, "mafia_kill", 2))  # Suitsid mafiya qo'lida o'ldi - oddiy o'yinda yutardi
    assert not g.get(2).alive
    vote(g, (3, 5), (4, 5))  # Suitsid qasosi Donni ham olib ketgan bo'lishi mumkin - ovozni tiriklar beradi
    vote(g, (3, 6), (4, 6))
    assert g.winner == "oq" and not g.get(2).won
    g = teams(mk("podshoh", "don", "tinch", "tinch", "qorovul", "tinch"), {1, 3, 5})
    vote(g, (2, 1), (4, 1), (6, 1))  # Podshoh osildi - oddiy o'yinda mafiya yutardi
    assert g.phase != FINISHED


def test_team_targets_anyone_but_self():
    g = teams(mk("don", "mafiya", "tinch", "tinch"), {1, 3})
    ts = g.targets(1, "mafia_kill")
    assert 2 in ts and 3 in ts and 1 not in ts


def test_team_hunt_no_fine():
    g = teams(mk("ovchi", "tinch", "don", "tinch", "tinch", "tinch"), {1, 2, 3})
    night(g, (1, "check", 2))
    ev = g.hunter_kill(1)
    assert ev and ev[0].data["fine"] == 0


def test_team_sides_survive_save():
    g = teams(mk("don", "tinch", "komissar", "tinch"), {1, 2})
    g2 = Game.from_dict(json.loads(json.dumps(g.to_dict())))
    assert g2.sides == g.sides and g2.side(1) == "oq"


def test_simulate_teams():
    for seed in range(300):
        rng = random.Random(seed)
        n = rng.choice(range(4, 41, 2))
        g = Game.create(1, [(i, f"p{i}") for i in range(1, n + 1)], seed)
        teams(g, set(rng.sample(range(1, n + 1), n // 2)))
        for _ in range(g.max_days + 2):
            for p in g.night_actors():
                acts = g.available_actions(p.uid)
                if acts and rng.random() > 0.1:
                    k = rng.choice(acts)
                    ts = g.targets(p.uid, k)
                    if ts or k in ("dig", "sacrifice"):
                        g.submit(p.uid, k, rng.choice(ts) if ts else None)
            g = Game.from_dict(json.loads(json.dumps(g.to_dict())))
            g.resolve_night()
            if g.phase == FINISHED:
                break
            g.start_voting()
            for p in g.alive():
                if g.can_vote(p.uid):
                    g.cast_vote(p.uid, rng.choice([x.uid for x in g.alive()]))
            g.resolve_vote()
            if g.phase == FINISHED:
                break
        assert g.phase == FINISHED, seed
        won = {p.uid for p in g.players if p.won}
        if g.winner == DRAW:
            assert not won, seed
        else:
            assert g.winner in ("oq", "qora") and won == {u for u, s in g.sides.items() if s == g.winner}, seed
