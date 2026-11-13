"""🛡 Moderatsiya: so'kinish/reklama aniqlagichlari, vaqt, buyruqlar, avtomatik tozalash, warn -> ban, report, info."""
from types import SimpleNamespace as NS

import pytest

from mafia_zone import moderation as mod


@pytest.mark.parametrize("text", [
    "jalab", "Jalablar", "JALAAAAB", "j a l a b", "j.a.l.a.b", "ж а л а б", "жалаб", "qanjiq", "қанжиқ", "kanjik",
    "siktir", "s1ktir", "onangni sikay", "onangnisikay", "qo'toq", "qotoq", "dalbayob", "долбоёб", "suka", "сука",
    "блять", "blyat", "p1zdec", "ебало", "pizdec", "пиздец", "nahuy", "на хуй", "хуй", "pidaras", "пидор", "mudak", "гандон",
    "fohisha", "haromzoda", "suka!", "blya100", "j4lab", "salom jalab nima gap",
])
def test_swear_found(text):
    assert mod.is_swear(text), text


@pytest.mark.parametrize("text", [
    "salom hammaga", "I am here", "ahmoq emasman", "musiqa yoqadi", "sikl bo'yicha", "jalb qilish kerak",
    "Sukhrob keldi", "Amin aka", "Aminga ayt", "skay", "kun tun ovoz", "Don va Komissar", "mafiya yutdi",
    "Комиссар проверил", "спасибо большое", "сутки прошли", "kapiz da", "harom narsa", "it mushuk", "1 2 3 4 5",
    "Jaloliddin", "Sukayna", "eballi", "debil emas", "qo'shiq aytdi", "pizza yeymiz", "subutoy",
])
def test_swear_not_found(text):
    assert not mod.is_swear(text), text


def test_swear_extra_words_from_panel():
    assert not mod.is_swear("zormaxsus gap") and mod.is_swear("ZORMAXSUSlar", ["zormaxsus"])


def E(type, offset=0, length=0, url=None):
    return NS(type=type, offset=offset, length=length, url=url)


def test_ads():
    own = {"mygroup", "admiralmafiabot", "abc123"}
    assert mod.ad_reason("kiring t.me/boshqa_kanal", [], own) == "link"
    assert mod.ad_reason("https://t.me/+XyZ", [], own) == "link"
    assert mod.ad_reason("bizning guruh t.me/MyGroup", [], own) is None  # o'z guruhi
    assert mod.ad_reason("t.me/+abc123", [], own) is None  # o'z taklif havolasi
    assert mod.ad_reason("bot: https://t.me/AdmiralMafiabot?start=ref1", [], own) is None
    assert mod.ad_reason("sayt: example.com/aksiya", [], own) == "link"
    assert mod.ad_reason("bosing", [E("text_link", url="https://spam.uz")], own) == "link"
    assert mod.ad_reason("kanal @kino_uz", [], own, channel_mentions={"kino_uz"}) == "mention"
    assert mod.ad_reason("@ali salom", [], own) is None  # oddiy odam
    assert mod.ad_reason("", [], own, forwarded_channel=True) == "forward"
    assert mod.ad_reason("", [], own, has_buttons=True) == "buttons"
    assert mod.ad_reason("salom, ertaga 9.30 da o'yin", [], own) is None
    text = "salom 😎 @kino_uz"
    at = len(text[:text.index("@")].encode("utf-16-le")) // 2
    assert mod.mentions(text, [E("mention", at, 8)]) == ["kino_uz"]


def test_parse_duration():
    assert mod.parse_duration("30m") == 1800 and mod.parse_duration("2h") == 7200 and mod.parse_duration("1d") == 86400
    assert mod.parse_duration("45") == 2700 and mod.parse_duration("1soat") == 3600 and mod.parse_duration("2kun") == 172800
    assert mod.parse_duration("0m") == mod.MIN_MUTE and mod.parse_duration("999d") == mod.MAX_MUTE
    assert mod.parse_duration("spam") is None and mod.parse_duration("") is None
    assert mod.split_args("30m haqorat qildi") == (1800, "haqorat qildi")
    assert mod.split_args("reklama tashladi") == (None, "reklama tashladi") and mod.split_args(None) == (None, "")


