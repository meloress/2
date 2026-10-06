import os
from pathlib import Path

# Lokal .env (Railwayda Variables ishlatiladi; mavjud env ustun turadi)
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8-sig").splitlines():
        key, sep, val = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip().strip("'\"")  # Railway'da qo'shtirnoq/bo'shliq bilan kiritilsa ham
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}

# Railway "postgresql://..." beradi, SQLAlchemy async uchun drayverni qo'shamiz.
# Lokal sinov uchun DATABASE_URL bo'lmasa SQLite ishlatiladi.
_url = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///mafia.db"
DATABASE_URL = _url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)

DEFAULT_SETTINGS = {"lobby": 120, "night": 60, "day": 60, "vote": 45, "items": True, "afk": True, "confirm": True, "disabled": []}

# Iqtisod (spec, 7-bo'lim)
REWARD_PLAY, REWARD_WIN, DAILY_BONUS, REF_BONUS = 0, 40, 20, 50  # yutsa 40$, yutqazsa 0
DIAMOND_RATE = 50
SHOP = {"shield": 100, "verbena": 80, "doc": 120, "ticket": 150}
