"""Web admin panel: kirish, sessiya, CSRF, rollar va har bir o'zgartiruvchi amal."""
import asyncio
import json
from types import SimpleNamespace

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from mafia_zone import config, db, panel, runner

runner.GLOBAL_INTERVAL = 0
OWNER, MOD, VIEWER, USER, OTHER = 8_100_001, 8_100_002, 8_100_003, 8_100_004, 8_100_005


class FakeBot:
    id = 42

    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw.get("reply_markup")))
        return SimpleNamespace(message_id=1)

    async def send_photo(self, chat_id, photo, caption=None, **kw):
        self.sent.append((chat_id, caption, "photo"))
        return SimpleNamespace(photo=[SimpleNamespace(file_id="ph")])

    async def get_chat_member(self, chat_id, uid):
        return SimpleNamespace(status="administrator", can_delete_messages=True, can_restrict_members=True,
                               can_pin_messages=False)

    async def get_chat_member_count(self, chat_id):
        return 123

    async def leave_chat(self, chat_id):
        return True


def run(scenario):
    async def go():
        await db.init()
        config.ADMIN_IDS.add(OWNER)
        for uid, name, un in [(OWNER, "Ega", "ega"), (MOD, "Moder", "moder"), (VIEWER, "Kuzat", "kuzat"),
                              (USER, "Ali 100%_", "ali_uz"), (OTHER, "Vali", None)]:
            await db.upsert_user(uid, name, un)
        await db.set_admin(MOD, "moderator", OWNER)
        await db.set_admin(VIEWER, "viewer", OWNER)
        panel._roles_cache.clear()
        panel.BOT = FakeBot()
        async with TestClient(TestServer(panel.make_app())) as c:
            await scenario(c)
    asyncio.run(go())


async def login(c: TestClient, uid: int) -> str:
    """Kirish havolasi orqali sessiya; CSRF tokenni qaytaradi."""
    tok = panel.make_token("login", uid, 60)
    r = await c.get(f"/auth?t={tok}", allow_redirects=False)
    assert r.status == 303 and r.headers["Location"] == "/"
    me = await (await c.get("/api/me")).json()
    return me["csrf"]


def test_security_headers_and_index():
    async def s(c):
        r = await c.get("/")
        body = await r.text()
        assert r.status == 200 and "__V__" not in body and "/static/app.js?v=" in body
        assert "script-src 'self'" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Referrer-Policy"] == "no-referrer"
        assert (await c.get("/static/app.js")).status == 200
        assert (await c.get("/static/../panel.py")).status in (403, 404)
        assert (await c.get("/healthz")).status == 200
    run(s)


def test_login_flow_and_one_time_link():
    async def s(c):
        assert (await c.get("/api/me")).status == 401
        assert (await c.get("/api/public")).status == 200
        bad = await c.get("/auth?t=garbage", allow_redirects=False)
        assert bad.status == 303 and "err=link" in bad.headers["Location"]
        forged = panel.make_token("login", OWNER, 60)[:-4] + "0000"
        assert "err=link" in (await c.get(f"/auth?t={forged}", allow_redirects=False)).headers["Location"]
        expired = panel.make_token("login", OWNER, -1)
        assert "err=link" in (await c.get(f"/auth?t={expired}", allow_redirects=False)).headers["Location"]
        stranger = panel.make_token("login", USER, 60)  # admin emas
        assert "err=link" in (await c.get(f"/auth?t={stranger}", allow_redirects=False)).headers["Location"]
        session_as_login = panel.make_token("s", OWNER, 60)  # boshqa turdagi token kirish uchun ishlamaydi
        assert "err=link" in (await c.get(f"/auth?t={session_as_login}", allow_redirects=False)).headers["Location"]

        tok = panel.make_token("login", OWNER, 60)
        r = await c.get(f"/auth?t={tok}", allow_redirects=False)
        assert r.status == 303 and r.headers["Location"] == "/"
        cookie = r.cookies[panel.COOKIE]
        assert cookie["httponly"] and cookie["samesite"] == "Lax"
        me = await (await c.get("/api/me")).json()
        assert me["role"] == "owner" and me["csrf"] and "don" in me["roles"]
        c.session.cookie_jar.clear()
        again = await c.get(f"/auth?t={tok}", allow_redirects=False)  # bir martalik
        assert "err=link" in again.headers["Location"]
    run(s)


