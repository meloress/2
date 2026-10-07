"""Barcha o'zbekcha matnlar. Dvijok hodisalarini xabarlarga aylantiradi."""
from html import escape
from random import choice

from . import config
from .engine.game import DRAW, Event, Game
from .engine.roles import MAFIA, NEUTRAL, ROLES, TOWN

TEAM = {TOWN: "👨 Tinch aholi", MAFIA: "🤵 Mafiya", NEUTRAL: "🎭 Neytral"}
ITEMS = {"shield": "🛡 Qalqon", "verbena": "🧄 Verbena", "doc": "📄 Hujjat", "ticket": "🎟 Faol rol"}
ITEM_ABOUT = {
    "shield": "tungi o'limdan 1 marta saqlaydi",
    "verbena": "Vampir tishlashidan 1 marta saqlaydi",
    "doc": "tekshiruvda 1 marta \"Tinch\" ko'rsatadi",
    "ticket": "keyingi o'yinda oddiy Tinch o'rniga maxsus rol kafolatlanadi",
}
RANKS = [(0, "🐣 Yangi boshlovchi"), (3, "🔫 Ko'cha bezori"), (10, "🕶 Gangster"), (25, "💼 Kapo"),
         (50, "🎩 Konsilyere"), (100, "🤵‍♂️ Don"), (250, "👑 Krestniy ota")]


def rank(wins: int) -> str:
    return [title for need, title in RANKS if wins >= need][-1]
WINNER = {TOWN: "👨 Tinch aholi g'alaba qildi!", MAFIA: "🤵 Mafiya g'alaba qildi!",
          "qotil": "🔪 Qotil yakka g'alaba qildi!", "vampir": "🧛 Vampir yakka g'alaba qildi!",
          DRAW: "🤝 Durang!"}


