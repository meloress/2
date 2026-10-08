import asyncio
import logging
import re
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, ErrorEvent, LabeledPrice, PreCheckoutQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Message

from . import config, db, pro, texts
from .engine.game import CONFIRM, DAY, FINISHED, NIGHT, VOTING
from .engine.roles import ROLES
from .engine.setup import CORE
from .runner import NEXT, PLAYING, RUNNERS, Runner, _call, spawn, back_btn, pro_btn, bot_link, edit, grid, invite_url, profile_kb, send

log = logging.getLogger(__name__)
router = Router()
GROUPS = F.chat.type.in_({"group", "supergroup"})
PRIVATE = F.chat.type == "private"


@router.message.outer_middleware()
async def drop_commands(handler, msg: Message, data):
    """Guruhda botga yozilgan /buyruq ishlangandan keyin o'chiriladi (chat toza tursin)."""
    try:
        return await handler(msg, data)
    finally:
        text = msg.text or ""
        if msg.chat.type in ("group", "supergroup") and text.startswith("/"):
            cmd = text.split()[0]
            bot: Bot = data["bot"]
            if "@" not in cmd or cmd.split("@", 1)[1].lower() == ((await bot.me()).username or "").lower():
                await _call(msg.delete)


async def is_admin(bot: Bot, chat_id: int, uid: int, msg: Message | None = None) -> bool:
    if uid in config.ADMIN_IDS:
        return True
    if (sc := getattr(msg, "sender_chat", None)) and sc.id == chat_id:  # yashirin admin guruh nomidan yozadi
        return True
    m = await bot.get_chat_member(chat_id, uid)
    return m.status in ("administrator", "creator")


# ============ GURUH ============
@router.message(Command("game", "couplegame"), GROUPS)
async def cmd_game(msg: Message, bot: Bot, command: CommandObject | None = None):
    """/game - oddiy o'yin; /couplegame - 💞 paralar o'yini (faqat /couple juftlari)."""
    couple = getattr(command, "command", "") == "couplegame"
    if r := RUNNERS.get(msg.chat.id):
        if not r.game and r.couple == couple:  # ro'yxat hali ochiq: pastga qayta chiqariladi
            return await r.repost_lobby()
        return await msg.answer(texts.GAME_EXISTS if r.game else texts.OTHER_LOBBY)
    me = await bot.get_chat_member(msg.chat.id, bot.id)
    if me.status != "administrator":
        await msg.answer(texts.NOT_ADMIN_WARN)
    settings = await db.group_settings(msg.chat.id, msg.chat.title or "")
    if msg.chat.id in RUNNERS:  # await paytida boshqasi ochgan bo'lishi mumkin
        return
    r = Runner(bot, msg.chat.id, settings, msg.chat.title or "", couple=couple)
    r.opener = msg.from_user.id if msg.from_user else None
    await r.open_lobby()


@router.message(Command("testgame"), GROUPS, F.from_user.id.in_(config.ADMIN_IDS))
async def cmd_testgame(msg: Message, bot: Bot, command: CommandObject):
    """Bot egasi uchun: siz + bot-o'yinchilar. /testgame 8"""
    if msg.chat.id in RUNNERS:
        return await msg.answer(texts.GAME_EXISTS)
    n = int(command.args) if (command.args or "").strip().isdigit() else 8
    n = max(4, min(30, n))
    settings = await db.group_settings(msg.chat.id, msg.chat.title or "")  # haqiqiy o'yindagi vaqtlar
    r = Runner(bot, msg.chat.id, settings, msg.chat.title or "")
    r.add_bots(n - 1)
    await r.open_lobby()
    await msg.answer(f"🧪 Test o'yin: {n - 1} ta 🤖 bot qo'shildi. «Qo'shilish» ni bosing, keyin /begin.")


@router.message(Command("next"), GROUPS)
async def cmd_next(msg: Message):
    await db.upsert_user(msg.from_user.id, msg.from_user.full_name, msg.from_user.username)
    NEXT[msg.chat.id].add(msg.from_user.id)
    await msg.reply(texts.NEXT_OK)


@router.message(Command("extend"), GROUPS)
async def cmd_extend(msg: Message, bot: Bot, command: CommandObject):
    """/extend - 30 soniya, /extend 60 - 60 soniya. Faqat adminlar va /game bosgan; qolgan vaqt <= 10 daqiqa."""
    r = RUNNERS.get(msg.chat.id)
    if r and not r.game:
        if msg.from_user.id != r.opener and not await is_admin(bot, msg.chat.id, msg.from_user.id, msg):
            return await msg.answer(texts.ONLY_STARTER_EXTEND)
        arg = (command.args or "").strip()
        secs = min(600, max(1, int(arg))) if arg.isdigit() else 30
        secs = max(0, min(secs, int(time.time() + 600 - r.lobby_deadline)))  # ro'yxat cheksiz cho'zilmasin
        if not secs:
            return await msg.answer(texts.EXTEND_MAX)
        r.extend(secs)
        await msg.answer(f"⏳ Ro'yxatdan o'tish {secs} soniyaga uzaytirildi.")


@router.message(Command("begin", "couplestart"), GROUPS)
async def cmd_begin(msg: Message, bot: Bot, command: CommandObject | None = None):
    r = RUNNERS.get(msg.chat.id)
    if r and not r.game and getattr(command, "command", "") == "couplestart" and not r.couple:
        return await msg.answer(texts.NOT_COUPLE_LOBBY)
    if r and not r.game:
        uid = msg.from_user.id
        if uid != r.opener and not await is_admin(bot, msg.chat.id, uid, msg):
            return await msg.answer(texts.ONLY_STARTER)
        r.force_start()


@router.message(Command("stop"), GROUPS)
async def cmd_stop(msg: Message, bot: Bot):
    r = RUNNERS.get(msg.chat.id)
    if r:
        if not await is_admin(bot, msg.chat.id, msg.from_user.id, msg):
            return await msg.answer(texts.ONLY_ADMIN)
        await r.abort()


def _in_game(r, uid: int) -> bool:
    """O'yin ketyapti va o'yinchi tirik: chiqish limiti/jarimasi faqat shunda."""
    p = r.game.get(uid) if r.game else None
    return bool(p and p.alive and r.game.phase != FINISHED)


LEAVING: set[int] = set()  # ikki marta bosilsa jarima ikki marta yechilmasin