# ===================================== Telegram qismi (soxta bot) =====================================
import asyncio  # noqa: E402

from aiogram.filters import CommandObject  # noqa: E402

from mafia_zone import config, db, handlers, texts  # noqa: E402

ADMIN, MEMBER, OTHER, OWNER_ID, BOTID = 8_100_001, 8_100_002, 8_100_003, 8_100_009, 8_100_000


class Bot:
    """Faqat moderatsiya ishlatadigan usullar. rights=False - botda huquq yo'q (Telegram rad etadi -> None)."""
    id = BOTID

    def __init__(self, admins=(ADMIN,), rights=True):
        self.admins, self.rights = set(admins), rights
        self.sent, self.eph, self.restricted, self.banned, self.unbanned, self.deleted, self.edited = ([] for _ in range(7))
        self.muted: dict[int, object] = {}
        self._id = 100

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self._id += 1
        if e := kw.get("ephemeral_message_parameters"):
            self.eph.append((chat_id, e.receiver_user_id, text))
            return NS(message_id=0, ephemeral_message_id=self._id)
        self.sent.append((chat_id, text, reply_markup, kw))
        return NS(message_id=self._id)

    async def get_chat_member(self, chat_id, uid):
        if uid == BOTID:
            return NS(status="administrator", can_delete_messages=self.rights, can_restrict_members=self.rights)
        if uid in self.admins:
            return NS(status="administrator", can_restrict_members=True)
        if uid in self.muted:
            return NS(status="restricted", can_send_messages=False, until_date=self.muted[uid])
        return NS(status="member")

    async def get_chat_administrators(self, chat_id):
        users = [NS(user=NS(id=u, is_bot=False, full_name=f"admin{u}"), is_anonymous=False) for u in sorted(self.admins)]
        return users + [NS(user=NS(id=BOTID, is_bot=True, full_name="bot"), is_anonymous=False)]

    async def restrict_chat_member(self, chat_id, uid, permissions, until_date=None):
        if not self.rights:
            return None
        self.restricted.append((chat_id, uid, permissions, until_date))
        if permissions.can_send_messages is False:
            self.muted[uid] = until_date
        else:
            self.muted.pop(uid, None)
        return True

    async def ban_chat_member(self, chat_id, uid, **kw):
        if not self.rights:
            return None
        self.banned.append((chat_id, uid))
        return True

    async def unban_chat_member(self, chat_id, uid, only_if_banned=False):
        self.unbanned.append((chat_id, uid))
        return True

    async def get_chat(self, chat_id):
        if isinstance(chat_id, str):  # @username
            return NS(type="channel") if chat_id == "@kino_uz" else None
        return NS(permissions=None)

    async def delete_message(self, chat_id, msg_id):
        self.deleted.append((chat_id, msg_id))
        return True

    async def edit_message_text(self, text, chat_id, message_id, **kw):
        self.edited.append((chat_id, message_id, text))
        return True


def user(uid):
    return NS(id=uid, full_name=f"u{uid}", username=f"user{uid}", is_bot=False)


def gmsg(bot, chat, uid, text="", reply=None, **kw):
    m = NS(chat=NS(id=chat, type="supergroup", username=None, title="Guruh"), from_user=user(uid) if uid else None,
           sender_chat=None, reply_to_message=reply, text=text, entities=kw.pop("entities", None), caption=None,
           caption_entities=None, is_automatic_forward=None, new_chat_members=None, left_chat_member=None,
           forward_origin=kw.pop("forward_origin", None), reply_markup=None, bot=bot, message_id=kw.pop("mid", 50))
    deleted = []

    async def delete():
        deleted.append(True)
        return True

    async def answer(text, **kw):
        return await bot.send_message(chat, text, **kw)
    m.delete, m.answer, m.deleted = delete, answer, deleted
    return m