def mention(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={uid}">{escape(name)}</a>'


def pm(g: Game, uid: int) -> str:
    p = g.get(uid)
    return mention(p.uid, p.name)


def role(code: str) -> str:
    emoji, name = ROLES[code].name.split(" ", 1)
    return f"{emoji} {bold(name)}"


# ---------- lobby ----------
def lobby(names: list[str], left: int) -> str:
    body = "\n".join(f"{i}. {escape(n)}" for i, n in enumerate(names, 1)) or "— hali hech kim yo'q —"
    return (f"🎮 <b>MAFIA ZONE</b> — ro'yxatdan o'tish boshlandi!\n\n"
            f"👥 O'yinchilar ({len(names)}):\n{body}\n\n⏳ Qoldi: {left} soniya")


JOIN_BTN = "🤝 Qo'shilish"


def lobby_reminder(n: int) -> str:
    return f"⏳ <b>30 soniya qoldi!</b> Hozir {n} kishi ro'yxatda. Ulgurib qoling 👇"
NEED_PLAYERS = "😔 O'yinchilar yetarli emas (kamida 4 kishi kerak). O'yin bekor qilindi."
GAME_EXISTS = "⚠️ Bu guruhda o'yin allaqachon ketmoqda."
NOT_ADMIN_WARN = ("⚠️ Bot guruhda admin emas. O'yin bo'ladi, lekin tunda va o'liklarning xabarlarini "
                  "o'chira olmayman. Botni admin qiling (xabarlarni o'chirish huquqi bilan).")
JOINED = "✅ " + "𝐌𝐮𝐯𝐚𝐟𝐟𝐚𝐪𝐢𝐲𝐚𝐭𝐥𝐢 𝐫𝐨'𝐲𝐱𝐚𝐭𝐝𝐚𝐧 𝐨'𝐭𝐝𝐢𝐧𝐠𝐢𝐳!" + "\nGuruhga qayting va o'yin boshlanishini kuting."
ALREADY_IN_GAME = "⚠️ Siz allaqachon boshqa o'yindasiz."
NO_LOBBY = "⚠️ Bu guruhda ro'yxatdan o'tish ketmayapti."
LOBBY_FULL = ("⚠️ O'yin to'lgan (60 kishi). Sizni keyingi o'yin navbatiga yozdim — "
              "ro'yxat ochilishi bilan xabar beraman 🔔")
BANNED = "⛔️ Siz botdan foydalanishdan chetlatilgansiz."
STOPPED = "🛑 O'yin to'xtatildi."
ONLY_ADMIN = "⚠️ Bu buyruq faqat guruh adminlari uchun."
GROUP_ONLY = "Bu buyruq guruhda ishlaydi."


def role_card(g: Game, uid: int) -> str:
    p = g.get(uid)
    text = f"Siz - {role(p.role)} siz!\n{ROLES[p.role].about}"
    mates = g.teammates(uid)
    if mates:
        text += "\n\n🤝 <b>Sheriklaringizni eslab qoling!</b>\n" + "\n".join(
            f"{escape(m.name)} - {role(m.role)}" + ("" if m.alive else " 💀") for m in mates)
    own = [f"{ITEMS[i]} ×{q}" for i, q in p.items.items() if q > 0 and i in ITEMS]
    if own:
        text += "\n\n🎒 Buyumlaringiz: " + ", ".join(own)
    return text


def game_started(g: Game) -> str:
    return _game_started(g) + "\n\n" + composition(g)


def _game_started(g: Game) -> str:
    return choice([
        f"🎬 <b>O'yin boshlandi!</b> Shahar darvozalari yopildi — ichkarida {len(g.players)} kishi qoldi.\n"
        "Ulardan ba'zilari tinch fuqaro emas... 🤫 Rolingizni botdan bilib oling.",
        f"🎬 <b>Parda ochildi!</b> {len(g.players)} nafar o'yinchi, bitta shahar va ko'plab sirlar.\n"
        "Kim do'st, kim dushman — tez orada bilinadi. 🤫 Rolingiz botda.",
        f"🎬 <b>Mafia Zone</b> shahriga xush kelibsiz! {len(g.players)} kishining taqdiri hal bo'ladi.\n"
        "Hech kimga ishonmang... 🤫 Rolingizni botning shaxsiy chatida ko'ring.",
    ])


# ---------- tun ----------
ROLE_PROMPT = {
    "don": "🤵🏻 Don, oila sizning buyrug'ingizni kutyapti. Bu tun kim yo'qoladi?",
    "mafiya": "🤵 Oila yig'ildi. Kimni nishonga olamiz? (Yakuniy so'z Donniki)",
    "komissar": "🕵️‍♂️ Komissar, shahar sizga umid bog'lagan. Tekshiramizmi yoki otamizmi?",
    "doktor": "👨‍⚕️ Doktor, chamadoningiz tayyor. Bu tun kimning hayotini saqlaysiz?",
    "kezuvchi": "💃 Kezuvchi, kimga uyqu dori berasiz? U bu tun hech narsa qila olmaydi.",
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


def act_feed(role_code: str, kind: str = "") -> str:
    t = ACT_FEED.get((role_code, kind)) or ACT_FEED.get(role_code) or "🌑 Kimdir tunda harakatga keldi..."
    return t.format(r=role(role_code))


def vote_feed(g: Game, voter: int, target: int | None) -> str:
    if target is None:
        return f"{nm(g, voter)} hech kimga ovoz bermadi"
    return f"{nm(g, voter)} - {nm(g, target)} ga ovoz berdi"


NIGHT_CAPTION = ("🌚🌃 <b>Tun</b>\nKo'chaga faqat jasur va qo'rqmas odamlar chiqishdi.\n"
                 "Ertalab tirik qolganlarni sanaymiz...")
DAY_CAPTION = "🌝 <b>Xayrli tong</b>\n🌄 <b>Kun</b>\nShamollar tundagi mish-mishlarni butun shaharga yetkazmoqda..."


def night_start(g: Game, secs: int) -> str:
    return NIGHT_CAPTION


def night_prompt(g: Game, uid: int) -> str:
    r = g.get(uid).role
    return f"🌙 <b>{g.day}-tun</b>\n\n" + ROLE_PROMPT.get(r, f"{role(r)}, harakatingizni tanlang:")


def chosen(name: str | None) -> str:
    return f"Siz <b>{escape(name)}</b>ni tanladingiz" if name else "✅ Tanlovingiz qabul qilindi"


def mafia_voted(voter: str, target: str) -> str:
    return f"{escape(voter)} - {escape(target)} ga ovoz berdi"


def relay(name: str, text: str) -> str:
    return f"<b>{escape(name)}</b>:\n{escape(text)}"


def overheard(text: str) -> str:
    return f"👂 <i>Devor ortidan pichirlash eshitildi:</i> {escape(text)}"


LAST_WORDS_SECS = 60


LAST_WORDS_LATE = f"⌛️ Kechikdingiz — so'nggi so'z uchun {LAST_WORDS_SECS} soniya tugadi. Xabaringiz hech kimga yuborilmadi."


def victims(ev: list[Event]) -> list[int]:
    """Hodisalardan halok bo'lganlar (so'nggi so'z uchun). AFK va chiqib ketganlar kirmaydi."""
    out = []
    for e in ev:
        uid = {"killed": e.target, "hanged": e.target, "revenge": e.target, "linked": e.target,
               "tulki": e.target}.get(e.kind)
        if uid is not None and uid not in out:
            out.append(uid)
    return out


def last_words(g: Game, uid: int, text: str) -> str:
    return f"🕯 O'limidan oldin kimdir <b>{nm(g, uid)}</b> ning qichqirganini eshitdi:\n<i>{escape(text)}</i>"


SAVED = ["💉 Kimdir bu tun o'lim yoqasidan qaytdi! Ajal bu safar quruq ketdi.",
         "💉 Tunda kimgadir hujum bo'ldi... lekin u omon qoldi! Shaharda qahramonlar bor.",
         "💉 Qotil bu tun omadsiz chiqdi — qurboni tirik qoldi!"]
QUIET = ["🌤 Mo'jiza! Bu tun hech kim halok bo'lmadi. Lekin bu uzoq davom etmaydi...",
         "🌤 Tinch tun. Hamma tirik... hozircha.",
         "🌤 Hech kim o'lmadi. Mafiya nimanidir rejalashtiryaptimi?"]


def morning(g: Game, ev: list[Event]) -> tuple[list[str], list[tuple[int, str]]]:
    """([guruhga alohida xabarlar], [(uid, shaxsiy matn)])"""
    pub, priv = [], []
    n = lambda uid: nm(g, uid)
    w = lambda uid: who(g, uid)
    for e in ev:
        k = e.kind
        if k == "killed":
            if e.data["by"] == ["curse"]:
                pub.append(f"🔮 {w(e.target)} la'natlangan insonga duch keldi va shafqatsiz o'lim topdi.\n"
                           f"Aytishlaricha, bu ishni {role('sehrgar')} qilgan")
            else:
                killers = ", ".join(dict.fromkeys(role(g.get(u).role) for u in e.data.get("killers", [])))
                killers = killers or "noma'lum kimdir"
                pub.append(f"Tunda {w(e.target)}...\n{choice(VERBS)}\nAytishlaricha unikiga {killers} kelgan")
        elif k == "saved":
            pub.append(choice(SAVED))
        elif k == "mafia_idle":
            pub.append(f"🤵 Mafialar kelisha olishmadi va {role('don')} hech kimni tanlamadi!\n"
                       "Mafiya bu tun hech kimga tegmadi..")
        elif k == "mafia_result":
            text = (f"Mafiyaning ovoz berish jarayonida <b>{n(e.target)}</b> vahshiylarcha o'ldirildi."
                    if e.data["killed"] else f"Mafiyaning nishoni <b>{n(e.target)}</b> bu tun omon qoldi...")
            priv += [(p.uid, text) for p in g.players if p.alive and p.team == MAFIA]
        elif k == "revenge":
            pub.append(f"💥 {w(e.uid)} yolg'iz ketmadi — {w(e.target)} ham u bilan birga halok bo'ldi!")
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
            pub.append(score + f"<b>{n(e.target)}</b> kunduzgi yig'ilishda osildi!\nU {role(e.data['role'])} edi..")
        elif k == "spared":
            pub.append(f"📊 <b>Tasdiqlash natijalari:</b>\n{e.data['yes']} 👍 | {e.data['no']} 👎\n\n"
                       f"Aholi <b>{n(e.target)}</b>ni osishga rozi bo'lmadi... Bu safar u omon qoldi.")
        elif k == "no_hang":
            pub.append(choice(["Ovoz berish yakunlandi:\nAholi kelisha olmadi... Shu sababli bugun hech kim osilmadi...",
                               "Ovoz berish yakunlandi:\nFikrlar ikkiga bo'lindi... Dor bugun bo'sh qoldi..."]))
        elif k == "guard_saved":
            pub.append(f"👨‍🦳 Arqon tortilay deganda {role('qorovul')} yetib keldi va <b>{n(e.target)}</b>ni "
                       "dordan qutqarib qoldi!")
        elif k == "tulki":
            pub.append(f"🦊 {w(e.uid)} ayyorlik qildi: unga birinchi ovoz bergan {w(e.target)} ham u bilan ketdi!")
        elif k == "blocked":
            priv.append((e.uid, "💤 Boshingiz aylanib, ko'zingiz yumildi... Kimdir sizga uyqu dori berdi. "
                                "Bu tun hech narsa qila olmadingiz."))
        elif k == "stolen":
            priv.append((e.target, "🤹 Kimdir sizning tungi rejangizni o'g'irlab ketdi!"))
            priv.append((e.uid, f"🤹 Ajoyib fokus! {n(e.target)}ning harakatini o'zlashtirdingiz."))
        elif k == "saw_role":
            priv.append((e.uid, f"🤹 {n(e.target)}da o'g'irlaydigan harakat yo'q edi, lekin uning sirini bildingiz: "
                                f"{role(e.data['role'])}"))
        elif k == "checked":
            text = f"🔍 Tekshiruv natijasi: {n(e.target)} — <b>{TEAM[e.data['result']]}</b>"
            priv.append((e.uid, text))
            if g.get(e.uid).role == "komissar" and (s := g.by_role("serjant")):
                priv.append((s.uid, f"🕵️‍♂️ Komissardan xabar: {text}"))
        elif k == "interview":
            vis = ", ".join(n(v) for v in e.data["visitors"]) or "hech kim"
            priv.append((e.uid, f"🎤 Intervyu tayyor! Bu tun {n(e.target)}ning oldiga kelganlar: {vis}"))
        elif k == "witness":
            priv.append((e.uid, f"👀 Siz {n(e.target)}ning uyi oldida qotillikni o'z ko'zingiz bilan ko'rdingiz!\n"
                                "Qotil(lar): " + ", ".join(f"<b>{n(x)}</b>" for x in e.data["killers"])))
        elif k == "dug":
            extra = " va 💎 <b>olmos</b>" if e.data["diamond"] else ""
            priv.append((e.uid, f"⛏ Tunnel qazib <b>{e.data['dollars']} 💵</b>{extra} topdingiz!"))
        elif k == "item_used":
            priv.append((e.uid, f"{ITEMS[e.data['item']]} sizni qutqardi: {ITEM_ABOUT[e.data['item']]}."))
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
            f"🗣 Muhokama uchun {secs} sekund")


def vote_prompt(g: Game, secs: int) -> str:
    return (f"⚖️ <b>Aybdorlarni aniqlash va jazolash vaqti keldi!</b>\n"
            f"Ovoz berish uchun {secs} sekund\nOvoz berish uchun botga o'ting!")


SKIP_BTN = "🤐 Hech kimga ovoz bermayman"


def confirm_prompt(g: Game, secs: int) -> str:
    return (f"Rostdan ham <b>{nm(g, g.candidate)}</b> ni osishni hohlaysizmi?\n\n"
            f"⏰ Tasdiqlash uchun vaqt: {secs} sekund")


def confirm_result(g: Game) -> str:
    yes, no = g.confirm_tally()
    return f"Rostdan ham <b>{nm(g, g.candidate)}</b> ni osishni hohlaysizmi?\n\n{yes} 👍 | {no} 👎 — vaqt tugadi"


def ghost(name: str, text: str) -> str:
    return f"👻 <b>{escape(name)}</b> (narigi dunyodan): {escape(text)}"


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
            f"{mention(a, a_name)} sizga para bo'lish so'rovini yubormoqda 🪽")