@router.message(Command("leave"), GROUPS)
async def cmd_leave(msg: Message):
    """Kuniga config.LEAVE_FREE ta chiqish bepul, keyingisi tasdiq bilan -LEAVE_FINE (balans minusga tushadi)."""
    r, u = RUNNERS.get(msg.chat.id), msg.from_user
    if not r or PLAYING.get(u.id) is not r:
        return
    if not _in_game(r, u.id):  # ro'yxat bosqichi yoki o'lgan - bepul, sanalmaydi
        await r.leave(u.id)
        return await msg.answer(f"🚪 {texts.mention(u.id, u.full_name)} o'yindan chiqdi.")
    n, limit = await db.leaves_today(u.id), pro.leave_free(u.id)
    if n < limit:
        await db.count_leave(u.id)
        await r.leave(u.id)
        return await msg.answer(texts.left_free(u.id, u.full_name, n + 1, limit))
    kb = Kb(inline_keyboard=[[Btn(text=texts.leave_yes_btn(), callback_data=f"lv:{r.game_id}:{u.id}:1", style="danger")],
                             [Btn(text=texts.LEAVE_NO_BTN, callback_data=f"lv:{r.game_id}:{u.id}:0", style="success")]])
    await msg.answer(texts.leave_warn(u.id, u.full_name, limit), reply_markup=kb)


@router.callback_query(F.data.startswith("lv:"))
async def cb_leave(cq: CallbackQuery):
    _, gid, uid, yes = cq.data.split(":")
    uid = int(uid)
    if cq.from_user.id != uid:
        return await cq.answer(texts.NOT_YOUR_BTN, show_alert=True)
    await _call(cq.message.delete)
    r = PLAYING.get(uid)
    if yes != "1" or not r or str(r.game_id) != gid or not _in_game(r, uid) or uid in LEAVING:
        return await cq.answer(texts.LEAVE_STAY)
    LEAVING.add(uid)
    try:
        await db.count_leave(uid, config.LEAVE_FINE)
        await r.leave(uid)
    finally:
        LEAVING.discard(uid)
    await send(cq.bot, r.chat_id, texts.left_fined(uid, cq.from_user.full_name))
    await cq.answer()


@router.message(Command("top"), GROUPS)
async def cmd_top_group(msg: Message):
    await msg.answer(texts.top(await db.top(msg.chat.id), "Guruh reytingi"))


@router.message(Command("rules"))
async def cmd_rules(msg: Message):
    await msg.answer(texts.rules())


# ---------- sozlamalar ----------
TIMERS = {"lobby": ("👥 Ro'yxat", [60, 90, 120, 180, 300]), "night": ("🌙 Tun", [30, 45, 60, 90, 120]),
          "day": ("🌆 Kun", [30, 60, 90, 120, 180]), "vote": ("🗳 Ovoz", [30, 45, 60, 90])}


FLAGS = ("items", "afk", "confirm")


def settings_kb(s: dict) -> Kb:
    on = lambda x: "success" if x else "danger"
    rows = [[Btn(text=f"{label}: {s[k]} s", callback_data=f"s:{k}", style="primary")] for k, (label, _) in TIMERS.items()]
    rows.append([Btn(text=f"🎒 Buyumlar: {'✅' if s['items'] else '❌'}", callback_data="s:items", style=on(s["items"]))])
    rows.append([Btn(text=f"😴 AFK chiqarish: {'✅' if s['afk'] else '❌'}", callback_data="s:afk", style=on(s["afk"]))])
    rows.append([Btn(text=f"🪢 Osishni tasdiqlash: {'✅' if s['confirm'] else '❌'}", callback_data="s:confirm",
                     style=on(s["confirm"]))])
    rows.append([Btn(text="🎭 Rollar", callback_data="s:roles", style="primary")])
    return Kb(inline_keyboard=rows)


def roles_kb(s: dict) -> Kb:
    codes = [c for c in ROLES if c not in CORE]
    btns = [Btn(text=ROLES[c].name, callback_data=f"s:r:{c}", style="danger" if c in s["disabled"] else "success")
            for c in codes]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([Btn(text="⬅️ Orqaga", callback_data="s:main")])
    return Kb(inline_keyboard=rows)


@router.message(Command("settings"), GROUPS)
async def cmd_settings(msg: Message, bot: Bot):
    if not await is_admin(bot, msg.chat.id, msg.from_user.id, msg):
        return await msg.answer(texts.ONLY_ADMIN)
    s = await db.group_settings(msg.chat.id, msg.chat.title or "")
    await msg.answer("⚙️ <b>Guruh sozlamalari</b> (keyingi o'yindan kuchga kiradi)", reply_markup=settings_kb(s))


@router.callback_query(F.data.startswith("s:"))
async def cb_settings(cq: CallbackQuery, bot: Bot):
    chat = cq.message.chat.id
    if not await is_admin(bot, chat, cq.from_user.id):
        return await cq.answer(texts.ONLY_ADMIN, show_alert=True)
    s = await db.group_settings(chat)
    parts = cq.data.split(":")
    key = parts[1]
    if key in TIMERS:
        vals = TIMERS[key][1]
        s[key] = vals[(vals.index(s[key]) + 1) % len(vals)] if s[key] in vals else vals[0]
    elif key in FLAGS:
        s[key] = not s.get(key)
    elif key == "r":
        code = parts[2]
        dis = set(s["disabled"])
        dis.symmetric_difference_update({code})
        s["disabled"] = sorted(dis)
    if key in TIMERS or key in FLAGS:
        await db.save_group_settings(chat, s)
        await cq.message.edit_reply_markup(reply_markup=settings_kb(s))
    elif key == "r":
        await db.save_group_settings(chat, s)
        await cq.message.edit_reply_markup(reply_markup=roles_kb(s))
    elif key == "roles":
        await cq.message.edit_reply_markup(reply_markup=roles_kb(s))
    else:
        await cq.message.edit_reply_markup(reply_markup=settings_kb(s))
    await cq.answer()


# ---------- ovoz berish ----------
@router.callback_query(F.data.startswith("c:"))
async def cb_confirm(cq: CallbackQuery):
    _, gid, day, yes = cq.data.split(":")
    r = RUNNERS.get(cq.message.chat.id) or PLAYING.get(cq.from_user.id)  # guruhdan yoki botning shaxsiy chatidan
    if not r or r.game_id != int(gid):
        return await cq.answer("⌛️ Bu ovoz berish tugagan.")
    ok = await r.on_confirm(cq.from_user.id, int(day), yes == "1")
    await cq.answer(("👍 Osishga rozi bo'ldingiz" if yes == "1" else "👎 Rahm so'radingiz") if ok
                    else "❌ Siz ovoz bera olmaysiz")


# ---------- pul o'tkazish va tarqatish ----------
MAX_AMOUNT = 10 ** 9
_refresh: dict[int, asyncio.Task] = {}  # giveaway_id -> kechiktirilgan tahrir