def reply_to(uid, text="yomon gap", mid=40):
    return NS(from_user=user(uid), sender_chat=None, is_automatic_forward=None, message_id=mid, text=text, caption=None)


def cmd(name, args=None):
    return CommandObject(prefix=".", command=name, args=args)


def run(coro):
    async def go():
        await db.init()
        await coro
    asyncio.run(go())


def test_mod_commands():
    async def t():
        chat, bot = -8101, Bot()
        mod.forget(chat)
        await db.clear_warns(chat, MEMBER)
        # oddiy a'zo buyruq bera olmaydi - javob faqat unga
        m = gmsg(bot, chat, OTHER, reply=reply_to(MEMBER))
        await mod.cmd_mod(m, bot, cmd("mute"))
        assert m.deleted and not bot.restricted and bot.eph[-1] == (chat, OTHER, texts.MOD_ONLY_ADMIN)
        # reply yo'q - qanday ishlatish
        await mod.cmd_mod(gmsg(bot, chat, ADMIN), bot, cmd("ban"))
        assert bot.eph[-1][2] == texts.MOD_HOW["ban"]
        # adminni jazolab bo'lmaydi
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(ADMIN)), bot, cmd("mute"))
        assert bot.eph[-1][2] == texts.MOD_NOT_STAFF and not bot.restricted
        # mute 30m sabab
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("mute", "30m haqorat"))
        c, uid, perms, until = bot.restricted[-1]
        assert uid == MEMBER and perms.can_send_messages is False
        assert 1790 <= (until - db.now()).total_seconds() <= 1810
        assert "30 daqiqa" in bot.sent[-1][1] and "haqorat" in bot.sent[-1][1] and "admin" in bot.sent[-1][1].lower()
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("mute"))  # muddatsiz - 1 soat
        assert 3590 <= (bot.restricted[-1][3] - db.now()).total_seconds() <= 3610
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("unmute"))
        assert bot.restricted[-1][2].can_send_messages is True and MEMBER not in bot.muted
        # warn: 3 ta -> ban, ogohlantirishlar nolga tushadi
        for i in (1, 2):
            await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("warn", f"spam{i}"))
            assert f"{i}/3" in bot.sent[-1][1]
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("warns"))
        assert "2/3" in bot.sent[-1][1] and "spam1" in bot.sent[-1][1] and "bugun" in bot.sent[-1][1]
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("unwarn"))
        assert "1/3" in bot.sent[-1][1]
        for _ in range(2):
            await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(MEMBER)), bot, cmd("warn"))
        assert bot.banned[-1] == (chat, MEMBER) and "ban qilindi" in bot.sent[-1][1]
        assert await db.warns(chat, MEMBER) == []
        # kick = ban + unban; unban
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(OTHER)), bot, cmd("kick", "flood"))
        assert bot.banned[-1] == (chat, OTHER) and bot.unbanned[-1] == (chat, OTHER) and "flood" in bot.sent[-1][1]
        # botda huquq yo'q - adminga aytiladi
        bot.rights = False
        await mod.cmd_mod(gmsg(bot, chat, ADMIN, reply=reply_to(OTHER)), bot, cmd("ban"))
        assert bot.eph[-1][2] == texts.MOD_NO_RIGHTS
        # bot egasi istalgan guruhda
        old = set(config.ADMIN_IDS)
        config.ADMIN_IDS.add(OWNER_ID)
        try:
            bot.rights = True
            await mod.cmd_mod(gmsg(bot, chat, OWNER_ID, reply=reply_to(OTHER)), bot, cmd("ban"))
            assert bot.banned[-1] == (chat, OTHER)
        finally:
            config.ADMIN_IDS.clear()
            config.ADMIN_IDS.update(old)
    run(t())


