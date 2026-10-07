"""Har guruh uchun bitta Runner: lobby, faza sikli, taymerlar, saqlash va tiklash."""
import asyncio
import logging
import random
from random import choice
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from . import config, db, texts
from .engine.game import AFK_LIMIT, CONFIRM, DAY, FINISHED, NIGHT, SKIP, VOTING, Game
from .engine.roles import ACTION_LABELS, MAFIA, NO_TARGET
from .engine.setup import MAX_PLAYERS, MIN_PLAYERS

log = logging.getLogger(__name__)
RUNNERS: dict[int, "Runner"] = {}  # chat_id -> Runner
PLAYING: dict[int, "Runner"] = {}  # uid -> Runner (lobby yoki o'yin)
NEXT: dict[int, set[int]] = defaultdict(set)  # chat_id -> /next obunachilari (ponytail: xotirada)
BOT_USERNAME = ""

# ---------- yuborish (Telegram cheklovlari) ----------
_send_lock = asyncio.Lock()
_last_send = 0.0
GLOBAL_INTERVAL = 1 / 25  # ponytail: bitta global navbat, ~25 xabar/s; ko'p nusxada ishlasa Redis-limiter kerak
GROUP_PER_MIN = 19  # Telegram: guruhga ~20 xabar/daqiqa
EFFECT_WIN = "5046509860389126442"  # 🎉 (faqat shaxsiy chatda)
_group_sent: dict[int, deque] = defaultdict(deque)


def group_recent(chat_id: int) -> int:
    """Oxirgi 60 s da guruhga ketgan xabarlar soni."""
    q, t = _group_sent.get(chat_id) or (), time.monotonic()
    return sum(1 for x in q if t - x <= 60)


async def _group_slot(chat_id: int) -> None:
    if chat_id > 0:
        return
    q = _group_sent[chat_id]
    while True:
        t = time.monotonic()
        while q and t - q[0] > 60:
            q.popleft()
        if len(q) < GROUP_PER_MIN:
            q.append(t)
            return
        await asyncio.sleep(60.1 - (t - q[0]))


async def pace() -> None:
    """Global navbatda o'z vaqtini kutadi (o'yin xabarlari va e'lonlar bitta limitda)."""
    global _last_send
    async with _send_lock:
        wait = _last_send + GLOBAL_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_send = time.monotonic()


async def _call(fn, *a, **kw):
    for _ in range(3):
        try:
            await pace()
            return await fn(*a, **kw)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            log.info("telegram: %s", e)
            return None
    return None


FAKE_BASE = 9_000_000_000_000  # /testgame bot-o'yinchilari: ularga xabar yuborilmaydi
LAST_WORDS_SECS = texts.LAST_WORDS_SECS


MAX_TEXT = 3800  # Telegram limiti 4096; teglar uchun zaxira


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Qatorlar bo'yicha bo'ladi (teglar bitta qatordan oshmaydi)."""
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # juda uzun bitta qator
            parts.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + 1 + len(line) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    return parts + [cur]


async def send(bot: Bot, chat_id: int, text: str, kb: Kb | None = None, effect: str | None = None):
    if chat_id >= FAKE_BASE:
        return None
    if len(text) > MAX_TEXT:
        *head, text = split_text(text)
        for part in head:
            await send(bot, chat_id, part)
    await _group_slot(chat_id)
    kw = {"message_effect_id": effect} if effect and chat_id > 0 else {}
    return await _call(bot.send_message, chat_id, text, reply_markup=kb, disable_web_page_preview=True, **kw)


async def edit(bot: Bot, chat_id: int, msg_id: int, text: str, kb: Kb | None = None):
    await _group_slot(chat_id)
    return await _call(bot.edit_message_text, text=text, chat_id=chat_id, message_id=msg_id, reply_markup=kb,
                       disable_web_page_preview=True)


# Tugma ranglari: hujum - qizil, himoya - yashil, axborot - ko'k
DANGER_KINDS = {"mafia_kill", "hit", "kill", "bite", "shoot", "curse", "rage", "pair", "sacrifice", "rob", "steal"}
SAFE_KINDS = {"heal", "guard", "disguise"}


def kind_style(kind: str) -> str:
    return "danger" if kind in DANGER_KINDS else "success" if kind in SAFE_KINDS else "primary"


MEDIA = Path(__file__).resolve().parent.parent  # kun.mp4, tun.mp4
GIF_IDS: dict[str, str] = {}  # fayl -> Telegram file_id (bir marta yuklanadi)


async def send_gif(bot: Bot, chat_id: int, name: str, caption: str, kb: Kb | None = None):
    """GIF + izoh. Fayl yo'q yoki yuborilmasa - oddiy matn."""
    path = MEDIA / name
    if chat_id >= FAKE_BASE or not (name in GIF_IDS or path.exists()):
        return await send(bot, chat_id, caption, kb)
    await _group_slot(chat_id)
    m = await _call(bot.send_animation, chat_id, animation=GIF_IDS.get(name) or FSInputFile(path),
                    caption=caption, reply_markup=kb)
    if m is None:
        return await send(bot, chat_id, caption, kb)
    if media := (m.animation or m.video or m.document):
        GIF_IDS[name] = media.file_id
    return m


