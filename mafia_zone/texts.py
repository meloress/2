"""Barcha o'zbekcha matnlar. Dvijok hodisalarini xabarlarga aylantiradi."""
from datetime import timedelta
from html import escape
from random import choice

from . import config, pro
from .engine.game import DRAW, Event, Game
from .engine.roles import MAFIA, NEUTRAL, ROLES, TOWN

PRO_TZ = timedelta(hours=5)  # sanalar Toshkent vaqtida
TEAM = {TOWN: "👨 Tinch aholi", MAFIA: "🤵 Mafiya", NEUTRAL: "🎭 Neytral"}
ITEMS = {"shield": "🛡 Qalqon", "verbena": "🧄 Verbena", "doc": "📄 Hujjat", "mask": "🎭 Maska",
         "votesave": "⚖️ Ovoz himoyasi", "ticket": "🎟 Faol rol"}
ITEM_ABOUT = {
    "shield": "tungi o'limdan 1 marta saqlaydi",
    "verbena": "Vampir tishlashidan 1 marta saqlaydi",
    "doc": "mafiya yoki yakka rol bo'lsangiz, tekshiruvda 1 marta \"Tinch\" ko'rsatadi",
    "mask": "bir o'yin davomida rolingiz guruhga ochilmaydi — o'lganingizda ham",
    "votesave": "kunduzi osilishdan 1 marta saqlaydi (bir o'yinda bir marta)",
    "ticket": "keyingi o'yinda oddiy Tinch o'rniga maxsus rol kafolatlanadi",
}
for _c in config.ROLE_PICKS:  # "r_komissar": "🕵️‍♂️ Komissar Katani roli"
    ITEMS[f"r_{_c}"] = f"{ROLES[_c].name} roli"
    ITEM_ABOUT[f"r_{_c}"] = "keyingi o'yinda shu rol sizga tushadi (o'yinda bo'lsa; bo'lmasa keyingisiga qoladi)"
ALWAYS_SHOWN = ("shield", "verbena", "doc", "mask", "votesave")  # profilda 0 ta bo'lsa ham
MASKED = "🎭 Maskali"


def shown_role(g: Game, uid: int, code: str | None = None) -> str:
    """Guruhga ko'rinadigan rol: Maskali o'yinchining roli o'yin davomida yashirin."""
    p = g.get(uid)
    if p and p.items.get("mask", 0) > 0 and g.phase != "finished":
        return f"<b>{MASKED}</b>"
    return role(code or (p.role if p else "tinch"))
RANKS = [(0, "🐣 Yangi boshlovchi"), (3, "🔫 Ko'cha bezori"), (10, "🕶 Gangster"), (25, "💼 Kapo"),
         (50, "🎩 Konsilyere"), (100, "🤵‍♂️ Don"), (250, "👑 Krestniy ota")]


def rank(wins: int) -> str:
    return [title for need, title in RANKS if wins >= need][-1]
WINNER = {TOWN: "👨 Tinch aholi g'alaba qildi!", MAFIA: "🤵 Mafiya g'alaba qildi!",
          "qotil": "🔪 Qotil yakka g'alaba qildi!", "vampir": "🧛 Vampir yakka g'alaba qildi!",
          DRAW: "🤝 Durang!", "couple": "💞 Sevishganlar g'alaba qildi!"}


def mention(uid: int, name: str) -> str:
    """Bosilsa profil ochiladigan ism. PRO bo'lsa: [✅] PRO <nickname yoki ism>."""
    link = f'<a href="tg://user?id={uid}">{escape(pro.name(uid, name))}</a>'
    return f"{pro.badge()} <b>PRO</b> {link} {pro.tail()}" if pro.is_pro(uid) else link


def pm(g: Game, uid: int) -> str:
    """Bosilsa Telegram profili ochiladigan ism."""
    p = g.get(uid) if uid is not None else None
    return mention(p.uid, p.name) if p else "?"


def role(code: str) -> str:
    emoji, name = ROLES[code].name.split(" ", 1)
    return f"{emoji} {bold(name)}"


# ---------- lobby ----------
def lobby(members: list[tuple[int, str]], left: int) -> str:
    body = "\n".join(f"{i}. {mention(u, n)}" for i, (u, n) in enumerate(members, 1)) or "— hali hech kim yo'q —"
    return (f"🎮 <b>ADMIRAL MAFIA</b> — ro'yxatdan o'tish boshlandi!\n\n"
            f"👥 <b>O'yinchilar ({len(members)}):</b>\n{body}\n\n⏳ Qoldi: <b>{left}</b> soniya")


JOIN_BTN = "🤝 Qo'shilish"
COUPLE_JOIN_BTN = "❤️ Qo'shilish ❤️"
NO_COUPLE_JOIN = ("💔 <b>Sizda hozirda para yo'q.</b>\n\n"
                  "Paralar o'yiniga faqat juftlar qo'shiladi. Guruhda kimningdir xabariga javoban <b>/couple</b> "
                  "yozib, para bo'ling ❤️")
COUPLE_DROPPED = "💔 Jufti ro'yxatga yozilmagani uchun paralar o'yiniga kira olmadingiz. Keyingisida birga qo'shiling ❤️"
NEED_COUPLES = "💔 Paralar yetarli emas (kamida <b>2</b> para kerak).\n<b>O'yin bekor qilindi.</b>"
OTHER_LOBBY = "⚠️ Hozir boshqa o'yin ro'yxati ochiq. Avval u tugasin yoki admin /stop qilsin."
NOT_COUPLE_LOBBY = "⚠️ Ochiq ro'yxat oddiy o'yin uchun. Uni /begin bilan boshlang."


def couple_lobby(members: list[tuple[int, str]], partners: dict[int, int], left: int) -> str:
    """❤️ Ro'yxat: har para yangi qatorda, jufti kelmaganlar alohida."""
    names = dict(members)
    done, rows, waiting = set(), [], []
    for u, n in members:
        if u in done:
            continue
        p = partners.get(u)
        if p in names and partners.get(p) == u:
            done |= {u, p}
            rows.append(f"{len(rows) + 1}. ❤️ {mention(u, n)} + {mention(p, names[p])} ❤️")
        else:
            waiting.append(f"💔 {mention(u, n)} — jufti kutilmoqda")
    body = "\n".join(rows) or "— hali hech qaysi para yo'q —"
    wait = "\n\n" + "\n".join(waiting) if waiting else ""
    return ("❤️❤️ <b>PARALAR O'YINI</b> ❤️❤️\n<b>Ro'yxatdan o'tish boshlandi!</b>\n\n"
            f"❤️ <b>Paralar ({len(rows)}):</b>\n{body}{wait}\n\n⏳ Qoldi: <b>{left}</b> soniya")


def couple_dropped(dropped: list[tuple[int, str]]) -> str:
    return "💔 Jufti qo'shilmagani uchun chiqarildi: " + ", ".join(mention(u, n) for u, n in dropped)


def couple_started(g: Game) -> str:
    done, rows = set(), []
    for p in g.players:
        if p.uid in done:
            continue
        q = g.partner(p.uid)
        done |= {p.uid, q.uid}
        rows.append(f"{len(rows) + 1}. ❤️ {mention(p.uid, p.name)} + {mention(q.uid, q.name)} ❤️")
    return (f"❤️❤️ <b>PARALAR O'YINI BOSHLANDI!</b> ❤️❤️\n\n❤️ <b>Paralar ({len(rows)}):</b>\n" + "\n".join(rows)
            + "\n\n<i>Tinch aholi ham, mafiya ham yo'q — har kim o'z parasi uchun! Kim qo'lidan kelsa, otadi va osadi. "
              "Oxirgi tirik para g'olib bo'ladi 🏆</i>\n\n" + composition(g))


