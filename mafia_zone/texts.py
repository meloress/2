"""Barcha o'zbekcha matnlar. Dvijok hodisalarini xabarlarga aylantiradi."""
from datetime import timedelta
from html import escape
from random import choice

from . import config, pro
from .engine.game import DRAW, Event, Game
from .engine.roles import MAFIA, NEUTRAL, ROLES, TOWN

PRO_TZ = timedelta(hours=5)  # sanalar Toshkent vaqtida
TEAM = {TOWN: "👨 Tinch aholi", MAFIA: "🤵 Mafiya", NEUTRAL: "🪙 Neytral"}
ITEMS = {"shield": "🛡 Qalqon", "verbena": "🌿 Verbena", "doc": "📄 Hujjat", "mask": "🎭 Maska",
         "votesave": "⚖️ Ovoz himoyasi", "ticket": "🎟 Faol rol", "ironshield": "🪖 Temir qalqon"}
ITEM_ABOUT = {
    "shield": "tunda hujumdan 1 marta saqlaydi (osilishdan emas — buning uchun ⚖️ Ovoz himoyasi)",
    "verbena": "faqat Vampir tishlashidan 1 marta saqlaydi (Vampir 12+ kishilik o'yinlarda chiqadi)",
    "doc": "mafiya yoki yakka rol bo'lsangiz, tekshiruvda 1 marta \"Tinch\" ko'rsatadi",
    "mask": "osilsangiz, rolingiz guruhga ochilmaydi (bir o'yinda bir marta)",
    "votesave": "kunduzi osilishdan 1 marta saqlaydi (bir o'yinda bir marta)",
    "ticket": "keyingi o'yinda oddiy Tinch o'rniga maxsus rol kafolatlanadi",
    "ironshield": "faqat Konchi uchun: tunnel qulaganda 1 marta omon qoldiradi (bir o'yinda bir marta)",
}
ITEM_USED = {  # o'yinda ishlaganda shaxsiy xabar: "🛡 Qalqon sizni qutqardi: ..."
    "shield": "tunda sizga qilingan hujum qaytarildi",
    "verbena": "Vampir tishlay olmadi",
    "doc": "tekshiruvda «Tinch aholi» bo'lib ko'rindingiz",
    "votesave": "dordan omon qoldingiz",
    "ironshield": "tunnel qulab tushdi, lekin siz kondan omon chiqdingiz",
}
for _c in config.ROLE_PICKS:  # "r_komissar": "🕵️‍♂️ Komissar Katani roli"
    ITEMS[f"r_{_c}"] = f"{ROLES[_c].name} roli"
    ITEM_ABOUT[f"r_{_c}"] = "keyingi o'yinda shu rol sizga tushadi (o'yinda bo'lsa; bo'lmasa keyingisiga qoladi)"
ALWAYS_SHOWN = ("shield", "verbena", "doc", "mask", "votesave")  # profilda 0 ta bo'lsa ham
MASKED = "🎭 Maskali"


def shown_role(g: Game, uid: int, code: str | None = None, masked: bool = False) -> str:
    """Guruhga ko'rinadigan rol. 🎭 Maska faqat osilganda ishlaydi (hanged.masked): o'sha e'londa rol yashirin."""
    p = g.get(uid)
    if (masked or (p and "mask" in p.used)) and g.phase != "finished":  # maska ishlatilgan = osilgan: /players da ham
        return f"<b>{MASKED}</b>"
    return role(code or (p.role if p else "tinch"))
RANKS = [(0, "🔰 Yangi boshlovchi"), (3, "🔫 Ko'cha bezori"), (10, "🕶 Gangster"), (25, "💼 Kapo"),
         (50, "🎩 Konsilyere"), (100, "🤵‍♂️ Don"), (250, "👑 Krestniy ota")]


def rank(wins: int) -> str:
    return [title for need, title in RANKS if wins >= need][-1]
WINNER = {TOWN: "👨 Tinch aholi g'alaba qildi!", MAFIA: "🤵 Mafiya g'alaba qildi!",
          "qotil": "🔪 Qotil yakka g'alaba qildi!", "vampir": "🧛 Vampir yakka g'alaba qildi!",
          "gazabkor": "🧟 G'azabkor yakka g'alaba qildi!",
          DRAW: "🤝 Durang!", "couple": "💞 Sevishganlar g'alaba qildi!"}


def mention(uid: int, name: str) -> str:
    """Bosilsa profil ochiladigan ism + Pro ko'rinishi (pro_look)."""
    link = f'<a href="tg://user?id={uid}">{escape(pro.name(uid, name))}</a>'
    if pro.is_owner(uid):  # bot egasi: Pro o'rniga Creator
        return f"{pro.owner_badge()} {pro.CREATOR_TAG} {link} {pro.owner_tail()}"
    return pro_look(link, pro.tier(uid), pro.title(uid))


def pro_look(link: str, tier: int, title: str | None = None) -> str:
    """Pro 1: qalin kursiv ism (pro.name); Pro 2: + pro boshi oldida, qizil galochka keyin; Pro 3: + "Pro";
    toifa (guruh egasi): pro boshi + "Vip" + ism + qora galochka."""
    if title:
        return f"{pro.badge()} {pro.VIP_TAG} {link} {pro.vip_tail()}"
    if tier >= 3:
        return f"{pro.badge()} {pro.PRO_TAG} {link} {pro.tail()}"
    return f"{pro.badge()} {link} {pro.tail()}" if tier == 2 else link


def pm(g: Game, uid: int) -> str:
    """Bosilsa Telegram profili ochiladigan ism."""
    p = g.get(uid) if uid is not None else None
    return mention(p.uid, p.name) if p else "?"


def role(code: str) -> str:
    emoji, name = ROLES[code].name.split(" ", 1)
    return f"{emoji} {bold(name)}"


def team_label(team: str) -> str:
    """"🤵 𝐌𝐚𝐟𝐢𝐲𝐚": jamoa nomi ham rollardek matematik qalin (boshqa yozuvlar - oddiy <b>)."""
    emoji, name = TEAM[team].split(" ", 1)
    return f"{emoji} {bold(name)}"


def dur(secs: int) -> str:
    """Vaqt: 45 soniya / 2 daqiqa / 1 daqiqa 30 soniya."""
    h, rest = divmod(int(secs), 3600)
    m, s = divmod(rest, 60)
    if not h and not m:
        return f"{s} soniya"
    return " ".join(x for x in (h and f"{h} soat", m and f"{m} daqiqa", s and f"{s} soniya") if x)


def left_str(secs: int) -> str:
    """Qolgan vaqt: 1 daqiqadan ko'p bo'lsa - daqiqada (yuqoriga yaxlitlab), kam bo'lsa - soniyada."""
    return dur(-(-secs // 60) * 60) if secs >= 60 else f"{secs} soniya"


# ---------- lobby ----------
def lobby(members: list[tuple[int, str]], left: int) -> str:
    body = ", ".join(mention(u, n) for u, n in members)  # chapdan o'ngga, raqamsiz; bo'sh bo'lsa qator yo'q
    return (f"🎮 <b>ADMIRAL MAFIA</b> — ro'yxatdan o'tish boshlandi!\n👥 <b>O'yinchilar:</b>\n\n"
            f"{body + chr(10) + chr(10) if body else ''}Jami: <b>{len(members)} ta</b> | Kutish vaqti: <b>{left_str(left)}</b>")


JOIN_BTN = "🤝 Qo'shilish"
COUPLE_JOIN_BTN = "❤️ Qo'shilish ❤️"
NO_COUPLE_JOIN = ("💔 <b>Sizda hozirda para yo'q.</b>\n\n"
                  "Paralar o'yiniga faqat juftlar qo'shiladi. Guruhda kimningdir xabariga javoban <b>/couple</b> "
                  "yozib, para bo'ling ❤️")
COUPLE_DROPPED = "💔 Jufti ro'yxatga yozilmagani uchun paralar o'yiniga kira olmadingiz. Keyingisida birga qo'shiling ❤️"
NEED_COUPLES = "💔 Paralar yetarli emas (kamida <b>2</b> para kerak).\n<b>O'yin bekor qilindi.</b>"
OTHER_LOBBY = "⚠️ Hozir boshqa o'yin ro'yxati ochiq. Avval u tugasin yoki admin /stop qilsin."
NOT_COUPLE_LOBBY = "⚠️ Ochiq ro'yxat oddiy o'yin uchun. Uni /start bilan boshlang."
NOT_COUPLE_GAME = "⚠️ Hozirgi o'yin oddiy o'yin. Uni /stop bilan to'xtating."


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
            f"❤️ <b>Paralar:</b>\n\n{body}{wait}\n\nJami: <b>{len(rows)} para</b> | Kutish vaqti: <b>{left_str(left)}</b>")


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
              "Oxirgi tirik para g'olib bo'ladi 🏆</i>\n\n" + alive_composition(g))