def invite_url(uid: int) -> str:
    """Telegramning "ulashish" oynasi: do'st tanlanadi, taklif matni va havola tayyor holda boradi."""
    return f"https://t.me/share/url?url={quote(bot_link(f'ref{uid}'), safe='')}&text={quote(texts.INVITE_TEXT)}"


def profile_kb(inv, uid: int | None = None) -> Kb:
    """Profil tugmalari: har buyum ON/OFF (3 tadan qatorda), almashtirish, do'kon, do'st taklif qilish."""
    toggles = [Btn(text=f"{texts.ITEMS[i.item].split(' ', 1)[0]} - {'🟢 ON' if i.enabled else '🔴 OFF'}",
                   callback_data=f"t:{i.item}", style="success" if i.enabled else "danger")
               for i in inv if i.item in texts.ITEMS and i.qty > 0]
    rows = grid(toggles, 3) if toggles else []
    rows.append([Btn(text=texts.exchange_btn(), callback_data="x", style="primary"),
                 Btn(text="🛒 Do'kon", callback_data="shop", style="primary")])
    if uid is not None:
        rows.append([Btn(text=texts.INVITE_BTN, url=invite_url(uid), style="success")])
    return Kb(inline_keyboard=rows)


def grid(btns: list[Btn], cols: int | None = None) -> list[list[Btn]]:
    """Ko'p o'yinchida tugmalar 2-3 ustunda."""
    cols = cols or (1 if len(btns) <= 8 else 2 if len(btns) <= 30 else 3)
    return [btns[i:i + cols] for i in range(0, len(btns), cols)]


def bot_link(payload: str = "") -> str:
    return f"https://t.me/{BOT_USERNAME}" + (f"?start={payload}" if payload else "")


