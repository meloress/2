"""Mafia Zone premium emoji to'plamini yasash va Telegramga yuklash (/emojipack, bot egasi).

Har emoji: 100x100 PNG nishon - jamoa rangidagi gradient doira, oltin halqa, markazda Twemoji belgisi.
Twemoji (c) Twitter/jdecked, CC-BY 4.0: https://github.com/jdecked/twemoji
"""
import io
import logging
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .emoji import CATALOG, norm
from .engine.roles import ACTION_LABELS, MAFIA, NEUTRAL, ROLES, TOWN

log = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent / "assets" / "twemoji"
TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{}.png"
SIZE, SS = 100, 4  # yakuniy o'lcham, supersampling

TEAM_COLOR = {TOWN: (37, 99, 235), MAFIA: (200, 30, 45), NEUTRAL: (124, 58, 237)}
STYLE_COLOR = {"danger": (200, 30, 45), "success": (22, 163, 74), "primary": (37, 99, 235)}
UI_COLOR = (32, 32, 40)
RING = (245, 196, 81)


def _codes(ch: str, keep_fe0f: bool) -> str:
    return "-".join(f"{ord(c):x}" for c in ch if keep_fe0f or c != "️")


def glyph(ch: str) -> Image.Image | None:
    """Twemoji PNG (keshlanadi). Fayl nomida fe0f ba'zan bor, ba'zan yo'q - ikkalasini sinaymiz."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for name in dict.fromkeys([_codes(ch, False), _codes(ch, True)]):
        path = CACHE / f"{name}.png"
        if not path.exists():
            try:
                with urllib.request.urlopen(TWEMOJI.format(name), timeout=15) as r:
                    path.write_bytes(r.read())
            except Exception:
                continue
        return Image.open(path).convert("RGBA")
    return None


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def badge(g: Image.Image, color: tuple) -> bytes:
    s = SIZE * SS
    bg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    r0 = s // 2 - 2 * SS
    light, dark = _mix(color, (255, 255, 255), 0.35), _mix(color, (0, 0, 0), 0.45)
    for r in range(r0, 0, -SS):  # markazi yorug', cheti to'q gradient
        d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=_mix(light, dark, r / r0) + (255,))
    d.ellipse([2 * SS, 2 * SS, s - 2 * SS, s - 2 * SS], outline=RING + (255,), width=5 * SS)
    img = bg.resize((SIZE, SIZE), Image.LANCZOS)

    gs = 62
    g = g.resize((gs, gs), Image.LANCZOS)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 160), ((SIZE - gs) // 2 + 2, (SIZE - gs) // 2 + 3), g.split()[3])
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(2.5)))
    img.alpha_composite(g, ((SIZE - gs) // 2, (SIZE - gs) // 2))
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def color_for(ch: str) -> tuple:
    from .runner import kind_style
    for r in ROLES.values():
        if norm(r.name.split(" ", 1)[0]) == norm(ch):
            return TEAM_COLOR[r.team]
    for k, label in ACTION_LABELS.items():
        if norm(label.split(" ", 1)[0]) == norm(ch):
            return STYLE_COLOR[kind_style(k)]
    return UI_COLOR


def build() -> list[tuple[str, bytes]]:
    """[(oddiy emoji, png)] - Twemoji topilmaganlar tashlab ketiladi."""
    out = []
    for ch, _ in CATALOG:
        g = glyph(ch)
        if g is None:
            log.warning("twemoji topilmadi: %r", ch)
            continue
        out.append((ch, badge(g, color_for(ch))))
    return out


def pack_name(bot_username: str) -> str:
    return f"mafiazone_by_{bot_username}"


async def upload(bot, owner_id: int, bot_username: str) -> dict[str, str]:
    """To'plamni (qayta) yaratadi va {oddiy emoji: custom_emoji_id} qaytaradi."""
    from aiogram.types import BufferedInputFile, InputSticker

    icons = build()
    name = pack_name(bot_username)
    try:
        await bot.delete_sticker_set(name)  # qayta yaratish: eski to'plam o'chadi
    except Exception:
        pass
    sticker = lambda i, ch, png: InputSticker(sticker=BufferedInputFile(png, f"e{i}.png"), format="static",
                                              emoji_list=[ch])
    first = [sticker(i, ch, png) for i, (ch, png) in enumerate(icons[:50])]
    await bot.create_new_sticker_set(user_id=owner_id, name=name, title="Mafia Zone", stickers=first,
                                     sticker_type="custom_emoji")
    for i, (ch, png) in enumerate(icons[50:], 50):
        await bot.add_sticker_to_set(user_id=owner_id, name=name, sticker=sticker(i, ch, png))
    st = await bot.get_sticker_set(name)
    return {norm(ch): s.custom_emoji_id for (ch, _), s in zip(icons, st.stickers)}