NEED_PLAYERS = "😔 O'yinchilar yetarli emas (kamida <b>4</b> kishi kerak).\n<b>O'yin bekor qilindi.</b>"
GAME_EXISTS = "⚠️ Bu guruhda o'yin allaqachon ketmoqda."
NOT_ADMIN_WARN = ("⚠️ Bot guruhda admin emas. O'yin bo'ladi, lekin tunda va o'liklarning xabarlarini "
                  "o'chira olmayman. Botni admin qiling (xabarlarni o'chirish huquqi bilan).")
JOINED = "✅ " + "𝐌𝐮𝐯𝐚𝐟𝐟𝐚𝐪𝐢𝐲𝐚𝐭𝐥𝐢 𝐫𝐨'𝐲𝐱𝐚𝐭𝐝𝐚𝐧 𝐨'𝐭𝐝𝐢𝐧𝐠𝐢𝐳!" + "\nGuruhga qayting va o'yin boshlanishini kuting."
ALREADY_IN_GAME = "⚠️ Siz allaqachon boshqa o'yindasiz."
NO_LOBBY = "⚠️ Bu guruhda ro'yxatdan o'tish ketmayapti."
NO_LOBBY_START = "⚠️ Ro'yxat ochiq emas. Avval /game bilan ro'yxatni oching."
NO_GAME_HERE = "🎮 Hozir bu guruhda o'yin yo'q. /game bilan boshlang!"
PM_ONLY = "🤖 Bu buyruq botning shaxsiy chatida ishlaydi — botga o'ting."
LOBBY_FULL = ("⚠️ O'yin to'lgan (60 kishi). Sizni keyingi o'yin navbatiga yozdim — "
              "ro'yxat ochilishi bilan xabar beraman 🔔")
BANNED = "⛔️ Siz botdan foydalanishdan chetlatilgansiz."
LOBBY_LOST = ("🙏 <b>Uzr so'raymiz!</b>\nBot qisqa yangilanishdan o'tmoqda, shu bois ro'yxat bekor qilindi.\n"
              "⏳ <b>2 daqiqadan</b> so'ng /game yozing va o'yinni davom ettiramiz! 🎮")
GIVEAWAY_TTL_MIN = 60  # tarqatma shuncha daqiqadan keyin yopiladi


CUR = {"dollars": "💵", "diamonds": "💎"}


def giveaway_closed(text: str, currency: str = "dollars") -> str:
    what = "olmos" if currency == "diamonds" else "pul"
    return text + f"\n\n⌛️ <b>Vaqt tugadi.</b> Olinmagan {what} egasiga qaytarildi."


def giveaway_refund(amount: int, currency: str = "dollars") -> str:
    return f"↩️ Tarqatmangizdan olinmagan <b>{amount} {CUR[currency]}</b> hisobingizga qaytarildi."


STOPPED = "🛑 <b>O'yin to'xtatildi.</b>"
ONLY_ADMIN = "⚠️ Bu buyruq faqat guruh adminlari uchun."
def leave_only_pro(uid: int, name: str) -> str:
    return (f"🔒 {mention(uid, name)}, o'yindan chiqish faqat {pro.badge()} <b>Pro</b> foydalanuvchilar uchun.\n"
            "O'yinni oxirigacha o'ynang! Pro haqida: botga /pro yozing.")


def left_fined(uid: int, name: str) -> str:
    return f"🚪 {mention(uid, name)} o'yindan chiqdi va <b>{config.LEAVE_FINE} 💵</b> jarima to'ladi."


def debt_block(dollars: int) -> str:
    return (f"⛔️ Hisobingiz: <b>{dollars} 💵</b>\n"
            f"Hisobi <b>{config.DEBT_LIMIT} 💵</b> yoki undan kam bo'lgan o'yinchilar o'yinga qo'shila olmaydi.\n\n"
            "Balansni to'ldirish uchun 🤝 do'stlaringizni taklif qiling.")


KICK_HOW = "❌ O'yinchining xabariga reply qilib /kick yozing yoki raqamini bering: <code>/kick 5</code>"


def kicked(uid: int, name: str) -> str:
    return f"🚫 {mention(uid, name)} o'yindan chiqarildi."


NOT_YOUR_BTN = "❌ Bu tugma siz uchun emas"
ONLY_STARTER = "⚠️ O'yinni faqat guruh adminlari yoki /game bosgan odam boshlay oladi."
ONLY_STARTER_EXTEND = "⚠️ Ro'yxatni faqat guruh adminlari yoki /game bosgan odam uzaytira oladi."
GROUP_ONLY = "Bu buyruq guruhda ishlaydi."


NIGHT_CHAT_HINT = "💬 <i>Tunda shu yerga yozgan xabaringiz sheriklaringizga yetkaziladi.</i>"
DONISHMAND_NIGHT = "👂 Devorga qulog'ingizni tuting... Mafiya yoki Komissar shivirlashsa, bu yerda eshitasiz."


TEAM_DOT = {TOWN: "🔵", MAFIA: "🔴", NEUTRAL: "⚪️"}
RULE = {  # rol kartasida ⚠️ qatori: tavsifda yozilmagan cheklovlar
    "kezuvchi": "Bir odamni ketma-ket 2 tun uxlata olmaysiz, o'zingizni ham.",
    "qorovul": "Bir odamni ketma-ket 2 tun himoyalay olmaysiz.",
    "don": "Mafiyadoshlaringiz ovoz beradi, lekin yakuniy so'z sizniki.",
    "mafiya": "Nishonni Don hal qiladi, siz unga ovozingiz bilan yordam berasiz.",
    "aka": "Don bo'la olmaysiz: Don o'lib, mafiyadan faqat siz ikkovingiz qolsangiz, birgalikdagi hujumingiz bilan davom etasiz.",
    "uka": "Don bo'la olmaysiz: Don o'lib, mafiyadan faqat siz ikkovingiz qolsangiz, birgalikdagi hujumingiz bilan davom etasiz.",
}


def role_card(g: Game, uid: int) -> str:
    p = g.get(uid)
    team = ROLES[p.role].team
    text = (f"Siz — {role(p.role)} siz!\n{TEAM_DOT[team]} Jamoa: <b>{bold(TEAM[team].split(' ', 1)[1])}</b>\n"
            f"🎯 Vazifa: {ROLES[p.role].about}")
    if p.role in RULE:
        text += f"\n⚠️ {RULE[p.role]}"
    mates = g.teammates(uid)
    if mates:
        text += "\n\n🤝 <b>Sheriklaringizni eslab qoling!</b>\n" + "\n".join(
            f"<b>{escape(dn(m))}</b> — {role(m.role)}" + ("" if m.alive else " 💀") for m in mates)
        text += "\n\n" + NIGHT_CHAT_HINT
    if q := g.partner(uid):
        text += (f"\n\n💞 <b>Sizning juftingiz:</b> {escape(dn(q))} — {role(q.role)}" + ("" if q.alive else " 💀")
                 + "\n<i>U o'lsa, siz ham o'yindan chiqasiz. Unga yozish: xabarni <b>+</b> bilan boshlang.</i>")
    own = [f"{ITEMS[i]} ×{q}" for i, q in p.items.items() if q > 0 and i in ITEMS and not i.startswith("r_")]
    if own:
        text += "\n\n🎒 <b>Buyumlaringiz:</b> " + ", ".join(own)
    return text


ROLE_BTN = "🎭 Sizning rolingiz"
BACK_TO_GROUP = "Guruhga qaytish"
GAME_STARTED = "🎮 <b>O'YIN BOSHLANDI!</b>"
NOT_IN_GAME = "Siz bu o'yinda ishtirok etmayapsiz."


def role_alert(g: Game, uid: int) -> str:
    """Guruhdagi tugma uchun qalqib chiquvchi oyna: faqat roli (vazifasi va sheriklar - botda). Oddiy matn."""
    return f"Sizning rolingiz: {ROLES[g.get(uid).role].name}"


