"""Web admin panel: aiohttp, bot bilan bitta jarayonda (bitta Railway servisi).

Kirish: admin botga /panel yozadi -> bot 5 daqiqalik bir martalik havola beradi -> havola sessiya cookie qo'yadi.
Parol yo'q. Har so'rovda rol bazadan tekshiriladi (admin o'chirilsa darhol kira olmaydi).
O'zgartiruvchi so'rovlar: X-CSRF sarlavhasi + Origin tekshiruvi. Har bir amal admin_log jadvaliga yoziladi.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

from . import config, db, pro, runner, texts
from .engine.game import CONFIRM, DAY, NIGHT, VOTING
from .engine.roles import MAFIA, NEUTRAL, ROLES, TOWN

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent / "panel_static"
COOKIE = "mz_session"
SESSION_TTL = 12 * 3600
LOGIN_TTL = 5 * 60
TZ = timezone(timedelta(hours=5))  # Toshkent
RANK = {"viewer": 0, "moderator": 1, "owner": 2}
MAX_AMOUNT = 10 ** 9
BOT: Bot | None = None


# ---------- tokenlar ----------
def _secret() -> bytes:
    return (config.PANEL_SECRET or hashlib.sha256(f"mz-panel:{config.BOT_TOKEN}".encode()).hexdigest()).encode()


def _sign(body: str) -> str:
    return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def make_token(kind: str, uid: int, ttl: int) -> str:
    body = f"{kind}.{uid}.{int(time.time()) + ttl}.{secrets.token_urlsafe(12)}"
    return f"{body}.{_sign(body)}"


def read_token(token: str, kind: str) -> tuple[int, str] | None:
    """(uid, nonce) yoki None: imzo, tur va muddat tekshiriladi."""
    parts = (token or "").split(".")
    if len(parts) != 5:
        return None
    k, uid, exp, nonce, sig = parts
    if k != kind or not hmac.compare_digest(sig, _sign(".".join(parts[:4]))):
        return None
    try:
        uid_i, exp_i = int(uid), int(exp)
    except ValueError:
        return None
    return (uid_i, nonce) if exp_i > time.time() else None


_used: dict[str, float] = {}  # bir martalik havolalar (ponytail: xotirada; qayta ishga tushsa 5 daqiqa ichida qayta ishlaydi)


def _use_once(nonce: str) -> bool:
    t = time.time()
    for n in [n for n, exp in _used.items() if exp < t]:
        del _used[n]
    if nonce in _used:
        return False
    _used[nonce] = t + LOGIN_TTL
    return True


def login_link(uid: int) -> str:
    return f"{config.PANEL_URL}/auth?t={make_token('login', uid, LOGIN_TTL)}"


def csrf_for(session_nonce: str) -> str:
    return _sign(f"csrf.{session_nonce}")


# ---------- yordamchilar ----------
class Bad(web.HTTPBadRequest):
    def __init__(self, msg: str):
        super().__init__(text=json.dumps({"error": msg}), content_type="application/json")


class Forbidden(web.HTTPForbidden):
    def __init__(self, msg: str = "Bu amal uchun huquqingiz yo'q"):
        super().__init__(text=json.dumps({"error": msg}), content_type="application/json")


class NotFound(web.HTTPNotFound):
    def __init__(self, msg: str = "Topilmadi"):
        super().__init__(text=json.dumps({"error": msg}), content_type="application/json")


def ok(data=None) -> web.Response:
    return web.json_response({"ok": True, **(data or {})}, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def need(req: web.Request, role: str) -> None:
    if RANK[req["role"]] < RANK[role]:
        raise Forbidden()


async def body(req: web.Request) -> dict:
    try:
        data = await req.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise Bad("Noto'g'ri so'rov")
    if not isinstance(data, dict):
        raise Bad("Noto'g'ri so'rov")
    return data


def as_int(v, lo: int, hi: int, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise Bad(f"{name}: butun son kiriting")
    try:
        n = int(str(v).strip())
    except ValueError:
        raise Bad(f"{name}: butun son kiriting")
    if not lo <= n <= hi:
        raise Bad(f"{name}: {lo} dan {hi} gacha bo'lishi kerak")
    return n


def as_str(v, hi: int, name: str, required: bool = False) -> str:
    s = v.strip() if isinstance(v, str) else ""
    if v is not None and not isinstance(v, str):
        raise Bad(f"{name}: matn kiriting")
    if required and not s:
        raise Bad(f"{name}: to'ldiring")
    if len(s) > hi:
        raise Bad(f"{name}: {hi} belgidan oshmasin")
    return s


def page_arg(req: web.Request) -> int:
    try:
        return max(0, min(int(req.query.get("page", 0)), 10 ** 6))
    except ValueError:
        return 0


def path_int(req: web.Request, key: str) -> int:
    try:
        return int(req.match_info[key])
    except (KeyError, ValueError):
        raise NotFound()


def iso(t: datetime | None) -> str | None:
    return db._aware(t).isoformat() if t else None


async def audit(req: web.Request, action: str, target="", details: str = "") -> None:
    await db.log_action(req["uid"], action, target, details)


# ---------- middleware ----------
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


def _https(req: web.Request) -> bool:
    return req.headers.get("X-Forwarded-Proto", req.scheme).split(",")[0].strip() == "https"


@web.middleware
async def security(req: web.Request, handler):
    try:
        resp = await handler(req)
    except web.HTTPException as e:
        _harden(req, e)
        raise
    except Exception:
        log.exception("panel: %s %s", req.method, req.path)
        resp = web.json_response({"error": "Server xatosi. Qayta urinib ko'ring."}, status=500)
    _harden(req, resp)
    return resp


def _harden(req: web.Request, resp) -> None:
    h = resp.headers
    h["Content-Security-Policy"] = CSP
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if _https(req):
        h["Strict-Transport-Security"] = "max-age=31536000"
    if req.path.startswith("/api/") or req.path in ("/", "/auth"):
        h["Cache-Control"] = "no-store"


_roles_cache: dict[int, tuple[float, str | None]] = {}


async def role_of(uid: int) -> str | None:
    hit = _roles_cache.get(uid)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    role = await db.panel_role(uid)
    _roles_cache[uid] = (time.monotonic() + 15, role)  # admin o'chirilsa 15 s ichida chiqariladi
    return role


PUBLIC_API = {"/api/public"}


@web.middleware
async def auth(req: web.Request, handler):
    if not req.path.startswith("/api/") or req.path in PUBLIC_API:
        return await handler(req)
    tok = read_token(req.cookies.get(COOKIE, ""), "s")
    role = await role_of(tok[0]) if tok else None
    if not tok or not role:
        return web.json_response({"error": "Kirish kerak"}, status=401)
    if req.method not in ("GET", "HEAD"):
        origin = req.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != req.host:
            return web.json_response({"error": "Ruxsat etilmagan manba"}, status=403)
        if not hmac.compare_digest(req.headers.get("X-CSRF", ""), csrf_for(tok[1])):
            return web.json_response({"error": "Sessiya eskirgan. Sahifani yangilang."}, status=403)
    req["uid"], req["role"], req["nonce"] = tok[0], role, tok[1]
    return await handler(req)


# ---------- kirish ----------
async def page_auth(req: web.Request) -> web.Response:  # noqa: RET503 (redirect raise bilan)
    tok = read_token(req.query.get("t", ""), "login")
    if not tok or not _use_once(tok[1]) or not await role_of(tok[0]):
        raise web.HTTPSeeOther("/#/login?err=link")
    resp = web.HTTPSeeOther("/")
    resp.set_cookie(COOKIE, make_token("s", tok[0], SESSION_TTL), max_age=SESSION_TTL, httponly=True,
                    secure=_https(req), samesite="Lax", path="/")
    await db.log_action(tok[0], "login", "", req.headers.get("User-Agent", "")[:200])
    raise resp


async def api_public(req: web.Request) -> web.Response:
    return ok({"bot": runner.BOT_USERNAME})


async def api_me(req: web.Request) -> web.Response:
    u = await db.get_user(req["uid"])
    return ok({
        "id": req["uid"], "name": u.full_name if u else str(req["uid"]), "role": req["role"],
        "csrf": csrf_for(req["nonce"]), "bot": runner.BOT_USERNAME,
        "roles": {c: {"name": r.name, "team": r.team} for c, r in ROLES.items()},
        "items": {c: {"name": n, "about": texts.ITEM_ABOUT.get(c, "")} for c, n in texts.ITEMS.items()},
    })


async def api_logout(req: web.Request) -> web.Response:
    resp = ok()
    resp.del_cookie(COOKIE, path="/")
    return resp


# ---------- boshqaruv paneli ----------
PHASE = {NIGHT: "night", DAY: "day", VOTING: "voting", CONFIRM: "confirm"}


def live_games() -> list[dict]:
    out = []
    for chat_id, r in list(runner.RUNNERS.items()):
        g = r.game
        if g:
            alive = g.alive()
            started = r.meta.get("started")
            out.append({"chat_id": chat_id, "title": r.title or str(chat_id), "phase": PHASE.get(g.phase, g.phase),
                        "day": g.day, "alive": len(alive), "total": len(g.players),
                        "mafia": sum(p.team == MAFIA for p in alive),
                        "started": datetime.fromtimestamp(started, timezone.utc).isoformat() if started else None})
        else:
            out.append({"chat_id": chat_id, "title": r.title or str(chat_id), "phase": "lobby", "day": 0,
                        "alive": len(r.members), "total": len(r.members), "mafia": None, "started": None,
                        "lobby_left": max(0, int(r.lobby_deadline - time.time()))})
    out.sort(key=lambda x: -x["total"])
    return out


def period_start(period: str) -> datetime | None:
    t = datetime.now(TZ)
    if period == "today":
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if period in ("7", "30"):
        return t - timedelta(days=int(period))
    return None


def team_of(winner: str) -> str:
    return {TOWN: "town", MAFIA: "mafia", "draw": "draw"}.get(winner, "neutral")


async def api_dashboard(req: web.Request) -> web.Response:
    period = req.query.get("period", "today")
    if period not in ("today", "7", "30", "all"):
        period = "today"
    since = period_start(period)
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    chart_from = today - timedelta(days=13)
    d = await db.dashboard(since, chart_from)
    days = [(chart_from + timedelta(days=i)).date() for i in range(14)]
    games, users = {k: 0 for k in days}, {k: 0 for k in days}
    for t in d.pop("chart_games"):
        games[t.astimezone(TZ).date()] = games.get(t.astimezone(TZ).date(), 0) + 1
    for t in d.pop("chart_users"):
        users[t.astimezone(TZ).date()] = users.get(t.astimezone(TZ).date(), 0) + 1
    teams = {"town": 0, "mafia": 0, "neutral": 0, "draw": 0}
    for w, n in d.pop("winners").items():
        teams[team_of(w)] += n
    entries, _ = await db.get_log(0, 6)
    live = live_games()
    return ok({**d, "period": period, "teams": teams, "live": live[:8], "live_count": len(live),
               "playing": len(runner.PLAYING), "log": entries,
               "chart": [{"date": k.strftime("%d.%m"), "games": games[k], "users": users[k]} for k in days]})


# ---------- foydalanuvchilar ----------
def user_status(u: db.User) -> str:
    if u.banned:
        return "banned"
    if u.telegram_id in runner.PLAYING:
        return "playing"
    created, seen = db._aware(u.created_at), db._aware(u.last_seen)
    if created and created > db.now() - timedelta(days=1):
        return "new"
    if seen and seen > db.now() - timedelta(days=7):
        return "active"
    return "idle"


def user_row(u: db.User) -> dict:
    return {"id": u.telegram_id, "name": u.full_name, "username": u.username, "dollars": u.dollars,
            "diamonds": u.diamonds, "games": u.games, "wins": u.wins, "banned": u.banned, "status": user_status(u)}


async def api_users(req: web.Request) -> web.Response:
    q = req.query.get("q", "")[:64]
    filt = req.query.get("filter", "all")
    if filt not in ("all", "active", "banned", "rich", "games"):
        filt = "all"
    page = page_arg(req)
    rows, total = await db.users_page(q, filt, page)
    return ok({"items": [user_row(u) for u in rows], "total": total, "page": page, "size": 20})


async def api_user(req: web.Request) -> web.Response:
    uid = path_int(req, "uid")
    u = await db.get_user(uid)
    if not u:
        raise NotFound("Foydalanuvchi topilmadi")
    inv = {i.item: i for i in await db.inventory(uid)}
    p = await db.partner(uid)
    pu = await db.get_user(p) if p else None
    return ok({**user_row(u), "created_at": iso(u.created_at), "last_seen": iso(u.last_seen),
               "rank": texts.rank(u.wins), "admin_role": await db.panel_role(uid),
               "partner": {"id": p, "name": pu.full_name if pu else str(p)} if p else None,
               "items": [{"code": c, "name": n, "qty": inv[c].qty if c in inv else 0,
                          "enabled": inv[c].enabled if c in inv else True} for c, n in texts.ITEMS.items()],
               "history": await db.user_games(uid),
               "pro_until": iso(pro.until(uid)), "nickname": u.nickname})


async def _notify(uid: int, text: str) -> None:
    if BOT:
        await runner.send(BOT, uid, text)


async def api_balance(req: web.Request) -> web.Response:
    need(req, "owner")
    uid = path_int(req, "uid")
    d = await body(req)
    cur = d.get("currency")
    if cur not in ("dollars", "diamonds"):
        raise Bad("Valyutani tanlang")
    delta = as_int(d.get("delta"), -MAX_AMOUNT, MAX_AMOUNT, "Miqdor")
    if delta == 0:
        raise Bad("Miqdor 0 bo'lmasin")
    reason = as_str(d.get("reason"), 200, "Sabab")
    if not await db.get_user(uid):
        raise NotFound("Foydalanuvchi topilmadi")
    new = await db.change_balance(uid, cur, delta)
    if new is None:
        raise Bad("Balans yetmaydi: ayirgandan keyin manfiy bo'lib qoladi")
    sign = "💵" if cur == "dollars" else "💎"
    await audit(req, "balance", uid, f"{delta:+d} {cur}" + (f" · {reason}" if reason else ""))
    if d.get("notify", True):
        await _notify(uid, f"🎁 Administrator hisobingizni o'zgartirdi: <b>{delta:+d} {sign}</b>"
                           + (f"\nSabab: {texts.escape(reason)}" if reason else ""))
    return ok({"value": new})


async def api_item(req: web.Request) -> web.Response:
    need(req, "owner")
    uid = path_int(req, "uid")
    d = await body(req)
    item = d.get("item")
    if item not in texts.ITEMS:
        raise Bad("Bunday buyum yo'q")
    delta = as_int(d.get("delta"), -1000, 1000, "Miqdor")
    if not await db.get_user(uid):
        raise NotFound("Foydalanuvchi topilmadi")
    qty = await db.item_qty(uid, item, delta)
    await audit(req, "item", uid, f"{item} {delta:+d} -> {qty}")
    return ok({"qty": qty})


async def api_pro(req: web.Request) -> web.Response:
    """PRO berish (days > 0, muddat ustiga qo'shiladi) yoki olib tashlash (days = 0)."""
    need(req, "owner")
    uid = path_int(req, "uid")
    d = await body(req)
    days = as_int(d.get("days"), 0, 3650, "Kun")
    if not await db.get_user(uid):
        raise NotFound("Foydalanuvchi topilmadi")
    end = await db.set_pro(uid, days)
    await audit(req, "pro", uid, f"+{days} kun" if days else "olib tashlandi")
    if d.get("notify") is True and end:
        await _notify(uid, texts.pro_done(end))
    return ok({"pro_until": iso(end)})


async def api_nickname(req: web.Request) -> web.Response:
    """Nickname'ni o'chirish (haqoratli/aldovchi laqab)."""
    need(req, "moderator")
    uid = path_int(req, "uid")
    if not await db.get_user(uid):
        raise NotFound("Foydalanuvchi topilmadi")
    await db.set_nickname(uid, None)
    await audit(req, "nickname", uid, "o'chirildi")
    return ok({"nickname": None})


async def api_ban(req: web.Request) -> web.Response:
    need(req, "moderator")
    uid = path_int(req, "uid")
    d = await body(req)
    banned = d.get("banned")
    if not isinstance(banned, bool):
        raise Bad("Noto'g'ri so'rov")
    reason = as_str(d.get("reason"), 200, "Sabab")
    if await db.panel_role(uid):
        raise Bad("Adminni ban qilib bo'lmaydi. Avval adminlikdan oling.")
    if not await db.set_banned(uid, banned):
        raise NotFound("Foydalanuvchi topilmadi")
    await audit(req, "ban" if banned else "unban", uid, reason)
    return ok({"banned": banned})


# ---------- o'yinlar ----------
async def api_games(req: web.Request) -> web.Response:
    return ok({"items": live_games()})


async def api_game_players(req: web.Request) -> web.Response:
    need(req, "moderator")
    chat = path_int(req, "chat")
    r = runner.RUNNERS.get(chat)
    if not r:
        raise NotFound("O'yin tugagan")
    if r.game:
        players = [{"id": p.uid, "name": p.name, "role": p.role, "team": p.team, "alive": p.alive}
                   for p in r.game.players]
    else:
        players = [{"id": u, "name": n, "role": None, "team": None, "alive": True} for u, n in r.members]
    await audit(req, "view_roles", chat, r.title)
    return ok({"players": players, "title": r.title, "lobby": r.game is None})


async def api_game_stop(req: web.Request) -> web.Response:
    need(req, "moderator")
    chat = path_int(req, "chat")
    d = await body(req)
    reason = as_str(d.get("reason"), 200, "Sabab")
    r = runner.RUNNERS.get(chat)
    if not r:
        raise NotFound("O'yin allaqachon tugagan")
    await r.abort("🛑 O'yin administrator tomonidan to'xtatildi." + (f"\nSabab: {texts.escape(reason)}" if reason else ""))
    await audit(req, "stop_game", chat, reason or r.title)
    return ok()


# ---------- guruhlar ----------
_chat_cache: dict[int, tuple[float, dict]] = {}


async def chat_info(chat_id: int) -> dict:
    hit = _chat_cache.get(chat_id)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    info = {"members": None, "rights": "unknown"}
    if BOT:
        me = await runner._call(BOT.get_chat_member, chat_id, BOT.id)
        if me is None or me.status in ("left", "kicked"):
            info["rights"] = "none"
        elif me.status == "administrator":
            full = all(getattr(me, k, False) for k in ("can_delete_messages", "can_restrict_members",
                                                       "can_pin_messages"))
            info["rights"] = "full" if full else "partial"
        elif me.status == "creator":
            info["rights"] = "full"
        else:
            info["rights"] = "member"
        if info["rights"] != "none":
            info["members"] = await runner._call(BOT.get_chat_member_count, chat_id)
    _chat_cache[chat_id] = (time.monotonic() + 600, info)
    return info


async def api_groups(req: web.Request) -> web.Response:
    q = req.query.get("q", "")[:64]
    sort = req.query.get("sort", "week")
    if sort not in ("week", "total", "new"):
        sort = "week"
    page = page_arg(req)
    rows, total = await db.groups_page(q, sort, page)
    infos = await asyncio.gather(*(chat_info(g["chat_id"]) for g in rows))
    live = {g["chat_id"] for g in live_games()}
    for g, info in zip(rows, infos):
        g.update(info, live=g["chat_id"] in live)
    return ok({"items": rows, "total": total, "page": page, "size": 20})


SETTING_RANGES = {"lobby": (30, 600), "night": (15, 300), "day": (15, 600), "vote": (15, 300)}


async def api_group_settings(req: web.Request) -> web.Response:
    need(req, "owner")
    chat = path_int(req, "chat")
    if not await db.group_exists(chat):
        raise NotFound("Guruh topilmadi")
    d = await body(req)
    cur = await db.group_settings(chat)
    new = dict(cur)
    for k, (lo, hi) in SETTING_RANGES.items():
        if k in d:
            new[k] = as_int(d[k], lo, hi, k)
    for k in ("items", "afk", "confirm"):
        if k in d:
            if not isinstance(d[k], bool):
                raise Bad(f"{k}: ha/yo'q")
            new[k] = d[k]
    await db.save_group_settings(chat, new)
    diff = ", ".join(f"{k}: {cur.get(k)} → {v}" for k, v in new.items() if cur.get(k) != v)
    await audit(req, "group_settings", chat, diff or "o'zgarishsiz")
    return ok({"settings": new})


async def api_group_leave(req: web.Request) -> web.Response:
    need(req, "owner")
    chat = path_int(req, "chat")
    if chat >= 0:
        raise Bad("Bu guruh emas")
    if r := runner.RUNNERS.get(chat):
        await r.abort()
    left = await runner._call(BOT.leave_chat, chat) if BOT else None
    _chat_cache.pop(chat, None)
    await audit(req, "leave_group", chat, "chiqdi" if left else "chiqib bo'lmadi")
    if not left:
        raise Bad("Guruhdan chiqib bo'lmadi: bot allaqachon chiqarilgan bo'lishi mumkin")
    return ok()


# ---------- iqtisod ----------
ECON_RANGES = {"reward_win": (0, 100_000), "reward_play": (0, 100_000),
               "ref_bonus": (0, 100_000), "diamond_rate": (1, 1_000_000)}


async def api_economy(req: web.Request) -> web.Response:
    return ok({"values": db.economy()})


async def api_economy_save(req: web.Request) -> web.Response:
    need(req, "owner")
    d = await body(req)
    old = db.economy()
    new: dict = {}
    for k, (lo, hi) in ECON_RANGES.items():
        if k in d:
            new[k] = as_int(d[k], lo, hi, k)
    if "shop" in d:
        if not isinstance(d["shop"], dict) or set(d["shop"]) - set(config.SHOP):
            raise Bad("Do'kon narxlari noto'g'ri")
        new["shop"] = {**old["shop"], **{k: as_int(v, 1, 1_000_000, texts.ITEMS[k]) for k, v in d["shop"].items()}}
    if "shop_off" in d:
        if not isinstance(d["shop_off"], list) or set(d["shop_off"]) - set(config.SHOP):
            raise Bad("Do'kon holati noto'g'ri")
        new["shop_off"] = sorted(set(d["shop_off"]))
    if not new:
        raise Bad("O'zgarish yo'q")
    await db.save_settings(new)
    changes = []
    for k, v in new.items():
        if k == "shop":
            changes += [f"{i}: {old['shop'][i]} → {p}" for i, p in v.items() if old["shop"][i] != p]
        elif old.get(k) != v:
            changes.append(f"{k}: {old.get(k)} → {v}")
    await audit(req, "economy", "", "; ".join(changes) or "o'zgarishsiz")
    return ok({"values": db.economy()})


# ---------- adminlar va jurnal ----------
async def api_admins(req: web.Request) -> web.Response:
    need(req, "owner")
    return ok({"items": await db.list_admins()})


async def api_admin_add(req: web.Request) -> web.Response:
    need(req, "owner")
    d = await body(req)
    who = as_str(d.get("who"), 64, "Foydalanuvchi", required=True)
    role = d.get("role")
    if role not in db.ROLES_PANEL:
        raise Bad("Rolni tanlang")
    u = await db.user_by_username(who) if who.startswith("@") else (
        await db.get_user(int(who)) if who.isdigit() and len(who) < 19 else None)
    if not u:
        raise Bad("Foydalanuvchi topilmadi. U avval botga /start yozgan bo'lishi kerak.")
    if u.telegram_id in config.ADMIN_IDS:
        raise Bad("Bu bosh admin: uning rolini faqat ADMIN_IDS orqali o'zgartirish mumkin")
    await db.set_admin(u.telegram_id, role, req["uid"])
    _roles_cache.pop(u.telegram_id, None)
    await audit(req, "admin_set", u.telegram_id, role)
    return ok({"items": await db.list_admins()})


async def api_admin_remove(req: web.Request) -> web.Response:
    need(req, "owner")
    uid = path_int(req, "uid")
    if uid in config.ADMIN_IDS:
        raise Bad("Bosh adminni paneldan o'chirib bo'lmaydi")
    if not await db.remove_admin(uid):
        raise NotFound("Admin topilmadi")
    _roles_cache.pop(uid, None)
    await audit(req, "admin_remove", uid)
    return ok({"items": await db.list_admins()})


async def api_log(req: web.Request) -> web.Response:
    page = page_arg(req)
    items, total = await db.get_log(page)
    return ok({"items": items, "total": total, "page": page, "size": 30})


# ---------- e'lonlar ----------
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote",
                "tg-spoiler"}