NEED_PLAYERS = "😔 O'yinchilar yetarli emas (kamida <b>4</b> kishi kerak).\n<b>O'yin bekor qilindi.</b>"
GAME_EXISTS = "⚠️ Bu guruhda o'yin allaqachon ketmoqda."
NOT_ADMIN_WARN = ("⚠️ Bot guruhda admin emas. O'yin bo'ladi, lekin tunda va o'liklarning xabarlarini "
                  "o'chira olmayman. Botni admin qiling (xabarlarni o'chirish huquqi bilan).")
JOINED = "✅ " + "𝐌𝐮𝐯𝐚𝐟𝐟𝐚𝐪𝐢𝐲𝐚𝐭𝐥𝐢 𝐫𝐨'𝐲𝐱𝐚𝐭𝐝𝐚𝐧 𝐨'𝐭𝐝𝐢𝐧𝐠𝐢𝐳!" + "\nGuruhga qayting va o'yin boshlanishini kuting."
ALREADY_IN_GAME = "⚠️ Siz allaqachon boshqa o'yindasiz."
NO_LOBBY = "⚠️ Bu guruhda ro'yxatdan o'tish ketmayapti."
LOBBY_FULL = ("⚠️ O'yin to'lgan (60 kishi). Sizni keyingi o'yin navbatiga yozdim — "
              "ro'yxat ochilishi bilan xabar beraman 🔔")
BANNED = "⛔️ Siz botdan foydalanishdan chetlatilgansiz."
LOBBY_LOST = "♻️ Bot yangilandi va ro'yxatdan o'tish bekor bo'ldi.\nYangi o'yin uchun /game ni qayta bosing."
GIVEAWAY_TTL_MIN = 60  # tarqatma shuncha daqiqadan keyin yopiladi


def giveaway_closed(text: str) -> str:
    return text + "\n\n⌛️ <b>Vaqt tugadi.</b> Olinmagan pul egasiga qaytarildi."


def giveaway_refund(amount: int) -> str:
    return f"↩️ Tarqatmangizdan olinmagan <b>{amount} 💵</b> hisobingizga qaytarildi."


STOPPED = "🛑 <b>O'yin to'xtatildi.</b>"
ONLY_ADMIN = "⚠️ Bu buyruq faqat guruh adminlari uchun."
def left_free(uid: int, name: str, n: int, limit: int) -> str:
    return (f"🚪 {mention(uid, name)} o'yindan chiqdi.\n"
            f"ℹ️ Bugungi chiqishlar: <b>{n}/{limit}</b>. "
            f"Limitdan keyin har bir chiqish <b>-{config.LEAVE_FINE} 💵</b>.")


def leave_warn(uid: int, name: str, limit: int) -> str:
    return (f"⚠️ {mention(uid, name)}, diqqat qiling!\n\n"
            f"Siz bugun o'yindan <b>{limit} marta</b> chiqdingiz.\n"
            f"Bu safar chiqsangiz, hisobingizdan <b>{config.LEAVE_FINE} 💵</b> yechiladi "
            "(pul yetmasa, balans minusga tushadi).\n\n"
            f"❗️ Hisobi <b>{config.DEBT_LIMIT} 💵</b> ga yetgan o'yinchi o'yinlarga qo'shila olmaydi.")


def left_fined(uid: int, name: str) -> str:
    return f"🚪 {mention(uid, name)} o'yindan chiqdi va <b>{config.LEAVE_FINE} 💵</b> jarima to'ladi."


def debt_block(dollars: int) -> str:
    return (f"⛔️ Hisobingiz: <b>{dollars} 💵</b>\n"
            f"Hisobi <b>{config.DEBT_LIMIT} 💵</b> yoki undan kam bo'lgan o'yinchilar o'yinga qo'shila olmaydi.\n\n"
            "Balansni to'ldirish uchun 🤝 do'stlaringizni taklif qiling.")


def leave_yes_btn() -> str:
    return f"🚪 Chiqish (-{config.LEAVE_FINE} 💵)"


LEAVE_NO_BTN = "🎮 O'yinni davom ettirish"
LEAVE_STAY = "🎮 O'yinda qoldingiz. Omad!"
NOT_YOUR_BTN = "❌ Bu tugma siz uchun emas"
ONLY_STARTER = "⚠️ O'yinni faqat guruh adminlari yoki /game bosgan odam boshlay oladi."
ONLY_STARTER_EXTEND = "⚠️ Ro'yxatni faqat guruh adminlari yoki /game bosgan odam uzaytira oladi."
EXTEND_MAX = "⏳ Ro'yxat allaqachon 10 daqiqaga uzaytirilgan — bundan ko'p bo'lmaydi."
GROUP_ONLY = "Bu buyruq guruhda ishlaydi."


def role_card(g: Game, uid: int) -> str:
    p = g.get(uid)
    text = f"Siz - {role(p.role)} siz!\n{ROLES[p.role].about}"
    mates = g.teammates(uid)
    if mates:
        text += "\n\n🤝 <b>Sheriklaringizni eslab qoling!</b>\n" + "\n".join(
            f"<b>{escape(dn(m))}</b> - {role(m.role)}" + ("" if m.alive else " 💀") for m in mates)
    if q := g.partner(uid):
        text += (f"\n\n💞 <b>Sizning juftingiz:</b> {escape(dn(q))} - {role(q.role)}" + ("" if q.alive else " 💀")
                 + "\n<i>U o'lsa, siz ham o'yindan chiqasiz. Unga yozish: xabarni <b>+</b> bilan boshlang.</i>")
    own = [f"{ITEMS[i]} ×{q}" for i, q in p.items.items() if q > 0 and i in ITEMS and not i.startswith("r_")]
    if own:
        text += "\n\n🎒 <b>Buyumlaringiz:</b> " + ", ".join(own)
    return text


ROLE_BTN = "🎭 Sizning rolingiz"
GAME_STARTED = "🎮 <b>O'YIN BOSHLANDI!</b>"
NOT_IN_GAME = "Siz bu o'yinda ishtirok etmayapsiz."


def role_alert(g: Game, uid: int) -> str:
    """Guruhdagi tugma uchun qalqib chiquvchi oyna: faqat o'z roli va vazifasi (sheriklar - botda).
    Oddiy matn, Telegram limiti 200 belgi."""
    p = g.get(uid)
    text = f"Siz - {ROLES[p.role].name} siz!\n{ROLES[p.role].about}"
    return text if len(text) <= 200 else text[:199] + "…"


def game_started(g: Game) -> str:
    return _game_started(g) + "\n\n" + composition(g)


def _game_started(g: Game) -> str:
    return choice([
        f"🎬 <b>O'yin boshlandi!</b> Shahar darvozalari yopildi — ichkarida {len(g.players)} kishi qoldi.\n"
        "Ulardan ba'zilari tinch fuqaro emas... 🤫 Rolingizni botdan bilib oling.",
        f"🎬 <b>Parda ochildi!</b> {len(g.players)} nafar o'yinchi, bitta shahar va ko'plab sirlar.\n"
        "Kim do'st, kim dushman — tez orada bilinadi. 🤫 Rolingiz botda.",
        f"🎬 <b>Admiral Mafia</b> shahriga xush kelibsiz! {len(g.players)} kishining taqdiri hal bo'ladi.\n"
        "Hech kimga ishonmang... 🤫 Rolingizni botning shaxsiy chatida ko'ring.",
    ])