@router.message(Command("send", "give"), GROUPS)
async def cmd_send(msg: Message, bot: Bot, command: CommandObject):
    """/send 100 10 - 10 dan 10 kishiga; /send 100 - bitta kishiga hammasi; reply + /send 100 - o'tkazish.
    /give - xuddi shunday, faqat olmos. Buyruq har doim o'chiriladi (drop_commands)."""
    cur = "diamonds" if (getattr(command, "command", "") or "").lower() == "give" else "dollars"
    args = (command.args or "").split()
    nums = [int(a) for a in args] if args and all(a.isdigit() for a in args) else []
    me = await _user(msg) if nums and len(nums) <= 2 and all(0 < x <= MAX_AMOUNT for x in nums) else None
    if me and me.games < config.SEND_GAMES:  # yangi (ko'pincha soxta) profillardan pul to'plashga qarshi
        return await send(bot, msg.chat.id, texts.send_locked(me.games))
    if me:
        u, reply = msg.from_user, msg.reply_to_message
        target = reply.from_user if reply else None
        if len(nums) == 1 and target and not target.is_bot and target.id != u.id:
            await db.upsert_user(target.id, target.full_name, target.username)
            if await db.transfer(u.id, target.id, nums[0], cur):
                await send(bot, msg.chat.id, texts.transfer_done(u.full_name, u.id, target.full_name, target.id,
                                                                 nums[0], cur))
        elif len(nums) == 1 and not reply or len(nums) == 2 and nums[1] <= nums[0]:
            per = nums[-1]
            parts = nums[0] // per
            gid = await db.create_giveaway(msg.chat.id, u.id, per, parts, cur)
            if gid:
                kb = Kb(inline_keyboard=[[Btn(text=texts.GIVEAWAY_BTN, callback_data=f"g:{gid}", style="success")]])
                m = await send(bot, msg.chat.id, texts.giveaway(u.full_name, u.id, per, parts, (), cur), kb)
                if m:  # tarqatma tepada qadalib turadi, tugagach pindan olinadi (_refresh_giveaway)
                    await _call(bot.pin_chat_message, msg.chat.id, m.message_id, disable_notification=True)
                    await db.set_giveaway_msg(gid, m.message_id)
                    spawn(expire_giveaway(bot, gid, texts.GIVEAWAY_TTL_MIN * 60))


@router.callback_query(F.data.startswith("g:"))
async def cb_giveaway(cq: CallbackQuery, bot: Bot):
    gid = int(cq.data[2:])
    me = await _user(cq)
    if me and me.games < config.CLAIM_GAMES:
        return await cq.answer(texts.claim_locked(), show_alert=True)
    g = await db.claim(gid, cq.from_user.id) if me else None
    if not g:
        return await cq.answer(texts.GIVEAWAY_NO)
    await cq.answer(texts.GIVEAWAY_GOT.format(g.per, texts.CUR[g.currency or "dollars"]), show_alert=True)
    if gid not in _refresh:  # ko'p bosilganda 3 s da bir marta tahrirlash (guruh limiti)
        _refresh[gid] = asyncio.create_task(_refresh_giveaway(bot, cq.message.chat.id, cq.message.message_id, gid))


async def _refresh_giveaway(bot: Bot, chat_id: int, msg_id: int, gid: int) -> None:
    try:
        await asyncio.sleep(3)
        g = await db.get_giveaway(gid)
        sender = await db.get_user(g.sender_id)
        kb = None if g.left <= 0 else Kb(inline_keyboard=[[Btn(text=f"{texts.GIVEAWAY_BTN} ({g.left})",
                                                               callback_data=f"g:{gid}", style="success")]])
        await edit(bot, chat_id, msg_id, texts.giveaway(sender.full_name if sender else "?", g.sender_id,
                                                        g.per, g.parts, await db.giveaway_takers(gid),
                                                        g.currency or "dollars"), kb)
        if g.left <= 0:
            await _call(bot.unpin_chat_message, chat_id, message_id=msg_id)
    finally:
        _refresh.pop(gid, None)


async def expire_giveaway(bot: Bot, gid: int, delay: float) -> None:
    """Muddat tugadi: olinmagan ulushlar egasiga qaytadi, xabar tugmasiz qoladi va pindan olinadi."""
    await asyncio.sleep(max(0.0, delay))
    for _ in range(5):  # shu payt kimdir olayotgan bo'lsa, qayta urinish
        g, refund = await db.close_giveaway(gid)
        if refund >= 0:
            break
        await asyncio.sleep(1)
    if not g or refund <= 0:
        return
    if g.msg_id:
        sender = await db.get_user(g.sender_id)
        cur = g.currency or "dollars"
        text = texts.giveaway(sender.full_name if sender else "?", g.sender_id, g.per, g.parts,
                              await db.giveaway_takers(gid), cur)
        await edit(bot, g.chat_id, g.msg_id, texts.giveaway_closed(text, cur), None)
        await _call(bot.unpin_chat_message, g.chat_id, message_id=g.msg_id)
    await send(bot, g.sender_id, texts.giveaway_refund(refund, g.currency or "dollars"))


async def restore_giveaways(bot: Bot) -> None:
    """Qayta ishga tushishda ochiq tarqatmalarning muddat taymerlari tiklanadi."""
    ttl = texts.GIVEAWAY_TTL_MIN * 60
    for g in await db.open_giveaways():
        left = ttl - (db.now() - db._aware(g.created_at)).total_seconds()
        spawn(expire_giveaway(bot, g.id, left))


# ---------- para ----------
async def _couple_target(msg: Message, command: CommandObject):
    """Reply, @username yoki ismga bog'langan mention. (uid, ism) yoki None."""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        t = msg.reply_to_message.from_user
        return None if t.is_bot else (t.id, t.full_name)
    for ent in msg.entities or []:
        if ent.type == "text_mention" and ent.user and not ent.user.is_bot:
            return ent.user.id, ent.user.full_name
    arg = (command.args or "").strip()
    if arg.startswith("@") and (u := await db.user_by_username(arg)):
        return u.telegram_id, u.full_name
    return None


async def _name(uid: int) -> str:
    u = await db.get_user(uid)
    return u.full_name if u else "?"


