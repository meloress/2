"""PostgreSQL (lokalda SQLite) modellari va so'rovlar. Balans o'zgarishlari atomar UPDATE bilan."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Index, Integer, String, Text, case, delete, func,
                        select, text, update)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from . import config

Json = JSON().with_variant(JSONB(), "postgresql")
engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True,  # SQLite: qulf bo'lsa 30 s kutadi
                             connect_args={"timeout": 30} if config.DATABASE_URL.startswith("sqlite") else {})
Session = async_sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(t: datetime | None) -> datetime | None:
    """SQLite vaqt zonasisiz qaytaradi: UTC deb hisoblaymiz."""
    return t.replace(tzinfo=timezone.utc) if t is not None and t.tzinfo is None else t


SEEN_EVERY = timedelta(minutes=5)  # last_seen shundan tez-tez yozilmaydi


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64))
    dollars: Mapped[int] = mapped_column(Integer, default=0)
    diamonds: Mapped[int] = mapped_column(Integer, default=0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    last_bonus_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # migratsiya: _migrate()


class Inventory(Base):
    __tablename__ = "inventory"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item: Mapped[str] = mapped_column(String(16), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Group(Base):
    __tablename__ = "groups"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    settings: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GameRow(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running / finished / aborted
    state: Mapped[dict] = mapped_column(Json)
    winner: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("one_running_game", "chat_id", unique=True,
                            postgresql_where=text("status = 'running'"), sqlite_where=text("status = 'running'")),)


class GamePlayer(Base):
    __tablename__ = "game_players"
    game_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(16))
    team: Mapped[str] = mapped_column(String(16))
    alive: Mapped[bool] = mapped_column(Boolean)
    won: Mapped[bool] = mapped_column(Boolean)


class Giveaway(Base):
    __tablename__ = "giveaways"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    sender_id: Mapped[int] = mapped_column(BigInteger)
    per: Mapped[int] = mapped_column(Integer)  # bir kishiga
    parts: Mapped[int] = mapped_column(Integer)  # jami ulush
    left: Mapped[int] = mapped_column(Integer)  # qolgan ulush
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Claim(Base):
    __tablename__ = "giveaway_takes"  # yangi nom: eski jadvalda n ustuni yo'q
    giveaway_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    n: Mapped[int] = mapped_column(Integer, default=0)  # olish tartibi


async def transfer(src: int, dst: int, amount: int) -> bool:
    """src -> dst. Balans yetmasa hech narsa o'zgarmaydi."""
    if src == dst or amount <= 0:
        return False
    try:
        async with Session.begin() as s:
            r = await s.execute(update(User).where(User.telegram_id == src, User.dollars >= amount,
                                                   User.banned.is_(False)).values(dollars=User.dollars - amount))
            if r.rowcount != 1:
                return False
            r = await s.execute(update(User).where(User.telegram_id == dst).values(dollars=User.dollars + amount))
            if r.rowcount != 1:
                raise _Rollback  # qabul qiluvchi yo'q: yechilgan pul qaytadi
    except _Rollback:
        return False
    return True


class _Rollback(Exception):
    pass


async def create_giveaway(chat_id: int, sender: int, per: int, parts: int) -> int | None:
    async with Session.begin() as s:
        r = await s.execute(update(User).where(User.telegram_id == sender, User.dollars >= per * parts,
                                               User.banned.is_(False))
                            .values(dollars=User.dollars - per * parts))
        if r.rowcount != 1:
            return None
        g = Giveaway(chat_id=chat_id, sender_id=sender, per=per, parts=parts, left=parts)
        s.add(g)
        await s.flush()
        return g.id


async def get_giveaway(gid: int) -> Giveaway | None:
    async with Session() as s:
        return await s.get(Giveaway, gid)


class Couple(Base):
    """Har juftlik ikki qator (a->b, b->a). PK: bir odamning faqat bitta parasi bo'ladi."""
    __tablename__ = "couples"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    partner_id: Mapped[int] = mapped_column(BigInteger, index=True)