# ---------- tun ----------
ROLE_PROMPT = {
    "don": "🤵🏻 Don, oila sizning buyrug'ingizni kutyapti. Bu tun kim yo'qoladi?",
    "mafiya": "🤵 Oila yig'ildi. Kimni nishonga olamiz? (Yakuniy so'z Donniki)",
    "komissar": "🕵️‍♂️ Komissar, shahar sizga umid bog'lagan. Tekshiramizmi yoki otamizmi?",
    "doktor": "👨‍⚕️ Doktor, chamadoningiz tayyor. Bu tun kimning hayotini saqlaysiz?",
    "kezuvchi": "💃 Kezuvchi, kimga uyqu dori berasiz? U bu tun hech narsa qila olmaydi va ertaga ovoz bera olmaydi.",
    "daydi": "🍾 Daydi, bu tun qaysi uy oldida tunaysiz? Qotillik bo'lsa, guvoh bo'lasiz.",
    "qorovul": "👨‍🦳 Qorovul, ertaga kimni dordan himoya qilasiz?",
    "ovchi": "🏹 Ovchi, bu tun kimni kuzatamiz? Tongda uning roli sizga ochiladi — kunduzi o'ldirish yoki rahm "
             "qilish sizning qo'lingizda.",
    "jurnalist": "👩‍💻 Jurnalist, bu tun kimdan intervyu olamiz? Uning mehmonlarini ko'rasiz.",
    "yollanma": "🕴 Yollanma qotil, buyurtma bor. Kim?",
    "advokat": "👨‍💼 Advokat, qaysi mijozingizni bu tun himoya qilasiz?",
    "aka": "🧔 Aka, ukangiz bilan bir nishonni tanlang — shundagina zarba o'tadi.",
    "uka": "👦 Uka, akangiz bilan bir nishonni tanlang — shundagina zarba o'tadi.",
    "qotil": "🔪 Qotil, pichoq o'tkir. Bu tun kimning navbati?",
    "gazabkor": "🧟 G'azabkor, g'azab ichingizni yondiryapti. Kim qurbon bo'ladi?",
    "sehrgar": "🧙 Sehrgar, qaysi uyni la'natlaysiz? Egasi tirik qoladi, lekin bu tun uning oldiga kelgan har kim "
               "halok bo'ladi.",
    "vampir": "🧛 Vampir, chanqoq kuchaydi. Kimning qonini ichamiz?",
    "qaroqchi": "🦹‍♂️ Qaroqchi, kimning cho'ntagini yengillatamiz?",
    "konchi": "👷‍♂️ Konchi, kirka tayyor. Qazishni boshlaymizmi?",
    "aferist": "🤹 Aferist, bu tun kimning harakatini o'g'irlaymiz?",
    "afsungar": "💣 Sizni osishdi, lekin yolg'iz ketmaysiz! Tong otguncha kimni o'zingiz bilan olib ketasiz?",
}


# Guruhdagi jonli lenta: kim harakat qilgani anonim, nishon ochilmaydi
ACT_FEED = {
    ("komissar", "check"): "{r} hujjatlarni tekshirishga ketdi...",
    ("komissar", "shoot"): "{r} pistoletini o'qladi...",
    "ovchi": "{r} shahar himoyasi uchun ketdi...",
    ("gazabkor", "sacrifice"): "{r} o'zini olovga tashlashga tayyorlanmoqda...",
    "don": "{r} navbatdagi o'ljasini tanladi...",
    "mafiya": "{r} nishonga ishora qildi...",
    "doktor": "{r} tungi navbatchilikka chiqdi...",
    "daydi": "{r} kimningdir eshigi oldida tunab qoldi...",
    "kezuvchi": "{r} kimningdir uyiga mehmonga ketdi...",
    "qorovul": "{r} tungi xizmatda...",
    "jurnalist": "{r} intervyu olishga ketdi...",
    "yollanma": "{r} buyurtmani qabul qildi...",
    "advokat": "{r} kimnidir himoya qilish uchun ketdi...",
    "aka": "{r} nishonni belgiladi...",
    "uka": "{r} nishonni belgiladi...",
    "qotil": "{r} navbatdagi qurbonini tanladi...",
    "gazabkor": "{r} qurbon izlab ketdi...",
    "sehrgar": "{r} kimningdir uyiga la'nat soldi...",
    "vampir": "{r} qorong'ilikka uchib ketdi...",
    "qaroqchi": "{r} o'g'irlikka chiqdi...",
    "konchi": "{r} yer ostiga tushdi...",
    "aferist": "{r} yangi firibgarlik o'ylab topdi...",
}


SKIP_FEED = {
    "doktor": "{r} bu tun dam olishga qaror qildi...",
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
    ("blast", True): "💥 Siz {t}ni o'zingiz bilan olib ketdingiz!",
    ("curse", True): "🔮 La'natingiz ishladi: {t} la'natlangan uyga kirib, halok bo'ldi.",  # {t} - kelgan odam
    ("curse_empty", False): "🔮 Bu tun {t}ning oldiga hech kim kelmadi — la'natingiz hech kimni topmadi.",
}
CHECKED_YOU = "🔍 Tunda kimdir sizni tekshirdi..."
ATTACK_OK = "🎯 Nishoningiz {t} halok bo'ldi."
ATTACK_FAIL = "😤 {t} omon qoldi — kimdir uni himoya qildi yoki unga kuchingiz yetmadi."
WHY = {  # hujum nega o'tmadi (Event data "why"): hujumchiga va mafiyaga aytiladi
    "heal": "👨‍⚕️ uni Doktor davolab qo'ydi",
    "shield": "🛡 uning Qalqoni bor ekan",
    "verbena": "🌿 uning Verbenasi bor ekan",
    "immune": "💪 unga sizning kuchingiz yetmaydi",
    "transformed": "🧬 u Voris ekan — taqdiri o'zgarib, boshqa rolga aylandi",
    "gone": "🔥 u shu tun o'zini qurbon qilib bo'lgan edi",
    "blocked": "💤 Donga uyqu dori berishdi — mafiya bu tun hujum qila olmadi",
    "stolen": "🤹 Aferist mafiyaning hujumini o'g'irlab ketdi",
}
IMMUNE_YOU = "💪 Tunda sizga hujum qilishdi, lekin bu hujum sizga ta'sir qilmadi!"
VISIT_ATTACKED = "🍾 {t}ning uyiga tunda kimdir hujum qildi, lekin u omon qoldi — qotillik bo'lmadi."


def attack_fail(why: str | None) -> str:
    """Hujumchiga: nishon omon qoldi + sababi (bilinsa)."""
    return f"😤 {{t}} omon qoldi: {WHY[why]}." if why in WHY else ATTACK_FAIL
ATTACKED_SAVED = "🩹 Tunda sizga hujum qilishdi, lekin omon qoldingiz!"
PATIENT = {True: "👨‍⚕️ Tunda sizga hujum qilishdi, lekin <b>Doktor</b> sizni qutqarib qoldi!",
           False: "👨‍⚕️ Tunda <b>Doktor</b> sizni ko'rgani keldi. Bu tun sizga hech kim hujum qilmadi."}


def act_feed(role_code: str, kind: str = "") -> str:
    t = ACT_FEED.get((role_code, kind)) or ACT_FEED.get(role_code) or "🌑 Kimdir tunda harakatga keldi..."
    return t.format(r=role(role_code))


def vote_feed(g: Game, voter: int, target: int | None) -> str:
    if target is None:
        return f"{pm(g, voter)} hech kimga ovoz bermadi"
    return f"{pm(g, voter)} → {pm(g, target)} ga ovoz berdi"


NIGHT_CAPTION = ("🌃 <b>Tun</b>\nKo'chaga faqat jasur va qo'rqmas odamlar chiqdi.\n"
                 "Ertalab tirik qolganlarni sanaymiz...")
DAY_CAPTION = "🌄 <b>Xayrli tong!</b>\nShamollar tundagi mish-mishlarni butun shaharga yetkazmoqda..."


def night_prompt(g: Game, uid: int) -> str:
    r = g.get(uid).role
    hint = "\n\n" + NIGHT_CHAT_HINT if any(m.alive for m in g.teammates(uid)) else ""
    return f"🌙 <b>{g.day}-tun</b>\n\n" + ROLE_PROMPT.get(r, f"{role(r)}, harakatingizni tanlang:") + hint


SKIP_NIGHT_BTN = "🚫 Hech narsa qilmayman"
SKIPPED_NIGHT = "😶 Siz bu tun hech narsa qilmaslikka qaror qildingiz"
DON_SKIPPED = "🤵🏻 Don bu tun hech kimga tegmaslikka qaror qildi."


CHOSEN = {"dig": "👷‍♂️ Tunnel qazilmoqda...", "sacrifice": "🔥 Siz o'zingizni olovga tashlashga qaror qildingiz..."}


def chosen(name: str | None) -> str:
    return f"✅ Siz <b>{escape(name)}</b>ni tanladingiz" if name else "✅ Tanlovingiz qabul qilindi"


def mafia_voted(voter: str, target: str) -> str:
    return f"🤵 {escape(voter)} → <b>{escape(target)}</b> ga ovoz berdi"


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
               "tulki": e.target, "heartbreak": e.target, "hunted": e.target, "collapsed": e.target}.get(e.kind)
        if uid is not None and uid not in out:
            out.append(uid)
    return out


def last_words(g: Game, uid: int, text: str) -> str:
    return f"🕯 <b>{nm(g, uid)}</b>ning so'nggi so'zlari:\n<i>«{text}»</i>"


SAVED = ["💉 Kimdir bu tun o'lim yoqasidan qaytdi! Ajal bu safar quruq ketdi.",
         "💉 Tunda kimgadir hujum bo'ldi... lekin u omon qoldi! Shaharda qahramonlar bor.",
         "💉 Hujumchi bu tun omadsiz chiqdi — qurboni tirik qoldi!"]  # "Qotil" emas: u alohida rol
QUIET = ["🌤 Mo'jiza! Bu tun hech kim halok bo'lmadi. Lekin bu uzoq davom etmaydi...",
         "🌤 Tinch tun. Hamma tirik... hozircha.",
         "🌤 Hech kim o'lmadi. Mafiya nimanidir rejalashtiryaptimi?"]