@router.message(Command("couple"))
async def cmd_couple(msg: Message, bot: Bot, command: CommandObject):
    me = await _user(msg)
    if not me:
        return
    target = await _couple_target(msg, command)
    if not target:
        return await msg.reply(texts.COUPLE_HOW if not command.args else texts.COUPLE_NOT_FOUND)
    uid, name = target
    if uid == me.telegram_id:
        return await msg.reply(texts.COUPLE_SELF)
    if await db.partner(me.telegram_id):
        return await msg.reply(texts.COUPLE_YOU_TAKEN)
    if await db.partner(uid):
        return await msg.reply(texts.COUPLE_THEY_TAKEN)
    kb = Kb(inline_keyboard=[[
        Btn(text="✅ Tasdiqlash", callback_data=f"cp:{me.telegram_id}:{uid}:1", style="success"),
        Btn(text="❌ Bekor qilish", callback_data=f"cp:{me.telegram_id}:{uid}:0", style="danger")]])
    await send(bot, msg.chat.id, texts.couple_request(me.telegram_id, me.full_name, uid, name), kb)


@router.callback_query(F.data.startswith("cp:"))
async def cb_couple(cq: CallbackQuery, bot: Bot):
    _, a, b, yes = cq.data.split(":")
    a, b = int(a), int(b)
    if cq.from_user.id != b:
        return await cq.answer(texts.COUPLE_NOT_YOU, show_alert=True)
    if not await _user(cq):
        return await cq.answer()
    if yes != "1":
        text = texts.couple_rejected(b, cq.from_user.full_name)
    elif await db.make_couple(a, b):
        text = texts.couple_made(a, await _name(a), b, cq.from_user.full_name)
    else:
        return await cq.answer(texts.COUPLE_FAILED, show_alert=True)
    await cq.answer()
    await edit(bot, cq.message.chat.id, cq.message.message_id, text)


@router.message(Command("uncouple"))
async def cmd_uncouple(msg: Message):
    me = await _user(msg)
    if not me:
        return
    p = await db.break_couple(me.telegram_id)
    await msg.reply(texts.couple_broken(me.telegram_id, me.full_name, p, await _name(p)) if p else texts.COUPLE_NONE)


@router.message(Command("mycouple"))
async def cmd_mycouple(msg: Message):
    me = await _user(msg)
    if not me:
        return
    p = await db.partner(me.telegram_id)
    await msg.reply(texts.couple_show(me.telegram_id, me.full_name, p, await _name(p)) if p else texts.COUPLE_NONE)


@router.message(Command("players"), GROUPS)
async def cmd_players(msg: Message):
    r = RUNNERS.get(msg.chat.id)
    if r and r.game:
        await msg.answer(texts.players(r.game))
    elif r:
        await msg.answer(r._lobby_text())
    else:
        await msg.answer("🎮 Hozir o'yin yo'q. /game bilan boshlang!")

@router.callback_query(F.data.startswith("v:"))
async def cb_vote(cq: CallbackQuery):
    """Ovoz berish botning shaxsiy chatida."""
    _, gid, day, target = cq.data.split(":")
    r = PLAYING.get(cq.from_user.id)
    if not r or r.game_id != int(gid):
        return await cq.answer("⌛️ Bu ovoz berish tugagan.")
    if not await r.on_vote(cq.from_user.id, int(day), int(target)):
        return await cq.answer("❌ Ovoz bera olmaysiz yoki vaqt tugadi")
    t = r.game.get(int(target)) if int(target) else None
    await cq.message.edit_text(texts.vote_chosen(texts.dn(t) if t else None))
    await cq.answer()


# ============ SHAXSIY CHAT ============
async def _user(msg_or_cq) -> db.User | None:
    u = msg_or_cq.from_user
    user = await db.upsert_user(u.id, u.full_name, u.username)
    return None if user.banned else user


@router.message(CommandStart(), PRIVATE)
async def cmd_start(msg: Message, bot: Bot, command: CommandObject):
    arg = command.args or ""
    is_new = await db.get_user(msg.from_user.id) is None
    if not await _user(msg):
        return await msg.answer(texts.BANNED)
    if is_new and arg.startswith("ref") and arg[3:].isdigit() and int(arg[3:]) != msg.from_user.id:
        inviter = int(arg[3:])
        if await db.get_user(inviter):  # bonus darhol emas: do'st REF_GAMES ta o'yin o'ynagach (pay_referrals)
            await db.set_referrer(msg.from_user.id, inviter)
            await send(bot, inviter, texts.ref_joined(msg.from_user.full_name))
    if arg == "panel":
        return await send_panel_link(msg)
    if arg.startswith("join"):
        u = await db.get_user(msg.from_user.id)
        if u and u.dollars <= config.DEBT_LIMIT:
            return await msg.answer(texts.debt_block(u.dollars))
        r = RUNNERS.get(int(arg[4:])) if arg[4:].lstrip("-").isdigit() else None
        if r and r.couple and not r.game:  # 💞 faqat jufti borlar
            if not (p := await db.partner(msg.from_user.id)):
                return await msg.answer(texts.NO_COUPLE_JOIN)
            r.partners[msg.from_user.id] = p
        return await msg.answer(r.join(msg.from_user.id, msg.from_user.full_name) if r else texts.NO_LOBBY)
    await msg.answer(texts.welcome(), reply_markup=start_kb(msg.from_user.id))


def start_kb(uid: int | None = None) -> Kb:
    # admin=...: guruhga qo'shishda kerakli huquqlar so'raladi (xabar o'chirish, cheklash, pin)
    add = bot_link() + "?startgroup=true&admin=delete_messages+restrict_members+pin_messages"
    rows = [[Btn(text="🎮 O'yinni guruhingizga qo'shing", url=add)],
            [Btn(text="🏆 Reyting", callback_data="m:top", style="danger")]]
    if config.NEWS_URL:
        rows.append([Btn(text="📰 Yangiliklar", url=config.NEWS_URL)])
    rows += [[Btn(text="🎭 Rollar", callback_data="m:rules"), Btn(text="🛒 Do'kon", callback_data="m:shop")],
             [Btn(text="👤 Mening profilim", callback_data="m:profile")], [pro_btn()]]
    if uid is not None:
        rows.append([Btn(text=texts.INVITE_BTN, url=invite_url(uid), style="success")])
    return Kb(inline_keyboard=rows)


