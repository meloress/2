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
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError,
                                TelegramRetryAfter, TelegramServerError)
from aiogram.types import FSInputFile, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from . import config, db, pro, texts
from .engine.game import AFK_LIMIT, CONFIRM, DAY, FINISHED, NIGHT, SKIP, VOTING, Game, couple_pairs
from .engine.roles import ACTION_LABELS, MAFIA, NO_TARGET, ROLES
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
    """Telegram so'rovi. Xato o'yinni yiqitmaydi: tarmoq/server xatosida qayta urinadi, oxirida None."""
    for attempt in range(3):
        try:
            await pace()
            return await fn(*a, **kw)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            log.info("telegram: %s", e)
            return None
        except (TelegramNetworkError, TelegramServerError) as e:  # vaqtinchalik uzilish / 5xx
            log.warning("telegram tarmoq xatosi (%d-urinish): %s", attempt + 1, e)
            await asyncio.sleep(1 + attempt * 2)
    return None


_BG: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    """Fon vazifasi. Havola saqlanadi: aks holda Python uni tugamasdan yig'ishtirib yuborishi mumkin."""
    t = asyncio.create_task(coro)
    _BG.add(t)
    t.add_done_callback(_BG.discard)
    return t


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
    """Profil tugmalari: har buyum ON/OFF (3 tadan qatorda), PRO, hamyon, do'kon, do'st taklif qilish."""
    toggles = [Btn(text=f"{texts.ITEMS[i.item].split(' ', 1)[0]} - {'🟢 ON' if i.enabled else '🔴 OFF'}",
                   callback_data=f"t:{i.item}", style="success" if i.enabled else "danger")
               for i in inv if i.item in texts.ITEMS and i.qty > 0]
    rows = grid(toggles, 3) if toggles else []
    rows += [[pro_btn()],
             [Btn(text=texts.BUY_BTN, callback_data="m:buy"), Btn(text=texts.GEM_BTN, callback_data="m:gem")],
             [Btn(text=texts.PAY_BTN, callback_data="m:pay"), Btn(text=texts.GIFT_BTN, callback_data="m:gift")],
             [Btn(text=texts.GROUPS_BTN, callback_data="m:groups"),
              Btn(text=texts.SHOP_BTN, callback_data="shop", style="primary")]]
    if config.NEWS_URL:
        rows.append([Btn(text=texts.NEWS_BTN, url=config.NEWS_URL)])
    if uid is not None:
        rows.append([Btn(text=texts.INVITE_BTN, url=invite_url(uid), style="success")])
    rows.append([back_btn()])
    return Kb(inline_keyboard=rows)


def pro_btn() -> Btn:
    return Btn(text=texts.PRO_BTN, callback_data="m:pro", style="success", icon_custom_emoji_id=pro.BADGE_ID)


def back_btn() -> Btn:
    """Bosh menyuga qaytish (handlers.cb_menu, m:home)."""
    return Btn(text=texts.BACK_BTN, callback_data="m:home")


def grid(btns: list[Btn], cols: int | None = None) -> list[list[Btn]]:
    """Ko'p o'yinchida tugmalar 2-3 ustunda."""
    cols = cols or (1 if len(btns) <= 8 else 2 if len(btns) <= 30 else 3)
    return [btns[i:i + cols] for i in range(0, len(btns), cols)]


def bot_link(payload: str = "") -> str:
    return f"https://t.me/{BOT_USERNAME}" + (f"?start={payload}" if payload else "")