def test_csrf_origin_and_roles():
    async def s(c):
        csrf = await login(c, VIEWER)
        url = f"/api/users/{USER}/ban"
        assert (await c.post(url, json={"banned": True})).status == 403  # CSRF yo'q
        assert (await c.post(url, json={"banned": True}, headers={"X-CSRF": "x"})).status == 403
        r = await c.post(url, json={"banned": True}, headers={"X-CSRF": csrf})
        assert r.status == 403 and "huquq" in (await r.json())["error"]  # kuzatuvchi ban qila olmaydi
        assert (await c.get("/api/admins")).status == 403
        c.session.cookie_jar.clear()

        csrf = await login(c, MOD)
        evil = await c.post(url, json={"banned": True}, headers={"X-CSRF": csrf, "Origin": "https://evil.example"})
        assert evil.status == 403
        assert (await c.post(url, json={"banned": True}, headers={"X-CSRF": csrf})).status == 200
        assert (await db.get_user(USER)).banned
        r = await c.post(f"/api/users/{OWNER}/ban", json={"banned": True}, headers={"X-CSRF": csrf})
        assert r.status == 400  # adminni ban qilib bo'lmaydi
        r = await c.post(f"/api/users/{USER}/balance", json={"currency": "dollars", "delta": 5}, headers={"X-CSRF": csrf})
        assert r.status == 403  # moderator pul bera olmaydi
        assert (await c.post(url, json={"banned": False}, headers={"X-CSRF": csrf})).status == 200

        await db.remove_admin(MOD)  # adminlikdan olindi: kesh tozalangach kira olmaydi
        panel._roles_cache.clear()
        assert (await c.get("/api/me")).status == 401
        await db.set_admin(MOD, "moderator", OWNER)
    run(s)


def test_balance_items_and_audit_log():
    async def s(c):
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}
        before = (await db.get_user(USER)).dollars
        r = await c.post(f"/api/users/{USER}/balance", json={"currency": "dollars", "delta": 500, "reason": "konkurs"},
                         headers=hdr)
        assert r.status == 200 and (await r.json())["value"] == before + 500
        assert any(chat == USER and "+500" in t for chat, t, _ in panel.BOT.sent)  # foydalanuvchiga xabar
        too_much = await c.post(f"/api/users/{USER}/balance", json={"currency": "dollars", "delta": -(before + 501)},
                                headers=hdr)
        assert too_much.status == 400 and (await db.get_user(USER)).dollars == before + 500  # manfiyga tushmaydi
        for bad in [{"currency": "dollars", "delta": 0}, {"currency": "btc", "delta": 1},
                    {"currency": "dollars", "delta": "abc"}, {"currency": "dollars", "delta": 10 ** 12},
                    {"currency": "dollars", "delta": True}]:
            assert (await c.post(f"/api/users/{USER}/balance", json=bad, headers=hdr)).status == 400, bad
        assert (await c.post(f"/api/users/{USER}/balance", data="not json", headers=hdr)).status == 400
        assert (await c.post("/api/users/999/balance", json={"currency": "dollars", "delta": 1},
                             headers=hdr)).status == 404

        r = await c.post(f"/api/users/{USER}/item", json={"item": "shield", "delta": 2}, headers=hdr)
        assert (await r.json())["qty"] == 2
        r = await c.post(f"/api/users/{USER}/item", json={"item": "shield", "delta": -5}, headers=hdr)
        assert (await r.json())["qty"] == 2  # manfiyga tushmaydi
        assert (await c.post(f"/api/users/{USER}/item", json={"item": "bomb", "delta": 1}, headers=hdr)).status == 400

        detail = await (await c.get(f"/api/users/{USER}")).json()
        assert detail["dollars"] == before + 500 and {"code": "shield", "name": detail["items"][0]["name"],
                                                       "qty": 2, "enabled": True} in detail["items"]
        log = await (await c.get("/api/log")).json()
        actions = [e["action"] for e in log["items"]]
        assert "balance" in actions and "item" in actions and "login" in actions
        assert any("konkurs" in e["details"] for e in log["items"])
    run(s)


def test_users_search_is_safe():
    async def s(c):
        await login(c, VIEWER)
        for q in ["%", "_", "100%_", "ali", "@ali_uz", str(USER), "'; drop table users; --", "9" * 40]:
            r = await c.get("/api/users", params={"q": q})
            assert r.status == 200, q
        found = await (await c.get("/api/users", params={"q": "100%_"})).json()
        assert [u["id"] for u in found["items"]] == [USER]  # % va _ oddiy belgi sifatida
        pct = await (await c.get("/api/users", params={"q": "%"})).json()
        assert [u["id"] for u in pct["items"]] == [USER]  # faqat ismida % borlar, hamma emas
        by_id = await (await c.get("/api/users", params={"q": str(USER)})).json()
        assert by_id["items"][0]["id"] == USER
        for f in ["all", "active", "banned", "rich", "games", "nonsense"]:
            assert (await c.get("/api/users", params={"filter": f, "page": "-3"})).status == 200
        assert (await c.get("/api/users/abc")).status == 404
    run(s)


