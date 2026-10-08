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
REWARD_PLAY, REWARD_WIN, REF_BONUS = 0, 40, 50  # yutsa 40$, yutqazsa 0
# Ko'p profil bilan pul yig'ishga qarshi: shuncha tugagan o'yin kerak
REF_GAMES, CLAIM_GAMES, SEND_GAMES = 3, 3, 5  # taklif bonusi / tarqatmadan olish / /send
LEAVE_FREE, LEAVE_FINE, DEBT_LIMIT = 3, 200, -1000  # kuniga 3 ta bepul chiqish; -1000 da o'yinga kirolmaydi
DIAMOND_RATE = 300  # Exchange: 1 olmos -> 300 dollar
DIAMONDS_OFF = False  # True = olmos bilan xarid (PRO, Xarid, olmosli buyumlar, Stars->olmos) yopiq: "hali ishlamayapti"
DOLLAR_PACKS = {1: 300, 2: 600, 3: 800, 4: 1500, 15: 5000, 30: 10000}  # Xarid: olmos -> dollar
DIAMOND_STARS = {1: 7, 5: 35, 10: 66, 15: 101, 30: 202, 50: 342, 200: 1388, 500: 3488, 1000: 6984, 2000: 13984}  # olmos -> Stars
NEWS_URL = os.environ.get("NEWS_URL", "").strip()  # yangiliklar kanali, bo'sh bo'lsa tugma chiqmaydi
SHOP = {"shield": 140, "verbena": 145, "doc": 190}  # dollar
SHOP_GEMS = {"mask": 1, "votesave": 2}  # olmos (PRO chegirmasi yo'q)
ROLE_PICKS = {"komissar": 3, "don": 3, "doktor": 2, "kezuvchi": 2}  # rolni tanlab olish, olmos
SHOP_OFF: set[str] = set()  # paneldan sotuvdan olingan buyumlar
# Bular paneldan o'zgaradi (db.load_settings): kodda doim config.X deb o'qing, "from config import X" emas.

# Admin panel: Railway "Generate Domain" qilinganda RAILWAY_PUBLIC_DOMAIN o'zi beriladi
_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
PANEL_URL = (os.environ.get("PANEL_URL", "").strip() or (f"https://{_domain}" if _domain else "")).rstrip("/")
PANEL_SECRET = os.environ.get("PANEL_SECRET", "").strip()  # bo'sh bo'lsa BOT_TOKEN dan hosil qilinadi
PORT = int(os.environ.get("PORT", "8080") or 8080)
EMOJI_PACK = os.getenv("EMOJI_PACK", "RestrictedEmoji").strip()  # animatsion emoji to'plami; bo'sh = o'chiq
