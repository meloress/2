"""O'yin holati va qoidalari. Telegramdan bexabar: faqat Event qaytaradi.

Tungi hisob-kitob tartibi (spec, 3-bo'lim):
  1a blok -> 1b Aferist, Qaroqchi -> 2 himoya -> 3 axborot -> 4 hujum -> 5 qasos/vorislik
"""
import random
from dataclasses import asdict, dataclass, field

from .roles import MAFIA, NEUTRAL, NO_TARGET, ROLES, TOWN
from .setup import deal

NIGHT, DAY, VOTING, CONFIRM, FINISHED = "night", "day", "voting", "confirm", "finished"
MAX_DAYS = 20
GAZAB_KILLS = 3
AFK_LIMIT = 3  # ketma-ket o'tkazib yuborilgan navbatlar (0 = o'chiq)
ATTACKS = {"mafia_kill", "hit", "kill", "bite", "shoot", "curse", "rage"}
SKIP = "skip"  # tunda "hech narsa qilmayman"
PICK = "r_"  # do'kondan olingan rol: "r_komissar" - keyingi o'yinda shu rol (o'yinda bo'lsa)
DRAW = "draw"
COUPLE = "couple"  # 💞 paralar rejimi: oxirgi ikki tirik - bir juft


def couple_pairs(uids: list[int], partners: dict[int, int]) -> dict[int, int]:
    """/couple juftlaridan ikkalasi ham o'yinda bo'lganlari: uid -> jufti."""
    inside = set(uids)
    return {u: p for u, p in partners.items() if u in inside and p in inside and partners.get(p) == u}

# Konchi o'ljasi: (ehtimol, dan, gacha). Foizlar o'yinchilarga ko'rsatilmaydi
DIG_DOLLARS = [(0.60, 10, 50), (0.25, 51, 150), (0.10, 151, 300), (0.04, 301, 500), (0.008, 501, 1000),
               (0.002, 1001, 2000)]
DIG_DIAMONDS = [(0.94, 0), (0.05, 1), (0.008, 2), (0.002, 3)]


def dig_loot(rng: random.Random) -> tuple[int, int]:
    """(dollar, olmos). Oraliq ichida kichik summa ko'proq chiqadi."""
    x = rng.random()
    for p, lo, hi in DIG_DOLLARS:
        if x < p:
            break
        x -= p
    dollars = min(hi, int(rng.triangular(lo, hi + 1, lo)))
    y = rng.random()
    for p, gems in DIG_DIAMONDS:
        if y < p:
            break
        y -= p
    return dollars, gems


@dataclass
class Event:
    kind: str
    uid: int | None = None
    target: int | None = None
    data: dict = field(default_factory=dict)


@dataclass
class Player:
    uid: int
    name: str
    role: str = "tinch"
    alive: bool = True
    items: dict = field(default_factory=dict)  # shield / verbena / doc -> soni
    last_target: int | None = None  # Doktor, Kezuvchi, Qorovul: ketma-ket cheklovi
    self_heal_used: bool = False
    kills: int = 0  # G'azabkor
    won: bool = False
    mute_day: int = 0  # shu kuni ovoz bera olmaydi (Qaroqchi o'g'irladi yoki Kezuvchi uxlatdi)
    idle: int = 0  # AFK hisoblagich
    score: int = 0  # yashirin hissa balli: faqat o'yin oxirida g'oliblarni tartiblash uchun, hech qayerda ko'rsatilmaydi

    @property
    def team(self) -> str:
        return ROLES[self.role].team