def test_economy_settings_apply_and_persist():
    async def s(c):
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}
        old_win, old_price = config.REWARD_WIN, config.SHOP["shield"]
        r = await c.post("/api/economy", json={"reward_win": 55, "shop": {"shield": 130}, "shop_off": ["ticket"]},
                         headers=hdr)
        assert r.status == 200
        assert config.REWARD_WIN == 55 and config.SHOP["shield"] == 130 and config.SHOP_OFF == {"ticket"}
        assert not await db.buy(USER, "ticket")  # sotuvdan olingan
        for bad in [{"reward_win": -1}, {"diamond_rate": 0}, {"shop": {"bomb": 1}}, {"shop": {"shield": 0}},
                    {"shop_off": ["bomb"]}, {}]:
            assert (await c.post("/api/economy", json=bad, headers=hdr)).status == 400, bad
        config.REWARD_WIN, config.SHOP["shield"] = 1, 1  # "qayta ishga tushish": bazadan yuklanadi
        config.SHOP_OFF.clear()
        await db.load_settings()
        assert config.REWARD_WIN == 55 and config.SHOP["shield"] == 130 and config.SHOP_OFF == {"ticket"}
        await c.post("/api/economy", json={"reward_win": old_win, "shop": {"shield": old_price}, "shop_off": []},
                     headers=hdr)
        assert config.REWARD_WIN == old_win and not config.SHOP_OFF
    run(s)


def test_admins_management():
    async def s(c):
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}
        r = await c.post("/api/admins", json={"who": "@nobody_here", "role": "moderator"}, headers=hdr)
        assert r.status == 400
        assert (await c.post("/api/admins", json={"who": str(OTHER), "role": "god"}, headers=hdr)).status == 400
        assert (await c.post("/api/admins", json={"who": str(OWNER), "role": "viewer"}, headers=hdr)).status == 400
        r = await c.post("/api/admins", json={"who": str(OTHER), "role": "viewer"}, headers=hdr)
        items = (await r.json())["items"]
        assert {"id": OTHER, "role": "viewer"}.items() <= next(a for a in items if a["id"] == OTHER).items()
        assert next(a for a in items if a["id"] == OWNER)["role"] == "owner"
        assert (await c.delete(f"/api/admins/{OWNER}", headers=hdr)).status == 400
        assert (await c.delete(f"/api/admins/{OTHER}", headers=hdr)).status == 200
        assert await db.panel_role(OTHER) is None
    run(s)


def test_broadcast_validation_and_test_send():
    async def s(c):
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}

        def form(**kw):
            f = FormData()
            for k, v in {"audience": "users", "text": "Salom", "buttons": "[]", "test": "1", **kw}.items():
                f.add_field(k, v)
            return f
        cases = [
            (dict(audience="all"), "Kimga"),
            (dict(text=""), "Matn yozing"),
            (dict(text="<b>ochiq"), "yopilmagan"),
            (dict(text='<a href="javascript:alert(1)">x</a>'), "Havola"),
            (dict(text="x" * 5000), "4096"),
            (dict(buttons="{bad"), "Tugmalar"),
            (dict(buttons=json.dumps([{"text": "a", "url": "ftp://x"}])), "havolasi"),
            (dict(buttons=json.dumps([{"text": "", "url": "https://t.me/x"}])), "Tugma matni"),
            (dict(buttons=json.dumps([{"text": "a", "url": "https://t.me/x"}] * 7)), "6 ta"),
        ]
        for kw, msg in cases:
            r = await c.post("/api/broadcast", data=form(**kw), headers=hdr)
            assert r.status == 400 and msg in (await r.json())["error"], (kw, await r.text())
        r = await c.post("/api/broadcast", data=form(text="<img src=x onerror=alert(1)>"), headers=hdr)
        assert r.status == 200 and panel.BOT.sent[-1][1].startswith("&lt;img")  # teg emas, oddiy matn bo'lib ketadi
        ok_form = form(text="Tom & Jerry <3 <b>qalin</b>",
                       buttons=json.dumps([{"text": "Kanal", "url": "https://t.me/kanal"}]))
        r = await c.post("/api/broadcast", data=ok_form, headers=hdr)
        assert r.status == 200 and (await r.json())["test"]
        chat, text, kb = panel.BOT.sent[-1]
        assert chat == OWNER and text == "Tom &amp; Jerry &lt;3 <b>qalin</b>" and kb.inline_keyboard[0][0].url

        photo = form(text="rasm")
        photo.add_field("photo", b"\x89PNG fake", filename="a.png", content_type="image/png")
        assert (await c.post("/api/broadcast", data=photo, headers=hdr)).status == 200
        assert panel.BOT.sent[-1][2] == "photo"
        bad_type = form()
        bad_type.add_field("photo", b"MZ", filename="a.exe", content_type="application/octet-stream")
        assert (await c.post("/api/broadcast", data=bad_type, headers=hdr)).status == 400

        n = len(panel.BOT.sent)
        r = await c.post("/api/broadcast", data=form(test="0", audience="users"), headers=hdr)
        bid = (await r.json())["id"]
        for _ in range(100):
            await asyncio.sleep(0.02)
            if panel.BROADCAST["id"] is None:
                break
        info = await (await c.get("/api/broadcast")).json()
        row = next(b for b in info["history"] if b["id"] == bid)
        assert row["status"] == "done" and row["sent"] == row["total"] == len(panel.BOT.sent) - n
        csrf_v = None
        c.session.cookie_jar.clear()
        csrf_v = await login(c, MOD)
        assert (await c.post("/api/broadcast", data=form(), headers={"X-CSRF": csrf_v})).status == 403
    run(s)