def morning(g: Game, ev: list[Event]) -> tuple[list[str], list[tuple[int, str]]]:
    """([guruhga alohida xabarlar], [(uid, shaxsiy matn)])"""
    pub, priv = [], []
    n = lambda uid: pm(g, uid)  # ismlar bosilsa Telegram profili ochiladi
    healed = {e.target for e in ev if e.kind == "result" and e.data["kind"] == "heal" and e.data["ok"]}
    immune: set[int] = set()  # hujum ta'sir qilmagan nishonlar (Sehrgar, Qotil) - o'ziga bir marta aytiladi
    masks = {e.target: e.uid for e in ev if e.kind == "result" and e.data["kind"] == "disguise"}  # nishon -> Advokat
    w = lambda uid: who(g, uid)
    for e in ev:
        k = e.kind
        if k == "killed":
            # rollar tun boshidagi holatda (masalan, jarimadan oldingi Ovchi)
            victim = f"{shown_role(g, e.target, e.data.get('role'))} — <b>{n(e.target)}</b>"
            if e.data["by"] == ["curse"]:
                pub.append(f"🔮 Tunda {victim} la'natlangan uyga kirib qoldi va shafqatsiz o'lim topdi.\n"
                           f"Aytishlaricha, u uyga {role('sehrgar')} la'nat solgan.")
            else:
                codes = e.data.get("killer_roles") or [g.get(u).role for u in e.data.get("killers", [])]
                killers = ", ".join(role(c) for c in dict.fromkeys(codes)) or "noma'lum kimdir"
                pub.append(f"☠️ Tunda {victim} {choice(VERBS)}\nAytishlaricha, unikiga {killers} kelgan.")
        elif k == "saved":
            pub.append(choice(SAVED))
            if e.target not in healed:  # Doktor qutqargan bo'lsa - unga alohida (PATIENT)
                priv.append((e.target, ATTACKED_SAVED))
        elif k == "result":
            if e.data["kind"] == "visit" and e.data.get("attacked"):
                t = VISIT_ATTACKED
            else:
                t = RESULT.get((e.data["kind"], e.data["ok"])) or (ATTACK_OK if e.data["ok"] else attack_fail(e.data.get("why")))
            priv.append((e.uid, t.format(t=f"<b>{n(e.target)}</b>")))
            if e.data.get("why") == "immune":
                immune.add(e.target)
            if e.data["kind"] == "heal" and e.target != e.uid:  # bemorga ham
                priv.append((e.target, PATIENT[e.data["ok"]]))
        elif k == "mafia_idle":
            pub.append(f"🤵 Bu tun mafiya hech kimga tegmadi: {role('don')} nishon tanlamadi.")
        elif k == "mafia_result":
            if e.data.get("why") == "immune":
                immune.add(e.target)
            why = WHY.get(e.data.get("why"))
            text = (f"🎯 Mafiyaning nishoni <b>{n(e.target)}</b> o'ldirildi." if e.data["killed"]
                    else f"😤 Mafiyaning nishoni <b>{n(e.target)}</b> bu tun omon qoldi" + (f": {why}." if why else "."))
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
            pub.append(f"😴 {w(e.target)} bir necha tun harakat qilmadi va o'yindan chiqarildi.")
        elif k == "left":
            pub.append(f"🚫 {w(e.target)} o'yindan chiqarildi." if e.data.get("kicked")
                       else f"🚪 {w(e.target)} shaharni tashlab qochdi...")
        elif k == "hanged":
            score = (f"📊 <b>Tasdiqlash natijalari:</b>\n{e.data['yes']} 👍 | {e.data['no']} 👎\n\n"
                     if "yes" in e.data else "")
            pub.append(score + f"🪢 <b>{pm(g, e.target)}</b> kunduzgi yig'ilish qarori bilan osildi.\n"
                               f"U {shown_role(g, e.target, e.data['role'], e.data.get('masked'))} edi.")
        elif k == "vote_saved":
            pub.append(f"⚖️ Arqon tortilay deganda <b>{pm(g, e.target)}</b> {ITEMS['votesave']}ni ko'rsatdi "
                       "va dordan omon qoldi!")
        elif k == "spared":
            pub.append(f"📊 <b>Tasdiqlash natijalari:</b>\n{e.data['yes']} 👍 | {e.data['no']} 👎\n\n"
                       f"Aholi <b>{pm(g, e.target)}</b>ni osishga rozi bo'lmadi — bu safar u omon qoldi.")
        elif k == "no_hang":
            pub.append(choice(["⚖️ <b>Ovoz berish yakunlandi</b>\nAholi bir qarorga kela olmadi — bugun hech kim osilmadi.",
                               "⚖️ <b>Ovoz berish yakunlandi</b>\nFikrlar ikkiga bo'lindi — dor bugun bo'sh qoldi."]))
        elif k == "guard_saved":
            pub.append(f"👨‍🦳 Arqon tortilay deganda {role('qorovul')} yetib keldi va <b>{pm(g, e.target)}</b>ni "
                       "dordan qutqarib qoldi!")
            if q := g.by_role("qorovul"):  # Qorovulning o'ziga ham: himoyasi ishladi
                priv.append((q.uid, f"👨‍🦳 Siz himoyalagan <b>{n(e.target)}</b>ni dordan qutqardingiz!"))
        elif k == "tulki":
            pub.append(f"🦊 {w(e.uid)} ayyorlik qildi: unga birinchi ovoz bergan {w(e.target)} ham u bilan ketdi!")
        elif k == "blocked":
            priv.append((e.uid, "💤 Boshingiz aylanib, ko'zingiz yumildi... Kimdir sizga uyqu dori berdi. "
                                "Bu tun hech narsa qila olmadingiz, ertaga esa <b>ovoz bera olmaysiz</b>."))
        elif k == "stolen":
            priv.append((e.target, "🤹 Kimdir sizning tungi rejangizni o'g'irlab ketdi!"))
            priv.append((e.uid, f"🤹 Ajoyib fokus! {n(e.target)}ning harakatini o'zlashtirdingiz."))
        elif k == "steal_empty":
            priv.append((e.uid, f"🤹 {n(e.target)}da bu tun o'g'irlaydigan harakat yo'q edi — qo'lingiz bo'sh qoldi."))
        elif k == "checked":
            text = f"🔍 Tekshiruv natijasi: {n(e.target)} — {role(e.data['result'])}"
            if [e.uid, e.target] not in g.hunt:  # Ovchiga - "💀 O'ldirish" tugmali alohida xabar (runner, hunt_pm)
                priv.append((e.uid, text))
            priv.append((e.target, CHECKED_YOU))  # kim tekshirgani aytilmaydi
            if e.target in masks and e.data["result"] == "tinch":  # Advokatga: niqob ishladi
                priv.append((masks[e.target], f"🎭 Niqobingiz ishladi: kimdir <b>{n(e.target)}</b>ni tekshirdi "
                                              "va u Tinch aholi bo'lib ko'rindi!"))
            if g.get(e.uid).role == "komissar":  # sherigi (Serjant yoki shu tun Komissar bo'lgan Serjant) ham biladi
                priv += [(m.uid, f"🕵️‍♂️ Komissardan xabar: {text}") for m in g.teammates(e.uid) if m.alive]
        elif k == "interview":
            vis = ", ".join(n(v) for v in e.data["visitors"]) or "hech kim"
            priv.append((e.uid, f"🎤 Intervyu tayyor! Bu tun {n(e.target)}ning oldiga kelganlar: {vis}"))
        elif k == "witness":
            priv.append((e.uid, f"👀 Siz {n(e.target)}ning uyi oldida qotillikni o'z ko'zingiz bilan ko'rdingiz!\n"
                                "Hujum qilgan(lar): " +", ".join(f"<b>{n(x)}</b>" for x in e.data["killers"])))
        elif k == "dug":
            d, gems = e.data["dollars"], e.data["diamonds"]
            extra = f" va <b>{gems} 💎</b> olmos" if gems else ""
            head = ("💎 <b>Olmos koni!</b> " if gems >= 2 else "") + ("💰 <b>Oltin tomir!</b> " if d > 500 else "")
            priv.append((e.uid, f"{head}👷‍♂️ <b>Tabriklaymiz!</b>\nTunneldan <b>{d} 💵</b> dollar{extra} topdingiz!"))
            pub.append(f"{role('konchi')} bugun tunda <b>{d} 💵</b> dollar{extra} topdi!")
        elif k == "collapsed":  # Konchi qazishda halok bo'ldi
            pub.append(f"🪦 Bugun tunda {shown_role(g, e.target, e.data['role'])} — <b>{n(e.target)}</b>ning jasadi "
                       f"{e.data['tunnel']}-tunneldan topildi.")
        elif k == "dig_saved":
            pub.append(f"{role('konchi')} {ITEMS['ironshield'].split(' ', 1)[1].lower()}dan foydalandi va kondan "
                       "omon chiqdi!")
        elif k == "item_used" and e.data["item"] == "mask":
            priv.append((e.uid, f"{ITEMS['mask']} ishladi: osilganingizda rolingiz guruhga ochilmadi."))
        elif k == "item_used":
            used = ITEM_USED.get(e.data["item"]) or ITEM_ABOUT[e.data["item"]]
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
            for m in g.teammates(e.uid):  # jamoa yangi Don/Komissarni bilsin
                if m.alive:
                    priv.append((m.uid, f"⭐️ {n(e.uid)} endi {role(e.data['role'])}!"))
        elif k == "hunted":  # Ovchi kunduzi o'ldirdi (Game.hunter_kill)
            victim = f"{shown_role(g, e.target, e.data['role'])} — <b>{n(e.target)}</b>"
            pub.append(f"🏹 Bugun noxush hodisa yuz berdi: aholidan {victim}ning murdasi topildi.\n"
                       f"Aytishlaricha, bu {role('ovchi')}ning ishi.")
            if fine := e.data["fine"]:
                pub.append(f"💸 {role('ovchi')} tinch fuqaroni o'ldirgani uchun <b>{fine} 💵</b> jarima to'ladi.")
                priv.append((e.uid, f"💸 Siz tinch fuqaroni o'ldirdingiz: <b>{fine} 💵</b> jarima — pul "
                                    f"<b>{n(e.target)}</b>ga o'tdi."))
                priv.append((e.target, f"💵 Ovchi jarimasi: <b>{fine} 💵</b> hisobingizga tushdi."))
            else:
                priv.append((e.uid, f"🎯 Siz <b>{n(e.target)}</b>ni o'ldirdingiz."))
    priv += [(uid, IMMUNE_YOU) for uid in sorted(immune)]
    return pub, priv