@router.callback_query(F.data.startswith("m:"))
async def cb_menu(cq: CallbackQuery):
    """Bosh menyu bo'limlari o'sha xabarning o'zida ochiladi, ⬅️ Orqaga bilan menyuga qaytiladi."""
    what = cq.data[2:]
    back = Kb(inline_keyboard=[[back_btn()]])
    ASK.pop(cq.from_user.id, None)  # boshqa bo'limga o'tdi - kutilayotgan javob bekor
    if what == "home":
        await show(cq, texts.welcome(), start_kb(cq.from_user.id))
    elif what == "rules":
        await show(cq, texts.rules(), back)
    elif what == "pro":
        await show(cq, texts.pro_info(cq.from_user.id), pro_kb())
    elif what == "top":
        await show(cq, texts.top(await db.top(), "Umumiy reyting"), back)
    elif what in ("buy", "gem") and config.DIAMONDS_OFF:
        return await cq.answer(texts.DIAMONDS_OFF, show_alert=True)
    elif what == "buy":
        btns = [Btn(text=f"{d}💵 - {n}💎", callback_data=f"xd:{n}") for n, d in config.DOLLAR_PACKS.items()]
        await show(cq, texts.BUY_DOLLARS, Kb(inline_keyboard=grid(btns, 2) + [[prof_back()]]))
    elif what == "gem":
        await show(cq, texts.GEM_WHO, Kb(inline_keyboard=[[Btn(text=texts.SELF_BTN, callback_data="gm:me"),
                                                          Btn(text=texts.OTHER_BTN, callback_data="gm:to")],
                                                         [prof_back()]]))
    elif what == "groups":
        await show(cq, texts.top_groups(await db.top_groups()), Kb(inline_keyboard=[[prof_back()]]))
    elif what in ("pay", "gift"):
        if not (u := await _user(cq)):
            return await cq.answer(texts.BANNED, show_alert=True)
        kb = Kb(inline_keyboard=[[prof_back()]])
        if u.games < config.SEND_GAMES:  # /send bilan bir xil: yangi profillardan pul yig'ishga qarshi
            await show(cq, texts.send_locked(u.games), kb)
        else:
            ASK[u.telegram_id] = "dollars" if what == "pay" else "diamonds"
            await show(cq, texts.ask_send(ASK[u.telegram_id]), kb)
    elif what in ("profile", "shop"):
        if not (u := await _user(cq)):
            return await cq.answer(texts.BANNED, show_alert=True)
        if what == "shop":
            await show(cq, texts.shop(u.dollars, u.telegram_id, u.diamonds), shop_kb(u.telegram_id))
        else:
            inv = await db.inventory(u.telegram_id)
            await show(cq, texts.profile(u, inv), profile_kb(inv, u.telegram_id))
    await cq.answer()


async def show(cq: CallbackQuery, text: str, kb: Kb) -> None:
    """Xabarni joyida almashtiradi; tahrirlab bo'lmasa (eski yoki media xabar) - yangisini yuboradi."""
    try:
        await cq.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await cq.message.answer(text, reply_markup=kb)


# ---------- hamyon: Xarid, Olmos (Stars), yuborish ----------
ASK: dict[int, str] = {}  # uid -> keyingi xabarda kutilgan javob: "to" (sovg'a kimga) | "dollars" / "diamonds" (kimga, qancha)


def prof_back() -> Btn:
    return Btn(text=texts.BACK_BTN, callback_data="m:profile")


def stars_kb(target: int = 0) -> Kb:
    """target: 0 - o'zim uchun, aks holda sovg'a oluvchi."""
    btns = [Btn(text=f"💎 {n} = ⭐ {s}", callback_data=f"gs:{n}:{target}") for n, s in config.DIAMOND_STARS.items()]
    return Kb(inline_keyboard=grid(btns, 2) + [[Btn(text=texts.BACK_BTN, callback_data="m:gem")]])


@router.callback_query(F.data.startswith(("xd:", "gm:", "gs:")))
async def cb_wallet(cq: CallbackQuery):
    """xd:<olmos> - dollar paketi; gm:me / gm:to - kim uchun olmos; gs:<olmos>:<target> - Stars hisob-fakturasi."""
    if not await _user(cq):
        return await cq.answer(texts.BANNED, show_alert=True)
    if config.DIAMONDS_OFF:
        return await cq.answer(texts.DIAMONDS_OFF, show_alert=True)
    uid = cq.from_user.id
    kind, _, rest = cq.data.partition(":")
    if kind == "xd":
        n = int(rest) if rest.isdigit() else 0
        if not await db.buy_dollars(uid, n):
            return await cq.answer(texts.NO_DIAMONDS, show_alert=True)
        return await cq.answer(texts.dollars_bought(n, config.DOLLAR_PACKS[n]), show_alert=True)
    if kind == "gm":
        if rest == "to":
            ASK[uid] = "to"
            await show(cq, texts.ASK_TO, Kb(inline_keyboard=[[Btn(text=texts.BACK_BTN, callback_data="m:gem")]]))
        else:
            await show(cq, texts.stars_menu(), stars_kb())
        return await cq.answer()
    n, _, target = rest.partition(":")
    if not (n.isdigit() and int(n) in config.DIAMOND_STARS and target.isdigit()):
        return await cq.answer()
    n, target = int(n), int(target)
    if target and not await db.get_user(target):
        return await cq.answer(texts.WALLET_NO_USER, show_alert=True)
    await _call(cq.bot.send_invoice, chat_id=uid, title=f"{n} olmos" + (" (sovg'a)" if target else ""),
                description=f"Admiral Mafia: {n} 💎 olmos" + (" do'stingizga sovg'a." if target else " hisobingizga."),
                payload=f"dm:{n}:{target}", currency="XTR",
                prices=[LabeledPrice(label=f"{n} olmos", amount=config.DIAMOND_STARS[n])])
    await cq.answer()


async def _find_user(s: str) -> db.User | None:
    return await db.get_user(int(s)) if s.isdigit() else await db.user_by_username(s)


async def _answer_ask(msg: Message, ask: str) -> None:
    uid, parts = msg.from_user.id, msg.text.split()
    if ask == "to":
        t = await _find_user(parts[0]) if len(parts) == 1 else None
        if not t:
            return await msg.answer(texts.WALLET_NO_USER)
        target = 0 if t.telegram_id == uid else t.telegram_id
        return await msg.answer(texts.stars_menu(texts.mention(t.telegram_id, t.full_name) if target else None),
                                reply_markup=stars_kb(target))
    if len(parts) != 2 or not parts[1].isdigit() or not 0 < int(parts[1]) <= MAX_AMOUNT:
        return await msg.answer(texts.WALLET_FORMAT)
    if not (t := await _find_user(parts[0])):
        return await msg.answer(texts.WALLET_NO_USER)
    if t.telegram_id == uid:
        return await msg.answer(texts.WALLET_SELF)
    if not (me := await _user(msg)):
        return await msg.answer(texts.BANNED)
    if me.games < config.SEND_GAMES:
        return await msg.answer(texts.send_locked(me.games))
    n = int(parts[1])
    if not await db.transfer(uid, t.telegram_id, n, ask):
        return await msg.answer(texts.NO_MONEY if ask == "dollars" else texts.NO_DIAMONDS)
    await msg.answer(texts.sent_ok(texts.mention(t.telegram_id, t.full_name), n, ask))
    await send(msg.bot, t.telegram_id, texts.got_money(texts.mention(uid, me.full_name), n, ask))


