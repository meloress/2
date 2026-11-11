"""O'yinchilar soniga qarab rollarni taqsimlash (spec, 6-bo'lim)."""
import random

from .roles import MAFIA, ROLES

MIN_PLAYERS, MAX_PLAYERS = 4, 60
MAFIA_POOL = ["mafiya", "advokat", "jurnalist", "yollanma", "aka_uka"]
NEUTRAL_POOL = ["qotil", "gazabkor", "sehrgar", "vampir", "qaroqchi", "konchi", "tulki", "aferist", "sotqin"]
TOWN_POOL = ["daydi", "kezuvchi", "afsungar", "voris", "janob", "ovchi", "donishmand", "suitsid", "qorovul", "podshoh"]
CORE = {"don", "komissar", "tinch", "mafiya"}  # o'chirib bo'lmaydi
# Balans: kichik o'yin bir harakatda tugab qolmasin, katta o'yinda "bo'sh" Tinch aholi kam bo'lsin
SMALL_GAME = 7  # shu songacha Donni bir zarbada olib ketadigan rollar tushmaydi
SMALL_BANNED = {"afsungar", "suitsid", "podshoh"}
KILLER_NEUTRALS = {"qotil", "gazabkor", "sehrgar", "vampir"}
KILLERS_FROM = 12  # har tunda o'ldiradigan neytrallar shu sondan
BIG_GAME = 30  # shu sondan ba'zi rollar 3 tagacha takrorlanadi
REPEATABLE = ["daydi", "kezuvchi", "ovchi", "janob"]
MAX_KILLERS = 1  # prod (2026-11, 12+ kishi): 2 qotil neytralli o'yinda tinchlar 29% yutardi (0-1 tasida 50-56%)
# Prod (2026-10-07..11-11, 926 o'yin): tinchlar 5/6/10 kishida ~66%, 7 kishida 43% yutardi -> maxsus tinch rollar
# soni shu sonlarda 1 taga kamroq/ko'proq. ponytail: qo'lda jadval; yangi statistika bilan qayta ko'rib chiqiladi
TOWN_SPECIAL_ADJ = {5: -1, 6: -1, 7: 1, 10: -1}
# Rol aylanishi (assign): oxirgi o'yinlarda shu rolni olganlarga kamroq, ketma-ket Tinch bo'lganlarga ko'proq
REPEAT_W = (0.1, 0.35, 0.6)  # shu rol 1 / 2 / 3 o'yin oldin bo'lgan bo'lsa - ehtimol koeffitsienti
MAFIA_AGAIN_W = 0.5  # oldingi o'yinda ham mafiyada edi
TINCH_BOOST = 0.6  # har ketma-ket oddiy Tinch o'yini uchun maxsus rol ehtimoli +60%


def deal(n: int, rng: random.Random, disabled: frozenset = frozenset()) -> list[str]:
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        raise ValueError(f"o'yinchilar soni {MIN_PLAYERS}..{MAX_PLAYERS} bo'lishi kerak")
    off = set(disabled) - CORE
    pool = lambda xs: [x for x in xs if x not in off and not (x == "aka_uka" and {"aka", "uka"} & off)]

    # Mafiya
    m = max(1, (n + 2) // 4)  # 6 kishida 2, 10 da 3, 14 da 4 (n // 4 da tinch aholi ~60% yutardi)
    roles = ["don"]
    for r in rng.sample(pool(MAFIA_POOL), len(pool(MAFIA_POOL))):
        free = m - len(roles)
        if r == "aka_uka" and free >= 2:
            roles += ["aka", "uka"]
        elif r != "aka_uka" and free >= 1:
            roles.append(r)
    roles += ["mafiya"] * (m - len(roles))

    # Neytrallar
    k = sum(n >= x for x in (8, 14, 20, 26, 34, 42, 50))  # 60 kishida 7 neytral
    neutrals = [x for x in pool(NEUTRAL_POOL) if n >= KILLERS_FROM or x not in KILLER_NEUTRALS]
    picked = []
    for x in rng.sample(neutrals, len(neutrals)):  # qotil neytrallar ko'pi bilan MAX_KILLERS ta
        if len(picked) < k and (x not in KILLER_NEUTRALS or sum(y in KILLER_NEUTRALS for y in picked) < MAX_KILLERS):
            picked.append(x)
    roles += picked

    # Tinch aholi
    town = ["komissar"] + [r for r, need in (("doktor", 5), ("serjant", 8)) if n >= need and r not in off]
    t = n - len(roles) - len(town)
    tpool = [x for x in pool(TOWN_POOL) if n > SMALL_GAME or x not in SMALL_BANNED]
    want = max(0, min(int(t * 0.7), t - 1) + TOWN_SPECIAL_ADJ.get(n, 0))
    specials = rng.sample(tpool, min(len(tpool), want, t))
    if n >= BIG_GAME:  # oddiy Tinch aholi ~ n/7 qolguncha takrorlanadigan rollar qo'shiladi
        extra = [x for x in pool(REPEATABLE) for _ in range(2)]
        need = t - len(specials) - n // 7
        specials += rng.sample(extra, max(0, min(need, len(extra))))
    if "podshoh" in specials and "qorovul" not in specials:
        specials[specials.index("podshoh")] = "qorovul" if "qorovul" not in off else "tinch"
    town += specials
    roles += town + ["tinch"] * (n - len(roles) - len(town))

    rng.shuffle(roles)
    return roles


def assign(roles: list[str], history: list[list[str]], rng: random.Random) -> list[str]:
    """Rollarni o'yinchilarga taqsimlash (i-o'yinchi -> natija[i]). history[i] - uning oxirgi rollari (yangisi oldin).
    Oddiy shuffle o'rniga og'irlikli tanlov: Don/Komissar va boshqa maxsus rollar ketma-ket bir odamga kamdan-kam
    tushadi, uzoq vaqt Tinch bo'lib yurganlarga maxsus rol tezroq tushadi. Tarkib o'zgarmaydi."""
    order = [r for r in ("don", "komissar") if r in roles]
    rest = [r for r in roles if r != "tinch"]
    for r in order:
        rest.remove(r)
    rng.shuffle(rest)
    order += rest
    free, out = list(range(len(roles))), [None] * len(roles)

    def weight(i: int, role: str) -> float:
        h, w = history[i], 1.0
        for back, k in enumerate(REPEAT_W):
            if back < len(h) and h[back] == role:
                w *= k
                break
        if h and ROLES[role].team == MAFIA and h[0] in ROLES and ROLES[h[0]].team == MAFIA:
            w *= MAFIA_AGAIN_W
        streak = next((j for j, x in enumerate(h) if x != "tinch"), len(h))
        return w * (1 + TINCH_BOOST * streak)

    for role in order:
        ws = [weight(i, role) for i in free]
        i = rng.choices(free, ws)[0]
        out[i] = role
        free.remove(i)
    for i in free:
        out[i] = "tinch"
    return out