HUNT_BTN = "💀 O'ldirish"
HUNT_LATE = "⌛️ Kech qoldingiz: osish boshlandi, endi o'ldira olmaysiz."
HUNT_NO = "❌ Endi o'ldira olmaysiz"


def hunt_pm(g: Game, target: int, shown: str) -> str:
    """Ovchiga tongda: tanlagan odamining roli (tekshiruvdagidek ko'rinadi) va tanlov - o'ldirish yoki rahm."""
    from .engine.game import HUNT_FINE
    return (f"🏹 <b>{nm(g, target)}</b> — {role(shown)}\n\n"
            f"Osish boshlanguncha uni o'ldirishingiz yoki rahm qilishingiz mumkin (rahm qilsangiz - hech narsa bosmang).\n"
            f"⚠️ Tinch aholini o'ldirsangiz, <b>{HUNT_FINE[0]}–{HUNT_FINE[1]} 💵</b> jarima to'laysiz — "
            "pul o'sha o'yinchiga o'tadi.")


def day_start(g: Game, secs: int) -> str:
    """Kunduzgi GIF'dan keyingi xabar: tiriklar, tarkib, muhokama vaqti."""
    return (f"☀️ <b>{g.day}-kun</b>\n\n{alive_list(g)}\n\n{alive_composition(g)}\n\n"
            f"🗣 Muhokama uchun <b>{dur(secs)}</b>")


def vote_prompt(g: Game, secs: int) -> str:
    return (f"⚖️ <b>Aybdorni aniqlash va jazolash vaqti keldi!</b>\n"
            f"🗳 Ovoz tugmalari shu yerda — faqat sizga ko'rinadi (yoki botga o'ting).\n⏳ Vaqt: <b>{dur(secs)}</b>")


SKIP_BTN = "🤐 Hech kimga ovoz bermayman"


def confirm_prompt(g: Game, secs: int) -> str:
    return (f"🪢 Rostdan ham <b>{pm(g, g.candidate)}</b> ni osishni xohlaysizmi?\n\n"
            f"⏳ Tasdiqlash uchun vaqt: <b>{dur(secs)}</b>")


def confirm_pm(g: Game) -> str:
    return f"🪢 <b>{pm(g, g.candidate)}</b> ni osamizmi?\nTanlang:"


def confirm_result(g: Game) -> str:
    yes, no = g.confirm_tally()
    return f"🪢 Rostdan ham <b>{pm(g, g.candidate)}</b> ni osishni xohlaysizmi?\n\n<b>{yes} 👍 | {no} 👎</b> — vaqt tugadi"


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


def transfer_done(sender: str, sender_id: int, target: str, target_id: int, amount: int,
                  currency: str = "dollars") -> str:
    return f"💸 {mention(sender_id, sender)} → {mention(target_id, target)}: <b>{amount} {CUR[currency]}</b>"


GIVEAWAY_SHOW = 60  # ro'yxatda ko'rsatiladigan olganlar (xabar 4096 belgidan oshmasin)


def giveaway(sender: str, sender_id: int, per: int, parts: int, takers: list[tuple[int, str]] = (),
             currency: str = "dollars") -> str:
    """takers: [(uid, ism)] olish tartibida."""
    c = CUR[currency]
    text = f"{mention(sender_id, sender)} <b>{per * parts}</b> {c} ulashmoqda!"
    if takers:
        lines = [f"{i}. {mention(uid, name)} - {per}{c}" for i, (uid, name) in enumerate(takers[:GIVEAWAY_SHOW], 1)]
        if len(takers) > GIVEAWAY_SHOW:
            lines.append(f"... va yana {len(takers) - GIVEAWAY_SHOW} kishi")
        text += "\n\n<b>Sovg'a olganlar:</b>\n\n" + "\n".join(lines)
    return text


GIVEAWAY_BTN = "💰 Olish"
GIVEAWAY_GOT = "🎉 +{} {} oldingiz!"
GIVEAWAY_NO = "😔 Bu tarqatma tugagan"
GIVEAWAY_TAKEN = "✅ Siz bu tarqatmadan allaqachon olgansiz"
GIVEAWAY_MEMBERS = "👥 Tarqatmadan faqat shu guruh a'zolari oladi. Avval guruhga qo'shiling."
LATE_VOTE = "⌛️ Kechikdingiz: ovoz berish vaqti tugagan"
LATE_NIGHT = "⌛️ Kechikdingiz: tun tugagan, harakat qabul qilinmadi"
GIVEAWAY_EARLY = "🤖 Juda tez bosdingiz - bu avtomatik bosishga o'xshaydi. Bu tarqatmadan ololmaysiz."


# ---------- para ----------
COUPLE_HOW = "❌ Reply qilib yoki /couple @username yozing."
COUPLE_LOCKED = "💍 Siz parani uzolmaysiz! Bu juftlik abadiy 😏"
AS_CHANNEL = "❌ Guruhda kanal nomidan yozib bo'lmaydi — o'z profilingizdan yozing."
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
    "gazabkor": "G'azab shaharni yutib yubordi. Kul ustida faqat G'azabkor qoldi... 🔥",
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
    lines += [f"    {i}. {pm(g, p.uid)} — {role(p.role)}" for i, p in enumerate(won, 1)] or ["    —"]
    if rest:
        lines += ["", "<b>Qolgan o'yinchilar:</b>"]
        lines += [f"    {i}. {pm(g, p.uid)} — {role(p.role)}" for i, p in enumerate(rest, len(won) + 1)]
    if minutes is not None:
        lines += ["", f"⏱ O'yin <b>{minutes}</b> daqiqa davom etdi"]
    return "\n".join(lines)


def result_pm(won: bool, reward: int, u=None, inv=()) -> str:
    head = (f"🎉 <b>Siz g'alaba qozondingiz!</b>\nYutganingiz uchun sizga <b>{reward} 💵</b> berildi" if won
            else "😔 <b>O'yin tugadi!</b>\nBu safar yutqazdingiz." + (f" Ishtirok uchun <b>{reward} 💵</b>" if reward else ""))
    return head + ("\n\n" + profile_card(u, inv) if u else "")


NEXT_OK = "🔔 Bu guruhda keyingi o'yin boshlanganda sizga xabar beraman."


def join_greet(uid: int, name: str) -> str:
    """Guruhga yangi kelgan odamga shaxsiy salom (rasm izohi)."""
    return f"𝘼𝙨𝙨𝙖𝙡𝙤𝙢𝙪 𝙖𝙡𝙖𝙮𝙠𝙪𝙢 𝙝𝙪𝙧𝙢𝙖𝙩𝙡𝙞 {mention(uid, name)} 𝙗𝙞𝙯𝙣𝙞𝙣𝙜 𝙧𝙖𝙨𝙢𝙞𝙮 𝙜𝙪𝙧𝙪𝙝𝙞𝙢𝙞𝙯𝙜𝙖 𝙭𝙪𝙨𝙝 𝙠𝙚𝙡𝙞𝙗𝙨𝙞𝙯!"


def next_game(title: str) -> str:
    return f"🎮 <b>{escape(title)}</b> guruhida yangi o'yin boshlandi! Qo'shilish uchun tugmani bosing 👇"