def couple_rejected(b: int, b_name: str) -> str:
    return f"❌ 🪽 {mention(b, b_name)} taklifni rad etdi."


def couple_made(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"❤️ 🪽 ❤️ {mention(a, a_name)} va {mention(b, b_name)} endi para!"


def couple_broken(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"💔 🪽 {mention(a, a_name)} va {mention(b, b_name)} parasi bekor qilindi."


def couple_show(a: int, a_name: str, b: int, b_name: str) -> str:
    return f"❤️ {mention(a, a_name)} ❤️ {mention(b, b_name)}"


NO_GAME ="🎮 Hozir o'yinda emassiz. Guruhda /game bilan boshlang!"


WINNER_STORY = {
    TOWN: "Shahar ozod! Oxirgi mafiyachi ham qo'lga olindi. Ko'chalarda bayram! 🎊",
    MAFIA: "Shahar endi Mafiya qo'lida. Don sigarasini tutatib, jilmaydi... 🚬",
    "qotil": "Shahar huvullab qoldi. Faqat Qotil qon izlarini artib, yo'lida davom etdi... 🔪",
    "vampir": "Tun abadiy bo'ldi. Vampir taxtga o'tirdi... 🦇",
    DRAW: "Hech kim g'olib bo'lmadi. Shahar xarobaga aylandi... 🌫",
}


def game_over(g: Game, minutes: int | None = None) -> str:
    won = [p for p in g.players if p.won]
    rest = [p for p in g.players if not p.won]
    lines = ["🏁 <b>O'yin tugadi!</b>", "", "🏆 <b>G'oliblar:</b>"]
    lines += [f"    {i}. {pm(g, p.uid)} - {role(p.role)}" for i, p in enumerate(won, 1)] or ["    —"]
    if rest:
        lines += ["", "<b>Qolgan o'yinchilar:</b>"]
        lines += [f"    {i}. {pm(g, p.uid)} - {role(p.role)}" for i, p in enumerate(rest, len(won) + 1)]
    if minutes is not None:
        lines += ["", f"O'yin: {minutes} minut davom etdi"]
    return "\n".join(lines)


def result_pm(won: bool, reward: int, u=None, inv=()) -> str:
    head = (f"🎉 <b>Siz g'alaba qozondingiz!</b>\nYutganingiz uchun sizga {reward} 💵 berildi" if won
            else "😔 <b>O'yin tugadi!</b>\nBu safar yutqazdingiz." + (f" Ishtirok uchun {reward} 💵" if reward else ""))
    return head + ("\n\n" + profile_card(u, inv) if u else "")


NEXT_OK = "🔔 Bu guruhda keyingi o'yin boshlanganda sizga xabar beraman."


def next_game(title: str) -> str:
    return f"🎮 <b>{escape(title)}</b> guruhida yangi o'yin boshlandi! Qo'shilish uchun tugmani bosing 👇"


# ---------- PM: profil, do'kon ----------
def welcome() -> str:
    return ("👋 <b>Salom! Mafiya olamiga xush kelibsan!</b>\n"
            "<b>Men 🤵 Mafia Zone o'yinining rasmiy botiman.</b>\n\n"
            "<b>Bu shunchaki o'yin emas — sirlar, hiyla va ishonch dunyosi.</b>\n"
            "<b>Guruhga qo'sh, rolingni ol, o'zingni ko'rsat!</b> 🎯\n"
            "🎭 <b>Seni roling kutmoqda...</b>")


def start_pm() -> str:
    return ("🎮 <b>MAFIA ZONE</b> ga xush kelibsiz!\n\n"
            "Meni guruhga qo'shing, admin qiling va /game buyrug'ini yozing.\n\n"
            "/profile — profil va buyumlar\n/shop — do'kon\n/bonus — kunlik bonus\n/top — reyting\n/rules — rollar")


def profile(u, inv, ref_link: str = "") -> str:
    return (profile_card(u, inv)
            + "\n\n<i>Tugmalar: ✅ yoqilgan buyum o'yinda avtomatik ishlatiladi</i>"
            + (f"\n\n🤝 Do'stlaringizni taklif qiling — har biri uchun +{config.REF_BONUS} 💵:\n{ref_link}" if ref_link else ""))


def ref_bonus(name: str) -> str:
    return f"🤝 Sizning havolangiz orqali <b>{escape(name)}</b> qo'shildi! +{config.REF_BONUS} 💵"


def shop(dollars: int) -> str:
    rows = "\n".join(f"{ITEMS[i]} — {p} 💵: {ITEM_ABOUT[i]}" for i, p in config.SHOP.items() if i not in config.SHOP_OFF)
    return f"🛒 <b>Do'kon</b>\n\nBalans: {dollars} 💵\n\n{rows}"


BOUGHT = "✅ Sotib olindi!"
NO_MONEY = "😔 Pul yetarli emas."
BONUS_OK = "🎁 Kunlik bonus olindi!"
BONUS_WAIT = "⏳ Bonusni 24 soatda bir marta olish mumkin."
def exchange_btn() -> str:
    return f"💎 1 → {config.DIAMOND_RATE} 💵"


def top(rows, title: str) -> str:
    if not rows:
        return f"🏆 {title}\n\n— hali o'yinlar yo'q —"
    medals = ["🥇", "🥈", "🥉"]
    body = "\n".join(f"{medals[i] if i < 3 else f'{i + 1}.'} {escape(name or '?')} — {w} 🏆 / {gm} 🎮 · {rank(w or 0)}"
                     for i, (name, w, gm) in enumerate(rows))
    return f"🏆 <b>{title}</b>\n\n{body}"


def rules() -> str:
    out = ["📜 <b>MAFIA ZONE rollari</b>"]
    for team in (TOWN, MAFIA, NEUTRAL):
        out.append(f"\n<b>{TEAM[team]}</b>")
        out += [f"{r.name} — {r.about}" for r in ROLES.values() if r.team == team]
    return "\n".join(out)


_BOLD = {**{chr(65 + i): chr(0x1D400 + i) for i in range(26)}, **{chr(97 + i): chr(0x1D41A + i) for i in range(26)}}


def bold(s: str) -> str:
    """𝐊𝐨𝐦𝐢𝐬𝐬𝐚𝐫 uslubidagi qalin harflar (matematik bold)."""
    return "".join(_BOLD.get(c, c) for c in s)


def nm(g: Game, uid: int) -> str:
    p = g.get(uid) if uid is not None else None
    return escape(p.name) if p else "?"  # o'yinchi chiqib ketgan bo'lsa ham xabar yiqilmasin


def who(g: Game, uid: int) -> str:
    return f"{role(g.get(uid).role)} - {nm(g, uid)}"


VERBS = ["vahshiylarcha o'ldirildi.", "shafqatsizlarcha o'ldirildi.", "tongni ko'ra olmadi."]


def alive_composition(g: Game) -> str:
    out = []
    for team, label in ((MAFIA, "🤵🏻 Mafiya"), (NEUTRAL, "👤 Yakka rollar"), (TOWN, "🏘 Tinch aholilar")):
        ps = [p for p in g.alive() if p.team == team]
        if not ps:
            continue
        counts: dict[str, int] = {}
        for p in ps:
            counts[p.role] = counts.get(p.role, 0) + 1
        roles = ", ".join(role(c) + (f" - {k}" if k > 1 else "") for c, k in counts.items())
        out.append(f"<b>{label} - {len(ps)}</b>\n{roles}")
    return "\n\n".join(out) + f"\n\n<b>Jami: {len(g.alive())}</b>"


def alive_list(g: Game) -> str:
    return "<b>Tirik o'yinchilar:</b>\n" + "\n".join(
        f"{i}. {escape(p.name)}" for i, p in enumerate(g.players, 1) if p.alive)


def vote_pm(g: Game) -> str:
    return f"🗳 <b>{g.day}-kun · ovoz berish</b>\nKimni osamiz? Tanlang:"


def vote_chosen(name: str | None) -> str:
    return f"✅ Ovozingiz: <b>{escape(name)}</b>" if name else "✅ Siz hech kimga ovoz bermadingiz"


composition = alive_composition


def death_pm(hanged: bool) -> str:
    how = "Sizni shafqatsizlarcha osib o'ldirishdi!" if hanged else "Sizni vahshiylarcha otib o'ldirishdi!"
    return f"{how}\n💀 So'nggi so'zingizni aytishingiz mumkin.\n⏰ Vaqt: {LAST_WORDS_SECS} sekund"


def profile_card(u, inv) -> str:
    have = {i.item: i.qty for i in inv}
    items = "\n".join(f"{label.split(' ', 1)[0]} {bold(label.split(' ', 1)[1])}: {have.get(code, 0)} ta"
                      for code, label in ITEMS.items())
    return (f"<b>{bold('Mafia Zone')}</b>\n\n"
            f"{bold('ID')}: <code>{u.telegram_id}</code>\n👤 {bold('Ism')}: {escape(u.full_name)}\n"
            f"🎖 {bold('Unvon')}: {rank(u.wins)}\n\n"
            f"💵 {bold('Dollar')}: {u.dollars}\n💎 {bold('Olmos')}: {u.diamonds}\n\n{items}\n\n"
            f"🎲 {bold('Jami o' + chr(39) + 'yinlar')}: {u.games}\n🏆 {bold('G' + chr(39) + 'alabalar')}: {u.wins}")