def shop_kb(uid: int | None = None) -> Kb:
    price = (lambda p: pro.price(uid, p)) if uid is not None else (lambda p: p)  # PRO: -25%
    rows = [[Btn(text=f"{texts.ITEMS[i]} ({price(p)}💵)", callback_data=f"b:{i}", style="success")]
            for i, p in config.SHOP.items() if i not in config.SHOP_OFF]
    rows += [[Btn(text=f"{texts.ITEMS[i]} ({p}💎)", callback_data=f"b:{i}", style="primary")]
             for i, p in config.SHOP_GEMS.items()]
    rows.append([Btn(text=texts.ROLE_SHOP_BTN, callback_data="shoproles", style="primary")])
    return Kb(inline_keyboard=rows + [[back_btn()]])


def roles_shop_kb() -> Kb:
    rows = [[Btn(text=f"{texts.ITEMS['r_' + c]} ({p}💎)", callback_data=f"b:r_{c}", style="primary")]
            for c, p in config.ROLE_PICKS.items()]
    return Kb(inline_keyboard=rows + [[Btn(text=texts.BACK_BTN, callback_data="shop")]])


def pro_kb() -> Kb:
    """Har paket: olmos va Stars tugmasi yonma-yon."""
    rows = [[Btn(text=f"{d} kun — {dm} 💎", callback_data=f"pro:d:{d}"),
             Btn(text=f"{d} kun — {st} ⭐", callback_data=f"pro:s:{d}", style="primary")]
            for d, (dm, st) in pro.PACKS.items()]
    return Kb(inline_keyboard=rows + [[back_btn()]])


@router.message(Command("pro"), PRIVATE)
async def cmd_pro(msg: Message):
    if not await _user(msg):
        return await msg.answer(texts.BANNED)
    await msg.answer(texts.pro_info(msg.from_user.id), reply_markup=pro_kb())


@router.callback_query(F.data.startswith("pro:"))
async def cb_pro(cq: CallbackQuery):
    """pro:d:<kun> - olmos bilan; pro:s:<kun> - Telegram Stars hisob-fakturasi."""
    _, how, days = cq.data.split(":")
    days = int(days) if days.isdigit() else 0
    if days not in pro.PACKS or not await _user(cq):
        return await cq.answer()
    if how == "d" and config.DIAMONDS_OFF:
        return await cq.answer(texts.DIAMONDS_OFF, show_alert=True)
    if how == "d":
        end = await db.buy_pro_diamonds(cq.from_user.id, days)
        if not end:
            return await cq.answer(texts.PRO_NO_DIAMONDS, show_alert=True)
        await show(cq, texts.pro_info(cq.from_user.id), pro_kb())
        return await cq.answer(f"🎉 PRO faollashdi! {days} kun qo'shildi.", show_alert=True)
    stars = pro.PACKS[days][1]
    await _call(cq.bot.send_invoice, chat_id=cq.from_user.id, title=f"PRO · {days} kun",
                description=f"Admiral Mafia PRO akkaunt: belgi, nickname, x1.5 g'alaba puli, -25% do'kon — {days} kun.",
                payload=f"pro:{days}", currency="XTR",
                prices=[LabeledPrice(label=f"PRO {days} kun", amount=stars)])
    await cq.answer()


def _pro_payload(payload: str) -> int | None:
    days = payload[4:] if payload.startswith("pro:") else ""
    return int(days) if days.isdigit() and int(days) in pro.PACKS else None


def _dm_payload(payload: str) -> tuple[int, int] | None:
    """dm:<olmos>:<target> -> (olmos, target); target 0 - to'lovchining o'zi."""
    p = payload.split(":")
    if len(p) == 3 and p[0] == "dm" and p[1].isdigit() and p[2].isdigit() and int(p[1]) in config.DIAMOND_STARS:
        return int(p[1]), int(p[2])
    return None


@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    """Telegram to'lovdan oldin so'raydi: paket va narx mos bo'lsagina tasdiqlanadi."""
    days, dm = _pro_payload(q.invoice_payload), _dm_payload(q.invoice_payload)
    if dm and config.DIAMONDS_OFF:
        return await q.answer(ok=False, error_message=texts.DIAMONDS_OFF)
    if q.currency == "XTR" and (
            days and q.total_amount == pro.PACKS[days][1]
            or dm and q.total_amount == config.DIAMOND_STARS[dm[0]] and (not dm[1] or await db.get_user(dm[1]))):
        return await q.answer(ok=True)
    await q.answer(ok=False, error_message="To'lov ma'lumoti noto'g'ri. /pro orqali qaytadan urinib ko'ring.")


@router.message(F.successful_payment)
async def on_paid(msg: Message):
    pay = msg.successful_payment
    days, dm = _pro_payload(pay.invoice_payload), _dm_payload(pay.invoice_payload)
    if not (days or dm):
        return
    uid, charge = msg.from_user.id, pay.telegram_payment_charge_id
    try:
        await db.upsert_user(uid, msg.from_user.full_name, msg.from_user.username)
        if days:
            end = await db.add_pro(uid, days, "stars", pay.total_amount, charge)
        else:
            end = await db.add_paid_diamonds(uid, dm[1] or uid, dm[0], pay.total_amount, charge)
    except Exception:  # pul yechilgan, xarid yozilmadi: Telegram qayta yubormaydi - Stars qaytariladi
        log.exception("Stars to'lovi yozilmadi: uid=%s charge=%s payload=%s amount=%s", uid, charge,
                      pay.invoice_payload, pay.total_amount)
        try:
            await msg.bot.refund_star_payment(user_id=uid, telegram_payment_charge_id=charge)
            await msg.answer(texts.PAY_REFUNDED)
        except Exception:
            log.exception("Stars qaytarilmadi: uid=%s charge=%s", uid, charge)
            await msg.answer(texts.PAY_FAILED)
        return
    if not end:  # shu to'lov avval hisoblangan (takror xabar)
        return
    if days:
        return await msg.answer(texts.pro_done(end))
    n, target = dm
    if target and target != uid:
        t = await db.get_user(target)
        await msg.answer(texts.diamonds_paid(n, texts.mention(target, t.full_name if t else "?")))
        await send(msg.bot, target, texts.got_money(texts.mention(uid, msg.from_user.full_name), n, "diamonds"))
    else:
        await msg.answer(texts.diamonds_paid(n))


@router.message(Command("paysupport"), PRIVATE)
async def cmd_paysupport(msg: Message):
    """Telegram Stars qoidasi: raqamli mahsulot sotadigan bot to'lov yordamini ko'rsatishi shart."""
    await msg.answer(texts.pay_support())