# ---------- PM: profil, do'kon ----------
def welcome() -> str:
    return ("👋 <b>Mafiya olamiga xush kelibsiz!</b>\n"
            "Men — 🤵 <b>Admiral Mafia</b> o'yinining rasmiy botiman.\n\n"
            "Bu shunchaki o'yin emas — sirlar, hiyla va ishonch dunyosi.\n"
            "Botni guruhga qo'shing, rolingizni oling va o'zingizni ko'rsating! 🎯\n\n"
            "🎭 <i>Rolingiz sizni kutmoqda...</i>")


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
            "Pro to'lovi bilan muammo bo'lsa (pul yechildi, lekin Pro yoqilmadi va hokazo), "
            f"to'lov chekining skrinshoti bilan yozing: {admins}.\n"
            "Hal qilinmasa, ⭐ Stars to'liq qaytariladi.")


PAY_REFUNDED = ("⚠️ Texnik xato tufayli xarid amalga oshmadi — <b>⭐ Stars to'liq qaytarildi</b>.\n"
                "Birozdan keyin qaytadan urinib ko'ring.")
PAY_FAILED = "⚠️ To'lovda texnik xato bo'ldi. /paysupport orqali adminga yozing — muammo hal qilinadi."

PRO_BTN = "Pro akkaunt"  # tugmada Pro belgisi ikonka bo'lib turadi
PRO_NO_DIAMONDS = "😔 Olmos yetarli emas. Olmos Konchi qazishidan chiqadi — yoki ⭐ Stars bilan oling."
NICK_ONLY_PRO = "🏷 Laqab faqat 3-daraja Pro foydalanuvchilar uchun. Batafsil: /pro"
NICK_LOCKED = "🔒 Sizning ismingiz qulflangan — uni o'zgartirib bo'lmaydi 😏"
NICK_CLEARED = "✅ Laqab o'chirildi. O'yinlarda Telegram ismingiz ko'rinadi."
NICK_HOW = "🏷 Laqab qo'yish: <code>/nickname Laqabingiz</code>\nO'chirish: <code>/nickname</code>"
PRO_EXPIRING = (f"⏳ Pro muddatingiz <b>24 soat ichida</b> tugaydi.\n"
                "Belgi, chegirma va boshqa imkoniyatlar saqlanib qolishi uchun /pro orqali uzaytiring.")
TIER_ICON = {1: "⭐", 2: "🌟", 3: "💫"}
TITLE_BTN = "👑 Vip toifa"
TITLE_ADD_BTN = "➕ Guruhga qo'shish"
TITLE_CHECK_BTN = "✅ Tekshirish"
TITLE_HAVE = "👑 Sizda Vip toifasi bor — cheksiz Pro 3."


def _pro_date(t) -> str:
    return f"{t + PRO_TZ:%d.%m.%Y}"


def _pro_have(uid: int) -> str:
    end, t = pro.until(uid), pro.title(uid)
    if not end:
        return ""
    if t:
        return f"\n\n{pro.badge()} Sizda <b>Vip</b> toifasi bor: cheksiz <b>Pro 3</b>."
    return f"\n\n{pro.badge()} Sizda <b>Pro {pro.tier(uid)}</b> bor: <b>{_pro_date(end)}</b> gacha."


def pro_info(uid: int) -> str:
    return f"{pro.badge()} <b>Pro AKKAUNT</b>\n\n<b>Pro</b> olish uchun darajani tanlang{_pro_have(uid)}"


def pro_tier(uid: int, tier: int, name: str) -> str:
    """Bitta daraja: ro'yxatda qanday ko'rinadi va nimalar beradi."""
    look = pro_look(escape(pro.short(pro.fancy(name))), tier)
    win = pro.WIN[tier]
    rows = ["☀️ Kunduzi o'yinda bo'lmasangiz yoki o'lgan bo'lsangiz ham guruhda yozish (tunda emas)",
            "🚪 /leave (o'yindan bepul chiqish, cheksiz)"]
    if tier >= 3:
        rows.append("🏷 /nickname (o'z nomini o'rnatish)")
    rows.append(f"🛒 Do'kon chegirmasi ({pro.DISCOUNT[tier]}%)")
    if win > 100:
        rows.append(f"💵 G'alaba puli x{win / 100:g} ({config.REWARD_WIN} o'rniga {config.REWARD_WIN * win // 100} 💵)")
    switch = ("\n\n<i>Boshqa darajadan o'tsangiz, qolgan kunlaringiz narx bo'yicha yangi darajaga "
              "qayta hisoblanadi.</i>") if pro.until(uid) and not pro.title(uid) else ""
    return (f"{TIER_ICON[tier]} <b>Pro {tier}</b>\n\n👁 Ro'yxatda ko'rinishi:\n{look}\n\n"
            + "\n".join(f"✅ {r}" for r in rows) + _pro_have(uid) + switch + card_note())


def pro_done(end, tier: int = 3) -> str:
    nick = "\n\n🏷 Laqab qo'yish: /nickname" if tier >= 3 else ""
    return f"🎉 {pro.badge()} <b>Pro {tier} faollashdi!</b>\nMuddat: <b>{_pro_date(end)}</b> gacha.{nick}"


def title_info() -> str:
    look = f"{pro.badge()} {pro.VIP_TAG} {escape(pro.short(pro.fancy('Ism')))} {pro.vip_tail()}"
    return ("👑 <b>Vip toifa — guruh egalari uchun</b>\n\n"
            "Admiral Mafia o'ynaladigan katta guruhingiz bormi? Unda Pro'ni <b>tekin</b> oling!\n\n"
            "📋 <b>Talablar:</b>\n"
            f"👥 {config.TITLE_MEMBERS} va undan ko'p a'zo\n"
            f"🎮 Kamida {config.TITLE_GAMES} ta o'yin o'ynalgan, oxirgisi {config.TITLE_DAYS} kun ichida\n"
            "👑 Guruhni aynan siz ochgan bo'lishingiz (egasi), bot esa guruhda turishi kerak\n\n"
            "🎁 <b>Mukofot:</b> muddatsiz <b>Pro 3</b> va ismingiz oldida <b>Vip</b> belgisi:\n"
            f"{look}\n\n"
            f"Bot guruhingizda bo'lmasa, avval «{TITLE_ADD_BTN}» orqali qo'shing, so'ng «{TITLE_CHECK_BTN}» ni bosing.")


def title_done(title: str) -> str:
    return (f"🎉 {pro.badge()} <b>Vip</b> toifasi berildi! ({escape(title)})\nEndi sizda cheksiz <b>Pro 3</b> bor.\n\n"
            "🏷 Laqab qo'yish: /nickname")


def title_none() -> str:
    return ("😔 Shartlarga mos guruh topilmadi.\nBot o'sha guruhda bo'lishi, siz guruh egasi bo'lishingiz, "
            f"guruhda kamida {config.TITLE_MEMBERS}+ a'zo va {config.TITLE_GAMES} ta o'yin, oxirgisi "
            f"{config.TITLE_DAYS} kun ichida bo'lishi kerak.")


def nick_set(nick: str) -> str:
    return f"✅ Laqabingiz: <b>{escape(nick)}</b>\nEndi o'yinlarda shu ism ko'rinadi."


INVITE_BTN = "🤝 Do'stni taklif qilish"
BACK_BTN = "⬅️ Orqaga"
INVITE_TEXT = "🎭 Admiral Mafia — Telegramdagi mafiya o'yini! Men bilan o'yna 👇"


def profile(u, inv) -> str:
    return (profile_card(u, inv)
            + "\n\n<i>🟢 ON bo'lgan buyumlar o'yinda o'zi ishlatiladi, 🔴 OFF (chizilgan) — saqlanib turadi</i>"
            + f"\n\n🤝 Har bir taklif qilingan do'st uchun <b>+{config.REF_BONUS} 💵</b>")


def ref_bonus(name: str) -> str:
    return (f"🎉 <b>{escape(pro.short(name))}</b> sizning taklifingiz bilan qo'shildi!\n"
            f"Taklif uchun hisobingizga <b>+{config.REF_BONUS} 💵</b> tushdi.")


def shop(dollars: int, uid: int | None = None, diamonds: int | None = None) -> str:
    """"Nima sotib olamiz?" - har buyum va nima qilishi; narxlar tugmalarda (handlers.shop_kb)."""
    on = uid is not None and pro.is_pro(uid)
    about = lambda s: s[:1].upper() + s[1:]
    codes = [i for i in config.SHOP if i not in config.SHOP_OFF] + list(config.SHOP_GEMS)
    rows = [f"{ITEMS[i]} - {about(ITEM_ABOUT[i])}" for i in codes]
    rows.append(f"{ROLE_SHOP_BTN} - Oldindan rol sotib olib, keyingi o'yinda shu rol bilan o'ynashingiz mumkin")
    sale = (f"\n{pro.badge()} <b>Pro chegirmasi: -{pro.DISCOUNT[pro._raw(uid)]}%</b> <i>(dollarli buyumlarga)</i>"
            if on else "")
    gems = f" · <b>{diamonds} 💎</b>" if diamonds is not None else ""
    return ("🛒 <b>Nima sotib olamiz?</b>\n\n" + "\n\n".join(rows)
            + f"\n\n💰 Balans: <b>{dollars} 💵</b>{gems}{sale}")


