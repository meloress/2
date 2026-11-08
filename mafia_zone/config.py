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
CLAIM_DELAY = 1.0  # tarqatma chiqqandan keyin shuncha soniya ichida bosgan (avto-bosuvchi bot) shu tarqatmadan ololmaydi
# /start menyusidagi guruh tugmalari: (nomi, havola). Avtomatik "eng faol guruhlar" o'rniga - qo'lda tanlangan
FEATURED_GROUPS = [("SKARFACE MAFIA 🥷🏻", "https://t.me/+OVoKusV3WqphZWUy")]
CARD_ADMIN = "jumayeevou"  # karta orqali to'lov: Stars ekranlarida shu adminga havola
SEASON_PRIZES = [10, 5, 3]  # oylik reyting: 1-, 2-, 3-o'ringa olmos (oy tugagach db.pay_season)
# /leave o'yin paytida faqat PRO uchun (kuniga pro.leave_free ta bepul, keyin jarima). Oddiy o'yinchida bepul chiqish 0:
# guruhdan chiqib ketsa darhol jarima. -1000 da o'yinga kirolmaydi
LEAVE_FREE, LEAVE_FINE, DEBT_LIMIT = 0, 200, -1000
DIAMOND_RATE = 300  # Exchange: 1 olmos -> 300 dollar
DIAMONDS_OFF = False  # True = olmos bilan xarid (PRO, Xarid, olmosli buyumlar, Stars->olmos) yopiq: "hali ishlamayapti"
DOLLAR_PACKS = {1: 300, 2: 600, 3: 800, 4: 1500, 15: 5000, 30: 10000}  # Xarid: olmos -> dollar
# Olmos paketlari: karta orqali (so'm) va Stars. Ikkalasida paketlar bir xil
DIAMOND_SUM = {1: 1150, 7: 7850, 15: 16500, 30: 32000, 55: 57000, 100: 100000, 250: 240000, 500: 462500, 1000: 890000}
DIAMOND_STARS = {1: 6, 7: 39, 15: 83, 30: 160, 55: 285, 100: 500, 250: 1200, 500: 2313, 1000: 4450}
# Olmos uchun karta raqami: Railway Variables'da CARD_NUMBER (gitga yozilmaydi). Bo'sh - karta to'lovi yopiq
CARD_NUMBER = "".join(c for c in os.environ.get("CARD_NUMBER", "") if c.isdigit())
CARD_ORDER_MIN = 7  # karta buyurtmasi shuncha daqiqa amal qiladi ("To'ladim" shu vaqt ichida)
NEWS_URL = os.environ.get("NEWS_URL", "").strip()  # yangiliklar kanali, bo'sh bo'lsa tugma chiqmaydi
SHOP = {"shield": 140, "verbena": 145, "doc": 190}  # dollar
SHOP_GEMS = {"mask": 1, "votesave": 2}  # olmos (PRO chegirmasi yo'q)
# Rolni tanlab olish, olmos (Tinchdan boshqa hamma rol). Narx - vazifaga qarab:
# 1 - tungi harakati yo'q yoki oddiy; 2 - foydali harakat/maxsus g'alaba; 3 - kuchli (o'ldiradi yoki hal qiladi);
# 4 - yakka g'olib qotillar va Konchi (o'yinda o'rtacha ~2 💎 qiymatida pul/olmos qazadi: narx undan yuqori)
ROLE_PICKS = {
    "komissar": 3, "serjant": 1, "doktor": 2, "daydi": 1, "kezuvchi": 2, "afsungar": 2, "voris": 1, "janob": 1,
    "ovchi": 2, "donishmand": 1, "suitsid": 2, "qorovul": 2, "podshoh": 1,
    "mafiya": 1, "don": 3, "jurnalist": 2, "yollanma": 3, "advokat": 2, "aka": 2, "uka": 2,
    "sotqin": 1, "qotil": 4, "gazabkor": 3, "sehrgar": 4, "vampir": 3, "qaroqchi": 3, "konchi": 4, "tulki": 2,
    "aferist": 2,
}
SHOP_OFF: set[str] = set()  # paneldan sotuvdan olingan buyumlar
# Bular paneldan o'zgaradi (db.load_settings): kodda doim config.X deb o'qing, "from config import X" emas.

# Admin panel: Railway "Generate Domain" qilinganda RAILWAY_PUBLIC_DOMAIN o'zi beriladi
_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
PANEL_URL = (os.environ.get("PANEL_URL", "").strip() or (f"https://{_domain}" if _domain else "")).rstrip("/")
PANEL_SECRET = os.environ.get("PANEL_SECRET", "").strip()  # bo'sh bo'lsa BOT_TOKEN dan hosil qilinadi
PORT = int(os.environ.get("PORT", "8080") or 8080)
# Oddiy emoji -> animatsion almashtirish to'plami. 2026-11: o'chirilgan - o'yin matnlarida oddiy emoji (env e'tiborsiz).
# PRO belgisi (pro.badge/tail, tugma ikonkasi) bunga kirmaydi - u premium bo'lib qoladi
EMOJI_PACK = ""
# Rol portretlari (premium emoji; to'plam: t.me/addemoji/admiral_roles_by_AdmiralMafiabot): rol kodi -> custom_emoji_id.
# Matnda rol emojisi (Role.name boshidagi) shu portretga almashadi. To'plamdan emas, shu yerdan: Telegram to'plamda
# teri rangini olib tashlaydi (🤵🏻 Don va 🤵🏼 Mafiya ikkalasi 🤵 bo'lib qoladi).
ROLE_EMOJI = {
    "tinch": "5440476919709614472", "komissar": "5442666077425281968", "serjant": "5442701386351422873",
    "doktor": "5443069735631630389", "daydi": "5443051202847751070", "kezuvchi": "5442822611803351913",
    "afsungar": "5442650800226611382", "voris": "5442899203955143365", "janob": "5442864869986579422",
    "ovchi": "5440899535901602436", "donishmand": "5442633139321088632", "suitsid": "5442632383406844556",
    "qorovul": "5440656857364474035", "podshoh": "5443081740065226197", "mafiya": "5442925227161987216",
    "don": "5443134087126625851", "jurnalist": "5440791023552868226", "yollanma": "5440753309445042704",
    "advokat": "5442648261900938537", "aka": "5442625979610608414", "uka": "5442632271737697753",
    "sotqin": "5440364743753772617", "qotil": "5442712746539918130", "gazabkor": "5443088624897799959",
    "sehrgar": "5442868774111851721", "vampir": "5442753600268841336", "qaroqchi": "5442939632482300722",
    "konchi": "5442847260620664377", "tulki": "5440720349866011565", "aferist": "5442738881415916709",
}