URL_RE = re.compile(r"^(https?://|tg://)[^\s<>\"']{1,500}$", re.I)


class _Check(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.length, self.error = [], 0, ""

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.error = self.error or f"<{tag}> tegi ruxsat etilmagan"
        a = dict(attrs)
        if tag == "a" and not URL_RE.match(a.get("href") or ""):
            self.error = self.error or "Havola http://, https:// yoki tg:// bilan boshlansin"
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.error = self.error or f"<{tag}/> ruxsat etilmagan"

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.error = self.error or f"</{tag}> yopilishi noto'g'ri"

    def handle_data(self, data):
        self.length += len(data)


_TAG = "|".join(sorted(ALLOWED_TAGS, key=len, reverse=True))


def normalize_html(text: str) -> str:
    """Teg yoki HTML-entity bo'lmagan & va < ni ekranlaydi (Telegram ularni rad etadi)."""
    text = re.sub(r"&(?!(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);)", "&amp;", text)
    return re.sub(rf"<(?!/?({_TAG})(\s[^<>]*)?>)", "&lt;", text)


def check_html(text: str) -> tuple[str, int]:
    """(xato, ko'rinadigan matn uzunligi). Telegram HTML qoidalari."""
    p = _Check()
    try:
        p.feed(text)
        p.close()
    except Exception:
        return "Matnni tekshirib bo'lmadi", 0
    if not p.error and p.stack:
        p.error = f"<{p.stack[-1]}> yopilmagan"
    return p.error, p.length


BROADCAST: dict = {"id": None, "cancel": False}  # bir vaqtda bitta e'lon
AUDIENCES = ("users", "active", "groups")


async def audience_ids(audience: str) -> list[int]:
    if audience == "groups":
        return await db.group_ids()
    if audience == "active":
        return await db.active_user_ids(7)
    return await db.all_user_ids()


def b_row(b: db.Broadcast) -> dict:
    return {"id": b.id, "audience": b.audience, "text": b.text, "photo": b.photo, "total": b.total, "sent": b.sent,
            "blocked": b.blocked, "failed": b.failed, "status": b.status, "created_at": iso(b.created_at),
            "finished_at": iso(b.finished_at), "buttons": b.buttons or []}


async def api_broadcast_info(req: web.Request) -> web.Response:
    return ok({"counts": {"users": await db.count_users(), "active": await db.count_active(7),
                          "groups": len(await db.group_ids())},
               "history": [b_row(b) for b in await db.broadcasts()], "running": BROADCAST["id"]})


def _kb(buttons: list) -> Kb | None:
    return Kb(inline_keyboard=[[Btn(text=b["text"], url=b["url"])] for b in buttons]) if buttons else None


async def _deliver(chat: int, text: str, kb, photo: bytes | None, file_id: list) -> str:
    """'sent' / 'blocked' / 'failed'. file_id: rasm bir marta yuklanadi, keyin qayta ishlatiladi."""
    for _ in range(3):
        await runner.pace()
        try:
            if photo is not None:
                m = await BOT.send_photo(chat, file_id[0] if file_id else BufferedInputFile(photo, "photo.jpg"),
                                         caption=text or None, reply_markup=kb)
                if not file_id and m.photo:
                    file_id.append(m.photo[-1].file_id)
            else:
                await BOT.send_message(chat, text, reply_markup=kb, disable_web_page_preview=True)
            return "sent"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramBadRequest as e:
            log.info("broadcast %s: %s", chat, e)
            return "failed"
        except Exception:
            log.exception("broadcast %s", chat)
            return "failed"
    return "failed"


async def _run_broadcast(bid: int, ids: list[int], text: str, kb, photo: bytes | None) -> None:
    n = {"sent": 0, "blocked": 0, "failed": 0}
    file_id: list = []
    status = "done"
    try:
        for i, chat in enumerate(ids):
            if BROADCAST["cancel"]:
                status = "cancelled"
                break
            n[await _deliver(chat, text, kb, photo, file_id)] += 1
            if i % 20 == 19:
                await db.update_broadcast(bid, **n)
    except Exception:
        log.exception("broadcast %s", bid)
        status = "interrupted"
    finally:
        await db.update_broadcast(bid, **n, status=status, finished_at=db.now())
        BROADCAST.update(id=None, cancel=False)


MAX_PHOTO = 10 * 1024 * 1024


async def api_broadcast_send(req: web.Request) -> web.Response:
    need(req, "owner")
    if not BOT:
        raise Bad("Bot ishlamayapti")
    try:
        form = await req.post()
    except (ValueError, web.HTTPRequestEntityTooLarge):
        raise Bad(f"Fayl juda katta (ko'pi {MAX_PHOTO // 1024 // 1024} MB)")
    audience = form.get("audience")
    if audience not in AUDIENCES:
        raise Bad("Kimga yuborishni tanlang")
    text = form.get("text") if isinstance(form.get("text"), str) else ""
    text = text.strip()
    if len(text) > 12000:
        raise Bad("Matn juda uzun")
    photo_f = form.get("photo")
    photo = None
    if photo_f is not None and not isinstance(photo_f, str):
        if (photo_f.content_type or "") not in ("image/jpeg", "image/png", "image/webp"):
            raise Bad("Rasm JPG, PNG yoki WEBP bo'lsin")
        photo = photo_f.file.read(MAX_PHOTO + 1)
        if len(photo) > MAX_PHOTO:
            raise Bad("Rasm 10 MB dan katta")
        if not photo:
            photo = None
    if not text and photo is None:
        raise Bad("Matn yozing yoki rasm qo'shing")
    text = normalize_html(text)
    err, length = check_html(text)
    if err:
        raise Bad(err)
    limit = 1024 if photo is not None else 4096
    if length > limit:
        raise Bad(f"Matn {limit} belgidan oshmasin" + (" (rasm izohi)" if photo is not None else ""))
    try:
        raw = json.loads(form.get("buttons") or "[]")
    except (json.JSONDecodeError, TypeError):
        raise Bad("Tugmalar noto'g'ri")
    if not isinstance(raw, list) or len(raw) > 6:
        raise Bad("Ko'pi bilan 6 ta tugma")
    buttons = []
    for b in raw:
        if not isinstance(b, dict):
            raise Bad("Tugmalar noto'g'ri")
        t = as_str(b.get("text"), 64, "Tugma matni", required=True)
        u = as_str(b.get("url"), 512, "Tugma havolasi", required=True)
        if not URL_RE.match(u):
            raise Bad(f"«{t}» havolasi https:// yoki tg:// bilan boshlansin")
        buttons.append({"text": t, "url": u})
    kb = _kb(buttons)
    if form.get("test") == "1":
        res = await _deliver(req["uid"], text, kb, photo, [])
        if res != "sent":
            raise Bad("Sinov yuborilmadi: botni bloklamaganingizni tekshiring yoki matnni tekshiring")
        return ok({"test": True})
    if BROADCAST["id"]:
        raise Bad("Boshqa e'lon hali yuborilmoqda")
    ids = [i for i in await audience_ids(audience) if i < runner.FAKE_BASE]
    if not ids:
        raise Bad("Bu auditoriyada hech kim yo'q")
    bid = await db.create_broadcast(req["uid"], audience, text, buttons, photo is not None, len(ids))
    BROADCAST.update(id=bid, cancel=False)
    runner.spawn(_run_broadcast(bid, ids, text, kb, photo))
    await audit(req, "broadcast", bid, f"{audience}: {len(ids)} ta")
    return ok({"id": bid, "total": len(ids)})


async def api_broadcast_cancel(req: web.Request) -> web.Response:
    need(req, "owner")
    bid = path_int(req, "bid")
    if BROADCAST["id"] != bid:
        raise Bad("Bu e'lon yuborilmayapti")
    BROADCAST["cancel"] = True
    await audit(req, "broadcast_cancel", bid)
    return ok()


# ---------- statik fayllar ----------
_index_cache: dict = {}


async def page_index(req: web.Request) -> web.Response:
    """index.html: ?v= fayllar o'zgarish vaqtidan — yangi deploydan keyin brauzer eski JS'ni ishlatmaydi."""
    if "html" not in _index_cache:
        v = str(int(max((STATIC / f).stat().st_mtime for f in ("app.js", "app.css"))))
        _index_cache["html"] = (STATIC / "index.html").read_text(encoding="utf-8").replace("__V__", v)
    return web.Response(text=_index_cache["html"], content_type="text/html", charset="utf-8")


async def healthz(req: web.Request) -> web.Response:
    return web.Response(text="ok")


def make_app() -> web.Application:
    app = web.Application(middlewares=[security, auth], client_max_size=MAX_PHOTO + 512 * 1024)
    r = app.router
    r.add_get("/", page_index)
    r.add_get("/auth", page_auth)
    r.add_get("/healthz", healthz)
    r.add_static("/static/", STATIC, append_version=False)
    r.add_get("/api/public", api_public)
    r.add_get("/api/me", api_me)
    r.add_post("/api/logout", api_logout)
    r.add_get("/api/dashboard", api_dashboard)
    r.add_get("/api/users", api_users)
    r.add_get("/api/users/{uid}", api_user)
    r.add_post("/api/users/{uid}/balance", api_balance)
    r.add_post("/api/users/{uid}/item", api_item)
    r.add_post("/api/users/{uid}/ban", api_ban)
    r.add_post("/api/users/{uid}/pro", api_pro)
    r.add_post("/api/users/{uid}/nickname", api_nickname)
    r.add_get("/api/games", api_games)
    r.add_get("/api/games/{chat}/players", api_game_players)
    r.add_post("/api/games/{chat}/stop", api_game_stop)
    r.add_get("/api/groups", api_groups)
    r.add_post("/api/groups/{chat}/settings", api_group_settings)
    r.add_post("/api/groups/{chat}/leave", api_group_leave)
    r.add_get("/api/economy", api_economy)
    r.add_post("/api/economy", api_economy_save)
    r.add_get("/api/admins", api_admins)
    r.add_post("/api/admins", api_admin_add)
    r.add_delete("/api/admins/{uid}", api_admin_remove)
    r.add_get("/api/log", api_log)
    r.add_get("/api/broadcast", api_broadcast_info)
    r.add_post("/api/broadcast", api_broadcast_send)
    r.add_post("/api/broadcast/{bid}/cancel", api_broadcast_cancel)
    return app


async def start(bot: Bot) -> web.AppRunner | None:
    """Bot bilan birga ishga tushadi. Port band bo'lsa bot baribir ishlayveradi."""
    global BOT
    BOT = bot
    await db.interrupt_broadcasts()
    app_runner = web.AppRunner(make_app(), access_log=None)
    await app_runner.setup()
    try:
        await web.TCPSite(app_runner, "0.0.0.0", config.PORT).start()
    except OSError as e:
        log.error("admin panel ishga tushmadi (port %s): %s", config.PORT, e)
        return None
    log.info("admin panel: port %s, manzil: %s", config.PORT, config.PANEL_URL or "(PANEL_URL yo'q)")
    return app_runner