ROLE_SHOP_BTN = "🃏 Rolni tanlab olish"


def roles_shop(diamonds: int) -> str:
    blocks = []
    for team in (TOWN, MAFIA, NEUTRAL):
        rows = [f"{role(c)} — <b>{p} 💎</b>" for c, p in config.ROLE_PICKS.items() if ROLES[c].team == team]
        if rows:
            blocks.append(f"<b>{team_label(team)}</b>\n" + "\n".join(rows))
    return (f"🃏 <b>Rolni tanlab olish</b>\n\n💎 Balans: <b>{diamonds}</b>\n\n" + "\n\n".join(blocks) + "\n\n"
            f"<i>{ITEM_ABOUT['r_don'].capitalize()}. Ba'zi rollar faqat ko'p kishilik o'yinlarda chiqadi "
            "(yakka qotillar — 12 kishidan). Profilda 🔴 OFF qilsangiz, saqlanib turadi.</i>")


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


CARD_BTN = "💳 Karta orqali sotib olish"
CARD_NOTE = "💳 <b>Karta orqali</b> to'lamoqchimisiz?"


def card_note() -> str:
    """Stars bilan sotiladigan har ekran oxirida (tugmasi: handlers.card_btn)."""
    return f"\n\n{CARD_NOTE} Admin bilan bog'laning: @{config.CARD_ADMIN}"


def stars_menu(target: str | None = None) -> str:
    return "⭐ <b>STARS ORQALI TO'LOV</b>" + (f"\n\n🎁 Sovg'a: {target}" if target else "")