# ---------- tun ----------
ROLE_PROMPT = {
    "don": "🤵🏻 Don, oila sizning buyrug'ingizni kutyapti. Bu tun kim yo'qoladi?",
    "mafiya": "🤵 Oila yig'ildi. Kimni nishonga olamiz? (Yakuniy so'z Donniki)",
    "komissar": "🕵️‍♂️ Komissar, shahar sizga umid bog'lagan. Tekshiramizmi yoki otamizmi?",
    "doktor": "👨‍⚕️ Doktor, chamadoningiz tayyor. Bu tun kimning hayotini saqlaysiz?",
    "kezuvchi": "💃 Kezuvchi, kimga uyqu dori berasiz? U bu tun hech narsa qila olmaydi va ertaga ovoz bera olmaydi.",
    "daydi": "🍾 Daydi, bu tun qaysi uy oldida tunaysiz? Qotillik bo'lsa, guvoh bo'lasiz.",
    "qorovul": "👨‍🦳 Qorovul, ertaga kimni dordan himoya qilasiz?",
    "ovchi": "🏹 Ovchi, miltiq o'qlangan. Iz olamizmi yoki o'q uzamizmi? Ehtiyot bo'ling — tinchga tegsa, jazo bor!",
    "jurnalist": "👩‍💻 Jurnalist, bu tun kimdan intervyu olamiz? Uning mehmonlarini ko'rasiz.",
    "yollanma": "🕴 Yollanma qotil, buyurtma bor. Kim?",
    "advokat": "👨‍💼 Advokat, qaysi mijozingizni bu tun himoya qilasiz?",
    "aka": "🧔 Aka, ukangiz bilan bir nishonni tanlang — shundagina zarba o'tadi.",
    "uka": "👦 Uka, akangiz bilan bir nishonni tanlang — shundagina zarba o'tadi.",
    "qotil": "🔪 Qotil, pichoq o'tkir. Bu tun kimning navbati?",
    "gazabkor": "🧟 G'azabkor, g'azab ichingizni yondiryapti. Kim qurbon bo'ladi?",
    "sehrgar": "🧙 Sehrgar, qaysi uyni la'natlaysiz?",
    "vampir": "🧛 Vampir, chanqoq kuchaydi. Kimning qonini ichamiz?",
    "qaroqchi": "🦹‍♂️ Qaroqchi, kimning cho'ntagini yengillatamiz?",
    "konchi": "👷‍♂️ Konchi, kirka tayyor. Qazishni boshlaymizmi?",
    "aferist": "🤹 Aferist, bu tun kimning harakatini o'g'irlaymiz?",
}


# Guruhdagi jonli lenta: kim harakat qilgani anonim, nishon ochilmaydi
ACT_FEED = {
    ("komissar", "check"): "{r} hujjatlarni tekshirishga ketdi...",
    ("komissar", "shoot"): "{r} pistoletini o'qladi...",
    ("ovchi", "check"): "{r} iz quvib o'rmonga kirdi...",
    ("ovchi", "shoot"): "{r} miltig'ini o'qladi...",
    ("gazabkor", "sacrifice"): "{r} o'zini olovga tashlashga tayyorlanmoqda...",
    "don": "{r} navbatdagi o'ljasini tanladi...",
    "mafiya": "{r} nishonga ishora qildi...",
    "doktor": "{r} tungi navbatchilikka chiqdi...",
    "daydi": "{r} kimningdir eshigi oldida tunab qoldi...",
    "kezuvchi": "{r}ning bu tun qandaydir mehmoni bor ekan...",
    "qorovul": "{r} tungi xizmatda...",
    "jurnalist": "{r} intervyu olishga ketdi...",
    "yollanma": "{r} buyurtmani qabul qildi...",
    "advokat": "{r} kimnidir himoya qilish uchun ketdi...",
    "aka": "{r} nishonni belgiladi...",
    "uka": "{r} nishonni belgiladi...",
    "qotil": "{r} navbatdagi qurbonini tanladi...",
    "gazabkor": "{r} qurbon izlab ketdi...",
    "sehrgar": "{r} kimnidir la'natlamoqda...",
    "vampir": "{r} qorong'ilikka uchib ketdi...",
    "qaroqchi": "{r} o'g'irlikka chiqdi...",
    "konchi": "{r} yer ostiga tushdi...",
    "aferist": "{r} yangi firibgarlik o'ylab topdi...",
}


SKIP_FEED = {
    "doktor": "{r} bugun dam olarkan...",
    "komissar": "{r} bu tun ishdan dam oldi...",
    "ovchi": "{r} bu tun ovga chiqmadi...",
    "kezuvchi": "{r} bu tun hech kimning oldiga bormadi...",
    "qorovul": "{r} bu tun postini tashlab, uxlab qoldi...",
    "daydi": "{r} bu tun ko'chaga chiqmadi...",
    "mafiya": "{r} bu tun ovoz bermadi...",
    "konchi": "{r} bu tun qazishga chiqmadi...",
    "gazabkor": "{r} bu tun g'azabini bosdi...",
}
SKIP_FEED_DEFAULT = "{r} bu tun dam olishga qaror qildi..."


def skip_feed(role_code: str) -> str | None:
    """"Hech narsa qilmayman" - guruhga. Don uchun yo'q: ertalab "Don hech kimni tanlamadi" chiqadi."""
    if role_code == "don":
        return None
    return SKIP_FEED.get(role_code, SKIP_FEED_DEFAULT).format(r=role(role_code))


RESULT = {  # (harakat, muvaffaqiyat) -> shaxsiy xabar; {t} - nishon
    ("heal", True): "💉 Siz {t}ga yordam bera oldingiz — uni o'limdan qutqarib qoldingiz!",
    ("heal", False): "💉 Siz {t}ni davoladingiz. Bu tun unga hech kim hujum qilmadi.",
    ("guard", True): "🛡 {t} sizning himoyangizda: ertaga uni osib bo'lmaydi.",
    ("block", True): "💤 {t}ga uyqu dori berdingiz: u bu tun hech narsa qila olmadi va ertaga ovoz bera olmaydi.",
    ("disguise", True): "🎭 {t}ni niqobladingiz: bu tun tekshiruvda u Tinch bo'lib ko'rinadi.",
    ("visit", False): "🍾 {t}ning uyi oldida tun tinch o'tdi — qotillik bo'lmadi.",
    ("pair", False): "👊 Sherigingiz boshqa nishonni tanladi — {t}ga hujum bo'lmadi.",
}
CHECKED_YOU = "🔍 Kimdir rolingizga juda ham qiziqdi..."
ATTACK_OK = "🎯 Nishoningiz {t} halok bo'ldi."
ATTACK_FAIL = "😤 {t} omon qoldi — kimdir uni himoya qildi yoki unga kuchingiz yetmadi."
ATTACKED_SAVED = "🩹 Tunda sizga hujum qilishdi, lekin omon qoldingiz!"
PATIENT = {True: "👨‍⚕️ Tunda sizga hujum qilishdi, lekin <b>Doktor</b> sizni qutqarib qoldi!",
           False: "👨‍⚕️ Tunda <b>Doktor</b> sizni ko'rgani keldi. Bu tun sizga hech kim hujum qilmadi."}


def act_feed(role_code: str, kind: str = "") -> str:
    t = ACT_FEED.get((role_code, kind)) or ACT_FEED.get(role_code) or "🌑 Kimdir tunda harakatga keldi..."
    return t.format(r=role(role_code))


def vote_feed(g: Game, voter: int, target: int | None) -> str:
    if target is None:
        return f"{pm(g, voter)} hech kimga ovoz bermadi"
    return f"{pm(g, voter)} - {pm(g, target)} ga ovoz berdi"


NIGHT_CAPTION = ("🌚🌃 <b>Tun</b>\nKo'chaga faqat jasur va qo'rqmas odamlar chiqishdi.\n"
                 "Ertalab tirik qolganlarni sanaymiz...")
DAY_CAPTION = "🌝 <b>Xayrli tong</b>\n🌄 <b>Kun</b>\nShamollar tundagi mish-mishlarni butun shaharga yetkazmoqda..."


def night_start(g: Game, secs: int) -> str:
    return NIGHT_CAPTION