class Runner:
    def __init__(self, bot: Bot, chat_id: int, settings: dict, title: str = "", couple: bool = False):
        self.bot, self.chat_id, self.s, self.title = bot, chat_id, settings, title
        self.couple = couple  # 💞 paralar o'yini (/couplegame)
        self.partners: dict[int, int] = {}  # qo'shilganda: uid -> /couple jufti (ro'yxatda juftlab ko'rsatish)
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
        self.confirm_shown: tuple[int, int] | None = None  # guruh xabaridagi 👍/👎 sonlari (keraksiz tahrir bo'lmasin)
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
            await db.save_lobby(self.chat_id, self.lobby_msg)
        for uid in NEXT.pop(self.chat_id, set()):
            await send(self.bot, uid, texts.next_game(self.title), self._lobby_kb())

    async def repost_lobby(self) -> None:
        """Ro'yxat yozishmalar orasida tepada qolib ketganda: o'sha ro'yxat bilan pastda qayta chiqadi."""
        old = self.lobby_msg
        m = await send(self.bot, self.chat_id, self._lobby_text(), self._lobby_kb())
        if not m:
            return
        if self.game or self.chat_id not in RUNNERS:  # yuborish paytida o'yin boshlangan/bekor bo'lgan bo'lishi mumkin
            await _call(self.bot.delete_message, self.chat_id, m.message_id)
            return
        self.lobby_msg = m.message_id
        await db.save_lobby(self.chat_id, self.lobby_msg)
        if old:
            await _call(self.bot.delete_message, self.chat_id, old)
        await _call(self.bot.pin_chat_message, self.chat_id, self.lobby_msg, disable_notification=True)

    async def _drop_lobby_msg(self) -> None:
        """O'yin bekor bo'lganda: ro'yxat xabari pindan olinadi va o'chiriladi."""
        if self.lobby_msg:
            msg, self.lobby_msg = self.lobby_msg, None
            await _call(self.bot.unpin_chat_message, self.chat_id, message_id=msg)
            await _call(self.bot.delete_message, self.chat_id, msg)

    def _lobby_text(self) -> str:
        left = max(0, int(self.lobby_deadline - time.time()))
        return texts.couple_lobby(self.members, self.partners, left) if self.couple else texts.lobby(self.members, left)

    def _lobby_kb(self) -> Kb:
        if self.couple:  # 💞 qizil tugma
            return Kb(inline_keyboard=[[Btn(text=texts.COUPLE_JOIN_BTN, url=bot_link(f"join{self.chat_id}"),
                                            style="danger")]])
        return Kb(inline_keyboard=[[Btn(text=texts.JOIN_BTN, url=bot_link(f"join{self.chat_id}"), style="success")]])

    async def _lobby_loop(self) -> None:
        last_edit = time.time()
        while time.time() < self.lobby_deadline and len(self.members) < MAX_PLAYERS:
            await asyncio.sleep(1)
            if self.lobby_msg and (self.lobby_dirty and time.time() - last_edit > 5 or time.time() - last_edit > 30):
                self.lobby_dirty, last_edit = False, time.time()
                await self._refresh_lobby()
        await self._start_game()

    async def _refresh_lobby(self) -> None:
        """Ro'yxatni yangilaydi; tahrirlab bo'lmasa (admin o'chirgan) - qayta yuboriladi, qo'shilish tugmasi yo'qolmaydi."""
        if not await edit(self.bot, self.chat_id, self.lobby_msg, self._lobby_text(), self._lobby_kb()):
            await self.repost_lobby()

    def join(self, uid: int, name: str) -> str:
        if self.game:
            return texts.NO_LOBBY
        if PLAYING.get(uid) not in (None, self):
            return texts.ALREADY_IN_GAME
        if len(self.members) >= MAX_PLAYERS:
            NEXT[self.chat_id].add(uid)
            return texts.LOBBY_FULL
        if all(u != uid for u, _ in self.members):
            self.members.append((uid, name))  # nickname ko'rsatishda qo'yiladi (PRO tugasa - darhol yo'qoladi)
            PLAYING[uid] = self
            self.lobby_dirty = True
        return texts.JOINED

    def extend(self, secs: int = 30) -> None:
        self.lobby_deadline += secs
        self.lobby_dirty = True

    def force_start(self) -> None:
        self.lobby_deadline = 0

    async def _start_game(self) -> None:
        await db.drop_lobby(self.chat_id)  # ro'yxat bosqichi tugadi (boshlandi yoki bekor)
        if self.couple:  # jufti qo'shilmaganlar (yoki ajrashganlar) chiqariladi
            partners = {u: p for u, _ in self.members if (p := await db.partner(u))}
            pairs = couple_pairs([u for u, _ in self.members], partners)
            dropped = [(u, n) for u, n in self.members if u not in pairs]
            self.members = [(u, n) for u, n in self.members if u in pairs]
            for u, _ in dropped:
                PLAYING.pop(u, None)
                await send(self.bot, u, texts.COUPLE_DROPPED)
            if dropped:
                await send(self.bot, self.chat_id, texts.couple_dropped(dropped))
        if len(self.members) < MIN_PLAYERS:  # ro'yxat xabari o'chadi, bekor qilingani alohida yoziladi
            await self._drop_lobby_msg()
            await send(self.bot, self.chat_id, texts.NEED_COUPLES if self.couple else texts.NEED_PLAYERS)
            self.close()
            return
        if self.lobby_msg:
            await _call(self.bot.unpin_chat_message, self.chat_id, message_id=self.lobby_msg)
        uids = [u for u, _ in self.members]
        items = await db.game_items(uids) if self.s["items"] else {}
        self.game = Game.create(self.chat_id, self.members, random.SystemRandom().randrange(2 ** 31),
                                frozenset(self.s["disabled"]), items, AFK_LIMIT if self.s.get("afk", True) else 0,
                                self.s.get("confirm", True))
        if self.couple:
            self.game.pairs, self.game.couple_mode = pairs, True
        spent = self.game.use_role_picks() + [(u, "ticket") for u in self.game.use_tickets()]
        spent += [(p.uid, "mask") for p in self.game.players if p.items.get("mask", 0) > 0]  # maska shu o'yinga
        for uid, item in spent:
            await db.change_item(uid, item, -1)
        self.meta["started"] = time.time()
        self.game_id = await db.create_game(self.chat_id, self.state())
        if self.game_id is None:
            await send(self.bot, self.chat_id, texts.GAME_EXISTS)
            self.close()
            return
        role_kb = Kb(inline_keyboard=[[Btn(text=texts.ROLE_BTN, callback_data=f"r:{self.game_id}", style="primary")]])
        if self.lobby_msg:
            await edit(self.bot, self.chat_id, self.lobby_msg,
                       texts.couple_started(self.game) if self.couple else texts.game_started(self.game), role_kb)
        await send(self.bot, self.chat_id, texts.GAME_STARTED, role_kb)  # pastda: botga o'tmasdan rolni ko'rish

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
            self.confirm_shown = g.confirm_tally()
            # tugmalar botda ham: admin guruhdagi xabarni o'chirsa ham hamma ovoz bera oladi
            pm_kb = self._confirm_kb(pm=True)
            for p in g.alive():
                if g.can_confirm(p.uid):
                    await send(self.bot, p.uid, texts.confirm_pm(g), pm_kb)
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

    def _confirm_kb(self, pm: bool = False) -> Kb:
        pre = f"c:{self.game_id}:{self.game.day}"
        yes, no = ("Osilsin", "Rahm qilinsin") if pm else self.game.confirm_tally()
        return Kb(inline_keyboard=[[Btn(text=f"👍 {yes}", callback_data=f"{pre}:1", style="success"),
                                    Btn(text=f"👎 {no}", callback_data=f"{pre}:0", style="danger")]])

    async def _edit_confirm(self, final: bool) -> None:
        g = self.game
        if g.phase != CONFIRM or g.candidate is None:  # kech kelgan bosish: tasdiq allaqachon tugagan
            self.confirm_dirty = False
            return
        mid = self.meta.get("confirm_msg")
        if final:  # tahrirlab bo'lmasa (xabar o'chirilgan) - natija yangi xabar bo'lib chiqadi
            self.confirm_dirty = False
            self.meta.pop("confirm_msg", None)
            if not (mid and await edit(self.bot, self.chat_id, mid, texts.confirm_result(g))):
                await send(self.bot, self.chat_id, texts.confirm_result(g))
            return
        if g.confirm_tally() == self.confirm_shown:
            return
        self.confirm_shown = g.confirm_tally()
        text, kb = texts.confirm_prompt(g, self.s["vote"]), self._confirm_kb()
        if not (mid and await edit(self.bot, self.chat_id, mid, text, kb)):  # admin o'chirdi - qayta yuboriladi
            m = await send(self.bot, self.chat_id, text, kb)
            self.meta["confirm_msg"] = m.message_id if m else None

    async def on_confirm(self, uid: int, day: int, yes: bool) -> bool:
        async with self.lock:
            g = self.game
            if not g or g.day != day or not g.cast_confirm(uid, yes):
                return False
            await self.save()
            self.confirm_dirty = True
        return True

    def _labeler(self, uid: int):
        """Tugma: (matn, icon). "5. Ism": o'yin boshidagi raqam; sheriklar oldida rol emojisi; PRO - belgi ikonkasi."""
        g = self.game
        mates = {m.uid: ROLES[m.role].name.split(" ", 1)[0] for m in g.teammates(uid)}

        def label(t: int) -> tuple[str, str | None]:
            text, icon = pro.label(t, g.get(t).name)
            return f"{g.num(t)}. " + (f"{mates[t]} {text}" if t in mates else text), icon  # raqam - ro'yxatdagi
        return label

    def _btn(self, lab: tuple[str, str | None], data: str, style: str | None) -> Btn:
        return Btn(text=lab[0], callback_data=data, style=style, icon_custom_emoji_id=lab[1])

    def vote_kb(self, uid: int) -> Kb:
        g = self.game
        label = self._labeler(uid)
        rows = [[self._btn(label(p.uid), f"v:{self.game_id}:{g.day}:{p.uid}", "danger")]
                for p in g.alive() if p.uid != uid]  # bir ustunda
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
                await db.add_balance(e.uid, e.data["dollars"], e.data["diamonds"])

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
                spawn(self._last_words_timeout(uid, self.last_words[uid]))

    async def _finish(self) -> None:
        g = self.game
        double = {p.uid for p in g.players if p.won and p.alive and (q := g.partner(p.uid)) and q.won and q.alive}
        await db.finish_game(self.game_id, self.chat_id, "finished", g.winner,
                             [(p.uid, p.role, p.team, p.alive, p.won) for p in g.players], double)
        for inviter, name in await db.pay_referrals([p.uid for p in g.players if p.uid < FAKE_BASE]):
            await send(self.bot, inviter, texts.ref_bonus(name))
        self.close()
        minutes = max(1, round((time.time() - self.meta["started"]) / 60)) if "started" in self.meta else None
        await send(self.bot, self.chat_id, texts.game_over(g, minutes))
        for p in g.players:
            reward = config.REWARD_PLAY + (pro.win_reward(p.uid) * (2 if p.uid in double else 1) if p.won else 0)
            if p.uid >= FAKE_BASE:
                continue
            u = await db.get_user(p.uid)
            inv = await db.inventory(p.uid) if u else []
            await send(self.bot, p.uid, texts.result_pm(p.won, reward, u, inv), profile_kb(inv, p.uid) if u else None,
                       effect=EFFECT_WIN if p.won else None)

    async def abort(self, text: str = texts.STOPPED) -> None:
        if self.game_id:
            await db.finish_game(self.game_id, self.chat_id, "aborted", None, [])
        else:  # ro'yxat bosqichida /stop
            await self._drop_lobby_msg()
            await db.drop_lobby(self.chat_id)
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
        label = self._labeler(uid)
        rows = grid([self._btn(label(t), f"a:{pre}:{kind}:{t}", kind_style(kind)) for t in g.targets(uid, kind)])
        return Kb(inline_keyboard=rows + [skip])

    async def on_action(self, uid: int, day: int, kind: str, target: int) -> bool:
        async with self.lock:
            g = self.game
            again = g is not None and (uid in g.actions or uid in g.mafia_votes)  # tanlovni almashtirdi
            if not g or g.phase != NIGHT or g.day != day or not g.submit(uid, kind, target or None):
                return False
            await self.save()
            if not again:  # qayta tanlov guruhga yozilmaydi
                line = texts.skip_feed(g.get(uid).role) if kind == SKIP else texts.act_feed(g.get(uid).role, kind)
                if line:
                    self.live_lines.append(line)
        if kind == SKIP and g.get(uid).role == "don":
            for m in g.teammates(uid):
                if m.alive:
                    await send(self.bot, m.uid, texts.DON_SKIPPED)
        if kind == "mafia_kill":
            me = g.get(uid)
            for m in g.teammates(uid):
                if m.alive:
                    await send(self.bot, m.uid, texts.mafia_voted(texts.dn(me), texts.dn(g.get(target))))
        return True

    async def on_vote(self, uid: int, day: int, target: int) -> bool:
        async with self.lock:
            g = self.game
            if not g or g.day != day or not g.cast_vote(uid, target or None):
                return False
            await self.save()
            self.live_lines.append(texts.vote_feed(g, uid, target or None))
        return True

    async def _last_words_timeout(self, uid: int, deadline: float) -> None:
        """So'nggi so'z yozilmay vaqt tugasa - o'ziga xabar."""
        await asyncio.sleep(max(0.0, deadline - time.time()))
        if self.last_words.get(uid) == deadline:
            del self.last_words[uid]
            await send(self.bot, uid, texts.LAST_WORDS_TIMEOUT)

    async def on_private_text(self, uid: int, text: str, entities=None) -> bool:
        """text - oddiy matn (mantiq uchun); ko'rsatishda texts.said: premium emoji saqlanadi."""
        g = self.game
        if not g:
            return False
        if (deadline := self.last_words.pop(uid, None)) is not None:
            if deadline > time.time():
                await send(self.bot, self.chat_id, texts.last_words(g, uid, texts.said(text, entities)))
                await send(self.bot, uid, texts.LAST_WORDS_SENT)
            else:  # kechikdi: hech qayerga yuborilmaydi
                await send(self.bot, uid, texts.LAST_WORDS_LATE)
            return True
        p = g.get(uid)
        if g.pairs and p and p.alive and text.startswith("+"):  # 💞 juftga shaxsiy xabar
            q = g.partner(uid)
            if q and q.alive and text[1:].strip():
                await send(self.bot, q.uid, texts.partner_msg(texts.dn(p), texts.said(text, entities, len(text) - len(text[1:].lstrip()))))
                await send(self.bot, uid, texts.PARTNER_SENT)
            else:
                await send(self.bot, uid, texts.NO_PARTNER)
            return True
        if p and not p.alive:  # 👻 o'liklar chati
            for d in g.players:
                if not d.alive and d.uid != uid:
                    await send(self.bot, d.uid, texts.ghost(texts.dn(p), texts.said(text, entities)))
            return True
        if g.phase != NIGHT or not p or not (p.team == MAFIA or p.role in ("komissar", "serjant")):
            return False
        for m in g.teammates(uid):
            if m.alive:
                await send(self.bot, m.uid, texts.relay(texts.dn(p), texts.said(text, entities)))
        dn = g.by_role("donishmand")
        if dn and dn.uid != uid:
            await send(self.bot, dn.uid, texts.overheard(texts.said(text, entities)))
        return True

    async def move(self, new_id: int) -> None:
        """Guruh supergroup'ga aylandi: Telegram yangi chat ID beradi, eski xabar ID'lari yaroqsiz."""
        RUNNERS.pop(self.chat_id, None)
        old, self.chat_id = self.chat_id, new_id
        RUNNERS[new_id] = self
        self.lobby_msg = None
        if self.game:
            self.game.chat_id = new_id
            await db.move_chat(old, new_id)
            await self.save()
        else:
            await db.drop_lobby(old)

    async def leave(self, uid: int) -> None:
        if not self.game:
            self.members = [(u, n) for u, n in self.members if u != uid]
            PLAYING.pop(uid, None)
            self.lobby_dirty = True
            return
        if PLAYING.get(uid) is self:  # boshqa guruhdagi o'yinga kira olsin
            del PLAYING[uid]
        async with self.lock:
            ev = self.game.kill_player(uid)
            if not ev:
                return
            await self.save()
        await self._announce(DAY, ev)


async def restore(bot: Bot) -> None:
    for row in await db.lobbies():  # ro'yxatlar xotirada edi - qayta ishga tushishda yo'qoldi
        await _call(bot.unpin_chat_message, row.chat_id, message_id=row.msg_id)
        await _call(bot.delete_message, row.chat_id, row.msg_id)
        await send(bot, row.chat_id, texts.LOBBY_LOST)
        await db.drop_lobby(row.chat_id)
    for row in await db.running_games():
        r = Runner(bot, row.chat_id, await db.group_settings(row.chat_id))
        r.game, r.meta, r.game_id = Game.from_dict(row.state["game"]), row.state.get("meta", {}), row.id
        for p in r.game.players:
            PLAYING[p.uid] = r
        r.task = asyncio.create_task(r._loop())
        log.info("restored game %s in %s", row.id, row.chat_id)