def test_dashboard_games_groups():
    async def s(c):
        csrf = await login(c, OWNER)
        await db.group_settings(-100777, "Test guruh")
        d = await (await c.get("/api/dashboard", params={"period": "7"})).json()
        assert len(d["chart"]) == 14 and d["users"] >= 5 and set(d["teams"]) == {"town", "mafia", "neutral", "draw"}
        assert (await c.get("/api/dashboard", params={"period": "bogus"})).status == 200
        assert (await (await c.get("/api/games")).json())["items"] == []
        assert (await c.post("/api/games/-1/stop", json={}, headers={"X-CSRF": csrf})).status == 404
        g = await (await c.get("/api/groups", params={"q": "test"})).json()
        row = next(x for x in g["items"] if x["chat_id"] == -100777)
        assert row["members"] == 123 and row["rights"] == "partial"  # pin huquqi yo'q
        r = await c.post("/api/groups/-100777/settings", json={"night": 45, "afk": False},
                         headers={"X-CSRF": csrf})
        assert r.status == 200 and (await db.group_settings(-100777))["night"] == 45
        assert (await c.post("/api/groups/-100777/settings", json={"night": 5},
                             headers={"X-CSRF": csrf})).status == 400
        assert (await c.post("/api/groups/-100777/settings", json={"afk": "yes"},
                             headers={"X-CSRF": csrf})).status == 400
        assert (await c.post("/api/groups/-5/settings", json={}, headers={"X-CSRF": csrf})).status == 404
        assert (await c.post("/api/groups/-100777/leave", json={}, headers={"X-CSRF": csrf})).status == 200
        assert (await c.get("/api/nope")).status == 404
    run(s)


def test_last_seen_and_migration():
    async def s(c):
        u = await db.get_user(USER)
        assert u.last_seen is not None  # upsert_user yozadi
    run(s)


def test_pro_grant_remove_and_nickname():
    from mafia_zone import pro

    async def s(c):
        csrf = await login(c, MOD)
        hdr = {"X-CSRF": csrf}
        assert (await c.post(f"/api/users/{USER}/pro", json={"days": 7}, headers=hdr)).status == 403  # faqat owner
        csrf = await login(c, OWNER)
        hdr = {"X-CSRF": csrf}
        r = await c.post(f"/api/users/{USER}/pro", json={"days": 7, "notify": True}, headers=hdr)
        assert r.status == 200 and (await r.json())["pro_until"] and pro.is_pro(USER)
        assert any(chat == USER and "PRO" in t for chat, t, _ in panel.BOT.sent)
        for bad in ({"days": -1}, {"days": "x"}, {"days": 99999}):
            assert (await c.post(f"/api/users/{USER}/pro", json=bad, headers=hdr)).status == 400, bad
        await db.set_nickname(USER, "Shoh")
        detail = await (await c.get(f"/api/users/{USER}")).json()
        assert detail["pro_until"] and detail["nickname"] == "Shoh"
        assert (await c.post(f"/api/users/{USER}/nickname", json={}, headers=hdr)).status == 200
        assert (await db.get_user(USER)).nickname is None
        r = await c.post(f"/api/users/{USER}/pro", json={"days": 0}, headers=hdr)
        assert r.status == 200 and (await r.json())["pro_until"] is None and not pro.is_pro(USER)
        actions = [e["action"] for e in (await (await c.get("/api/log")).json())["items"]]
        assert "pro" in actions and "nickname" in actions
    run(s)
