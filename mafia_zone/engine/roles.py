"""29 rol ta'rifi. Faqat ma'lumot: qoidalar game.py da."""
from dataclasses import dataclass

TOWN, MAFIA, NEUTRAL = "town", "mafia", "neutral"


@dataclass(frozen=True)
class Role:
    code: str
    name: str
    team: str
    actions: tuple[str, ...] = ()  # tungi harakat turlari
    about: str = ""


_ROLES = [
    # --- Tinch aholi ---
    Role("tinch", "👨 Tinch aholi", TOWN, (), "Kunduzi muhokama va ovoz berishda qatnashasiz. Mafiyani toping!"),
    Role("komissar", "🕵️‍♂️ Komissar Katani", TOWN, ("check", "shoot"), "Har tunda 1 kishini tekshirasiz yoki otasiz."),
    Role("serjant", "👮 Serjant", TOWN, (), "Komissar yordamchisi. Komissar o'lsa, uning o'rnini egallaysiz."),
    Role("doktor", "👨‍⚕️ Doktor", TOWN, ("heal",), "Tunda 1 kishini o'limdan saqlaysiz. O'zingizni ketma-ket 2 tun davolay olmaysiz."),
    Role("daydi", "🍾 Daydi", TOWN, ("visit",), "Tunda bir uyga borasiz. U yerda qotillik bo'lsa, qotilni ko'rasiz."),
    Role("kezuvchi", "💃 Kezuvchi", TOWN, ("block",), "Tunda 1 kishini uxlatasiz: u harakat qila olmaydi va ertaga ovoz bera olmaydi."),
    Role("afsungar", "💣 Afsungar", TOWN, (), "Tunda o'ldirilsangiz, kunduzi qotilingizni olib ketasiz yoki kechirasiz. Osilsangiz, 1 kishini darhol olib ketasiz."),
    Role("voris", "🧬 Voris", TOWN, (), "Don o'ldirsa - Mafiyaga, Komissar otsa - Serjantga aylanasiz."),
    Role("janob", "🎖 Janob", TOWN, (), "Kunduzgi ovoz berishda ovozingiz 2 ta hisoblanadi."),
    Role("ovchi", "🏹 Ovchi", TOWN, ("check",), "Tunda 1 kishining rolini bilasiz va kunduzi uni o'ldirishingiz mumkin. "
         "Tinchni o'ldirsangiz, 100-200 💵 jarima."),
    Role("donishmand", "👨‍🏫 Donishmand", TOWN, (), "Tunda Mafiya va Komissar yozishmalarini ismsiz eshitasiz."),
    Role("suitsid", "🤦 Suitsid", TOWN, (), "Kunduzi osilsangiz, g'olib bo'lasiz. Tunda o'lsangiz - oddiy o'lim."),
    Role("qorovul", "👨‍🦳 Qorovul", TOWN, ("guard",), "Tunda 1 kishini himoyalaysiz: u ertaga osilmaydi."),
    Role("podshoh", "🤴 Podshoh", TOWN, (), "Muhim figura. Qorovulsiz osilsangiz, Mafiya va Neytrallar g'alaba qiladi."),
    # --- Mafiya ---
    Role("mafiya", "🤵🏼 Mafiya", MAFIA, ("mafia_kill",), "Mafiya jamoasi a'zosi. Don o'lsa, uning o'rnini egallashingiz mumkin."),
    Role("don", "🤵🏻 Don", MAFIA, ("mafia_kill",), "Mafiya sardori. Tunda kim o'lishini siz hal qilasiz."),
    Role("jurnalist", "👩‍💻 Jurnalist", MAFIA, ("interview",), "O'yinchidan intervyu olasiz va uning oldiga kim kelganini ko'rasiz."),
    Role("yollanma", "🕴 Yollanma qotil", MAFIA, ("hit",), "Don qaroridan tashqari yana 1 kishini o'ldirasiz."),
    Role("advokat", "👨‍💼 Advokat", MAFIA, ("disguise",), "1 mafiyadoshni himoyalaysiz: tekshiruvda u Tinch bo'lib ko'rinadi."),
    Role("aka", "🧔 Aka", MAFIA, ("pair",), "Uka bilan bir nishonni tanlasangiz, nishon o'ladi. Biringiz o'lsa, ikkinchingiz ham o'ladi."),
    Role("uka", "👦 Uka", MAFIA, ("pair",), "Aka bilan bir nishonni tanlasangiz, nishon o'ladi. Biringiz o'lsa, ikkinchingiz ham o'ladi."),
    # --- Neytrallar ---
    Role("sotqin", "🤓 Sotqin", NEUTRAL, (), "Tinchlar orasida yashaysiz. Mafiya yutsa va tirik bo'lsangiz, siz ham yutasiz."),
    Role("qotil", "🔪 Qotil", NEUTRAL, ("kill",), "Har tunda 1 kishini o'ldirasiz. Mafiya sizga tegolmaydi. Oxirgi tirik qoling!"),
    Role("gazabkor", "🧟 G'azabkor", NEUTRAL, ("rage", "sacrifice"), "Har tunda 1 kishini o'ldirasiz. 3 qurbondan keyin o'zingizni qurbon qilib g'olib bo'lasiz."),
    Role("sehrgar", "🧙 Sehrgar", NEUTRAL, ("curse",), "Tunda 1 uyni la'natlaysiz: o'sha tun unga kelganlar o'ladi. Don, Qotil va Komissar sizga tegolmaydi."),
    Role("vampir", "🧛 Vampir", NEUTRAL, ("bite",), "Tunda o'yinchini tishlaysiz. Doktor, Qalqon yoki Verbena saqlamasa, u o'ladi."),
    Role("qaroqchi", "🦹‍♂️ Qaroqchi", NEUTRAL, ("rob",), "O'yinchilardan pul, buyum yoki ovoz huquqini o'g'irlaysiz."),
    Role("konchi", "👷‍♂️ Konchi", NEUTRAL, ("dig",), "Har tunda qazib 10 dan 2000 gacha 💵 va 💎 topasiz. "
         "Tunnel qulashi mumkin (🪖 Temir qalqon saqlaydi)."),
    Role("tulki", "🦊 Tulki", NEUTRAL, (), "Kunduzi osilsangiz, sizga 1-ovoz bergan bilan birga o'lasiz va g'olib bo'lasiz."),
    Role("aferist", "🤹 Aferist", NEUTRAL, ("steal",), "Boshqa o'yinchining tungi harakatini o'g'irlaysiz."),
]

ROLES: dict[str, Role] = {r.code: r for r in _ROLES}

# Harakat turlari: nishonsizlari
NO_TARGET = {"dig", "sacrifice"}

ACTION_LABELS = {
    "check": "🔍 Tekshirish",
    "shoot": "🔫 Otish",
    "heal": "💉 Davolash",
    "visit": "🚶 Borish",
    "block": "💤 Uxlatish",
    "guard": "🛡 Himoyalash",
    "mafia_kill": "🔪 O'ldirish",
    "interview": "🎤 Intervyu",
    "hit": "🎯 Yo'q qilish",
    "disguise": "🎭 Niqoblash",
    "pair": "👊 Hujum",
    "kill": "🔪 So'yish",
    "rage": "😡 O'ldirish",
    "sacrifice": "🔥 O'zini qurbon qilish",
    "curse": "🪄 La'natlash",
    "bite": "🦷 Tishlash",
    "rob": "💰 O'g'irlash",
    "dig": "⛏ Qazish",
    "steal": "🃏 Harakatni o'g'irlash",
    "blast": "💥 Olib ketish",
}
