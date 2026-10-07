"""PostgreSQL (lokalda SQLite) modellari va so'rovlar. Balans o'zgarishlari atomar UPDATE bilan."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Index, Integer, String, delete, func, select, text,
                        update)
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


async def init() -> None:
    # ponytail: create_all; sxema birinchi marta o'zgarganda Alembic qo'shiladi
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)


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
