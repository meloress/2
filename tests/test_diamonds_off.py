"""config.DIAMONDS_OFF: olmos bilan xarid qilinadigan hamma joy "hali ishlamayapti" deydi, hech narsa yechilmaydi."""
import asyncio
from types import SimpleNamespace

from mafia_zone import config, db, handlers, texts

U = 7_700_000


def test_every_diamond_purchase_is_closed():
    async def t():
        await db.init()
        await db.upsert_user(U, "Ali", None)
        u = await db.get_user(U)
        await db.add_balance(U, 0, 100 - u.diamonds)
        config.DIAMONDS_OFF = True
        alerts, invoices = [], []

        async def answer(text=None, show_alert=False, **kw):
            alerts.append(text)

        async def edit_text(*a, **kw):
            pass

        async def send_invoice(**kw):
            invoices.append(kw)
        bot = SimpleNamespace(send_invoice=send_invoice)
        for data in ("pro:d:7", "xd:1", "gm:me", "gm:to", "gs:5:0", "b:mask", "b:votesave", "b:r_don", "m:buy", "m:gem"):
            alerts.clear()
            cq = SimpleNamespace(data=data, from_user=SimpleNamespace(id=U, full_name="Ali", username=None),
                                 answer=answer, bot=bot, message=SimpleNamespace(edit_text=edit_text, answer=edit_text))
            h = {"pro": handlers.cb_pro, "xd": handlers.cb_wallet, "gm": handlers.cb_wallet, "gs": handlers.cb_wallet,
                 "b": handlers.cb_shop, "shoproles": handlers.cb_shop, "m": handlers.cb_menu}[data.split(":")[0]]
            await h(cq)
            assert texts.DIAMONDS_OFF in alerts, data
        shown = []

        async def show_text(text, reply_markup=None, **kw):
            shown.append(text)
        alerts.clear()
        cq = SimpleNamespace(data="shoproles", from_user=SimpleNamespace(id=U, full_name="Ali", username=None),
                             answer=answer, bot=bot, message=SimpleNamespace(edit_text=show_text, answer=show_text))
        await handlers.cb_shop(cq)  # bo'lim ochiladi, faqat sotib olish yopiq
        assert texts.DIAMONDS_OFF not in alerts and "Rolni tanlab olish" in shown[-1]
        assert (await db.get_user(U)).diamonds == 100 and not invoices and not await db.buy(U, "mask")
        ok = []

        async def pcq(ok_=None, error_message=None, **kw):
            ok.append(kw.get("ok", ok_))
        await handlers.on_pre_checkout(SimpleNamespace(invoice_payload="dm:5:0", total_amount=35, currency="XTR",
                                                       from_user=SimpleNamespace(id=U), answer=pcq))
        assert ok == [False]  # eski hisob-faktura ham to'lanmaydi
        assert await db.buy(U, "shield") or True  # dollarli buyumlar ishlayveradi
    asyncio.run(t())
