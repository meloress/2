"""O'yinchilar soniga qarab rollarni taqsimlash (spec, 6-bo'lim)."""
import random

MIN_PLAYERS, MAX_PLAYERS = 4, 60
MAFIA_POOL = ["mafiya", "advokat", "jurnalist", "yollanma", "aka_uka"]
NEUTRAL_POOL = ["qotil", "gazabkor", "sehrgar", "vampir", "qaroqchi", "konchi", "tulki", "aferist", "sotqin"]
TOWN_POOL = ["daydi", "kezuvchi", "afsungar", "voris", "janob", "ovchi", "donishmand", "suitsid", "qorovul", "podshoh"]
CORE = {"don", "komissar", "tinch", "mafiya"}  # o'chirib bo'lmaydi


def deal(n: int, rng: random.Random, disabled: frozenset = frozenset()) -> list[str]:
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        raise ValueError(f"o'yinchilar soni {MIN_PLAYERS}..{MAX_PLAYERS} bo'lishi kerak")
    off = set(disabled) - CORE
    pool = lambda xs: [x for x in xs if x not in off and not (x == "aka_uka" and {"aka", "uka"} & off)]

    # Mafiya
    m = max(1, n // 4)
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
    neutrals = pool(NEUTRAL_POOL)
    roles += rng.sample(neutrals, min(k, len(neutrals)))

    # Tinch aholi
    town = ["komissar"] + [r for r, need in (("doktor", 5), ("serjant", 8)) if n >= need and r not in off]
    t = n - len(roles) - len(town)
    specials = rng.sample(pool(TOWN_POOL), min(len(pool(TOWN_POOL)), max(0, min(int(t * 0.7), t - 1))))
    if "podshoh" in specials and "qorovul" not in specials:
        specials[specials.index("podshoh")] = "qorovul" if "qorovul" not in off else "tinch"
    town += specials
    roles += town + ["tinch"] * (n - len(roles) - len(town))

    rng.shuffle(roles)
    return roles
