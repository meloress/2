"""To'lov kartalari (panel) va olmos to'lovi kartasi (vidjet): panelda kiritish va tekshirish, vidjet hajmi,
kartaning holati chek/tasdiq/rad/bekor bilan yangilanishi, vidjet chiqmasa - matnli ekran."""
import asyncio
import json
import zlib
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from mafia_zone import config, db, handlers, panel, texts, vidjet
from tests.test_money import BASE, mkuser
from tests.test_panel import OWNER, MOD, login, run as panel_run
from tests.test_wallet import cbs, cq

U = BASE + 7000
UZ = {"n": "5614684605535200", "o": "Ali Valiyev", "b": "Kapitalbank", "k": "Humo"}
XORIJ = {"n": "4916123412341234", "o": "Ali Valiyev", "t": "+998901234567", "b": "Uzum Bank", "k": "Visa"}


def run(coro):
    async def go():
        await db.init()
        return await coro
    return asyncio.run(go())


class WidgetBot:
    """aiogram Bot o'rnida: bot(method) - so'rovlar yoziladi, tarmoqqa chiqmaydi."""
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    async def __call__(self, method):
        self.calls.append(method)
        if not self.ok:
            raise RuntimeError("Bad Request: widget rejected")
        return SimpleNamespace(message_id=777) if isinstance(method, vidjet.SendWidget) else True

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        return SimpleNamespace(message_id=1)

    send_document = send_photo

    def sent(self):
        return [m for m in self.calls if isinstance(m, vidjet.SendWidget)]

    def states(self):
        return [json.loads(m.chat_data)["h"] for m in self.calls if isinstance(m, vidjet.EditMessageWidgetData)]


def test_widget_fits_telegram_limits_and_is_safe():
    assert len(zlib.compress(vidjet.HTML.encode(), 9)) <= 3900  # 4 KB (zlib) chegarasi, zaxira bilan
    css = vidjet.HTML.split("<script>")[0]
    assert "opacity" not in css and "filter" not in css and "background-clip" not in css
    assert "innerHTML=\"\"" in vidjet.HTML and vidjet.HTML.count("innerHTML") == 1  # faqat tozalash; matn - textContent
    assert "<svg" not in vidjet.HTML and "ADMIRAL MAFIA" in vidjet.HTML  # logo yo'q, faqat nom (egasining istagi)
    old = dict(config.CARDS)
    try:
        config.CARDS.clear()
        config.CARDS.update({"uz": {**UZ, "o": "X" * 40, "b": "B" * 30}, "xorij": {**XORIJ, "o": "Y" * 40, "b": "C" * 30}})
        o = SimpleNamespace(id=99999, diamonds=1000, amount=890000, status="new", created_at=db.now())
        d = vidjet.holat(o, "Z" * 25, texts.REJECT_TELL["s"])
        assert len(vidjet.dumps(d).encode()) <= 1024  # chat_data chegarasi
        assert d["u"]["nf"] == "5614 6846 0553 5200" and d["v"]["tf"] == "+998 90 123 45 67"
        assert d["v"]["b"] == "C" * 30 + " · VISA" and d["g"] == "Z" * 25 and d["h"] == "k"
    finally:
        config.CARDS.clear()
        config.CARDS.update(old)


def test_panel_cards_owner_only_validated_and_persist():
    async def s(c: TestClient):
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}
        old = dict(config.CARDS)
        r = await c.post("/api/cards", json={"uz": {**UZ, "n": "5614 6846-0553 5200", "o": "  Ali   Valiyev "},
                                             "xorij": {**XORIJ, "t": "+998 (90) 123-45-67"}}, headers=hdr)
        assert r.status == 200
        assert config.cards()["uz"] == UZ and config.cards()["xorij"] == XORIJ  # tozalab saqlandi
        for bad in [{"uz": {**UZ, "n": "1234"}}, {"uz": {**UZ, "o": ""}}, {"xorij": {**XORIJ, "t": "telefon"}},
                    {"uz": {**UZ, "k": "Bitcoin"}}, {"bomb": UZ}, {}, {"uz": "x"}]:
            assert (await c.post("/api/cards", json=bad, headers=hdr)).status == 400, bad
        assert config.cards()["uz"] == UZ  # xato so'rov hech narsani o'zgartirmadi
        log = [x for x in (await (await c.get("/api/log")).json())["items"] if x["action"] == "cards"]
        assert log and "···· 5200" in log[0]["details"] and UZ["n"] not in json.dumps(log)  # jurnalda faqat oxiri
        config.CARDS.clear()  # "qayta ishga tushish": bazadan yuklanadi
        await db.load_settings()
        assert config.cards()["xorij"] == XORIJ
        # bo'sh karta - o'chiriladi
        r = await c.post("/api/cards", json={"xorij": {"n": "", "o": "", "t": "", "b": "", "k": ""}}, headers=hdr)
        assert r.status == 200 and "xorij" not in config.CARDS and "uz" in config.CARDS
        # moderator kartalarni ko'ra ham, o'zgartira ham olmaydi
        mcsrf = await login(c, MOD)
        assert (await c.get("/api/cards")).status == 403
        assert (await c.post("/api/cards", json={"uz": UZ}, headers={"X-CSRF": mcsrf})).status == 403
        await db.save_settings({"cards": {k: v for k, v in old.items()}})
    panel_run(s)