@dataclass
class Game:
    chat_id: int
    seed: int
    players: list[Player]
    phase: str = NIGHT
    day: int = 1
    actions: dict = field(default_factory=dict)  # uid -> [kind, target]
    mafia_votes: dict = field(default_factory=dict)  # uid -> target
    votes: dict = field(default_factory=dict)  # voter -> target | None (o'tkazib yuborish)
    vote_log: list = field(default_factory=list)  # [voter, target] berilish tartibida
    guarded: int | None = None
    winner: str | None = None
    afk_limit: int = AFK_LIMIT
    max_days: int = MAX_DAYS  # katta o'yinda ko'proq kun kerak
    confirm: bool = False  # ikki bosqichli osish: nomzod -> 👍/👎
    candidate: int | None = None
    confirms: dict = field(default_factory=dict)  # uid -> True (osish) / False (rahm)
    pairs: dict = field(default_factory=dict)  # 💞 paralar o'yini: uid -> jufti (ikki tomonlama)
    couple_mode: bool = False  # 💞 tomonlar yo'q: oxirgi tirik juft yutadi

    # ---------- yaratish va saqlash ----------
    @classmethod
    def create(cls, chat_id: int, members: list[tuple[int, str]], seed: int,
               disabled: frozenset = frozenset(), items: dict | None = None,
               afk_limit: int = AFK_LIMIT, confirm: bool = False) -> "Game":
        roles = deal(len(members), random.Random(seed), disabled)
        items = items or {}
        players = [Player(uid, name, role, items=dict(items.get(uid, {})))
                   for (uid, name), role in zip(members, roles)]
        for p in players:
            if p.items.get("votesave", 0) > 1:
                p.items["votesave"] = 1  # bir o'yinda bir martadan ko'p emas
        return cls(chat_id, seed, players, afk_limit=afk_limit, confirm=confirm,
                   max_days=max(MAX_DAYS, len(players)))

    def use_role_picks(self) -> list[tuple[int, str]]:
        """Sotib olingan rollar: shu rol kimga tushgan bo'lsa, o'sha bilan almashtiriladi (tarkib o'zgarmaydi).
        Rol bu o'yinda yo'q yoki allaqachon o'zida bo'lsa - token sarflanmaydi. [(uid, item)] - sarflanganlar."""
        used, fixed = [], set()
        for p in self.players:  # qo'shilish tartibida: birinchi qo'shilgan oldin oladi
            for item in sorted(i for i, q in p.items.items() if i.startswith(PICK) and q > 0):
                want = item[len(PICK):]
                if p.role == want and p.uid not in fixed:
                    fixed.add(p.uid)
                    break
                x = next((x for x in self.players if x.role == want and x.uid not in fixed), None)
                if x and p.uid not in fixed:
                    p.role, x.role = x.role, p.role
                    fixed.add(p.uid)
                    used.append((p.uid, item))
                    break
        return used

    def use_tickets(self) -> list[int]:
        """🎟 Faol rol: chipta egasi Tinch aholi bo'lsa, rolini tasodifiy maxsus rol bilan almashtiradi."""
        rng = random.Random(f"{self.seed}:tickets")
        used = []
        for p in self.players:
            if p.items.get("ticket", 0) > 0 and p.role == "tinch":
                pool = [x for x in self.players if x.role != "tinch" and not x.items.get("ticket")
                        and not x.items.get(PICK + x.role)]  # sotib olingan rol tortib olinmaydi
                if pool:
                    x = rng.choice(pool)
                    p.role, x.role = x.role, p.role
                    p.items["ticket"] -= 1
                    used.append(p.uid)
        return used

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Game":
        d = dict(d)
        d["players"] = [Player(**p) for p in d["players"]]
        for k in ("actions", "mafia_votes", "votes", "confirms", "pairs"):
            d[k] = {int(u): v for u, v in d.get(k, {}).items()}
        return cls(**d)

    # ---------- yordamchilar ----------
    def get(self, uid: int) -> Player | None:
        return next((p for p in self.players if p.uid == uid), None)

    def num(self, uid: int) -> int:
        """O'yin boshidagi tartib raqami (1..n): o'yinchilar o'lsa ham o'zgarmaydi."""
        return next(i for i, p in enumerate(self.players, 1) if p.uid == uid)

    def alive(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def by_role(self, role: str) -> Player | None:
        return next((p for p in self.alive() if p.role == role), None)

    def teammates(self, uid: int) -> list[Player]:
        """Bir-birini taniydiganlar: mafiya jamoasi, Komissar+Serjant."""
        p = self.get(uid)
        if p.team == MAFIA:
            return [x for x in self.players if x.team == MAFIA and x.uid != uid]
        if p.role in ("komissar", "serjant"):
            return [x for x in self.players if x.role in ("komissar", "serjant") and x.uid != uid]
        return []

    # ---------- tun ----------
    def available_actions(self, uid: int) -> list[str]:
        p = self.get(uid)
        if not p or not p.alive or self.phase != NIGHT:
            return []
        if p.role == "gazabkor" and p.kills < GAZAB_KILLS:
            return ["rage"]
        return list(ROLES[p.role].actions)

    def targets(self, uid: int, kind: str) -> list[int]:
        p = self.get(uid)
        alive = self.alive()
        if kind in NO_TARGET:
            return []
        if kind == "heal":
            return [x.uid for x in alive if x.uid != p.last_target and (x.uid != uid or not p.self_heal_used)]
        if kind == "guard":
            return [x.uid for x in alive if x.uid != p.last_target]
        if kind == "block":
            return [x.uid for x in alive if x.uid not in (uid, p.last_target)]
        if kind == "disguise":
            return [x.uid for x in alive if x.team == MAFIA]
        if kind in ("mafia_kill", "hit", "pair"):
            if self.couple_mode:  # tomonlar yo'q: o'zi va juftidan boshqa hamma
                return [x.uid for x in alive if x.uid not in (uid, self.pairs.get(uid))]
            return [x.uid for x in alive if x.team != MAFIA]
        return [x.uid for x in alive if x.uid != uid]

    def submit(self, uid: int, kind: str, target: int | None = None) -> bool:
        acts = self.available_actions(uid)
        if kind == SKIP and acts:  # "Hech narsa qilmayman": harakat qilgan hisoblanadi (AFK emas)
            if "mafia_kill" in acts:
                self.mafia_votes[uid] = None
            else:
                self.actions[uid] = [SKIP, None]
            return True
        if kind not in acts:
            return False
        if kind in NO_TARGET:
            target = None
        elif target not in self.targets(uid, kind):
            return False
        if kind == "mafia_kill":
            self.mafia_votes[uid] = target
        else:
            self.actions[uid] = [kind, target]
        return True

    def all_acted(self) -> bool:
        for p in self.alive():
            acts = self.available_actions(p.uid)
            if not acts:
                continue
            done = self.mafia_votes if "mafia_kill" in acts else self.actions
            if p.uid not in done:
                return False
        return True

    def _mafia_target(self, rng: random.Random) -> tuple[int, int] | None:
        don = self.by_role("don")
        if not don:
            return None
        if don.uid in self.mafia_votes:  # Donning so'zi yakuniy: "hech kim" desa, o'ldirilmaydi
            t = self.mafia_votes[don.uid]
            return (don.uid, t) if t is not None else None
        votes = [t for u, t in self.mafia_votes.items() if t is not None and self.get(u).alive]
        if not votes:
            return None
        top = max(votes.count(t) for t in votes)
        return don.uid, rng.choice(sorted({t for t in votes if votes.count(t) == top}))

    def _use(self, p: Player, item: str, ev: list) -> bool:
        if p.items.get(item, 0) <= 0:
            return False
        p.items[item] -= 1
        ev.append(Event("item_used", p.uid, data={"item": item}))
        return True

    def _immune(self, v: Player, kind: str, src: str) -> bool:
        if v.role == "sehrgar":
            return kind in ("mafia_kill", "kill") or (kind == "shoot" and src == "komissar")
        if v.role == "qotil":
            return kind in ("mafia_kill", "hit")
        return False

    def resolve_night(self) -> list[Event]:
        rng = random.Random(f"{self.seed}:{self.day}:night")
        ev: list[Event] = []
        expected, acted = [p for p in self.alive() if self.available_actions(p.uid)], self.actions.keys() | self.mafia_votes.keys()
        self._track_idle(expected, acted)
        for p in expected:
            if p.uid not in acted:
                p.score -= 2  # tunda harakat qilmadi
        # Tun boshidagi rollar: matnlarda shu ko'rsatiladi (Ovchi jarimasi, Voris o'zgarishidan oldingi holat)
        roles0 = {p.uid: p.role for p in self.players}
        # acts: actor -> (kind, target, harakat egasining roli)
        acts = {u: (k, t, self.get(u).role) for u, (k, t) in self.actions.items()
                if self.get(u).alive and k != SKIP}
        m = self._mafia_target(rng)
        if m:
            acts[m[0]] = ("mafia_kill", m[1], "don")

        # 1a. Kezuvchi
        for u, (k, t, _) in acts.items():
            if k == "block":
                ev.append(Event("result", u, t, {"kind": k, "ok": True}))
                if self.get(t).team != self.get(u).team:
                    self.get(u).score += 2
        blocked = {t for k, t, _ in acts.values() if k == "block"}
        for t in blocked:
            acts.pop(t, None)
            self.get(t).mute_day = self.day  # ertangi kunduzgi ovoz berishda ham qatnasha olmaydi
            ev.append(Event("blocked", t))

        # 1b. Aferist
        for u in [u for u, a in acts.items() if a[0] == "steal"]:
            _, t, _ = acts.pop(u)
            stolen = acts.get(t)
            if stolen and stolen[0] not in ("steal", "sacrifice"):
                del acts[t]
                acts[u] = stolen
                ev.append(Event("stolen", u, t, {"kind": stolen[0]}))
            else:
                ev.append(Event("saw_role", u, t, {"role": self.get(t).role}))

        # 1b. Qaroqchi (himoyadan oldin: o'g'irlangan qalqon shu tun ishlamaydi)
        for u, (k, t, _) in acts.items():
            if k != "rob":
                continue
            v, thief = self.get(t), self.get(u)
            owned = sorted(i for i, q in v.items.items() if q > 0 and i != "mask" and not i.startswith(PICK))
            what = rng.choice(["dollars", "vote"] + (["item"] if owned else []))
            data = {"what": what}
            if what == "item":
                item = rng.choice(owned)
                v.items[item] -= 1
                thief.items[item] = thief.items.get(item, 0) + 1
                data["item"] = item
            elif what == "vote":
                v.mute_day = self.day
            ev.append(Event("robbed", u, t, data))

        # 2. Himoya va niqob
        healed, disguised = set(), set()
        for u, (k, t, _) in acts.items():
            if k == "heal":
                healed.add(t)
                if t == u:
                    self.get(u).self_heal_used = True
            elif k == "guard":
                self.guarded = t
                ev.append(Event("result", u, t, {"kind": k, "ok": True}))
            elif k == "disguise":
                disguised.add(t)
                ev.append(Event("result", u, t, {"kind": k, "ok": True}))
        for p in self.players:
            if p.role in ("doktor", "kezuvchi", "qorovul"):
                p.last_target = self.actions.get(p.uid, [None, None])[1]

        # 3. Axborot
        visitors: dict[int, list[int]] = {}
        for u, (k, t, _) in acts.items():
            if t is not None:
                visitors.setdefault(t, []).append(u)
        docced: set[int] = set()  # shu tun Hujjat ko'rsatganlar: boshqa tekshiruvda ham Tinch
        for u, (k, t, _) in acts.items():
            if k == "check":
                if self.get(t).team != self.get(u).team:  # haqiqiy jamoa bo'yicha (niqob ballga ta'sir qilmaydi)
                    self.get(u).score += 3
                ev.append(Event("checked", u, t, {"result": self._appear(t, disguised, docced, ev)}))
            elif k == "interview":
                ev.append(Event("interview", u, t, {"visitors": [x for x in visitors.get(t, []) if x != u]}))
            elif k == "dig":
                dollars, gems = dig_loot(rng)
                ev.append(Event("dug", u, data={"dollars": dollars, "diamonds": gems}))

        # 4. Hujumlar
        attacks: dict[int, list[tuple[int, str, str]]] = {}  # target -> [(actor, kind, src)]
        pairs: dict[int, list[int]] = {}
        for u, (k, t, src) in acts.items():
            if k in ATTACKS:
                attacks.setdefault(t, []).append((u, k, src))
            elif k == "pair":
                pairs.setdefault(t, []).append(u)
        for t, us in pairs.items():
            if len(us) >= 2:
                attacks.setdefault(t, []).extend((u, "pair", "aka") for u in us)
            else:
                ev.append(Event("result", us[0], t, {"kind": "pair", "ok": False}))

        for u, (k, t, _) in acts.items():  # Ovchi jarimasi: haqiqiy jamoa bo'yicha
            if k == "shoot" and self.get(u).role == "ovchi" and self.get(t).team == TOWN:
                self.get(u).role = "tinch"
                ev.append(Event("penalty", u, t))

        for u, (k, t, _) in acts.items():
            if k == "sacrifice":
                p = self.get(u)
                p.alive, p.won = False, True
                ev.append(Event("sacrificed", u))

        deaths: dict[int, list[tuple[int, str, str]]] = {}
        heal_saved: set[int] = set()
        for t, alist in attacks.items():
            v = self.get(t)
            alist = [a for a in alist if not self._immune(v, a[1], a[2])]
            if not alist or not v.alive:
                continue
            if t in healed:
                heal_saved.add(t)
                for u, (k, x, _) in acts.items():
                    if k == "heal" and x == t:
                        self.get(u).score += 3
                ev.append(Event("saved", target=t))
                continue
            if v.role == "voris" and all(a[1] == "mafia_kill" or (a[1] == "shoot" and a[2] == "komissar") for a in alist):
                v.role = "mafiya" if any(a[1] == "mafia_kill" for a in alist) else "serjant"
                ev.append(Event("transformed", t, data={"role": v.role}))
                continue
            only_bites = all(a[1] == "bite" for a in alist)
            # Suitsid mafiya qo'lida o'lib yutadi: unga qalqon/verbena zarar - ishlatilmaydi
            wants = v.role == "suitsid" and any(a[1] == "mafia_kill" for a in alist)
            if not wants and ((only_bites and self._use(v, "verbena", ev)) or self._use(v, "shield", ev)):
                ev.append(Event("saved", target=t))
                continue
            deaths[t] = alist

        def killer_roles(alist) -> list[str]:
            return list(dict.fromkeys(roles0[u] for u in sorted({a[0] for a in alist})))

        for u, (k, t, _) in acts.items():
            if k == "visit" and t in deaths:
                ev.append(Event("witness", u, t, {"killers": sorted({a[0] for a in deaths[t]}),
                                                  "killer_roles": killer_roles(deaths[t])}))

        for t, alist in deaths.items():
            self.get(t).alive = False
            for u in {a[0] for a in alist}:  # dushmanni o'ldirish +3, o'z jamoadoshini -3
                self.get(u).score += 3 if ROLES[roles0[u]].team != ROLES[roles0[t]].team else -3
            ev.append(Event("killed", target=t, data={"by": sorted({a[1] for a in alist}),
                                                      "killers": sorted({a[0] for a in alist}),
                                                      "killer_roles": killer_roles(alist), "role": roles0[t]}))
            for a in alist:
                if a[1] == "rage":
                    self.get(a[0]).kills += 1

        # 5. Qasos
        for t, alist in deaths.items():
            v = self.get(t)
            if v.role == "afsungar":
                avengers = {a[0] for a in alist}
            elif v.role == "suitsid" and any(a[1] == "mafia_kill" for a in alist):
                avengers = {a[0] for a in alist if a[1] == "mafia_kill"}
                v.won = True
            else:
                continue
            for u in sorted(avengers):
                if self.get(u).alive:
                    self.get(u).alive = False
                    ev.append(Event("revenge", t, u))

        # Shaxsiy natijalar: Doktor, Daydi (qotillik bo'lmasa), hujum qilganlar (mafiya ovozi - quyida, jamoaga)
        for u, (k, t, _) in acts.items():
            if k == "heal":
                ev.append(Event("result", u, t, {"kind": k, "ok": t in heal_saved}))
            elif k == "visit" and t not in deaths:
                ev.append(Event("result", u, t, {"kind": k, "ok": False}))
        for t, alist in attacks.items():
            for u, k, _ in alist:
                if k != "mafia_kill":
                    ev.append(Event("result", u, t, {"kind": k, "ok": not self.get(t).alive}))

        # Mafiya ovozining natijasi (sheriklarga) yoki Don umuman tanlamagani (guruhga)
        if m:
            if not self.get(m[1]).alive:  # Don ballni o'ldirish uchun oladi, shu nishonga ovoz bergan sheriklar +2
                for u, x in self.mafia_votes.items():
                    if x == m[1] and u != m[0]:
                        self.get(u).score += 2
            ev.append(Event("mafia_result", m[0], m[1], {"killed": not self.get(m[1]).alive}))
        elif self.by_role("don"):
            ev.append(Event("mafia_idle"))

        self.actions, self.mafia_votes = {}, {}
        self.phase = DAY
        self._kick_afk(ev)
        self._after_deaths(ev)
        self._check_win(ev)
        return ev

    def _appear(self, t: int, disguised: set, docced: set, ev: list) -> str:
        """Tekshiruvda ko'rinadigan rol: aniq rol; niqob, Hujjat va Sotqin - Tinch aholi.
        Hujjat faqat mafiya va yakka rollarda sarflanadi: tinch aholiga yashirinish kerak emas."""
        v = self.get(t)
        if t in disguised or v.role == "sotqin" or t in docced:
            return "tinch"
        if v.team != TOWN and self._use(v, "doc", ev):
            docced.add(t)
            return "tinch"
        return v.role

    def partner(self, uid: int) -> Player | None:
        return self.get(self.pairs[uid]) if uid in self.pairs else None

    def _after_deaths(self, ev: list) -> None:
        changed = True
        while changed:  # Aka/Uka va juftlar zanjiri: bittasining o'limi boshqasini ham olib ketishi mumkin
            changed = False
            bros = [p for p in self.players if p.role in ("aka", "uka")]
            if len(bros) == 2 and bros[0].alive != bros[1].alive:
                b = bros[0] if bros[0].alive else bros[1]
                b.alive, changed = False, True
                ev.append(Event("linked", target=b.uid))
            for p in self.players:
                if not p.alive and (q := self.partner(p.uid)) and q.alive:
                    q.alive, changed = False, True  # 💔 jufti bilan birga o'yindan chiqadi
                    ev.append(Event("heartbreak", p.uid, q.uid))
        if not self.by_role("komissar") and (s := self.by_role("serjant")):
            s.role = "komissar"
            ev.append(Event("promoted", s.uid, data={"role": "komissar"}))
        if not self.by_role("don"):
            mafia = sorted((p for p in self.alive() if p.team == MAFIA), key=lambda p: p.role != "mafiya")
            if mafia:
                mafia[0].role = "don"
                ev.append(Event("promoted", mafia[0].uid, data={"role": "don"}))

    # ---------- kun ----------
    def start_voting(self) -> None:
        self.phase, self.votes, self.vote_log = VOTING, {}, []

    def can_vote(self, uid: int) -> bool:
        p = self.get(uid)
        return bool(p and p.alive and p.mute_day != self.day and self.phase == VOTING)

    def cast_vote(self, voter: int, target: int | None) -> bool:
        if not self.can_vote(voter):
            return False
        if target is not None and (target == voter or not (t := self.get(target)) or not t.alive):
            return False
        self.votes[voter] = target
        self.vote_log.append([voter, target])
        return True

    def resolve_vote(self) -> list[Event]:
        ev: list[Event] = []
        self._track_idle([p for p in self.alive() if self.can_vote(p.uid)], self.votes.keys())
        tally: dict = {}
        for v, t in self.votes.items():
            tally[t] = tally.get(t, 0) + (2 if self.get(v).role == "janob" else 1)
        top = max(tally.values(), default=0)
        leaders = [t for t, c in tally.items() if c == top]
        if len(leaders) != 1 or leaders[0] is None:
            ev.append(Event("no_hang"))
        elif leaders[0] == self.guarded:
            ev.append(Event("guard_saved", target=leaders[0]))
        elif self.confirm:
            self.candidate, self.confirms, self.phase = leaders[0], {}, CONFIRM
            ev.append(Event("candidate", target=leaders[0], data={"votes": top}))
            return ev
        elif self._hang(leaders[0], {"votes": top}, ev):
            return ev
        return self._end_day(ev)

    def can_confirm(self, uid: int) -> bool:
        p = self.get(uid)
        return bool(p and p.alive and self.phase == CONFIRM and uid != self.candidate and p.mute_day != self.day)

    def cast_confirm(self, uid: int, yes: bool) -> bool:
        if not self.can_confirm(uid):
            return False
        self.confirms[uid] = bool(yes)
        return True

    def confirm_tally(self) -> tuple[int, int]:
        """(👍, 👎) - Janob ovozi 2 ta."""
        w = lambda u: 2 if self.get(u).role == "janob" else 1
        return (sum(w(u) for u, c in self.confirms.items() if c),
                sum(w(u) for u, c in self.confirms.items() if not c))

    def resolve_confirm(self) -> list[Event]:
        ev: list[Event] = []
        yes, no = self.confirm_tally()
        t, self.candidate = self.candidate, None
        if yes > no:
            if self._hang(t, {"votes": yes, "yes": yes, "no": no}, ev):
                return ev
        else:
            ev.append(Event("spared", target=t, data={"yes": yes, "no": no}))
        return self._end_day(ev)

    def _hang(self, t: int, data: dict, ev: list) -> bool:
        """Osish. True qaytarsa, o'yin shu zahoti tugadi (Podshoh)."""
        v = self.get(t)
        if v.role != "tulki" and self._use(v, "votesave", ev):  # Tulki osilib yutadi; ⚖️ Ovoz himoyasi: bir marta osilishdan saqlaydi, guruhga e'lon qilinadi
            ev.append(Event("vote_saved", target=t))
            return False
        v.alive = False
        for u, x in self.votes.items():  # dushmanni osishga ovoz +2, jamoadoshni -1
            if x == t:
                self.get(u).score += 2 if self.get(u).team != v.team else -1
        ev.append(Event("hanged", target=t, data={**data, "role": v.role}))
        if v.role == "podshoh" and not self.couple_mode:
            self.guarded = None
            self._after_deaths(ev)  # jufti ham chiqadi - g'oliblar qatoriga tushmasin
            self._finish(MAFIA, ev, podshoh=True)
            return True
        if v.role == "tulki":
            first = next(u for u, x in self.vote_log if x == t and self.votes.get(u) == t)
            self.get(first).alive = False
            v.won = True
            ev.append(Event("tulki", t, first))
        return False

    def _end_day(self, ev: list) -> list[Event]:
        self.day += 1
        self.phase = NIGHT
        for p in self.alive():
            p.score += 1  # yana bir kun omon qoldi
        self._kick_afk(ev)
        self._after_deaths(ev)
        self.guarded = None
        self._check_win(ev)
        return ev

    def _track_idle(self, expected: list[Player], acted) -> None:
        for p in expected:
            p.idle = 0 if p.uid in acted else p.idle + 1

    def _kick_afk(self, ev: list) -> None:
        for p in self.alive():
            if self.afk_limit and p.idle >= self.afk_limit:
                p.alive = False
                ev.append(Event("afk", target=p.uid))

    def kill_player(self, uid: int) -> list[Event]:
        """O'yinchi guruhdan chiqdi yoki /leave qildi."""
        ev: list[Event] = []
        p = self.get(uid)
        if p and p.alive and self.phase != FINISHED:
            p.alive = False
            ev.append(Event("left", target=uid))
            self._after_deaths(ev)
            self._check_win(ev)
        return ev

    # ---------- g'alaba ----------
    def _check_win(self, ev: list) -> None:
        if self.phase == FINISHED:
            return
        alive = self.alive()
        killers = [p for p in alive if p.role in ("qotil", "vampir")]
        mafia = [p for p in alive if p.team == MAFIA]
        if self.couple_mode:  # faqat juftlar: hamma tirik - bitta juft bo'lsa, o'sha yutadi
            if not alive:
                w = DRAW
            elif len(alive) <= 2 and all(p.uid in (alive[0].uid, self.pairs.get(alive[0].uid)) for p in alive):
                w = COUPLE
            elif self.day > self.max_days:
                w = DRAW
            else:
                return
            return self._finish(w, ev)
        if not alive:
            w = DRAW
        elif len(alive) == 2 and self.pairs.get(alive[0].uid) == alive[1].uid:
            w = COUPLE  # sevgi hamma narsadan ustun: tomonidan qat'i nazar
        elif len(alive) <= 2 and killers:
            w = killers[0].role
        elif not mafia and not killers:
            w = TOWN
        elif mafia and len(mafia) >= len(alive) - len(mafia) and not killers:
            w = MAFIA
        elif self.day > self.max_days:
            w = DRAW
        else:
            return
        self._finish(w, ev)

    def _finish(self, w: str, ev: list, podshoh: bool = False) -> None:
        """G'olib jamoadan faqat tiriklar yutadi. O'lib yutganlar (Suitsid, Tulki, G'azabkor) won=True ni
        o'limi paytida oladi va u saqlanadi."""
        self.winner, self.phase = w, FINISHED
        if self.couple_mode:  # o'lib yutish (Suitsid, Tulki...) yo'q: faqat oxirgi tirik juft
            for p in self.players:
                p.won = w == COUPLE and p.alive
                p.score += 2 if p.alive else 0
            ev.append(Event("game_over", data={"winner": w, "winners": [p.uid for p in self.players if p.won]}))
            return
        for p in self.players:
            if not p.alive:
                continue
            p.score += 2  # oxirigacha tirik
            if w == COUPLE:
                p.won = True
            elif w == TOWN and p.team == TOWN:
                p.won = True
            elif w == MAFIA and (p.team == MAFIA or p.role == "sotqin" or (podshoh and p.team == NEUTRAL)):
                p.won = True
            elif p.role == w:
                p.won = True
            if p.role in ("konchi", "sehrgar", "aferist"):
                p.won = True
        ev.append(Event("game_over", data={"winner": w, "winners": [p.uid for p in self.players if p.won]}))