def test_auto_swear_and_ads():
    async def t():
        chat, bot = -8102, Bot()
        await db.group_settings(chat, "G")
        await db.clear_warns(chat, MEMBER)
        s = await db.group_settings(chat)
        mod.forget(chat)
        m = gmsg(bot, chat, MEMBER, "jalab")
        assert not await mod.auto(m, bot) and not m.deleted  # standart o'chiq
        await db.save_group_settings(chat, {**s, "mod_swear": True, "mod_ads": True})
        mod.forget(chat)
        m = gmsg(bot, chat, MEMBER, "salom j.a.l.a.b")
        assert await mod.auto(m, bot) and m.deleted
        assert MEMBER in bot.muted and "30 daqiqa" in bot.sent[-1][1] and "so'kingani" in bot.sent[-1][1]
        m = gmsg(bot, chat, ADMIN, "jalab")
        assert not await mod.auto(m, bot) and not m.deleted  # admin jazolanmaydi
        m = gmsg(bot, chat, MEMBER, "salom hammaga, kecha zo'r o'yin bo'ldi")
        assert not await mod.auto(m, bot) and not m.deleted
        # reklama: o'chiriladi + ogohlantirish; 3-sida ban
        for i in (1, 2):
            m = gmsg(bot, chat, MEMBER, f"kiringlar t.me/spamkanal{i}")
            assert await mod.auto(m, bot) and m.deleted and f"{i}/3" in bot.sent[-1][1]
        m = gmsg(bot, chat, MEMBER, "@kino_uz ga obuna bo'ling", entities=[NS(type="mention", offset=0, length=8, url=None)])
        assert await mod.auto(m, bot) and bot.banned[-1] == (chat, MEMBER) and "<b>3</b> ta ogohlantirish oldi" in bot.sent[-1][1]
        m = gmsg(bot, chat, OTHER, "@user123 salom", entities=[NS(type="mention", offset=0, length=8, url=None)])
        assert not await mod.auto(m, bot)  # oddiy odamning @username'i
        m = gmsg(bot, chat, OTHER, "", forward_origin=NS(type="channel"))
        assert await mod.auto(m, bot) and m.deleted
        bot.rights = False  # o'chirib bo'lmasa - jazo ham yo'q
        m = gmsg(bot, chat, OTHER, "jalab")
        m.delete = lambda: asyncio.sleep(0)  # None qaytaradi
        n = len(bot.restricted)
        assert not await mod.auto(m, bot) and len(bot.restricted) == n
    run(t())


def test_report_and_admins():
    async def t():
        chat, bot = -8103, Bot(admins=(ADMIN, OTHER))
        mod.forget(chat)
        mod._calls.clear()
        await mod.cmd_report(gmsg(bot, chat, MEMBER), bot, cmd("report"))
        assert bot.eph[-1][2] == texts.REPORT_HOW
        await mod.cmd_report(gmsg(bot, chat, MEMBER, reply=reply_to(OWNER_ID, "reklama!!", 77)), bot, cmd("report", "spam"))
        pms = [x for x in bot.sent if x[0] in (ADMIN, OTHER)]
        assert {x[0] for x in pms} == {ADMIN, OTHER} and bot.eph[-1][2] == texts.REPORT_SENT
        assert "reklama!!" in pms[0][1] and "spam" in pms[0][1]
        cbs = [b.callback_data for row in pms[0][2].inline_keyboard for b in row if b.callback_data]
        assert cbs == [f"rp:{chat}:{OWNER_ID}:77:{a}" for a in ("m", "b", "d", "ok")]
        await mod.cmd_report(gmsg(bot, chat, MEMBER, reply=reply_to(OWNER_ID)), bot, cmd("report"))
        assert bot.eph[-1][2] == texts.REPORT_WAIT  # 5 daqiqada 1 marta
        answers = []

        def cq(uid, data):
            return NS(from_user=user(uid), data=data, message=NS(message_id=9, html_text="x"),
                      answer=lambda t=None, **kw: asyncio.sleep(0, answers.append(t)))
        await mod.cb_report(cq(MEMBER, f"rp:{chat}:{OWNER_ID}:77:m"), bot)
        assert answers[-1] == texts.MOD_ONLY_ADMIN and not bot.restricted
        await mod.cb_report(cq(ADMIN, f"rp:{chat}:{OWNER_ID}:77:m"), bot)
        assert bot.muted.get(OWNER_ID) and (chat, 77) in bot.deleted
        assert {c for c, _, _ in bot.edited} == {ADMIN, OTHER}  # ikkala adminning nusxasi yangilandi
        assert all("Ko'rib chiqildi" in t for *_, t in bot.edited)
        await mod.cb_report(cq(OTHER, f"rp:{chat}:{OWNER_ID}:77:b"), bot)
        assert answers[-1] == texts.REPORT_ALREADY and not bot.banned
        # .admins: guruhga bitta xabar (metka), har adminga shaxsiy; 5 daqiqada 1 marta
        n = len(bot.sent)
        await mod.cmd_admins(gmsg(bot, chat, MEMBER, reply=reply_to(OTHER, mid=88)), bot)
        group = [x for x in bot.sent[n:] if x[0] == chat]
        assert len(group) == 1 and f"tg://user?id={ADMIN}" in group[0][1] and f"tg://user?id={OTHER}" in group[0][1]
        assert f"tg://user?id={BOTID}" not in group[0][1] and group[0][3]["reply_parameters"].message_id == 88
        assert {x[0] for x in bot.sent[n:] if x[0] > 0} == {ADMIN, OTHER}
        await mod.cmd_admins(gmsg(bot, chat, MEMBER), bot)
        assert bot.eph[-1][2] == texts.ADMINS_WAIT
    run(t())