async def partner(uid: int) -> int | None:
    async with Session() as s:
        c = await s.get(Couple, uid)
        return c.partner_id if c else None


async def make_couple(a: int, b: int) -> bool:
    """Ikkalasi ham bo'sh bo'lsa juftlaydi. Bir vaqtda bosilsa ham PK ikkinchi parani yo'l qo'ymaydi."""
    from sqlalchemy.exc import IntegrityError
    if a == b:
        return False
    try:
        async with Session.begin() as s:
            s.add_all([Couple(user_id=a, partner_id=b), Couple(user_id=b, partner_id=a)])
    except IntegrityError:
        return False
    return True


async def break_couple(uid: int) -> int | None:
    """Parani bekor qiladi, sobiq parani qaytaradi."""
    async with Session.begin() as s:
        c = await s.get(Couple, uid)
        if not c:
            return None
        await s.execute(delete(Couple).where(Couple.user_id.in_([uid, c.partner_id])))
        return c.partner_id


async def user_by_username(username: str) -> User | None:
    async with Session() as s:
        return (await s.scalars(select(User).where(func.lower(User.username) == username.lower().lstrip("@"))
                                .limit(1))).first()


async def giveaway_takers(gid: int) -> list[tuple[int, str]]:
    """[(uid, ism)] olish tartibida."""
    async with Session() as s:
        rows = await s.execute(select(Claim.user_id, User.full_name)
                               .join(User, User.telegram_id == Claim.user_id)
                               .where(Claim.giveaway_id == gid).order_by(Claim.n))
        return [(uid, name or "?") for uid, name in rows]


async def claim(gid: int, uid: int) -> Giveaway | None:
    """Ulush olish. Muvaffaqiyatli bo'lsa yangilangan Giveaway, aks holda None (tugagan/olgan/o'ziniki)."""
    from sqlalchemy.exc import IntegrityError
    try:
        async with Session.begin() as s:
            g = await s.get(Giveaway, gid)
            if not g or g.sender_id == uid:
                return None
            s.add(Claim(giveaway_id=gid, user_id=uid))
            await s.flush()  # PK: bir odam ikki marta ololmaydi
            # atomar: bir vaqtda bosilsa ham ulushdan ortiq berilmaydi
            r = await s.execute(update(Giveaway).where(Giveaway.id == gid, Giveaway.left > 0)
                                .values(left=Giveaway.left - 1))
            if r.rowcount != 1:
                raise _Rollback
            await s.execute(update(User).where(User.telegram_id == uid).values(dollars=User.dollars + g.per))
            await s.refresh(g)
            await s.execute(update(Claim).where(Claim.giveaway_id == gid, Claim.user_id == uid)
                            .values(n=g.parts - g.left))
            return g
    except (IntegrityError, _Rollback):
        return None


# Mavjud jadvalga qo'shilgan ustunlar: create_all ularni qo'sha olmaydi.
# ponytail: qo'lda ADD COLUMN; murakkab o'zgarishlar boshlanganda Alembic'ga o'tiladi
COLUMNS = [("users", "last_seen", "TIMESTAMP WITH TIME ZONE")]


def _migrate(conn) -> None:
    from sqlalchemy import inspect
    insp = inspect(conn)
    for table, col, ddl in COLUMNS:
        if col not in {c["name"] for c in insp.get_columns(table)}:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


async def init() -> None:
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        await c.run_sync(_migrate)
    await load_settings()


# ---------- foydalanuvchilar ----------
async def upsert_user(uid: int, full_name: str, username: str | None) -> User:
    from sqlalchemy.exc import IntegrityError
    full_name = (full_name or "")[:128]
    for _ in range(2):  # bir vaqtda ikki so'rov: ikkinchisi IntegrityError -> qayta urinish
        try:
            async with Session.begin() as s:
                u = await s.get(User, uid)
                if not u:
                    u = User(telegram_id=uid, full_name=full_name, username=username, dollars=0, diamonds=0,
                             games=0, wins=0, banned=False)
                    s.add(u)
                elif (u.full_name, u.username) != (full_name, username):
                    u.full_name, u.username = full_name, username
                t = now()
                if u.last_seen is None or _aware(u.last_seen) < t - SEEN_EVERY:  # har xabarda yozmaslik uchun
                    u.last_seen = t
                return u
        except IntegrityError:
            continue
    return await get_user(uid)