def test_card_order_widget_states_and_fallback():
    """Kartalar paneldan: to'lov kartasi (vidjet) yangi xabar, menyu o'chadi; chek -> "t", tasdiq -> "a",
    rad -> "r" (sabab bilan), bekor -> "b"; vidjet rad etilsa - oldingi matnli ekran ikkala karta bilan."""
    async def t():
        payer, friend = U + 1, U + 2
        for u in (payer, friend):
            await mkuser(u, 0)
        old_cards, old_admins, old_send = dict(config.CARDS), config.ADMIN_IDS, handlers.send
        sent = []

        async def fake_send(bot, chat_id, text, kb=None, **kw):
            sent.append((chat_id, text))
        admin = 4242
        handlers.send, config.ADMIN_IDS = fake_send, {admin}
        config.CARDS.clear()
        config.CARDS.update({"uz": UZ, "xorij": XORIJ})
        bot = WidgetBot()

        def c(uid, data, log, mid=55):
            q = cq(uid, data, log)
            q.bot = bot
            q.message.message_id = mid

            async def delete():
                log.append(("deleted", mid))

            async def edit_reply_markup(reply_markup=None):
                log.append(("kb", reply_markup))

            async def edit_caption(caption=None, **kw):
                log.append(("caption", caption))
            q.message.delete, q.message.edit_reply_markup, q.message.edit_caption = delete, edit_reply_markup, edit_caption
            q.message.html_text = "💳 chek"
            return q

        def photo(uid, log):
            async def answer(t=None, reply_markup=None, **kw):
                log.append(("msg", t))
            return SimpleNamespace(from_user=SimpleNamespace(id=uid, full_name=f"u{uid}", username=None),
                                   photo=[SimpleNamespace(file_id="CHEKW", file_unique_id=f"W{len(log)}")],
                                   document=None, text=None, answer=answer, bot=bot)
        try:
            log = []
            await handlers.cb_card(c(payer, f"gc:30:{friend}", log))
            w = bot.sent()[-1]
            d = json.loads(w.chat_data)
            assert w.chat_id == payer and w.html == vidjet.HTML and d["h"] == "k" and d["d"] == 30
            assert d["u"]["n"] == UZ["n"] and d["v"]["t"] == XORIJ["t"] and d["g"]  # ikkala karta, sovg'a nomi
            assert "UZUM BANK · VISA" == d["v"]["b"] and d["sf"] == "32 000"
            assert ("deleted", 55) in log  # menyu xabari karta bilan almashdi
            # kartaning ostida takror yo'q: nusxa tugmalari ham, raqam/summa ham kartaning o'zida
            assert not any(b.copy_text for row in w.reply_markup.inline_keyboard for b in row)
            assert w.caption == texts.CARD_CAPTION and UZ["n"][-4:] not in w.caption and "chek" in w.caption
            oid = int(d["id"].split("-")[1])
            assert (await db.get_card_order(oid)).msg_id == 777
            # chek -> "t" (kartaning o'zi yangilanadi, to'lovchiga)
            await handlers.on_check(photo(payer, log))
            assert bot.states()[-1] == "t"
            await handlers.cb_order_admin(c(admin, f"oa:{oid}:1", log, mid=1))
            assert bot.states()[-1] == "a"
            # rad: sabab kartada
            await handlers.cb_card(c(payer, "gc:1:0", log))
            oid2 = int(json.loads(bot.sent()[-1].chat_data)["id"].split("-")[1])
            await handlers.on_check(photo(payer, log))
            await handlers.cb_order_admin(c(admin, f"oa:{oid2}:s", log, mid=1))
            last = json.loads(bot.calls[-1].chat_data)
            assert last["h"] == "r" and last["z"] == texts.REJECT_TELL["s"]
            # bekor - kartaning o'zidagi tugma: holat "b", tugmalar "orqaga"ga almashadi
            await handlers.cb_card(c(payer, "gc:7:0", log))
            oid3 = int(json.loads(bot.sent()[-1].chat_data)["id"].split("-")[1])
            await handlers.cb_card(c(payer, f"ox:{oid3}", log, mid=777))
            assert bot.states()[-1] == "b" and (await db.get_card_order(oid3)).status == "cancelled"
            assert log[-2][0] == "kb" and cbs(log[-2][1]) == ["gp:0"] and log[-1] == ("alert", texts.ORDER_CANCELLED_SHORT)
            # vidjet rad etildi - oldingi matnli ekran (ikkala karta, bank, telefon), menyu o'chmaydi
            bot.ok = False
            log.clear()
            await handlers.cb_card(c(payer, "gc:7:0", log))
            assert log[0][0] == "edit" and "🌍 <b>Chet eldan</b>" in log[0][1] and "Uzum Bank" in log[0][1]
            assert "+998901234567" in log[0][1] and "5614 6846 0553 5200" in log[0][1] and ("deleted", 55) not in log
        finally:
            config.CARDS.clear()
            config.CARDS.update(old_cards)
            handlers.send, config.ADMIN_IDS = old_send, old_admins
            handlers.ASK.pop(payer, None)
    run(t())


def test_card_screen_back_from_widget_deletes_it():
    """To'lov kartasidagi "Orqaga": kartani matnga tahrirlab bo'lmaydi - menyu yangi xabar, karta o'chadi."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText
    log = []

    async def edit_text(text, reply_markup=None):
        raise TelegramBadRequest(EditMessageText(text="x"), "there is no text in the message to edit")

    async def answer(text=None, reply_markup=None, **kw):
        log.append("new")

    async def delete():
        log.append("deleted")
    m = SimpleNamespace(edit_text=edit_text, answer=answer, delete=delete, model_extra={"widget": {"html": ""}})
    asyncio.run(handlers.show(SimpleNamespace(message=m), "menu", None))
    assert log == ["new", "deleted"]
    log.clear()
    m.model_extra = {}
    asyncio.run(handlers.show(SimpleNamespace(message=m), "menu", None))
    assert log == ["new"]  # oddiy (masalan, rasmli) xabar o'chirilmaydi