def test_info():
    async def t():
        chat, bot = -8104, Bot()
        mod.forget(chat)
        await db.clear_warns(chat, MEMBER)
        await db.member_joined(chat, MEMBER)
        await db.add_warn(chat, MEMBER, "reklama", None)
        bot.muted[MEMBER] = db.now()
        await mod.cmd_info(gmsg(bot, chat, OTHER, reply=reply_to(MEMBER)), bot)
        text = bot.sent[-1][1]
        assert f"<code>{MEMBER}</code>" in text and "@user" in text and "1/3" in text and "reklama" in text
        assert "Guruhga qo'shilgan: " + db.now().astimezone(mod.TZ).strftime("%Y-%m-%d") in text and "🔇 mute" in text
        await mod.cmd_info(gmsg(bot, chat, OTHER), bot)  # reply'siz - o'zi haqida
        assert f"<code>{OTHER}</code>" in bot.sent[-1][1] and "ma'lum emas" in bot.sent[-1][1]
    run(t())


def test_settings_mod_menu():
    async def t():
        chat, uid, bot = -8105, OWNER_ID, Bot()
        await db.group_settings(chat, "G")
        old = set(config.ADMIN_IDS)
        config.ADMIN_IDS.add(uid)
        edits, answers = [], []

        async def edit_text(text, reply_markup=None, **kw):
            edits.append((text, reply_markup))

        def cq(data):
            return NS(from_user=user(uid), data=data, bot=bot,
                      message=NS(chat=NS(id=chat), message_id=5, edit_text=edit_text),
                      answer=lambda t=None, **kw: asyncio.sleep(0, answers.append(t)))
        try:
            assert "s:mod" in [b.callback_data for row in handlers.settings_kb(await db.group_settings(chat)).inline_keyboard
                               for b in row]
            await handlers.cb_settings(cq("s:mod"), bot)
            assert "🛡" in edits[-1][0] and "Botda kerakli huquqlar bor" in edits[-1][0]
            await handlers.cb_settings(cq("s:mod_swear"), bot)
            await handlers.cb_settings(cq("s:mod_swear_min:+"), bot)
            await handlers.cb_settings(cq("s:mod_warn_max:-"), bot)
            s = await db.group_settings(chat)
            assert s["mod_swear"] and s["mod_swear_min"] == 60 and s["mod_warn_max"] == 2 and not s["mod_ads"]
            assert (await mod.settings(chat))[0]["mod_swear"]  # kesh darhol yangilandi
        finally:
            config.ADMIN_IDS.clear()
            config.ADMIN_IDS.update(old)
    run(t())
