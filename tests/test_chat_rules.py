"""O'yin vaqtida guruhda kim nima yoza oladi."""
import asyncio
from types import SimpleNamespace

import pytest

from mafia_zone import handlers, runner
from mafia_zone.engine.game import CONFIRM, DAY, FINISHED, NIGHT, VOTING, Game, Player

ALIVE, DEAD, OUTSIDER, ADMIN = 1, 2, 99, 77


def game(phase):
    g = Game(-1, 1, [Player(ALIVE, "a", "tinch"), Player(DEAD, "d", "tinch", alive=False),
                     Player(3, "x", "don")], phase=phase)
    return g


@pytest.mark.parametrize("phase", [NIGHT, DAY, VOTING, CONFIRM])
def test_numbers_allowed_for_everyone(phase):
    g = game(phase)
    for uid in (ALIVE, DEAD, OUTSIDER, None):
        for text in ("5", " 12 ", "007"):
            assert handlers.may_write(g, uid, text, admin=False)
        assert not handlers.may_write(g, uid, "5a", admin=False) or (uid == ALIVE and phase != NIGHT)


def test_alive_player_talks_only_by_day():
    for ph in (DAY, VOTING, CONFIRM):
        assert handlers.may_write(game(ph), ALIVE, "salom", admin=False)
    assert not handlers.may_write(game(NIGHT), ALIVE, "salom", admin=False)


def test_dead_and_outsiders_silent():
    for ph in (NIGHT, DAY, VOTING, CONFIRM):
        for uid in (DEAD, OUTSIDER):
            assert not handlers.may_write(game(ph), uid, "salom", admin=False)
            assert not handlers.may_write(game(ph), uid, "", admin=False)  # stiker/rasm


def test_admin_needs_bang():
    for ph in (NIGHT, DAY):
        assert handlers.may_write(game(ph), ADMIN, "!salom", admin=True)
        assert not handlers.may_write(game(ph), ADMIN, "salom", admin=True)
        assert not handlers.may_write(game(ph), OUTSIDER, "!salom", admin=False)  # oddiy odamga ! yordam bermaydi


def run_handler(phase, uid, text, admins=(), sender_chat=None, lobby=False):
    deleted = []

    async def delete():
        deleted.append(True)

    class Bot:
        async def get_chat_administrators(self, chat_id):
            return [SimpleNamespace(user=SimpleNamespace(id=a)) for a in admins]

    r = runner.Runner(None, -1, {})
    if not lobby:
        r.game = game(phase)
    msg = SimpleNamespace(chat=SimpleNamespace(id=-1), from_user=SimpleNamespace(id=uid) if uid else None,
                          sender_chat=sender_chat, text=text, caption=None, delete=delete)
    handlers._admins.clear()
    try:
        asyncio.run(handlers.on_group_message(msg, Bot()))
    finally:
        r.close()
    return bool(deleted)


def test_handler_end_to_end():
    assert run_handler(NIGHT, OUTSIDER, "salom")
    assert not run_handler(NIGHT, OUTSIDER, "42")
    assert not run_handler(DAY, ALIVE, "salom")
    assert run_handler(DAY, DEAD, "salom")
    assert not run_handler(NIGHT, ADMIN, "!salom", admins=[ADMIN])
    assert run_handler(NIGHT, ADMIN, "salom", admins=[ADMIN])
    assert not run_handler(NIGHT, 1087968824, "!e'lon", sender_chat=SimpleNamespace(id=-1))  # yashirin admin
    assert not run_handler(FINISHED, OUTSIDER, "salom")  # o'yin tugagan
    assert not run_handler(NIGHT, OUTSIDER, "salom", lobby=True)  # lobbi - erkin