@router.message(Command("nickname"), PRIVATE)
async def cmd_nickname(msg: Message, command: CommandObject):
    uid = msg.from_user.id
    if not pro.is_pro(uid):
        return await msg.answer(texts.NICK_ONLY_PRO)
    nick = " ".join((command.args or "").split())  # ortiqcha bo'shliqlar
    if not nick:
        await db.set_nickname(uid, None)
        return await msg.answer(texts.NICK_CLEARED + "\n\n" + texts.NICK_HOW)
    if err := pro.check_nick(nick):
        return await msg.answer(err)
    await db.set_nickname(uid, nick)
    await msg.answer(texts.nick_set(nick))


async def pro_reminder(bot: Bot) -> None:
    """Soatiga bir marta: 24 soat ichida tugaydigan PRO'larga eslatma (har biriga bir marta)."""
    while True:
        try:
            for uid in await db.pro_expiring(24):
                await send(bot, uid, texts.PRO_EXPIRING)
        except Exception:
            log.exception("pro eslatma")
        await asyncio.sleep(3600)


@router.message(Command("profile"), PRIVATE)
async def cmd_profile(msg: Message):
    if not (u := await _user(msg)):
        return await msg.answer(texts.BANNED)
    inv = await db.inventory(u.telegram_id)
    await msg.answer(texts.profile(u, inv), reply_markup=profile_kb(inv, u.telegram_id))


@router.message(Command("role"), PRIVATE)
async def cmd_role(msg: Message):
    r = PLAYING.get(msg.from_user.id)
    if not r or not r.game:
        return await msg.answer(texts.NO_GAME)
    await msg.answer(texts.role_card(r.game, msg.from_user.id))


@router.message(Command("shop"), PRIVATE)
async def cmd_shop(msg: Message):
    if not (u := await _user(msg)):
        return await msg.answer(texts.BANNED)
    await msg.answer(texts.shop(u.dollars, u.telegram_id, u.diamonds), reply_markup=shop_kb(u.telegram_id))


@router.message(Command("top"), PRIVATE)
async def cmd_top(msg: Message):
    await msg.answer(texts.top(await db.top(), "Umumiy reyting"))


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(texts.start_pm())


@router.callback_query(F.data.startswith("t:"))
async def cb_profile(cq: CallbackQuery):
    await db.toggle_item(cq.from_user.id, cq.data[2:])
    u = await db.get_user(cq.from_user.id)
    inv = await db.inventory(u.telegram_id)
    await cq.message.edit_text(texts.profile(u, inv), reply_markup=profile_kb(inv, u.telegram_id))
    await cq.answer()


@router.callback_query(F.data.startswith("b:") | F.data.in_({"shop", "shoproles"}))
async def cb_shop(cq: CallbackQuery):
    if not await _user(cq):
        return await cq.answer(texts.BANNED, show_alert=True)
    item = cq.data[2:] if cq.data.startswith("b:") else None
    gems = db.gem_price(item) if item else None
    if config.DIAMONDS_OFF and gems:  # bo'limlar ochiladi, olmosga sotib olish yopiq
        return await cq.answer(texts.DIAMONDS_OFF, show_alert=True)
    if item:
        if not gems and (item not in config.SHOP or item in config.SHOP_OFF):
            return await cq.answer()
        ok = await db.buy(cq.from_user.id, item)
        await cq.answer(texts.BOUGHT if ok else texts.NO_DIAMONDS if gems else texts.NO_MONEY, show_alert=not ok)
    u = await db.get_user(cq.from_user.id)
    if cq.data == "shoproles" or (item or "").startswith("r_"):
        await show(cq, texts.roles_shop(u.diamonds), roles_shop_kb())
    else:
        await show(cq, texts.shop(u.dollars, u.telegram_id, u.diamonds), shop_kb(u.telegram_id))


@router.callback_query(F.data.startswith("r:"))
async def cb_role(cq: CallbackQuery):
    """Guruhdagi "🎭 Sizning rolingiz": rol shaxsiy oynada ko'rinadi, faqat bosgan odamga."""
    r = PLAYING.get(cq.from_user.id)
    if not r or not r.game or str(r.game_id) != cq.data[2:] or not r.game.get(cq.from_user.id):
        return await cq.answer(texts.NOT_IN_GAME, show_alert=True)
    await cq.answer(texts.role_alert(r.game, cq.from_user.id), show_alert=True)


# ---------- tungi harakatlar ----------
@router.callback_query(F.data.startswith("k:"))
async def cb_kind(cq: CallbackQuery):
    _, gid, day, kind = cq.data.split(":")
    r = PLAYING.get(cq.from_user.id)
    if not r or r.game_id != int(gid) or not r.game or r.game.day != int(day):
        return await cq.answer("⌛️ Kech qoldingiz")
    kb = r.night_kb(cq.from_user.id, kind)
    if kb:
        await cq.message.edit_reply_markup(reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("a:"))
async def cb_action(cq: CallbackQuery):
    _, gid, day, kind, target = cq.data.split(":")
    r = PLAYING.get(cq.from_user.id)
    if not r or r.game_id != int(gid):
        return await cq.answer("⌛️ Kech qoldingiz")
    if not await r.on_action(cq.from_user.id, int(day), kind, int(target)):
        return await cq.answer("❌ Bu harakat mumkin emas yoki vaqt tugadi")
    t = r.game.get(int(target)) if int(target) else None
    await cq.message.edit_text(texts.SKIPPED_NIGHT if kind == "skip" else texts.chosen(texts.dn(t) if t else None))
    await cq.answer()


# ---------- bot egasi ----------
OWNER = F.from_user.id.in_(config.ADMIN_IDS)


@router.message(Command("panel"), PRIVATE)
async def send_panel_link(msg: Message):
    """Web admin panelga bir martalik kirish havolasi (faqat adminlarga)."""
    from . import panel
    if not await db.panel_role(msg.from_user.id):
        return await msg.answer("⛔ Sizda admin panelga kirish huquqi yo'q.")
    if not config.PANEL_URL:
        return await msg.answer("⚙️ Panel manzili sozlanmagan: Railway'da servis → Settings → Networking → "
                                "<b>Generate Domain</b> bosing (yoki PANEL_URL o'zgaruvchisini qo'ying).")
    link = panel.login_link(msg.from_user.id)
    note = ("🔐 <b>Admin panelga kirish</b>\n\nHavola <b>5 daqiqa</b> amal qiladi va faqat <b>bir marta</b> ishlaydi. "
            "Uni hech kimga bermang.")
    if link.startswith("https://"):
        await msg.answer(note, reply_markup=Kb(inline_keyboard=[[Btn(text="🔐 Panelga kirish", url=link,
                                                                      style="success")]]))
    else:  # lokal sinov (http): Telegram tugmaga faqat https qabul qiladi
        await msg.answer(f"{note}\n\n<code>{link}</code>")