def night_prompt(g: Game, uid: int) -> str:
    r = g.get(uid).role
    return f"🌙 <b>{g.day}-tun</b>\n\n" + ROLE_PROMPT.get(r, f"{role(r)}, harakatingizni tanlang:")


SKIP_NIGHT_BTN = "🚫 Hech narsa qilmayman"
SKIPPED_NIGHT = "😶 Siz bu tun hech narsa qilmaslikka qaror qildingiz"
DON_SKIPPED = "🤵🏻 Don bu tun hech kimga tegmaslikka qaror qildi."


def chosen(name: str | None) -> str:
    return f"Siz <b>{escape(name)}</b>ni tanladingiz" if name else "✅ Tanlovingiz qabul qilindi"


def mafia_voted(voter: str, target: str) -> str:
    return f"{escape(voter)} - {escape(target)} ga ovoz berdi"


USER_MARK = "\u2063"  # = emoji.USER: o'yinchi yozgan qism animatsion emoji'ga almashtirilmaydi
MAX_SAID = 500


def said(text: str, entities=None, skip: int = 0) -> str:
    """O'yinchi yozgan matn guruhga/boshqalarga: HTML-xavfsiz, premium (custom) emoji saqlanadi, boshqa formatlash yo'q.
    skip - boshidan tashlanadigan belgilar (masalan, juftga xabardagi "+")."""
    from aiogram.utils.text_decorations import html_decoration
    shift = len(text[:skip].encode("utf-16-le")) // 2  # Telegram ofsetlari UTF-16 birliklarida
    text = text[skip:]
    ents = [e.model_copy(update={"offset": e.offset - shift}) for e in entities or ()
            if e.type == "custom_emoji" and e.offset >= shift]
    if len(text) > MAX_SAID:  # kesilsa ofsetlar buziladi - oddiy matn
        text, ents = text[:MAX_SAID], []
    return USER_MARK + (html_decoration.unparse(text, ents) if ents else escape(text)) + USER_MARK


def relay(name: str, text: str) -> str:
    """text - said() natijasi."""
    return f"<b>{escape(name)}</b>:\n{text}"


def overheard(text: str) -> str:
    return f"👂 <i>Devor ortidan pichirlash eshitildi:</i> {text}"


LAST_WORDS_SECS = 60


LAST_WORDS_LATE = f"⌛️ Kechikdingiz — so'nggi so'z uchun {LAST_WORDS_SECS} soniya tugadi. Xabaringiz hech kimga yuborilmadi."
LAST_WORDS_SENT = "✅ <b>So'nggi so'zingiz guruhga yetkazildi.</b>"
LAST_WORDS_TIMEOUT = "⌛️ So'nggi so'z vaqti tugadi — siz hech narsa yozmadingiz."


def victims(ev: list[Event]) -> list[int]:
    """Hodisalardan halok bo'lganlar (so'nggi so'z uchun). AFK va chiqib ketganlar kirmaydi."""
    out = []
    for e in ev:
        uid = {"killed": e.target, "hanged": e.target, "revenge": e.target, "linked": e.target,
               "tulki": e.target, "heartbreak": e.target}.get(e.kind)
        if uid is not None and uid not in out:
            out.append(uid)
    return out


def last_words(g: Game, uid: int, text: str) -> str:
    return f"🕯 O'limidan oldin kimdir <b>{nm(g, uid)}</b> ning qichqirganini eshitdi:\n<i>{text}</i>"


SAVED = ["💉 Kimdir bu tun o'lim yoqasidan qaytdi! Ajal bu safar quruq ketdi.",
         "💉 Tunda kimgadir hujum bo'ldi... lekin u omon qoldi! Shaharda qahramonlar bor.",
         "💉 Qotil bu tun omadsiz chiqdi — qurboni tirik qoldi!"]
QUIET = ["🌤 Mo'jiza! Bu tun hech kim halok bo'lmadi. Lekin bu uzoq davom etmaydi...",
         "🌤 Tinch tun. Hamma tirik... hozircha.",
         "🌤 Hech kim o'lmadi. Mafiya nimanidir rejalashtiryaptimi?"]


