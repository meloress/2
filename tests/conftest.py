import os
import tempfile

# Testlar hech qachon haqiqiy mafia.db ga tegmasin
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def diamonds_on():
    """Prod'da olmos xaridlari hozircha yopiq (config.DIAMONDS_OFF); testlar ularni ochiq holda tekshiradi."""
    from mafia_zone import config
    old, config.DIAMONDS_OFF = getattr(config, "DIAMONDS_OFF", False), False
    yield
    config.DIAMONDS_OFF = old