class Runner:
    def __init__(self, bot: Bot, chat_id: int, settings: dict, title: str = ""):
        self.bot, self.chat_id, self.s, self.title = bot, chat_id, settings, title
        self.members: list[tuple[int, str]] = []
        self.opener: int | None = None  # /game bosgan: adminlardan tashqari u ham /begin qila oladi
        self.lobby_msg: int | None = None
        self.lobby_deadline = 0.0
        self.lobby_dirty = False
        self.game: Game | None = None
        self.game_id: int | None = None
        self.meta: dict = {}  # deadline, confirm_msg
        self.live_lines: list[str] = []  # tungi harakatlar va ovozlar: har biri alohida xabar
        self.confirm_dirty = False
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.last_words: dict[int, float] = {}
        RUNNERS[chat_id] = self

    # ---------- lobby ----------
    async def open_lobby(self) -> None:
        self.lobby_deadline = time.time() + self.s["lobby"]
        m = await send(self.bot, self.chat_id, self._lobby_text(), self._lobby_kb())
        self.lobby_msg = m.message_id if m else None
        self.task = asyncio.create_task(self._lobby_loop())
        if self.lobby_msg:
            await _call(self.bot.pin_chat_message, self.chat_id, self.lobby_msg, disable_notification=True)
        for uid in NEXT.pop(self.chat_id, set()):
            await send(self.bot, uid, texts.next_game(self.title), self._lobby_kb())

    def _lobby_text(self) -> str:
        return texts.lobby(self.members, max(0, int(self.lobby_deadline - time.time())))

    def _lobby_kb(self) -> Kb:
        return Kb(inline_keyboard=[[Btn(text=texts.JOIN_BTN, url=bot_link(f"join{self.chat_id}"), style="success")]])

    async def _lobby_loop(self) -> None:
        last_edit = time.time()
        while time.time() < self.lobby_deadline and len(self.members) < MAX_PLAYERS:
            await asyncio.sleep(1)
            if self.lobby_msg and (self.lobby_dirty and time.time() - last_edit > 5 or time.time() - last_edit > 30):
                self.lobby_dirty, last_edit = False, time.time()
                await edit(self.bot, self.chat_id, self.lobby_msg, self._lobby_text(), self._lobby_kb())
        await self._start_game()

    def join(self, uid: int, name: str) -> str:
        if self.game:
            return texts.NO_LOBBY
        if PLAYING.get(uid) not in (None, self):
            return texts.ALREADY_IN_GAME
        if len(self.members) >= MAX_PLAYERS:
            NEXT[self.chat_id].add(uid)
            return texts.LOBBY_FULL
        if all(u != uid for u, _ in self.members):
            self.members.append((uid, name))
            PLAYING[uid] = self
            self.lobby_dirty = True
        return texts.JOINED

    def extend(self, secs: int = 30) -> None:
        self.lobby_deadline += secs
        self.lobby_dirty = True

    def force_start(self) -> None:
        self.lobby_deadline = 0

    async def _start_game(self) -> None:
        if self.lobby_msg:
            await _call(self.bot.unpin_chat_message, self.chat_id, message_id=self.lobby_msg)
        if len(self.members) < MIN_PLAYERS:  # ro'yxat xabari o'chadi, bekor qilingani alohida yoziladi
            if self.lobby_msg:
                await _call(self.bot.delete_message, self.chat_id, self.lobby_msg)
            await send(self.bot, self.chat_id, texts.NEED_PLAYERS)
            self.close()
            return
        uids = [u for u, _ in self.members]
        items = await db.game_items(uids) if self.s["items"] else {}
        self.game = Game.create(self.chat_id, self.members, random.SystemRandom().randrange(2 ** 31),
                                frozenset(self.s["disabled"]), items, AFK_LIMIT if self.s.get("afk", True) else 0,
                                self.s.get("confirm", True))
        for uid in self.game.use_tickets():
            await db.change_item(uid, "ticket", -1)
        self.meta["started"] = time.time()
        self.game_id = await db.create_game(self.chat_id, self.state())
        if self.game_id is None:
            await send(self.bot, self.chat_id, texts.GAME_EXISTS)
            self.close()
            return
        if self.lobby_msg:
            await edit(self.bot, self.chat_id, self.lobby_msg, texts.game_started(self.game),
                       Kb(inline_keyboard=[[Btn(text="🎭 Rolimni ko'rish", url=bot_link(), style="primary")]]))
        for p in self.game.players:
            await send(self.bot, p.uid, texts.role_card(self.game, p.uid))
        await self._loop()

    # ---------- faza sikli ----------
    def state(self) -> dict:
        return {"game": self.game.to_dict(), "meta": self.meta}

    async def save(self) -> None:
        await db.save_game(self.game_id, self.state())

    async def _loop(self) -> None:
        try:
            while self.game.phase != FINISHED:
                await self._step()
            await self._finish()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("game %s crashed", self.game_id)
            await self.abort("⚠️ Texnik xato tufayli o'yin to'xtatildi. Uzr!")

    async def _step(self) -> None:
        g, ph = self.game, self.game.phase
        if "deadline" not in self.meta:
            secs = self.s[{NIGHT: "night", DAY: "day", VOTING: "vote", CONFIRM: "vote"}[ph]]
            self.meta["deadline"] = time.time() + secs
            await self._intro(ph, secs)
            await self.save()
        done = {NIGHT: g.all_acted, VOTING: self._all_voted, CONFIRM: self._all_confirmed}.get(ph, lambda: False)
        last_edit = 0.0
        while time.time() < self.meta["deadline"] and not done() and g.phase == ph:
            await asyncio.sleep(1)
            await self._flush_live()
            if self.confirm_dirty and time.time() - last_edit >= 3:  # 👍/👎 sonlari, 3 s da bir
                self.confirm_dirty, last_edit = False, time.time()
                await self._edit_confirm(final=False)
        await self._flush_live()
        if g.phase != ph:  # /leave o'yinni tugatgan bo'lishi mumkin
            return
        async with self.lock:
            self.meta.pop("deadline", None)
            if ph == NIGHT:
                ev = g.resolve_night()
            elif ph == DAY:
                g.start_voting()
                ev = None
            elif ph == VOTING:
                ev = g.resolve_vote()
            else:
                await self._edit_confirm(final=True)
                ev = g.resolve_confirm()
            if ev:
                await self._economy(ev)
            await self.save()
        if ev is not None:
            await self._announce(ph, ev)

    async def _intro(self, ph: str, secs: int) -> None:
        g = self.game
        if ph == NIGHT:
            await send_gif(self.bot, self.chat_id, "tun.mp4", texts.night_start(g, secs),
                           Kb(inline_keyboard=[[Btn(text="🌙 Botga o'tish", url=bot_link(), style="primary")]]))
            for p in g.alive():
                if kb := self.night_kb(p.uid):
                    await send(self.bot, p.uid, texts.night_prompt(g, p.uid), kb)
        elif ph == DAY:
            await send_gif(self.bot, self.chat_id, "kun.mp4", texts.DAY_CAPTION)
            await send(self.bot, self.chat_id, texts.day_start(g, secs))
        elif ph == VOTING:
            await send(self.bot, self.chat_id, texts.vote_prompt(g, secs),
                       Kb(inline_keyboard=[[Btn(text="🗳 Ovoz berish", url=bot_link(), style="primary")]]))
            for p in g.alive():
                if g.can_vote(p.uid):
                    await send(self.bot, p.uid, texts.vote_pm(g), self.vote_kb(p.uid))
        else:
            m = await send(self.bot, self.chat_id, texts.confirm_prompt(g, secs), self._confirm_kb())
            self.meta["confirm_msg"] = m.message_id if m else None
        await self._bots_act(ph)

    def add_bots(self, n: int) -> None:
        """/testgame: n ta bot-o'yinchi qo'shish."""
        start = FAKE_BASE + len(self.members)
        for i in range(n):
            if len(self.members) < MAX_PLAYERS:
                self.members.append((start + i, f"🤖 Bot {len(self.members) + 1}"))
        self.lobby_dirty = True

    async def _bots_act(self, ph: str) -> None:
        g = self.game
        for p in [p for p in g.alive() if p.uid >= FAKE_BASE]:
            if ph == NIGHT and (acts := g.available_actions(p.uid)):
                k = random.choice(acts)
                ts = g.targets(p.uid, k)
                if ts or k in NO_TARGET:
                    await self.on_action(p.uid, g.day, k, random.choice(ts) if ts else 0)
            elif ph == VOTING and g.can_vote(p.uid):
                others = [x.uid for x in g.alive() if x.uid != p.uid]
                await self.on_vote(p.uid, g.day, random.choice(others + [0]))
            elif ph == CONFIRM and g.can_confirm(p.uid):
                await self.on_confirm(p.uid, g.day, random.random() < 0.6)

    def _all_voted(self) -> bool:
        g = self.game
        return all(p.uid in g.votes for p in g.alive() if g.can_vote(p.uid))

    def _all_confirmed(self) -> bool:
        g = self.game
        return all(p.uid in g.confirms for p in g.alive() if g.can_confirm(p.uid))

    def _confirm_kb(self) -> Kb:
        pre = f"c:{self.game_id}:{self.game.day}"
        yes, no = self.game.confirm_tally()
        return Kb(inline_keyboard=[[Btn(text=f"👍 {yes}", callback_data=f"{pre}:1", style="success"),
                                    Btn(text=f"👎 {no}", callback_data=f"{pre}:0", style="danger")]])

    async def _edit_confirm(self, final: bool) -> None:
        g = self.game
        if g.phase != CONFIRM or g.candidate is None:  # kech kelgan bosish: tasdiq allaqachon tugagan
            self.confirm_dirty = False
            return
        if mid := self.meta.get("confirm_msg"):
            if final:
                self.confirm_dirty = False
                self.meta.pop("confirm_msg", None)
                await edit(self.bot, self.chat_id, mid, texts.confirm_result(g))
            else:
                await edit(self.bot, self.chat_id, mid, texts.confirm_prompt(g, self.s["vote"]), self._confirm_kb())

    async def on_confirm(self, uid: int, day: int, yes: bool) -> bool:
        async with self.lock:
            g = self.game
            if not g or g.day != day or not g.cast_confirm(uid, yes):
                return False
            await self.save()
            self.confirm_dirty = True
        return True

    def vote_kb(self, uid: int) -> Kb:
        g = self.game
        rows = grid([Btn(text=p.name, callback_data=f"v:{self.game_id}:{g.day}:{p.uid}", style="danger")
                     for p in g.alive() if p.uid != uid])
        rows.append([Btn(text=texts.SKIP_BTN, callback_data=f"v:{self.game_id}:{g.day}:0")])
        return Kb(inline_keyboard=rows)

    async def _flush_live(self) -> None:
        """Har harakat/ovoz alohida xabar. Guruh limiti to'lsa, navbatdagilar bitta xabarga birlashadi."""
        if not self.live_lines:
            return
        lines, self.live_lines = self.live_lines, []
        if len(lines) <= GROUP_PER_MIN - 4 - group_recent(self.chat_id):
            for line in lines:
                await send(self.bot, self.chat_id, line)
        else:
            await send(self.bot, self.chat_id, "\n".join(lines))

    async def _economy(self, ev) -> None:
        for e in ev:
            if e.kind == "robbed" and e.data["what"] == "dollars":
                e.data["amount"] = await db.rob_dollars(e.target, e.uid)
            elif e.kind == "robbed" and e.data["what"] == "item":
                await db.change_item(e.target, e.data["item"], -1)
                await db.change_item(e.uid, e.data["item"], 1)
            elif e.kind == "item_used":
                await db.change_item(e.uid, e.data["item"], -1)
            elif e.kind == "dug":
                await db.add_balance(e.uid, e.data["dollars"], int(e.data["diamond"]))

    async def _announce(self, ph: str, ev) -> None:
        g = self.game
        pub, priv = texts.morning(g, ev)
        if ph == NIGHT:  # tungi voqealar - bitta xabarda
            pub = ["\n\n".join(pub) if pub else choice(texts.QUIET)]
        for text in pub:
            await send(self.bot, self.chat_id, text)
        for uid, t in priv:
            await send(self.bot, uid, t)
        if g.phase != FINISHED:  # har qanday o'limdan keyin so'nggi so'z
            hanged = {e.target for e in ev if e.kind == "hanged"}
            for uid in texts.victims(ev):
                self.last_words[uid] = time.time() + LAST_WORDS_SECS
                await send(self.bot, uid, texts.death_pm(uid in hanged))

    async def _finish(self) -> None:
        g = self.game
        await db.finish_game(self.game_id, self.chat_id, "finished", g.winner,
                             [(p.uid, p.role, p.team, p.alive, p.won) for p in g.players])
        self.close()
        minutes = max(1, round((time.time() - self.meta["started"]) / 60)) if "started" in self.meta else None
        await send(self.bot, self.chat_id, texts.game_over(g, minutes))
        for p in g.players:
            reward = config.REWARD_PLAY + (config.REWARD_WIN if p.won else 0)
            if p.uid >= FAKE_BASE:
                continue
            u = await db.get_user(p.uid)
            inv = await db.inventory(p.uid) if u else []
            await send(self.bot, p.uid, texts.result_pm(p.won, reward, u, inv), profile_kb(inv, p.uid) if u else None,
                       effect=EFFECT_WIN if p.won else None)

    async def abort(self, text: str = texts.STOPPED) -> None:
        if self.game_id:
            await db.finish_game(self.game_id, self.chat_id, "aborted", None, [])
        elif self.lobby_msg:
            await edit(self.bot, self.chat_id, self.lobby_msg, text)
        await send(self.bot, self.chat_id, text)
        self.close()
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()

    def close(self) -> None:
        if RUNNERS.get(self.chat_id) is self:
            del RUNNERS[self.chat_id]
        for uid in [u for u, r in PLAYING.items() if r is self]:
            del PLAYING[uid]

    # ---------- tungi harakatlar ----------
    def night_kb(self, uid: int, kind: str | None = None) -> Kb | None:
        g = self.game
        acts = g.available_actions(uid)
        if not acts:
            return None
        pre = f"{self.game_id}:{g.day}"
        skip = [Btn(text=texts.SKIP_NIGHT_BTN, callback_data=f"a:{pre}:{SKIP}:0")]  # har menyuda pastda
        if kind is None and len(acts) > 1:
            return Kb(inline_keyboard=[[Btn(text=ACTION_LABELS[k], callback_data=f"k:{pre}:{k}", style=kind_style(k))]
                                       for k in acts] + [skip])
        kind = kind or acts[0]
        if kind in NO_TARGET:
            return Kb(inline_keyboard=[[Btn(text=ACTION_LABELS[kind], callback_data=f"a:{pre}:{kind}:0",
                                            style=kind_style(kind))], skip])
        rows = grid([Btn(text=g.get(t).name, callback_data=f"a:{pre}:{kind}:{t}", style=kind_style(kind))
                     for t in g.targets(uid, kind)])
        return Kb(inline_keyboard=rows + [skip])

    async def on_action(self, uid: int, day: int, kind: str, target: int) -> bool:
        async with self.lock:
            g = self.game
            if not g or g.phase != NIGHT or g.day != day or not g.submit(uid, kind, target or None):
                return False
            await self.save()
            if kind != SKIP:  # hech narsa qilmagani guruhga yozilmaydi
                self.live_lines.append(texts.act_feed(g.get(uid).role, kind))
        if kind == SKIP and g.get(uid).role == "don":
            for m in g.teammates(uid):
                if m.alive:
                    await send(self.bot, m.uid, texts.DON_SKIPPED)
        if kind == "mafia_kill":
            me = g.get(uid)
            for m in g.teammates(uid):
                if m.alive:
                    await send(self.bot, m.uid, texts.mafia_voted(me.name, g.get(target).name))
        return True

    async def on_vote(self, uid: int, day: int, target: int) -> bool:
        async with self.lock:
            g = self.game
            if not g or g.day != day or not g.cast_vote(uid, target or None):
                return False
            await self.save()
            self.live_lines.append(texts.vote_feed(g, uid, target or None))
        return True

    async def on_private_text(self, uid: int, text: str) -> bool:
        g = self.game
        if not g:
            return False
        if (deadline := self.last_words.pop(uid, None)) is not None:
            if deadline > time.time():
                await send(self.bot, self.chat_id, texts.last_words(g, uid, text[:500]))
            else:  # kechikdi: hech qayerga yuborilmaydi
                await send(self.bot, uid, texts.LAST_WORDS_LATE)
            return True
        p = g.get(uid)
        if p and not p.alive:  # 👻 o'liklar chati
            for d in g.players:
                if not d.alive and d.uid != uid:
                    await send(self.bot, d.uid, texts.ghost(p.name, text[:500]))
            return True
        if g.phase != NIGHT or not p or not (p.team == MAFIA or p.role in ("komissar", "serjant")):
            return False
        for m in g.teammates(uid):
            if m.alive:
                await send(self.bot, m.uid, texts.relay(p.name, text[:500]))
        dn = g.by_role("donishmand")
        if dn and dn.uid != uid:
            await send(self.bot, dn.uid, texts.overheard(text[:500]))
        return True

    async def leave(self, uid: int) -> None:
        if not self.game:
            self.members = [(u, n) for u, n in self.members if u != uid]
            PLAYING.pop(uid, None)
            self.lobby_dirty = True
            return
        async with self.lock:
            ev = self.game.kill_player(uid)
            if not ev:
                return
            await self.save()
        await self._announce(DAY, ev)


async def restore(bot: Bot) -> None:
    for row in await db.running_games():
        r = Runner(bot, row.chat_id, await db.group_settings(row.chat_id))
        r.game, r.meta, r.game_id = Game.from_dict(row.state["game"]), row.state.get("meta", {}), row.id
        for p in r.game.players:
            PLAYING[p.uid] = r
        r.task = asyncio.create_task(r._loop())
        log.info("restored game %s in %s", row.id, row.chat_id)