def morning(g: Game, ev: list[Event]) -> tuple[list[str], list[tuple[int, str]]]:
    """([guruhga alohida xabarlar], [(uid, shaxsiy matn)])"""
    pub, priv = [], []
    n = lambda uid: pm(g, uid)  # ismlar bosilsa Telegram profili ochiladi
    healed = {e.target for e in ev if e.kind == "result" and e.data["kind"] == "heal" and e.data["ok"]}
    w = lambda uid: who(g, uid)
    for e in ev:
        k = e.kind
        if k == "killed":
            # rollar tun boshidagi holatda (masalan, jarimadan oldingi Ovchi)
            victim = f"{shown_role(g, e.target, e.data.get('role'))} - <b>{n(e.target)}</b>"
            if e.data["by"] == ["curse"]:
                pub.append(f"🔮 {victim} la'natlangan insonga duch keldi va shafqatsiz o'lim topdi.\n"
                           f"Aytishlaricha, bu ishni {role('sehrgar')} qilgan")
            else:
                codes = e.data.get("killer_roles") or [g.get(u).role for u in e.data.get("killers", [])]
                killers = ", ".join(role(c) for c in dict.fromkeys(codes)) or "noma'lum kimdir"
                pub.append(f"Tunda {victim}...\n{choice(VERBS)}\nAytishlaricha unikiga {killers} kelgan")
        elif k == "saved":
            pub.append(choice(SAVED))
            if e.target not in healed:  # Doktor qutqargan bo'lsa - unga alohida (PATIENT)
                priv.append((e.target, ATTACKED_SAVED))
        elif k == "result":
            t = RESULT.get((e.data["kind"], e.data["ok"])) or (ATTACK_OK if e.data["ok"] else ATTACK_FAIL)
            priv.append((e.uid, t.format(t=f"<b>{n(e.target)}</b>")))
            if e.data["kind"] == "heal" and e.target != e.uid:  # bemorga ham
                priv.append((e.target, PATIENT[e.data["ok"]]))
        elif k == "mafia_idle":
            pub.append(f"🤵 Mafialar kelisha olishmadi va {role('don')} hech kimni tanlamadi!\n"
                       "Mafiya bu tun hech kimga tegmadi..")
        elif k == "mafia_result":
            text = (f"Mafiyaning ovoz berish jarayonida <b>{n(e.target)}</b> vahshiylarcha o'ldirildi."
                    if e.data["killed"] else f"Mafiyaning nishoni <b>{n(e.target)}</b> bu tun omon qoldi...")
            priv += [(p.uid, text) for p in g.players if p.alive and p.team == MAFIA]
        elif k == "revenge":
            pub.append(f"💥 {w(e.uid)} yolg'iz ketmadi — {w(e.target)} ham u bilan birga halok bo'ldi!")
        elif k == "heartbreak":
            pub.append(f"💔 {w(e.target)} juftidan — <b>{n(e.uid)}</b>dan ayrilib, u bilan birga o'yinni tark etdi...")
        elif k == "linked":
            pub.append(f"💔 {w(e.target)} jigaridan ayrilib, qayg'udan jon berdi...")
        elif k == "sacrificed":
            pub.append(f"🔥 {w(e.uid)} o'zini olovga tashladi va o'z g'alabasiga erishdi!")
        elif k == "afk":
            pub.append(f"😴 Aholidan kimdir {w(e.target)} o'limidan oldin:\n"
                       "<i>«Men o'yin paytida boshqa uxlamayma-a-a-a-an!»</i> deb qichqirganini eshitgan.")
        elif k == "left":
            pub.append(f"🚪 {w(e.target)} shaharni tashlab qochdi...")
        elif k == "hanged":
            score = (f"📊 <b>Tasdiqlash natijalari:</b>\n{e.data['yes']} 👍 | {e.data['no']} 👎\n\n"
                     if "yes" in e.data else "")
            pub.append(score + f"<b>{pm(g, e.target)}</b> kunduzgi yig'ilishda osildi!\nU {shown_role(g, e.target, e.data['role'])} edi..")
        elif k == "vote_saved":
            pub.append(f"⚖️ Arqon tortilay deganda <b>{pm(g, e.target)}</b> {ITEMS['votesave']}ni ko'rsatdi "
                       "va dordan omon qoldi!")
        elif k == "spared":
            pub.append(f"📊 <b>Tasdiqlash natijalari:</b>\n{e.data['yes']} 👍 | {e.data['no']} 👎\n\n"
                       f"Aholi <b>{pm(g, e.target)}</b>ni osishga rozi bo'lmadi... Bu safar u omon qoldi.")
        elif k == "no_hang":
            pub.append(choice(["<b>Ovoz berish yakunlandi:</b>\nAholi kelisha olmadi... Shu sababli bugun hech kim osilmadi...",
                               "<b>Ovoz berish yakunlandi:</b>\nFikrlar ikkiga bo'lindi... Dor bugun bo'sh qoldi..."]))
        elif k == "guard_saved":
            pub.append(f"👨‍🦳 Arqon tortilay deganda {role('qorovul')} yetib keldi va <b>{pm(g, e.target)}</b>ni "
                       "dordan qutqarib qoldi!")
        elif k == "tulki":
            pub.append(f"🦊 {w(e.uid)} ayyorlik qildi: unga birinchi ovoz bergan {w(e.target)} ham u bilan ketdi!")
        elif k == "blocked":
            priv.append((e.uid, "💤 Boshingiz aylanib, ko'zingiz yumildi... Kimdir sizga uyqu dori berdi. "
                                "Bu tun hech narsa qila olmadingiz, ertaga esa <b>ovoz bera olmaysiz</b>."))
        elif k == "stolen":
            priv.append((e.target, "🤹 Kimdir sizning tungi rejangizni o'g'irlab ketdi!"))
            priv.append((e.uid, f"🤹 Ajoyib fokus! {n(e.target)}ning harakatini o'zlashtirdingiz."))
        elif k == "saw_role":
            priv.append((e.uid, f"🤹 {n(e.target)}da o'g'irlaydigan harakat yo'q edi, lekin uning sirini bildingiz: "
                                f"{role(e.data['role'])}"))
        elif k == "checked":
            text = f"🔍 Tekshiruv natijasi: {n(e.target)} — {role(e.data['result'])}"
            priv.append((e.uid, text))
            priv.append((e.target, CHECKED_YOU))  # kim tekshirgani aytilmaydi
            if g.get(e.uid).role == "komissar" and (s := g.by_role("serjant")):
                priv.append((s.uid, f"🕵️‍♂️ Komissardan xabar: {text}"))
        elif k == "interview":
            vis = ", ".join(n(v) for v in e.data["visitors"]) or "hech kim"
            priv.append((e.uid, f"🎤 Intervyu tayyor! Bu tun {n(e.target)}ning oldiga kelganlar: {vis}"))
        elif k == "witness":
            priv.append((e.uid, f"👀 Siz {n(e.target)}ning uyi oldida qotillikni o'z ko'zingiz bilan ko'rdingiz!\n"
                                "Qotil(lar): " + ", ".join(f"<b>{n(x)}</b>" for x in e.data["killers"])))
        elif k == "dug":
            d, gems = e.data["dollars"], e.data["diamonds"]
            extra = f" va <b>{gems} 💎</b> olmos" if gems else ""
            head = ("💎 <b>Olmos koni!</b> " if gems >= 2 else "") + ("💰 <b>Oltin tomir!</b> " if d > 500 else "")
            priv.append((e.uid, f"{head}⛏ Tunnel qazib <b>{d} 💵</b>{extra} topdingiz!"))
            pub.append(f"{role('konchi')} bugun tunda <b>{d} 💵</b> dollar{extra} topdi!")
        elif k == "item_used":
            used = ("tekshiruvda «Tinch aholi» bo'lib ko'rindingiz" if e.data["item"] == "doc"
                    else ITEM_ABOUT[e.data["item"]])
            priv.append((e.uid, f"{ITEMS[e.data['item']]} sizni qutqardi: {used}."))
        elif k == "robbed":
            what = {"dollars": f"💵 {e.data.get('amount', 0)} dollar", "vote": "🗳 ertangi ovoz huquqi",
                    "item": ITEMS.get(e.data.get("item"), "")}[e.data["what"]]
            priv.append((e.target, f"🦹‍♂️ Ertalab cho'ntagingiz yengil tuyuldi... Qaroqchi o'g'irladi: {what}"))
            priv.append((e.uid, f"🦹‍♂️ Muvaffaqiyatli o'lja! {n(e.target)}dan: {what}"))
        elif k == "transformed":
            new = e.data["role"]
            done = "serjantga aylandi" if new == "serjant" else "mafiyaga qo'shildi"
            pub.append(f"{ROLES['voris'].name.split(' ')[0]}➡️{ROLES[new].name.split(' ')[0]} {bold('Voris')} {done}")
            priv.append((e.uid, f"🧬 O'lim yoqasida taqdiringiz o'zgardi! Siz endi {role(new)}siz!\n\n"
                                + role_card(g, e.uid)))
            for m in g.teammates(e.uid):
                if m.alive:
                    priv.append((m.uid, f"👥 {n(e.uid)} sizning safingizga qo'shildi!"))
        elif k == "promoted":
            priv.append((e.uid, f"⭐️ Yuksalish! Siz endi {role(e.data['role'])}siz!\n\n" + role_card(g, e.uid)))
        elif k == "penalty":
            priv.append((e.uid, "🏹 O'qingiz begunoh odamga tegdi! Vijdon azobi sizni qurolsiz qoldirdi."))
    return pub, priv


def day_start(g: Game, secs: int) -> str:
    """Kunduzgi GIF'dan keyingi xabar: tiriklar, tarkib, muhokama vaqti."""
    return (f"☀️ <b>{g.day}-kun</b>\n\n{alive_list(g)}\n\n{alive_composition(g)}\n\n"
            f"🗣 Muhokama uchun <b>{secs}</b> sekund")


def vote_prompt(g: Game, secs: int) -> str:
    return (f"⚖️ <b>Aybdorlarni aniqlash va jazolash vaqti keldi!</b>\n"
            f"Ovoz berish uchun <b>{secs}</b> sekund\nOvoz berish uchun botga o'ting!")


SKIP_BTN = "🤐 Hech kimga ovoz bermayman"


def confirm_prompt(g: Game, secs: int) -> str:
    return (f"Rostdan ham <b>{pm(g, g.candidate)}</b> ni osishni hohlaysizmi?\n\n"
            f"⏰ Tasdiqlash uchun vaqt: <b>{secs}</b> sekund")


def confirm_pm(g: Game) -> str:
    return f"🪢 <b>{pm(g, g.candidate)}</b> ni osamizmi?\nTanlang:"


def confirm_result(g: Game) -> str:
    yes, no = g.confirm_tally()
    return f"Rostdan ham <b>{pm(g, g.candidate)}</b> ni osishni hohlaysizmi?\n\n<b>{yes} 👍 | {no} 👎</b> — vaqt tugadi"


def partner_msg(name: str, text: str) -> str:
    return f"💞 <b>{escape(name)}</b> (juftingiz): {text}"


PARTNER_SENT = "💞 Juftingizga yuborildi."
NO_PARTNER = "💔 Sizda tirik juft yo'q."



def ghost(name: str, text: str) -> str:
    return f"👻 <b>{escape(name)}</b> (narigi dunyodan): {text}"


