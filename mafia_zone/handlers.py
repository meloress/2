import asyncio
import logging
import re
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ErrorEvent, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Message

from . import config, db, texts
from .engine.game import CONFIRM, DAY, FINISHED, NIGHT, VOTING
from .engine.roles import ROLES
from .engine.setup import CORE
from .runner import NEXT, PLAYING, RUNNERS, Runner, _call, bot_link, edit, profile_kb, send

log = logging.getLogger(__name__)
router = Router()
GROUPS = F.chat.type.in_({"group", "supergroup"})
PRIVATE = F.chat.type == "private"


async def is_admin(bot: Bot, chat_id: int, uid: int) -> bool:
    if uid in config.ADMIN_IDS:
        return True
    m = await bot.get_chat_member(chat_id, uid)
    return m.status in ("administrator", "creator")


# ============ GURUH ============
@router.message(Command("game"), GROUPS)
async def cmd_game(msg: Message, bot: Bot):
    if msg.chat.id in RUNNERS:
        return await msg.answer(texts.GAME_EXISTS)
    me = await bot.get_chat_member(msg.chat.id, bot.id)
    if me.status != "administrator":
        await msg.answer(texts.NOT_ADMIN_WARN)
    settings = await db.group_settings(msg.chat.id, msg.chat.title or "")
    if msg.chat.id in RUNNERS:  # await paytida boshqasi ochgan bo'lishi mumkin
        return
    await Runner(bot, msg.chat.id, settings, msg.chat.title or "").open_lobby()


@router.message(Command("testgame"), GROUPS, F.from_user.id.in_(config.ADMIN_IDS))
async def cmd_testgame(msg: Message, bot: Bot, command: CommandObject):
    """Bot egasi uchun: siz + bot-o'yinchilar. /testgame 8"""
    if msg.chat.id in RUNNERS:
        return await msg.answer(texts.GAME_EXISTS)
    n = int(command.args) if (command.args or "").strip().isdigit() else 8
    n = max(4, min(30, n))
    settings = await db.group_settings(msg.chat.id, msg.chat.title or "")
    settings |= {"lobby": 60, "night": 20, "day": 15, "vote": 15}  # test uchun tez
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
async def cmd_extend(msg: Message):
    r = RUNNERS.get(msg.chat.id)
    if r and not r.game:
        r.extend()
        await msg.answer("⏳ Ro'yxatdan o'tish 30 soniyaga uzaytirildi.")


@router.message(Command("begin"), GROUPS)
async def cmd_begin(msg: Message, bot: Bot):
    r = RUNNERS.get(msg.chat.id)
    if r and not r.game:
        if not await is_admin(bot, msg.chat.id, msg.from_user.id):
            return await msg.answer(texts.ONLY_ADMIN)
        r.force_start()


@router.message(Command("stop"), GROUPS)
async def cmd_stop(msg: Message, bot: Bot):
    r = RUNNERS.get(msg.chat.id)
    if r:
        if not await is_admin(bot, msg.chat.id, msg.from_user.id):
            return await msg.answer(texts.ONLY_ADMIN)
        await r.abort()


@router.message(Command("leave"), GROUPS)
async def cmd_leave(msg: Message):
    r = RUNNERS.get(msg.chat.id)
    if r and PLAYING.get(msg.from_user.id) is r:
        await r.leave(msg.from_user.id)
        await msg.answer(f"🚪 {texts.mention(msg.from_user.id, msg.from_user.full_name)} o'yindan chiqdi.")


@router.message(Command("top"), GROUPS)
async def cmd_top_group(msg: Message):
    await msg.answer(texts.top(await db.top(msg.chat.id), "Guruh reytingi"))


@router.message(Command("rules"))
async def cmd_rules(msg: Message):
    await msg.answer(texts.rules())