async def get_user(uid: int) -> User | None:
    async with Session() as s:
        return await s.get(User, uid)


async def add_balance(uid: int, dollars: int = 0, diamonds: int = 0) -> None:
    async with Session.begin() as s:
        await s.execute(update(User).where(User.telegram_id == uid)
                        .values(dollars=User.dollars + dollars, diamonds=User.diamonds + diamonds))


async def claim_bonus(uid: int) -> bool:
    t = now()
    async with Session.begin() as s:
        r = await s.execute(update(User).where(
            User.telegram_id == uid,
            (User.last_bonus_at.is_(None)) | (User.last_bonus_at < t - timedelta(hours=24)),
        ).values(dollars=User.dollars + config.DAILY_BONUS, last_bonus_at=t))
        return r.rowcount == 1


async def exchange_diamond(uid: int) -> bool:
    async with Session.begin() as s:
        r = await s.execute(update(User).where(User.telegram_id == uid, User.diamonds >= 1)
                            .values(diamonds=User.diamonds - 1, dollars=User.dollars + config.DIAMOND_RATE))
        return r.rowcount == 1


async def rob_dollars(victim: int, thief: int) -> int:
    async with Session.begin() as s:
        u = await s.get(User, victim)
        amount = min(50, (u.dollars if u else 0) * 20 // 100)
        if amount:
            r = await s.execute(update(User).where(User.telegram_id == victim, User.dollars >= amount)
                                .values(dollars=User.dollars - amount))
            if r.rowcount != 1:
                return 0
            await s.execute(update(User).where(User.telegram_id == thief).values(dollars=User.dollars + amount))
        return amount


async def set_banned(uid: int, banned: bool) -> bool:
    async with Session.begin() as s:
        r = await s.execute(update(User).where(User.telegram_id == uid).values(banned=banned))
        return r.rowcount == 1


async def all_user_ids() -> list[int]:
    async with Session() as s:
        return list((await s.scalars(select(User.telegram_id).where(User.banned.is_(False)))).all())


async def top(chat_id: int | None = None, limit: int = 10) -> list[tuple[str, int, int]]:
    async with Session() as s:
        if chat_id is None:
            q = select(User.full_name, User.wins, User.games).order_by(User.wins.desc(), User.games).limit(limit)
        else:
            wins = func.sum(func.cast(GamePlayer.won, Integer))
            q = (select(User.full_name, wins, func.count()).join(User, User.telegram_id == GamePlayer.user_id)
                 .where(GamePlayer.chat_id == chat_id).group_by(User.full_name, User.telegram_id)
                 .order_by(wins.desc()).limit(limit))
        return [tuple(r) for r in (await s.execute(q)).all()]


async def stats() -> dict:
    async with Session() as s:
        one = lambda q: s.scalar(q)
        return {
            "users": await one(select(func.count()).select_from(User)),
            "groups": await one(select(func.count()).select_from(Group)),
            "games": await one(select(func.count()).select_from(GameRow)),
            "running": await one(select(func.count()).select_from(GameRow).where(GameRow.status == "running")),
        }


# ---------- buyumlar ----------
async def inventory(uid: int) -> list[Inventory]:
    async with Session() as s:
        return list((await s.scalars(select(Inventory).where(Inventory.user_id == uid, Inventory.qty > 0))).all())


async def _add_item(s, uid: int, item: str, n: int) -> None:
    """Atomar: qty = qty + n (manfiyga tushmaydi)."""
    r = await s.execute(update(Inventory).where(Inventory.user_id == uid, Inventory.item == item,
                                                Inventory.qty + n >= 0).values(qty=Inventory.qty + n))
    if r.rowcount == 0 and n > 0 and not await s.get(Inventory, (uid, item)):
        s.add(Inventory(user_id=uid, item=item, qty=n, enabled=True))
        await s.flush()


async def buy(uid: int, item: str) -> bool:
    if item not in config.SHOP or item in config.SHOP_OFF:
        return False
    price = config.SHOP[item]
    async with Session.begin() as s:
        r = await s.execute(update(User).where(User.telegram_id == uid, User.dollars >= price)
                            .values(dollars=User.dollars - price))
        if r.rowcount != 1:
            return False
        await _add_item(s, uid, item, 1)
        return True


async def change_item(uid: int, item: str, n: int) -> None:
    async with Session.begin() as s:
        await _add_item(s, uid, item, n)


async def toggle_item(uid: int, item: str) -> None:
    async with Session.begin() as s:
        inv = await s.get(Inventory, (uid, item))
        if inv:
            inv.enabled = not inv.enabled


async def game_items(uids: list[int]) -> dict[int, dict[str, int]]:
    async with Session() as s:
        rows = await s.scalars(select(Inventory).where(Inventory.user_id.in_(uids), Inventory.qty > 0,
                                                       Inventory.enabled.is_(True)))
        out: dict[int, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r.user_id, {})[r.item] = r.qty
        return out


# ---------- guruhlar ----------
async def group_settings(chat_id: int, title: str = "") -> dict:
    from sqlalchemy.exc import IntegrityError
    for _ in range(2):
        try:
            async with Session.begin() as s:
                g = await s.get(Group, chat_id)
                if not g:
                    g = Group(chat_id=chat_id, title=title[:256], settings={})
                    s.add(g)
                elif title and g.title != title:
                    g.title = title[:256]
                return {**config.DEFAULT_SETTINGS, **(g.settings or {})}
        except IntegrityError:
            continue
    return dict(config.DEFAULT_SETTINGS)


async def save_group_settings(chat_id: int, settings: dict) -> None:
    async with Session.begin() as s:
        g = await s.get(Group, chat_id)
        g.settings = dict(settings)


# ---------- o'yinlar ----------
async def create_game(chat_id: int, state: dict) -> int | None:
    from sqlalchemy.exc import IntegrityError
    try:
        async with Session.begin() as s:
            row = GameRow(chat_id=chat_id, state=state, status="running")
            s.add(row)
            await s.flush()
            return row.id
    except IntegrityError:
        return None


async def save_game(game_id: int, state: dict) -> None:
    async with Session.begin() as s:
        await s.execute(update(GameRow).where(GameRow.id == game_id).values(state=state))


async def running_games() -> list[GameRow]:
    async with Session() as s:
        return list((await s.scalars(select(GameRow).where(GameRow.status == "running"))).all())


async def finish_game(game_id: int, chat_id: int, status: str, winner: str | None,
                      players: list[tuple[int, str, str, bool, bool]]) -> None:
    """players: (uid, role, team, alive, won). Mukofot faqat status == 'finished' bo'lsa."""
    async with Session.begin() as s:
        await s.execute(update(GameRow).where(GameRow.id == game_id)
                        .values(status=status, winner=winner, finished_at=now()))
        if status != "finished":
            return
        for uid, role, team, alive, won in players:
            s.add(GamePlayer(game_id=game_id, user_id=uid, chat_id=chat_id, role=role, team=team,
                             alive=alive, won=won))
            await s.execute(update(User).where(User.telegram_id == uid).values(
                games=User.games + 1, wins=User.wins + int(won),
                dollars=User.dollars + config.REWARD_PLAY + (config.REWARD_WIN if won else 0)))


# ============ ADMIN PANEL ============
class PanelAdmin(Base):
    """Paneldagi qo'shimcha adminlar. Bosh adminlar (ADMIN_IDS) bu yerda saqlanmaydi."""
    __tablename__ = "panel_admins"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # moderator / viewer
    added_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AdminLog(Base):
    __tablename__ = "admin_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[str] = mapped_column(String(512), default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[dict] = mapped_column(Json)


class Broadcast(Base):
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    audience: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    buttons: Mapped[list] = mapped_column(Json, default=list)
    photo: Mapped[bool] = mapped_column(Boolean, default=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/done/cancelled/interrupted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- sozlamalar (paneldan o'zgaradi, config'ga qo'llanadi) ----------
ECONOMY = {"reward_win": "REWARD_WIN", "reward_play": "REWARD_PLAY", "daily_bonus": "DAILY_BONUS",
           "ref_bonus": "REF_BONUS", "diamond_rate": "DIAMOND_RATE"}


def economy() -> dict:
    return {**{k: getattr(config, attr) for k, attr in ECONOMY.items()},
            "shop": dict(config.SHOP), "shop_off": sorted(config.SHOP_OFF)}


def _apply(key: str, value) -> None:
    if key in ECONOMY:
        setattr(config, ECONOMY[key], int(value))
    elif key == "shop":
        config.SHOP.update({k: int(v) for k, v in value.items() if k in config.SHOP})  # joyida: importlar ko'radi
    elif key == "shop_off":
        config.SHOP_OFF.clear()
        config.SHOP_OFF.update(k for k in value if k in config.SHOP)


async def load_settings() -> None:
    async with Session() as s:
        for row in await s.scalars(select(Setting)):
            try:
                _apply(row.key, row.value["v"])
            except (KeyError, TypeError, ValueError, AttributeError):
                pass  # buzilgan qiymat: standart qoladi


async def save_settings(values: dict) -> None:
    async with Session.begin() as s:
        for key, v in values.items():
            row = await s.get(Setting, key)
            if row:
                row.value = {"v": v}
            else:
                s.add(Setting(key=key, value={"v": v}))
    for key, v in values.items():
        _apply(key, v)


# ---------- adminlar va jurnal ----------
ROLES_PANEL = ("moderator", "viewer")


async def panel_role(uid: int) -> str | None:
    if uid in config.ADMIN_IDS:
        return "owner"
    async with Session() as s:
        a = await s.get(PanelAdmin, uid)
        return a.role if a and a.role in ROLES_PANEL else None


async def list_admins() -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(select(PanelAdmin, User.full_name, User.username)
                                .outerjoin(User, User.telegram_id == PanelAdmin.user_id)
                                .order_by(PanelAdmin.created_at))).all()
        owners = {u.telegram_id: u for u in await s.scalars(
            select(User).where(User.telegram_id.in_(list(config.ADMIN_IDS))))}
    out = [{"id": uid, "name": owners[uid].full_name if uid in owners else "",
            "username": owners[uid].username if uid in owners else None, "role": "owner"}
           for uid in sorted(config.ADMIN_IDS)]
    out += [{"id": a.user_id, "name": name or "", "username": un, "role": a.role}
            for a, name, un in rows if a.user_id not in config.ADMIN_IDS]
    return out


async def set_admin(uid: int, role: str, by: int) -> None:
    async with Session.begin() as s:
        a = await s.get(PanelAdmin, uid)
        if a:
            a.role = role
        else:
            s.add(PanelAdmin(user_id=uid, role=role, added_by=by))


async def remove_admin(uid: int) -> bool:
    async with Session.begin() as s:
        return (await s.execute(delete(PanelAdmin).where(PanelAdmin.user_id == uid))).rowcount == 1


async def log_action(admin_id: int, action: str, target="", details: str = "") -> None:
    async with Session.begin() as s:
        s.add(AdminLog(admin_id=admin_id, action=action[:32], target=str(target)[:64], details=str(details)[:512]))


async def get_log(page: int, size: int = 30) -> tuple[list[dict], int]:
    async with Session() as s:
        total = await s.scalar(select(func.count()).select_from(AdminLog))
        rows = (await s.execute(select(AdminLog, User.full_name)
                                .outerjoin(User, User.telegram_id == AdminLog.admin_id)
                                .order_by(AdminLog.id.desc()).offset(page * size).limit(size))).all()
    return [{"id": r.id, "at": _aware(r.at).isoformat(), "admin_id": r.admin_id, "admin": name or str(r.admin_id),
             "action": r.action, "target": r.target, "details": r.details} for r, name in rows], total


# ---------- statistika ----------
async def dashboard(since: datetime | None, chart_from: datetime) -> dict:
    """since: davr boshi (None = hammasi). chart_from: grafik boshi."""
    async with Session() as s:
        async def cnt(model, *w):
            return int(await s.scalar(select(func.count()).select_from(model).where(*w)) or 0)

        users, groups = await cnt(User), await cnt(Group)
        fin = [GameRow.status == "finished"] + ([GameRow.started_at >= since] if since else [])
        res = {
            "users": users,
            "users_new": await cnt(User, User.created_at >= since) if since else users,
            "active": await cnt(User, User.last_seen >= (since or now() - timedelta(days=30))),
            "groups": groups,
            "groups_new": await cnt(Group, Group.created_at >= since) if since else groups,
            "games": await cnt(GameRow, *fin),
            "money": int(await s.scalar(select(func.coalesce(func.sum(User.dollars), 0))) or 0),
            "diamonds": int(await s.scalar(select(func.coalesce(func.sum(User.diamonds), 0))) or 0),
            "banned": await cnt(User, User.banned.is_(True)),
        }
        res["winners"] = {k or "": int(v) for k, v in (await s.execute(
            select(GameRow.winner, func.count()).where(*fin).group_by(GameRow.winner))).all()}
        dur_from = max(since or chart_from, now() - timedelta(days=30))
        dur = (await s.execute(select(GameRow.started_at, GameRow.finished_at).where(
            GameRow.status == "finished", GameRow.finished_at.is_not(None), GameRow.started_at >= dur_from)
            .limit(5000))).all()
        secs = [(_aware(b) - _aware(a)).total_seconds() for a, b in dur]
        res["avg_minutes"] = round(sum(secs) / len(secs) / 60) if secs else 0
        res["chart_games"] = [_aware(t) for t in await s.scalars(
            select(GameRow.started_at).where(GameRow.status == "finished", GameRow.started_at >= chart_from))]
        res["chart_users"] = [_aware(t) for t in await s.scalars(
            select(User.created_at).where(User.created_at >= chart_from))]
    return res


# ---------- foydalanuvchilar ----------
def _search(q: str, cols, id_col, signed: bool = False):
    """Matn qidiruvi (LIKE belgilari ekranlanadi) yoki aniq ID."""
    q = q.strip()
    esc = q.lstrip("@").lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cond = None
    for c in cols:
        part = func.lower(func.coalesce(c, "")).like(f"%{esc}%", escape="\\")
        cond = part if cond is None else cond | part
    digits = q.lstrip("-") if signed else q
    if digits.isdigit() and len(digits) < 19:
        cond = (id_col == int(q)) | cond
    return cond


async def users_page(q: str, filt: str, page: int, size: int = 20) -> tuple[list[User], int]:
    w = [_search(q, (User.full_name, User.username), User.telegram_id)] if q.strip() else []
    if filt == "active":
        w.append(User.last_seen >= now() - timedelta(days=7))
    elif filt == "banned":
        w.append(User.banned.is_(True))
    order = {"rich": User.dollars.desc(), "games": User.games.desc()}.get(filt, User.created_at.desc())
    async with Session() as s:
        total = int(await s.scalar(select(func.count()).select_from(User).where(*w)) or 0)
        rows = list((await s.scalars(select(User).where(*w).order_by(order, User.telegram_id)
                                     .offset(page * size).limit(size))).all())
    return rows, total


async def user_games(uid: int, limit: int = 10) -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(select(GamePlayer, GameRow.finished_at, Group.title)
                                .join(GameRow, GameRow.id == GamePlayer.game_id)
                                .outerjoin(Group, Group.chat_id == GamePlayer.chat_id)
                                .where(GamePlayer.user_id == uid).order_by(GamePlayer.game_id.desc())
                                .limit(limit))).all()
    return [{"game_id": p.game_id, "chat_id": p.chat_id, "group": title or str(p.chat_id), "role": p.role,
             "won": p.won, "alive": p.alive, "at": _aware(at).isoformat() if at else None} for p, at, title in rows]


async def change_balance(uid: int, currency: str, delta: int) -> int | None:
    """Atomar. Balans manfiyga tushadigan ayirish rad etiladi. Yangi qiymat yoki None."""
    col = {"dollars": User.dollars, "diamonds": User.diamonds}[currency]
    async with Session.begin() as s:
        r = await s.execute(update(User).where(User.telegram_id == uid, col + delta >= 0)
                            .values({currency: col + delta}))
        if r.rowcount != 1:
            return None
        return int(await s.scalar(select(col).where(User.telegram_id == uid)))


async def item_qty(uid: int, item: str, delta: int) -> int:
    async with Session.begin() as s:
        await _add_item(s, uid, item, delta)
        return int(await s.scalar(select(Inventory.qty).where(Inventory.user_id == uid, Inventory.item == item))
                   or 0)


# ---------- guruhlar ----------
async def groups_page(q: str, sort: str, page: int, size: int = 20) -> tuple[list[dict], int]:
    week = now() - timedelta(days=7)
    wk = func.sum(case((GameRow.started_at >= week, 1), else_=0))
    stats_q = (select(GameRow.chat_id, func.count().label("total"), wk.label("week"))
               .where(GameRow.status == "finished").group_by(GameRow.chat_id).subquery())
    w = [_search(q, (Group.title,), Group.chat_id, signed=True)] if q.strip() else []
    total_c, week_c = func.coalesce(stats_q.c.total, 0), func.coalesce(stats_q.c.week, 0)
    order = {"total": total_c.desc(), "new": Group.created_at.desc()}.get(sort, week_c.desc())
    async with Session() as s:
        total = int(await s.scalar(select(func.count()).select_from(Group).where(*w)) or 0)
        rows = (await s.execute(select(Group, total_c, week_c).outerjoin(stats_q, stats_q.c.chat_id == Group.chat_id)
                                .where(*w).order_by(order, Group.chat_id).offset(page * size).limit(size))).all()
    return [{"chat_id": g.chat_id, "title": g.title, "total": int(t or 0), "week": int(wv or 0),
             "created_at": _aware(g.created_at).isoformat(),
             "settings": {**config.DEFAULT_SETTINGS, **(g.settings or {})}} for g, t, wv in rows], total


async def group_ids() -> list[int]:
    async with Session() as s:
        return list((await s.scalars(select(Group.chat_id))).all())


async def active_user_ids(days: int = 7) -> list[int]:
    async with Session() as s:
        return list((await s.scalars(select(User.telegram_id).where(
            User.banned.is_(False), User.last_seen >= now() - timedelta(days=days)))).all())


async def count_active(days: int = 7) -> int:
    async with Session() as s:
        return int(await s.scalar(select(func.count()).select_from(User).where(
            User.banned.is_(False), User.last_seen >= now() - timedelta(days=days))) or 0)


async def count_users() -> int:
    async with Session() as s:
        return int(await s.scalar(select(func.count()).select_from(User).where(User.banned.is_(False))) or 0)


async def group_exists(chat_id: int) -> bool:
    async with Session() as s:
        return await s.get(Group, chat_id) is not None


# ---------- e'lonlar ----------
async def create_broadcast(admin_id: int, audience: str, text_: str, buttons: list, photo: bool, total: int) -> int:
    async with Session.begin() as s:
        b = Broadcast(admin_id=admin_id, audience=audience, text=text_, buttons=buttons, photo=photo, total=total)
        s.add(b)
        await s.flush()
        return b.id


async def update_broadcast(bid: int, **values) -> None:
    async with Session.begin() as s:
        await s.execute(update(Broadcast).where(Broadcast.id == bid).values(**values))


async def broadcasts(limit: int = 20) -> list[Broadcast]:
    async with Session() as s:
        return list((await s.scalars(select(Broadcast).order_by(Broadcast.id.desc()).limit(limit))).all())


async def interrupt_broadcasts() -> None:
    """Bot qayta ishga tushganda yarim qolgan e'lonlar."""
    async with Session.begin() as s:
        await s.execute(update(Broadcast).where(Broadcast.status == "running")
                        .values(status="interrupted", finished_at=now()))