def players(g: Game) -> str:
    dead = "\n".join(f"💀 {who(g, p.uid)}" for p in g.players if not p.alive)
    return (f"{alive_list(g)}\n\n{alive_composition(g)}"
            + (f"\n\n☠️ <b>Halok bo'lganlar:</b>\n{dead}" if dead else ""))


def transfer_done(sender: str, sender_id: int, target: str, target_id: int, amount: int) -> str:
    return f"💸 {mention(sender_id, sender)} → {mention(target_id, target)}: <b>{amount} 💵</b>"


GIVEAWAY_SHOW = 60  # ro'yxatda ko'rsatiladigan olganlar (xabar 4096 belgidan oshmasin)


def giveaway(sender: str, sender_id: int, per: int, parts: int, takers: list[tuple[int, str]] = ()) -> str:
    """takers: [(uid, ism)] olish tartibida."""
    text = f"{mention(sender_id, sender)} <b>{per * parts}</b> 💵 ulashmoqda!"
    if takers:
        lines = [f"{i}. {mention(uid, name)} - {per}💵" for i, (uid, name) in enumerate(takers[:GIVEAWAY_SHOW], 1)]
        if len(takers) > GIVEAWAY_SHOW:
            lines.append(f"... va yana {len(takers) - GIVEAWAY_SHOW} kishi")
        text += "\n\n<b>Sovg'a olganlar:</b>\n\n" + "\n".join(lines)
    return text


GIVEAWAY_BTN = "💰 Olish"
GIVEAWAY_GOT = "🎉 +{} 💵 oldingiz!"
GIVEAWAY_NO = "😔 Tugagan yoki siz allaqachon olgansiz"


# ---------- para ----------
COUPLE_HOW = "❌ Reply qilib yoki /couple @username yozing."
COUPLE_NOT_FOUND = "❌ Bu foydalanuvchi topilmadi. U avval botga /start yozgan bo'lishi kerak yoki reply qiling."
COUPLE_SELF = "❌ O'zingizga para bo'lolmaysiz 🙂"
COUPLE_YOU_TAKEN = "❌ Sizda allaqachon para bor. Avval /uncouple qiling."
COUPLE_THEY_TAKEN = "❌ Bu foydalanuvchining allaqachon parasi bor."
COUPLE_NOT_YOU = "❌ Bu so'rov siz uchun emas"
COUPLE_FAILED = "❌ Bo'lmadi: kimdir allaqachon para bo'lib ulgurdi."
COUPLE_NONE = "💔 Sizda para yo'q. /couple bilan taklif qiling."


def couple_request(a: int, a_name: str, b: int, b_name: str) -> str:
    return (f"💌 {mention(b, b_name)}, diqqat qiling!\n"
            f"{mention(a, a_name)} sizga para bo'lish so'rovini yubormoqda")


def couple_rejected(b: int, b_name: str) -> str:
    return f"❌ {mention(b, b_name)} taklifni rad etdi."