# ---------- sozlamalar ----------
TIMERS = {"lobby": ("👥 Ro'yxat", [60, 90, 120, 180, 300]), "night": ("🌙 Tun", [30, 45, 60, 90, 120]),
          "day": ("🌆 Kun", [30, 60, 90, 120, 180]), "vote": ("🗳 Ovoz", [30, 45, 60, 90])}


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
    if not await is_admin(bot, msg.chat.id, msg.from_user.id):
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
    elif key in ("items", "afk", "confirm"):
        s[key] = not s[key]
    elif key == "r":
        code = parts[2]
        dis = set(s["disabled"])
        dis.symmetric_difference_update({code})
        s["disabled"] = sorted(dis)
    if key in TIMERS or key in ("items", "afk", "confirm"):
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
    r = RUNNERS.get(cq.message.chat.id)
    if not r or r.game_id != int(gid):
        return await cq.answer("⌛️ Bu ovoz berish tugagan.")
    ok = await r.on_confirm(cq.from_user.id, int(day), yes == "1")
    await cq.answer(("👍 Osishga rozi bo'ldingiz" if yes == "1" else "👎 Rahm so'radingiz") if ok
                    else "❌ Siz ovoz bera olmaysiz")


# ---------- pul o'tkazish va tarqatish ----------
MAX_AMOUNT = 10 ** 9
_refresh: dict[int, asyncio.Task] = {}  # giveaway_id -> kechiktirilgan tahrir


@router.message(Command("send"), GROUPS)
async def cmd_send(msg: Message, bot: Bot, command: CommandObject):
    """/send 100 10 - 10 dan 10 kishiga; /send 100 - bitta kishiga hammasi; reply + /send 100 - o'tkazish.
    Xato bo'lsa jim o'chiriladi."""
    args = (command.args or "").split()
    nums = [int(a) for a in args] if args and all(a.isdigit() for a in args) else []
    ok = False
    if nums and len(nums) <= 2 and all(0 < x <= MAX_AMOUNT for x in nums) and await _user(msg):
        u, reply = msg.from_user, msg.reply_to_message
        target = reply.from_user if reply else None
        if len(nums) == 1 and target and not target.is_bot and target.id != u.id:
            await db.upsert_user(target.id, target.full_name, target.username)
            if await db.transfer(u.id, target.id, nums[0]):
                await send(bot, msg.chat.id, texts.transfer_done(u.full_name, u.id, target.full_name, target.id, nums[0]))
                ok = True
        elif len(nums) == 1 and not reply or len(nums) == 2 and nums[1] <= nums[0]:
            per = nums[-1]
            parts = nums[0] // per
            gid = await db.create_giveaway(msg.chat.id, u.id, per, parts)
            if gid:
                kb = Kb(inline_keyboard=[[Btn(text=texts.GIVEAWAY_BTN, callback_data=f"g:{gid}", style="success")]])
                await send(bot, msg.chat.id, texts.giveaway(u.full_name, u.id, per, parts), kb)
                ok = True
    if not ok:
        await _call(msg.delete)


@router.callback_query(F.data.startswith("g:"))
async def cb_giveaway(cq: CallbackQuery, bot: Bot):
    gid = int(cq.data[2:])
    g = await db.claim(gid, cq.from_user.id) if await _user(cq) else None
    if not g:
        return await cq.answer(texts.GIVEAWAY_NO)
    await cq.answer(texts.GIVEAWAY_GOT.format(g.per), show_alert=True)
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
                                                        g.per, g.parts, await db.giveaway_takers(gid)), kb)
    finally:
        _refresh.pop(gid, None)


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
    await cq.message.edit_text(texts.vote_chosen(t.name if t else None))
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
        if await db.get_user(inviter):
            await db.add_balance(inviter, config.REF_BONUS)
            await send(bot, inviter, texts.ref_bonus(msg.from_user.full_name))
    if arg == "panel":
        return await send_panel_link(msg)
    if arg.startswith("join"):
        r = RUNNERS.get(int(arg[4:])) if arg[4:].lstrip("-").isdigit() else None
        return await msg.answer(r.join(msg.from_user.id, msg.from_user.full_name) if r else texts.NO_LOBBY)
    await msg.answer(texts.welcome(), reply_markup=start_kb())


def start_kb() -> Kb:
    # admin=...: guruhga qo'shishda kerakli huquqlar so'raladi (xabar o'chirish, cheklash, pin)
    add = bot_link() + "?startgroup=true&admin=delete_messages+restrict_members+pin_messages"
    rows = [[Btn(text="🎮 O'yinni guruhingizga qo'shing", url=add)],
            [Btn(text="🏆 Reyting", callback_data="m:top", style="danger")]]
    if config.NEWS_URL:
        rows.append([Btn(text="📰 Yangiliklar", url=config.NEWS_URL)])
    rows += [[Btn(text="🎭 Rollar", callback_data="m:rules"), Btn(text="🛒 Do'kon", callback_data="m:shop")],
             [Btn(text="👤 Mening profilim", callback_data="m:profile")]]
    return Kb(inline_keyboard=rows)