@router.message(Command("stats"), PRIVATE, OWNER)
async def cmd_stats(msg: Message):
    s = await db.stats()
    await msg.answer(f"📊 Foydalanuvchilar: {s['users']}\n👥 Guruhlar: {s['groups']}\n"
                     f"🎮 O'yinlar: {s['games']}\n▶️ Hozir ketayotgan: {s['running']}\n"
                     f"⏳ Lobbi/o'yin (xotirada): {len(RUNNERS)}")


@router.message(Command("broadcast"), PRIVATE, OWNER)
async def cmd_broadcast(msg: Message, bot: Bot, command: CommandObject):
    src = msg.reply_to_message
    if not src and not command.args:
        return await msg.answer("Xabarga reply qilib /broadcast yozing yoki: /broadcast matn")
    ids = await db.all_user_ids()
    await msg.answer(f"📣 {len(ids)} ta foydalanuvchiga yuborilmoqda...")

    async def run():
        ok = 0
        for uid in ids:
            res = await (_call(bot.copy_message, uid, src.chat.id, src.message_id) if src
                         else send(bot, uid, command.args))
            ok += res is not None
        await send(bot, msg.chat.id, f"✅ Yuborildi: {ok}/{len(ids)}")

    spawn(run())


@router.message(Command("ban", "unban"), PRIVATE, OWNER)
async def cmd_ban(msg: Message, command: CommandObject):
    if not (command.args or "").strip().isdigit():
        return await msg.answer(f"/{command.command} <telegram_id>")
    ok = await db.set_banned(int(command.args), command.command == "ban")
    await msg.answer("✅" if ok else "Topilmadi")


@router.message(Command("give"), PRIVATE, OWNER)
async def cmd_give(msg: Message, command: CommandObject):
    try:
        uid, dollars, *rest = map(int, (command.args or "").split())
    except ValueError:
        return await msg.answer("/give <telegram_id> <dollar> [olmos]")
    await db.add_balance(uid, dollars, rest[0] if rest else 0)
    await msg.answer("✅")


@router.message(PRIVATE, F.text)
async def on_private_text(msg: Message):
    if (ask := ASK.pop(msg.from_user.id, None)) and not msg.text.startswith("/"):
        return await _answer_ask(msg, ask)
    r = PLAYING.get(msg.from_user.id)
    if r and not msg.text.startswith("/") and await r.on_private_text(msg.from_user.id, msg.text, msg.entities):
        return
    if not r:
        await msg.answer(texts.start_pm())


@router.my_chat_member()
async def on_bot_removed(upd: ChatMemberUpdated):
    """Bot guruhdan chiqarildi: o'yin to'xtaydi, o'yinchilar boshqa o'yinga kira oladi."""
    if upd.new_chat_member.status in ("left", "kicked") and (r := RUNNERS.get(upd.chat.id)):
        await r.abort()


@router.message(F.migrate_to_chat_id)
async def on_migrate(msg: Message):
    """Guruh supergroup'ga aylandi: o'yin yangi chat ID ga ko'chadi."""
    if r := RUNNERS.get(msg.chat.id):
        await r.move(msg.migrate_to_chat_id)


# ---------- umumiy guruh xabarlari (eng oxirida bo'lishi shart) ----------
@router.message(GROUPS, F.left_chat_member)
async def on_left(msg: Message):
    r = RUNNERS.get(msg.chat.id)
    uid = msg.left_chat_member.id
    if r and PLAYING.get(uid) is r:
        if _in_game(r, uid):  # guruhdan chiqib ketish ham chiqish: limitdan keyin so'ramasdan jarima
            fine = config.LEAVE_FINE if await db.leaves_today(uid) >= pro.leave_free(uid) else 0
            await db.count_leave(uid, fine)
            if fine:
                await send(msg.bot, msg.chat.id, texts.left_fined(uid, msg.left_chat_member.full_name))
        await r.leave(uid)


NUMBER = re.compile(r"\s*\d+\s*")
TALK_PHASES = {DAY, VOTING, CONFIRM}
_admins: dict[int, tuple[float, set[int]]] = {}  # chat_id -> (vaqt, admin id'lari), 5 daqiqa kesh


async def group_admins(bot: Bot, chat_id: int) -> set[int]:
    t, ids = _admins.get(chat_id, (0.0, set()))
    if time.monotonic() - t > 300:
        try:
            ids = {m.user.id for m in await bot.get_chat_administrators(chat_id)}
        except Exception:
            pass  # olinmasa eski ro'yxat qoladi
        _admins[chat_id] = (time.monotonic(), ids)
    return ids


def may_write(game, uid: int | None, text: str, admin: bool) -> bool:
    """O'yin vaqtida: raqam - hammaga; '!...' - adminga; kunduzi - tirik o'yinchiga."""
    if text and NUMBER.fullmatch(text):
        return True
    if admin and text.startswith("!"):
        return True
    p = game.get(uid) if uid else None
    if p is None and uid is not None and pro.is_pro(uid):  # PRO tomoshabin: faqat kunduzi
        return game.phase in TALK_PHASES
    return bool(p and p.alive and game.phase in TALK_PHASES)


@router.message(GROUPS)  # tahrirlar ataylab tekshirilmaydi: raqam -> matn fishkasi
async def on_group_message(msg: Message, bot: Bot):
    r = RUNNERS.get(msg.chat.id)
    if not r or not r.game or r.game.phase == FINISHED:
        return  # lobbi va o'yindan tashqari - erkin
    uid = msg.from_user.id if msg.from_user else None
    anon_admin = bool(msg.sender_chat and msg.sender_chat.id == msg.chat.id)  # yashirin admin
    admin = anon_admin or (uid is not None and (uid in config.ADMIN_IDS or uid in await group_admins(bot, msg.chat.id)))
    if anon_admin:
        uid = None  # o'yinchi sifatida tanilmaydi
    if not may_write(r.game, uid, msg.text or msg.caption or "", admin):
        await _call(msg.delete)


# ---------- umumiy xato ushlagich: foydalanuvchi xato ko'rmaydi, log yoziladi ----------
@router.errors()
async def on_error(event: ErrorEvent):
    log.error("handler xatosi: %r", event.exception, exc_info=event.exception)
    if cq := event.update.callback_query:
        try:
            await cq.answer()
        except Exception:
            pass
    return True