def couple_made(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"❤️ {mention(a, a_name)} va {mention(b, b_name)} endi para!"


def couple_broken(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"💔 {mention(a, a_name)} va {mention(b, b_name)} parasi bekor qilindi."


def couple_show(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"❤️ {mention(a, a_name)} ❤️ {mention(b, b_name)}"


NO_GAME ="🎮 Hozir o'yinda emassiz. Guruhda /game bilan boshlang!"


WINNER_STORY = {
    TOWN: "Shahar ozod! Oxirgi mafiyachi ham qo'lga olindi. Ko'chalarda bayram! 🎊",
    MAFIA: "Shahar endi Mafiya qo'lida. Don sigarasini tutatib, jilmaydi... 🚬",
    "qotil": "Shahar huvullab qoldi. Faqat Qotil qon izlarini artib, yo'lida davom etdi... 🔪",
    "vampir": "Tun abadiy bo'ldi. Vampir taxtga o'tirdi... 🦇",
    DRAW: "Hech kim g'olib bo'lmadi. Shahar xarobaga aylandi... 🌫",
    "couple": "Shaharda faqat ikki yurak qoldi. Ular qo'l ushlashib, tongni birga kutib olishdi... 💞",
}


def game_over(g: Game, minutes: int | None = None) -> str:
    order = sorted(g.players, key=lambda p: (-p.score, not p.alive))  # yashirin hissa balli bo'yicha (ko'rsatilmaydi)
    won = [p for p in order if p.won]
    rest = [p for p in order if not p.won]
    lines = ["🏁 <b>O'yin tugadi!</b>"]
    if g.winner in WINNER:  # qaysi tomon yutgani
        lines += [f"<b>{WINNER[g.winner]}</b>", f"<i>{WINNER_STORY[g.winner]}</i>"]
    lines += ["", "🏆 <b>G'oliblar:</b>"]
    lines += [f"    {i}. {pm(g, p.uid)} - {role(p.role)}" for i, p in enumerate(won, 1)] or ["    —"]
    if rest:
        lines += ["", "<b>Qolgan o'yinchilar:</b>"]
        lines += [f"    {i}. {pm(g, p.uid)} - {role(p.role)}" for i, p in enumerate(rest, len(won) + 1)]
    if minutes is not None:
        lines += ["", f"⏱ O'yin <b>{minutes}</b> minut davom etdi"]
    return "\n".join(lines)


def result_pm(won: bool, reward: int, u=None, inv=()) -> str:
    head = (f"🎉 <b>Siz g'alaba qozondingiz!</b>\nYutganingiz uchun sizga <b>{reward} 💵</b> berildi" if won
            else "😔 <b>O'yin tugadi!</b>\nBu safar yutqazdingiz." + (f" Ishtirok uchun <b>{reward} 💵</b>" if reward else ""))
    return head + ("\n\n" + profile_card(u, inv) if u else "")


NEXT_OK = "🔔 Bu guruhda keyingi o'yin boshlanganda sizga xabar beraman."


def next_game(title: str) -> str:
    return f"🎮 <b>{escape(title)}</b> guruhida yangi o'yin boshlandi! Qo'shilish uchun tugmani bosing 👇"


# ---------- PM: profil, do'kon ----------
def welcome() -> str:
    return ("👋 <b>Salom! Mafiya olamiga xush kelibsan!</b>\n"
            "<b>Men 🤵 Admiral Mafia o'yinining rasmiy botiman.</b>\n\n"
            "<b>Bu shunchaki o'yin emas — sirlar, hiyla va ishonch dunyosi.</b>\n"
            "<b>Guruhga qo'sh, rolingni ol, o'zingni ko'rsat!</b> 🎯\n"
            "🎭 <b>Seni roling kutmoqda...</b>")


def start_pm() -> str:
    return ("🎮 <b>ADMIRAL MAFIA</b> ga xush kelibsiz!\n\n"
            "<b>Qanday boshlash kerak:</b>\n"
            "1️⃣ Meni guruhingizga qo'shing\n"
            "2️⃣ Admin qiling (xabarlarni o'chirish huquqi bilan)\n"
            "3️⃣ Guruhda /game yozing\n\n"
            "<b>Buyruqlar:</b>\n"
            "👤 /profile — profil va buyumlar\n"
            "🛒 /shop — do'kon\n"
            "🏆 /top — reyting\n"
            "🎭 /rules — rollar")


# ---------- PRO ----------
def pay_support() -> str:
    admins = ", ".join(mention(a, "admin") for a in sorted(config.ADMIN_IDS)) or "bot adminiga"
    return ("💳 <b>To'lov bo'yicha yordam</b>\n\n"
            "PRO to'lovi bilan muammo bo'lsa (pul yechildi, lekin PRO yoqilmadi va hokazo), "
            f"to'lov chekining skrinshoti bilan yozing: {admins}.\n"
            "Hal qilinmasa, ⭐ Stars to'liq qaytariladi.")


PAY_REFUNDED = ("⚠️ Texnik xato tufayli xarid amalga oshmadi — <b>⭐ Stars to'liq qaytarildi</b>.\n"
                "Birozdan keyin qaytadan urinib ko'ring.")
PAY_FAILED = "⚠️ To'lovda texnik xato bo'ldi. /paysupport orqali adminga yozing — muammo hal qilinadi."

PRO_BTN = "PRO akkaunt"  # tugmada PRO belgisi ikonka bo'lib turadi
PRO_NO_DIAMONDS = "😔 Olmos yetarli emas. Olmos Konchi qazishidan chiqadi — yoki ⭐ Stars bilan oling."
NICK_ONLY_PRO = "🏷 Nickname faqat PRO foydalanuvchilar uchun. /pro"
NICK_CLEARED = "✅ Nickname o'chirildi. O'yinlarda Telegram ismingiz ko'rinadi."
NICK_HOW = "🏷 Nickname qo'yish: <code>/nickname Laqabingiz</code>\nO'chirish: <code>/nickname</code>"
PRO_EXPIRING = (f"⏳ PRO muddatingiz <b>24 soat ichida</b> tugaydi.\n"
                "Belgi, chegirma va boshqa imkoniyatlar saqlanib qolishi uchun /pro orqali uzaytiring.")


def _pro_date(t) -> str:
    return f"{t + PRO_TZ:%d.%m.%Y}"


def pro_info(uid: int) -> str:
    end = pro.until(uid)
    have = (f"\n\n{pro.badge()} Sizda PRO bor: <b>{_pro_date(end)}</b> gacha.\n"
            "<i>Yana sotib olsangiz, muddat ustiga qo'shiladi.</i>") if end else ""
    win = config.REWARD_WIN
    return (f"{pro.badge()} <b>PRO AKKAUNT</b>\n\n"
            "<b>PRO</b> sizga quyidagilarni beradi:\n\n"
            f"{pro.badge()} <b>PRO belgisi</b> — ismingiz yonida, hamma ko'radi\n"
            "🏷 <b>Nickname</b> — o'yinlarda o'z laqabingiz (/nickname)\n"
            "💬 <b>Kunduzi yozish</b> — o'yinda bo'lmasangiz ham muhokamaga qo'shiling\n"
            f"💵 <b>G'alaba puli x1.5</b> — {win} o'rniga {win * 3 // 2} 💵\n"
            "🛒 <b>Do'konda -25%</b> chegirma\n"
            f"🚪 <b>Kuniga 5 ta</b> bepul chiqish (oddiylarga {config.LEAVE_FREE} ta)\n"
            "✨ <b>Maxsus profil</b> — PRO sarlavha va muddat"
            f"{have}\n\n🛒 <b>Sotib olish usulini tanlang:</b>")


def pro_done(end) -> str:
    return (f"🎉 {pro.badge()} <b>PRO faollashdi!</b>\nMuddat: <b>{_pro_date(end)}</b> gacha.\n\n"
            "🏷 Laqab qo'yish: /nickname")


def nick_set(nick: str) -> str:
    return f"✅ Nickname: <b>{escape(nick)}</b>\nEndi o'yinlarda shu ism ko'rinadi."


INVITE_BTN = "🤝 Do'stni taklif qilish"
BACK_BTN = "⬅️ Orqaga"
INVITE_TEXT = "🎭 Admiral Mafia — Telegramdagi mafiya o'yini! Men bilan o'yna 👇"


def profile(u, inv) -> str:
    return (profile_card(u, inv)
            + "\n\n<i>🟢 ON bo'lgan buyumlar o'yinda o'zi ishlatiladi</i>"
            + f"\n\n🤝 Har bir taklif qilingan do'st uchun <b>+{config.REF_BONUS} 💵</b>"
              f"\n<i>(do'stingiz {config.REF_GAMES} ta o'yin o'ynagach beriladi)</i>")


def ref_joined(name: str) -> str:
    return (f"🤝 <b>{escape(name)}</b> sizning taklifingiz bilan qo'shildi!\n"
            f"U <b>{config.REF_GAMES} ta</b> o'yin o'ynagach, sizga <b>+{config.REF_BONUS} 💵</b> beriladi.")


def ref_bonus(name: str) -> str:
    return (f"🎉 <b>{escape(name)}</b> {config.REF_GAMES} ta o'yin o'ynadi!\n"
            f"Taklif uchun hisobingizga <b>+{config.REF_BONUS} 💵</b> tushdi.")


def send_locked(games: int) -> str:
    return (f"🔒 Pul o'tkazish va tarqatish <b>{config.SEND_GAMES} ta</b> o'yindan keyin ochiladi.\n"
            f"Siz hozircha <b>{games} ta</b> o'yin o'ynagansiz.")


def claim_locked() -> str:
    return f"🔒 Tarqatmadan olish uchun kamida {config.CLAIM_GAMES} ta o'yin o'ynagan bo'lishingiz kerak"


def shop(dollars: int, uid: int | None = None, diamonds: int | None = None) -> str:
    on = uid is not None and pro.is_pro(uid)

    def cost(i: str, p: int) -> str:
        return f"<s>{p}</s> <b>{pro.price(uid, p)} 💵</b>" if on else f"<b>{p} 💵</b>"
    rows = [f"<b>{ITEMS[i]}</b> — {cost(i, p)}\n<i>{ITEM_ABOUT[i]}</i>"
            for i, p in config.SHOP.items() if i not in config.SHOP_OFF]
    rows += [f"<b>{ITEMS[i]}</b> — <b>{p} 💎</b>\n<i>{ITEM_ABOUT[i]}</i>" for i, p in config.SHOP_GEMS.items()]
    rows.append(f"<b>{ROLE_SHOP_BTN}</b> — 💎\n<i>keyingi o'yinda o'zingiz tanlagan rol bilan o'ynaysiz</i>")
    sale = f"\n{pro.badge()} <b>PRO chegirmasi: -25%</b> <i>(dollarli buyumlarga)</i>" if on else ""
    gems = f" · <b>{diamonds} 💎</b>" if diamonds is not None else ""
    return f"🛒 <b>Do'kon</b>\n\n💰 Balans: <b>{dollars} 💵</b>{gems}{sale}\n\n" + "\n\n".join(rows)


ROLE_SHOP_BTN = "🃏 Rolni tanlab olish"


def roles_shop(diamonds: int) -> str:
    rows = "\n".join(f"{role(c)} — <b>{p} 💎</b>" for c, p in config.ROLE_PICKS.items())
    return (f"🃏 <b>Rolni tanlab olish</b>\n\n💎 Balans: <b>{diamonds}</b>\n\n{rows}\n\n"
            f"<i>{ITEM_ABOUT['r_don']}. Profilda 🔴 OFF qilsangiz, saqlanib turadi.</i>")


BOUGHT = "✅ Sotib olindi!"
NO_MONEY = "😔 Pul yetarli emas."


# ---------- hamyon (profil menyusi) ----------
BUY_BTN, GEM_BTN, PAY_BTN, GIFT_BTN = "💵 Xarid", "💎 Olmos", "💵 Pul yuborish", "💎 Olmos yuborish"
GROUPS_BTN, NEWS_BTN, SHOP_BTN = "🏆 Top guruhlar", "📰 Yangiliklar", "🛒 Do'kon"
SELF_BTN, OTHER_BTN = "🙋 O'zim uchun", "🎁 Birov uchun"
BUY_DOLLARS = "💵 <b>Dollar sotib olish uchun variantni tanlang:</b>"
GEM_WHO = "💎 <b>Olmos sotib olish</b>\n\nKimga sotib olmoqchisiz?"
ASK_TO = ("🎁 <b>Kimga olmos sovg'a qilasiz?</b>\n\n<b>@username</b> yoki <b>Telegram ID</b> yuboring.\n"
          "<i>U botga kamida bir marta /start bosgan bo'lishi kerak.</i>")
NO_DIAMONDS = "😔 Olmos yetarli emas."
DIAMONDS_OFF = "🚧 Bu tizim hali ishlamayapti. Tez orada ishga tushadi!"
WALLET_NO_USER = "😔 Bunday foydalanuvchi topilmadi. U botga /start bosgan bo'lishi kerak."
WALLET_FORMAT = "❌ Format: <code>@username 100</code> yoki <code>123456789 100</code>. Menyudan qaytadan urinib ko'ring."
WALLET_SELF = "❌ O'zingizga yuborib bo'lmaydi."


def stars_menu(target: str | None = None) -> str:
    return "⭐ <b>STARS ORQALI TO'LOV</b>" + (f"\n\n🎁 Sovg'a: {target}" if target else "")


def ask_send(currency: str) -> str:
    what = "💵 Pul" if currency == "dollars" else "💎 Olmos"
    return (f"{what} <b>yuborish</b>\n\nKimga va qancha? Masalan:\n"
            "<code>@username 100</code> yoki <code>123456789 100</code>")


def _cur(currency: str) -> str:
    return "💵" if currency == "dollars" else "💎"


def sent_ok(target: str, n: int, currency: str) -> str:
    return f"✅ {target} ga <b>{n} {_cur(currency)}</b> yuborildi."


def got_money(sender: str, n: int, currency: str) -> str:
    return f"🎁 {sender} sizga <b>{n} {_cur(currency)}</b> yubordi!"


def dollars_bought(diamonds: int, dollars: int) -> str:
    return f"✅ {diamonds} 💎 → {dollars} 💵"


def diamonds_paid(n: int, target: str | None = None) -> str:
    return f"🎉 {target} ga <b>{n} 💎</b> sovg'a qilindi!" if target else f"🎉 Hisobingizga <b>{n} 💎</b> qo'shildi!"


def top_groups(rows) -> str:
    if not rows:
        return "🏆 <b>Top guruhlar</b>\n\n— hali o'yinlar yo'q —"
    medals = ["🥇", "🥈", "🥉"]
    body = "\n".join(f"{medals[i] if i < 3 else f'{i + 1}.'} <b>{escape(t)}</b> — {n} 🎮" for i, (t, n) in enumerate(rows))
    return f"🏆 <b>Top guruhlar</b>\n\n{body}"


def top(rows, title: str) -> str:
    if not rows:
        return f"🏆 <b>{title}</b>\n\n— hali o'yinlar yo'q —"
    medals = ["🥇", "🥈", "🥉"]
    body = "\n".join(f"{medals[i] if i < 3 else f'{i + 1}.'} {mention(uid, name or '?')} — {w} 🏆 / {gm} 🎮 · {rank(w or 0)}"
                     for i, (uid, name, w, gm) in enumerate(rows))
    return f"🏆 <b>{title}</b>\n\n{body}"


def rules() -> str:
    out = ["📜 <b>ADMIRAL MAFIA rollari</b>"]
    for team in (TOWN, MAFIA, NEUTRAL):
        out.append(f"\n<b>{TEAM[team]}</b>")
        out += [f"{role(c)} — {r.about}" for c, r in ROLES.items() if r.team == team]
    return "\n".join(out)


_BOLD = {**{chr(65 + i): chr(0x1D400 + i) for i in range(26)}, **{chr(97 + i): chr(0x1D41A + i) for i in range(26)}}


def bold(s: str) -> str:
    """𝐊𝐨𝐦𝐢𝐬𝐬𝐚𝐫 uslubidagi qalin harflar (matematik bold)."""
    return "".join(_BOLD.get(c, c) for c in s)


def nm(g: Game, uid: int) -> str:
    p = g.get(uid) if uid is not None else None
    return escape(dn(p)) if p else "?"  # o'yinchi chiqib ketgan bo'lsa ham xabar yiqilmasin


def dn(p) -> str:
    """O'yinchining ko'rsatiladigan ismi (oddiy matn): PRO nickname shu paytdagi holat bo'yicha."""
    return pro.name(p.uid, p.name)


def who(g: Game, uid: int) -> str:
    return f"{shown_role(g, uid)} - {pm(g, uid)}"


VERBS = ["vahshiylarcha o'ldirildi.", "shafqatsizlarcha o'ldirildi.", "tongni ko'ra olmadi."]


def alive_composition(g: Game) -> str:
    out = []
    masked = [p for p in g.alive() if p.items.get("mask", 0) > 0]
    for team, label in ((MAFIA, "🤵🏻 Mafiya"), (NEUTRAL, "👤 Yakka rollar"), (TOWN, "🏘 Tinch aholilar")):
        ps = [p for p in g.alive() if p.team == team and p not in masked]
        if not ps:
            continue
        counts: dict[str, int] = {}
        for p in ps:
            counts[p.role] = counts.get(p.role, 0) + 1
        roles = ", ".join(role(c) + (f" - {k}" if k > 1 else "") for c, k in counts.items())
        out.append(f"<b>{label} - {len(ps)}</b>\n{roles}")
    if masked:  # jamoasi ham ko'rinmaydi
        out.append(f"<b>{MASKED} - {len(masked)}</b>")
    return "\n\n".join(out) + f"\n\n<b>Jami: {len(g.alive())}</b>"


def alive_list(g: Game) -> str:
    return "<b>Tirik o'yinchilar:</b>\n" + "\n".join(
        f"{g.num(p.uid)}. {mention(p.uid, p.name)}" for p in g.alive())  # boshidagi raqam saqlanadi


def vote_pm(g: Game) -> str:
    return f"🗳 <b>{g.day}-kun · ovoz berish</b>\nKimni osamiz? Tanlang:"


def vote_chosen(name: str | None) -> str:
    return f"✅ Ovozingiz: <b>{escape(name)}</b>" if name else "✅ Siz hech kimga ovoz bermadingiz"


composition = alive_composition


def death_pm(hanged: bool) -> str:
    how = "Sizni shafqatsizlarcha osib o'ldirishdi!" if hanged else "Sizni vahshiylarcha otib o'ldirishdi!"
    return f"<b>{how}</b>\n💀 So'nggi so'zingizni aytishingiz mumkin.\n⏰ Vaqt: <b>{LAST_WORDS_SECS}</b> sekund"


def profile_card(u, inv) -> str:
    have = {i.item: i.qty for i in inv}
    items = "\n".join(f"{label.split(' ', 1)[0]} {bold(label.split(' ', 1)[1])}: {have.get(code, 0)} ta"
                      for code, label in ITEMS.items() if code in ALWAYS_SHOWN or have.get(code))
    end = pro.until(u.telegram_id)
    head = (f"{pro.badge()} <b>{bold('PRO')} · {bold('Admiral Mafia')}</b>" if end
            else f"<b>{bold('Admiral Mafia')}</b>")
    status = ""
    if end:
        days = max(1, -(-int((end - pro._now()).total_seconds()) // 86400))  # yuqoriga yaxlitlash
        status = f"{pro.badge()} {bold('PRO')}: <b>{end + PRO_TZ:%d.%m.%Y}</b> gacha ({days} kun)\n"
    return (f"{head}\n\n"
            f"{bold('ID')}: <code>{u.telegram_id}</code>\n👤 {bold('Ism')}: {escape(pro.name(u.telegram_id, u.full_name))}\n"
            f"🎖 {bold('Unvon')}: {rank(u.wins)}\n{status}\n"
            f"💵 {bold('Dollar')}: {u.dollars}\n💎 {bold('Olmos')}: {u.diamonds}\n\n{items}\n\n"
            f"🎲 {bold('Jami o' + chr(39) + 'yinlar')}: {u.games}\n🏆 {bold('G' + chr(39) + 'alabalar')}: {u.wins}")