@router.callback_query(F.data.startswith("m:"))
async def cb_menu(cq: CallbackQuery):
    what = cq.data[2:]
    if what == "rules":
        await cq.message.answer(texts.rules())
    elif what == "top":
        await cq.message.answer(texts.top(await db.top(), "Umumiy reyting"))
    elif what in ("profile", "shop"):
        if not (u := await _user(cq)):
            return await cq.answer(texts.BANNED, show_alert=True)
        if what == "shop":
            await cq.message.answer(texts.shop(u.dollars), reply_markup=shop_kb())
            return await cq.answer()
        inv = await db.inventory(u.telegram_id)
        await cq.message.answer(texts.profile(u, inv, bot_link(f"ref{u.telegram_id}")), reply_markup=profile_kb(inv))
    await cq.answer()


def shop_kb() -> Kb:
    return Kb(inline_keyboard=[[Btn(text=f"{texts.ITEMS[i]} — {p} 💵", callback_data=f"b:{i}", style="success")]
                               for i, p in config.SHOP.items() if i not in config.SHOP_OFF])


@router.message(Command("profile"), PRIVATE)
async def cmd_profile(msg: Message):
    if not (u := await _user(msg)):
        return await msg.answer(texts.BANNED)
    inv = await db.inventory(u.telegram_id)
    await msg.answer(texts.profile(u, inv, bot_link(f"ref{u.telegram_id}")), reply_markup=profile_kb(inv))


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
    await msg.answer(texts.shop(u.dollars), reply_markup=shop_kb())


@router.message(Command("bonus"), PRIVATE)
async def cmd_bonus(msg: Message):
    if not await _user(msg):
        return await msg.answer(texts.BANNED)
    ok = await db.claim_bonus(msg.from_user.id)
    await msg.answer(f"{texts.BONUS_OK} +{config.DAILY_BONUS} 💵" if ok else texts.BONUS_WAIT)


@router.message(Command("top"), PRIVATE)
async def cmd_top(msg: Message):
    await msg.answer(texts.top(await db.top(), "Umumiy reyting"))


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(texts.start_pm())


@router.callback_query(F.data.startswith("t:") | (F.data == "x"))
async def cb_profile(cq: CallbackQuery):
    if cq.data == "x":
        if not await db.exchange_diamond(cq.from_user.id):
            return await cq.answer("😔 Olmos yo'q", show_alert=True)
    else:
        await db.toggle_item(cq.from_user.id, cq.data[2:])
    u = await db.get_user(cq.from_user.id)
    inv = await db.inventory(u.telegram_id)
    await cq.message.edit_text(texts.profile(u, inv, bot_link(f"ref{u.telegram_id}")), reply_markup=profile_kb(inv))
    await cq.answer()


@router.callback_query(F.data.startswith("b:") | (F.data == "shop"))
async def cb_shop(cq: CallbackQuery):
    if not await _user(cq):
        return await cq.answer(texts.BANNED, show_alert=True)
    if cq.data != "shop":
        item = cq.data[2:]
        if item not in config.SHOP or item in config.SHOP_OFF:
            return await cq.answer()
        ok = await db.buy(cq.from_user.id, item)
        await cq.answer(texts.BOUGHT if ok else texts.NO_MONEY, show_alert=not ok)
    u = await db.get_user(cq.from_user.id)
    await cq.message.edit_text(texts.shop(u.dollars), reply_markup=shop_kb())


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
    await cq.message.edit_text(texts.chosen(t.name if t else None))
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

    asyncio.create_task(run())


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
    r = PLAYING.get(msg.from_user.id)
    if r and not msg.text.startswith("/") and await r.on_private_text(msg.from_user.id, msg.text):
        return
    if not r:
        await msg.answer(texts.start_pm())


# ---------- umumiy guruh xabarlari (eng oxirida bo'lishi shart) ----------
@router.message(GROUPS, F.left_chat_member)
async def on_left(msg: Message):
    r = RUNNERS.get(msg.chat.id)
    uid = msg.left_chat_member.id
    if r and PLAYING.get(uid) is r:
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