# ---------- olmos: karta orqali (admin tasdiqlaydi) ----------
def som(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def gem_shop(target: str | None = None) -> str:
    return ("💎 <b>OLMOS DO'KONI</b>" + (f"\n🎁 Sovg'a: {target}" if target else "")
            + "\n\nKerakli paketni tanlang:")


STARS_PAY_BTN = "⭐ Stars orqali to'lash"
COPY_CARD_BTN = "📋 Kartani nusxalash"
COPY_CARD_ABROAD_BTN = "📋 Chet el kartasini nusxalash"
CANCEL_ORDER_BTN = "❌ Bekor qilish"
CHECK_NEED_PHOTO = "📸 Iltimos, to'lov chekini <b>rasm (skrinshot)</b> qilib yuboring."
APPROVE_BTN = "✅ Tasdiqlash — pul keldi"
REJECT_WHY = {"n": "❌ Pul kelmadi", "s": "❌ Summa boshqa", "c": "❌ Chek emas"}  # admin tugmalari
REJECT_TELL = {"n": "pul kartaga kelmadi", "s": "kelgan summa buyurtmadagidan boshqa",
               "c": "yuborilgan rasm to'lov cheki emas"}  # foydalanuvchiga sabab
ORDER_CANCELLED = "❌ <b>Buyurtma bekor qilindi.</b>"
ORDER_CANCELLED_SHORT = "❌ Buyurtma bekor qilindi"
ORDER_DONE_ALREADY = "Bu buyurtma allaqachon ko'rib chiqilgan"


def card_off() -> str:
    return f"💳 Karta orqali to'lov hozircha sozlanmagan. Stars orqali to'lang yoki @{config.CARD_ADMIN} ga yozing."


def order_no(oid: int) -> str:
    return f"TOP-{oid}"


def _num(card: str) -> str:
    return " ".join(card[i:i + 4] for i in range(0, len(card), 4))


def _card_lines(c: dict) -> str:
    """Karta raqami, bank/turi va egasi (paneldan - escape), telefon (chet el kartasida)."""
    about = " · ".join(escape(x) for x in (c.get("b", ""), c.get("k", ""), c.get("o", "")) if x)
    return (f"<code>{_num(c['n'])}</code>" + (f"\n     {about}" if about else "")
            + (f"\n     📱 Bankka ulangan raqam: <code>{escape(c['t'])}</code>" if c.get("t") else ""))


def card_pay(o, cards: dict, target: str | None = None) -> str:
    """To'lov ekrani (vidjet chiqmasa - shu matn). cards - config.cards(); target - sovg'a oluvchi (mention)."""
    where = f"do'stingizga: {target}" if target else "hisobingizga"
    if set(cards) == {"uz"}:
        lines = f"💳 <b>Karta</b>: {_card_lines(cards['uz'])}\n"
    else:
        lines = "".join(f"{label}: {_card_lines(cards[k])}\n" for k, label in
                        (("uz", "🇺🇿 <b>O'zbekistondan</b>"), ("xorij", "🌍 <b>Chet eldan</b> (Rossiya va b.)"))
                        if k in cards)
    return ("💳 <b>To'lovni amalga oshiring</b>\n\n"
            f"📦 💎 {o.diamonds} <b>olmos</b> → {where}\n\n"
            + lines +
            f"💰 <b>To'lov summasi</b>: {som(o.amount)} so'm\n"
            f"🆔 <b>ID</b>: <code>{order_no(o.id)}</code>\n\n"
            "⚠️ <b>Muhim</b>: aynan shu summani yuboring (ko'p ham, kam ham emas).\n"
            "📸 To'lagach, <b>chekni (skrinshot)</b> shu yerga yuboring — admin tekshirib, olmosni hisobga tushiradi.\n\n"
            f"⏱ To'lov <b>{config.CARD_ORDER_MIN}</b> daqiqa amal qiladi.")


# To'lov kartasi (vidjet) ostidagi matn: karta raqami va summa kartaning o'zida - bu yerda takrorlanmaydi
# (egasining istagi, 2026-11-11). Vidjet chiqmasa - to'liq matnli ekran (card_pay) yuboriladi.
CARD_CAPTION = "📸 To'lagach, <b>chekni (skrinshot)</b> shu chatga yuboring — admin tekshirib, olmosni hisobga tushiradi."


def order_wait(o) -> str:
    return (f"⏳ <b>Chek qabul qilindi, to'lovingiz tekshirilmoqda</b> ({order_no(o.id)}).\n"
            f"💎 {o.diamonds} olmos · {som(o.amount)} so'm\n\n"
            "Admin tasdiqlagach, olmos hisobga tushadi va sizga xabar keladi.")


def order_expired() -> str:
    return (f"⌛️ <b>Buyurtma vaqti tugadi</b> ({config.CARD_ORDER_MIN} daqiqa). Yangi buyurtma bering.\n"
            f"To'lab qo'ygan bo'lsangiz, chek bilan @{config.CARD_ADMIN} ga yozing.")


def order_admin(o, payer: str, username: str | None, target: str | None, dup: int | None = None) -> str:
    """Bot egasiga chek rasmi ostida: tekshirib, tasdiqlaydi yoki sabab bilan rad etadi.
    dup - shu chek avval yuborilgan buyurtma (bitta skrinshot bilan ikki marta olmos olishga urinish)."""
    at = f" (@{escape(username)})" if username else ""
    warn = f"⚠️ <b>Diqqat: bu chek avval #{order_no(dup)} da yuborilgan!</b>\n\n" if dup else ""
    return (f"{warn}💳 <b>Karta to'lovi #{order_no(o.id)}</b>\n\n"
            f"👤 {payer}{at} · <code>{o.payer}</code>\n"
            f"💎 {o.diamonds} olmos" + (f" → 🎁 {target}" if target else "") + "\n"
            f"💰 Kutilgan summa: <b>{som(o.amount)} so'm</b>\n"
            "💳 Karta: " + " / ".join(("🌍 " if k == "xorij" else "") + "···· " + c["n"][-4:]
                                    for k, c in config.cards().items()) + "\n\n"
            "Bank ilovangizda <b>aynan shu summa</b> kelganini tekshiring.")


def check_not_delivered(o) -> str:
    return (f"⚠️ Chekingiz adminga yetib bormadi ({order_no(o.id)}). Iltimos, chek va shu ID bilan "
            f"@{config.CARD_ADMIN} ga yozing.")


def order_admin_done(text: str, why: str | None, admin: str) -> str:
    """why: None - tasdiqlandi, aks holda REJECT_WHY kaliti."""
    return text + (f"\n\n✅ Tasdiqlandi — {admin}" if why is None else f"\n\n{REJECT_WHY[why]} — {admin}")


def order_rejected(o, why: str) -> str:
    return (f"❌ <b>To'lov tasdiqlanmadi</b> ({order_no(o.id)}): {REJECT_TELL[why]}.\n"
            f"Xato bo'lsa, chek bilan @{config.CARD_ADMIN} ga yozing.")


def ask_send(currency: str) -> str:
    what = "💵 Pul" if currency == "dollars" else "💎 Olmos"
    return (f"{what} <b>yuborish</b>\n\nKimga va qancha? Masalan:\n"
            "<code>@username 100</code> yoki <code>123456789 100</code>")


def sent_ok(target: str, n: int, currency: str) -> str:
    return f"✅ {target} ga <b>{n} {CUR[currency]}</b> yuborildi."


def got_money(sender: str, n: int, currency: str) -> str:
    return f"🎁 {sender} sizga <b>{n} {CUR[currency]}</b> yubordi!"


def dollars_bought(diamonds: int, dollars: int) -> str:
    return f"✅ <b>{diamonds} 💎</b> → <b>{dollars} 💵</b> ga almashtirildi."


def diamonds_paid(n: int, target: str | None = None) -> str:
    return f"🎉 {target} ga <b>{n} 💎</b> sovg'a qilindi!" if target else f"🎉 Hisobingizga <b>{n} 💎</b> qo'shildi!"


PLACES = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _place(i: int) -> str:
    return PLACES[i] if i < len(PLACES) else f"{i + 1}."


def _top(title: str, entries: list[str]) -> str:
    """Har o'rin 2 qator: ism, ostida └ raqamlar."""
    head = f"🏆 <b>{title}</b>"
    return f"{head}\n\n" + ("\n".join(entries) if entries else "— hali o'yinlar yo'q —")


def top_groups(rows) -> str:
    """Guruh nomi ham ism kabi qisqaradi (pro.short)."""
    return _top("Top guruhlar", [f"{_place(i)} <b>{escape(pro.short(t or '?'))}</b>\n"
                                 f"└ 🎮 {f'{n:,}'.replace(',', ' ')} ta o'yin" for i, (t, n) in enumerate(rows)])


def top(rows, title: str, me: tuple[int, int, int] | None = None, show_me: bool = False, head: str = "") -> str:
    """me: (o'rin, g'alaba, o'yin) - so'ragan odamning o'rni (show_me: botdagi reytingda, guruhda emas)."""
    entries = []
    for i, (uid, name, w, gm) in enumerate(rows):
        w, gm = w or 0, gm or 0
        rate = round(100 * w / gm) if gm else 0
        entries.append(f"{_place(i)} {mention(uid, name or '?')}\n"
                       f"└ 🏆 {w} · 🎮 {gm} · {rate}% · {rank(w)}")
    text = _top(title, entries)
    if head:
        text = text.replace("\n\n", f"\n{head}\n\n", 1)
    if me:
        text += f"\n\n📍 Siz: {me[0]}-o'rin · 🏆 {me[1]} · 🎮 {me[2]}"
    elif show_me:
        text += "\n\n📍 Siz hali reytingda yo'qsiz — o'ynang va yuqoriga chiqing!"
    return text


MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
TOP_MONTH_BTN, TOP_ALL_BTN = "📅 Oylik", "🏆 Umumiy"


def month_name(key: str) -> str:
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def season_head(key: str, days_left: int) -> str:
    """Oylik reyting sarlavhasi ostida: qaysi oy, qancha qoldi, top-3 mukofoti."""
    prizes = " ".join(f"{p}{n}💎" for p, n in zip(PLACES, config.SEASON_PRIZES) if n)
    return f"📅 <i>{month_name(key)} mavsumi · tugashiga {days_left} kun</i>\n🎁 {prizes}"


def season_won(key: str, place: int, prize: int) -> str:
    return (f"🎉 <b>{month_name(key)} mavsumi yakunlandi!</b>\n"
            f"Siz oylik reytingda {_place(place - 1)} <b>{place}-o'rinni</b> egalladingiz va <b>{prize} 💎</b> oldingiz!")


def rules() -> str:
    out = ["📜 <b>ADMIRAL MAFIA rollari</b>"]
    for team in (TOWN, MAFIA, NEUTRAL):
        out.append(f"\n<b>{team_label(team)}</b>")
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
    return f"{shown_role(g, uid)} — {pm(g, uid)}"


VERBS = ["vahshiylarcha o'ldirildi.", "shafqatsizlarcha o'ldirildi.", "tongni ko'ra olmadi."]


def alive_composition(g: Game) -> str:
    out = []
    # Ko'rinish: "🤵🏻 Mafiya - 8" sarlavha, ostida "🤵🏼 𝐌𝐚𝐟𝐢𝐲𝐚 - 6, 🤵🏻 𝐃𝐨𝐧" (bir xil rollar soni bilan)
    for team, label in ((MAFIA, "🤵🏻 Mafiya"), (NEUTRAL, "🪙 Yakka rollar"), (TOWN, "🏘 Tinch aholilar")):
        ps = [p for p in g.alive() if p.team == team]
        if not ps:
            continue
        counts: dict[str, int] = {}
        for p in ps:
            counts[p.role] = counts.get(p.role, 0) + 1
        roles = ", ".join(role(c) + (f" - {k}" if k > 1 else "") for c, k in counts.items())
        out.append(f"<b>{label} - {len(ps)}</b>\n{roles}")  # sarlavha - oddiy Telegram qalin, rollar - matematik
    return "\n\n".join(out) + f"\n\n<b>Jami: {len(g.alive())}</b>"


def alive_list(g: Game) -> str:
    return "<b>Tirik o'yinchilar:</b>\n" + "\n".join(
        f"{g.num(p.uid)}. {mention(p.uid, p.name)}" for p in g.alive())  # boshidagi raqam saqlanadi


def vote_pm(g: Game) -> str:
    return f"🗳 <b>{g.day}-kun · ovoz berish</b>\nKimni osamiz? Tanlang:"


def vote_chosen(name: str | None) -> str:
    return f"✅ Ovozingiz: <b>{escape(name)}</b>" if name else "✅ Siz hech kimga ovoz bermadingiz"


def death_pm(hanged: bool, hunted: bool = False, collapsed: bool = False) -> str:
    how = ("Tunnel ustingizga qulab tushdi — kondan chiqa olmadingiz." if collapsed
           else f"{role('ovchi')} sizga rahm-shafqat qilmasdan joningizni oldi." if hunted
           else "Sizni shafqatsizlarcha osib o'ldirishdi!" if hanged else "Siz vahshiylarcha o'ldirildingiz!")
    return f"<b>{how}</b>\n💀 So'nggi so'zingizni yozishingiz mumkin.\n⏳ Vaqt: <b>{LAST_WORDS_SECS}</b> soniya"


def _item_row(label: str, qty: int, off: bool) -> str:
    """"🛡 <b>Qalqon</b>: 2 ta"; o'chirilgan (OFF) buyum ustidan chiziladi - o'yinga olinmaydi."""
    emo, name = label.split(" ", 1)
    row = f"<b>{name}</b>: {qty} ta"
    return f"{emo} " + (f"<s>{row}</s>" if off else row)


def profile_card(u, inv) -> str:
    have = {i.item: i for i in inv}
    items = "\n".join(_item_row(label, have[code].qty if code in have else 0, code in have and not have[code].enabled)
                      for code, label in ITEMS.items()
                      if not code.startswith("r_") and (code in ALWAYS_SHOWN or code in have and have[code].qty))
    picks = [(c, i) for c, i in have.items() if c.startswith("r_") and i.qty > 0 and c[2:] in ROLES]
    named = [(role(c[2:]) + (f" ×{i.qty}" if i.qty > 1 else ""), i.enabled) for c, i in picks]
    pick = ", ".join(t if on else f"<s>{t}</s>" for t, on in named) or "—"
    end = pro.until(u.telegram_id)
    # Matematik qalin (bold()) - faqat rollar va jamoalar; profil yozuvlari - oddiy Telegram qalin
    uid, title = u.telegram_id, pro.title(u.telegram_id)
    head = f"{pro.badge()} <b>Pro · Admiral Mafia</b>" if end else "<b>Admiral Mafia</b>"
    status = ""
    if title:
        status = f"{pro.badge()} <b>Vip</b>: cheksiz Pro 3\n"
    elif end:
        days = max(1, -(-int((end - pro._now()).total_seconds()) // 86400))  # yuqoriga yaxlitlash
        status = f"{pro.badge()} <b>Pro {pro.tier(uid)}</b>: <b>{end + PRO_TZ:%d.%m.%Y}</b> gacha ({days} kun)\n"
    # f-string ichida ' ishlatib bo'lmaydi (Python 3.11)
    games, wins, nxt = "<b>Jami o'yinlar</b>", "<b>G'alabalar</b>", "<b>Keyingi o'yindagi rol</b>"
    return (f"{head}\n\n"
            f"<b>ID</b>: <code>{u.telegram_id}</code>\n"
            f"👤 <b>Ism</b>: <b><i>{escape(pro.name(u.telegram_id, u.full_name))}</i></b>\n"
            f"🏅 <b>Unvon</b>: {rank(u.wins)}\n{status}\n"
            f"💵 <b>Dollar</b>: {u.dollars}\n💎 <b>Olmos</b>: {u.diamonds}\n\n{items}\n\n"
            f"🃏 {nxt}: {pick}\n\n"
            f"🎲 {games}: {u.games}\n🏆 {wins}: {u.wins}")
