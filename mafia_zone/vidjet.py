"""Olmos to'lovi kartasi — Telegram vidjeti (Bot API 10.4, `sendWidget`).

Karta faqat KO'RSATADI: raqamlar, summa, taymer, holat. Tugmalar (nusxa, bekor,
orqaga) xabar ostida qoladi, holat esa botdan keladi (`editMessageWidgetData`):
chek keldi → "t", tasdiq → "a", rad → "r", bekor → "b". Vaqt tugashini karta
o'zi hisoblaydi ("e"). Vidjet chiqmasa (eski ilova, rad) — oddiy matnli ekran.

⚠️ Chegaralar (Telegram): HTML siqilganda (zlib) 4 KB, `chat_data` 1 KB,
balandlik 600 px. `opacity`/`filter` yo'q (vidjet ularni "og'ir" deb sanaydi),
matn faqat `textContent` (ism va bank nomi — paneldan, ishonchsiz).
aiogram 3.31 bu usullarni bilmaydi — o'zimizning `TelegramMethod`.
"""
import json
import logging
import time
from typing import Any

from aiogram.methods.base import TelegramMethod
from aiogram.types import InlineKeyboardMarkup

from . import config

log = logging.getLogger(__name__)

_CSS = """
body{margin:0;padding:10px;font-family:system-ui,sans-serif}
.hd{padding:13px 16px;border-radius:18px;color:#fff;background:radial-gradient(140% 170% at 0 0,#5a0c1c 0,#22060c 55%,#0b0204 100%);box-shadow:inset 0 0 0 1px #d4a64a55}
.vk{font-size:.62em;font-weight:800;letter-spacing:.26em;color:#d4a64a}
.wm{font-size:1.1em;font-weight:800;letter-spacing:.08em;white-space:nowrap;margin-top:2px}
.st{font-size:.8em;color:#e9c9c9;margin-top:3px}
.sg{display:flex;gap:4px;margin-top:8px;padding:4px;border-radius:14px;background:var(--tg-theme-secondary-bg-color)}
.sg button{flex:1;border:0;border-radius:10px;padding:9px 4px;font:600 .84em system-ui,sans-serif;color:var(--tg-theme-text-color);background:none}
.sg .on{color:#1a0a0d;background:linear-gradient(90deg,#f3d27a,#d4a64a)}
.bc{margin-top:8px;padding:12px 16px 11px;border-radius:18px;color:#fff;background:linear-gradient(135deg,#7a0f24,#2a070e 62%,#120306);box-shadow:inset 0 0 0 1px #d4a64a66}
.bt{display:flex;justify-content:space-between;gap:8px;font-size:.64em;font-weight:800;letter-spacing:.18em;color:#f3d27a}
.bt span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bn{font-size:1.3em;font-weight:600;letter-spacing:.07em;margin:12px 0 8px;font-variant-numeric:tabular-nums;white-space:nowrap}
.bo{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:.82em;color:#f1dcdc;margin-top:6px}
.bo span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cp{flex:none;border:0;border-radius:10px;padding:6px 11px;font:600 .8em system-ui,sans-serif;color:#fff;background:#ffffff2e}
.cp.l{color:#1a0a0d;background:linear-gradient(90deg,#f3d27a,#d4a64a)}
.yo{margin:8px 4px 0;font-size:.78em;line-height:1.4;color:var(--tg-theme-hint-color)}
.sm{display:flex;align-items:center;gap:10px;margin-top:8px;padding:10px 14px;border-radius:16px;background:var(--tg-theme-secondary-bg-color)}
.sm div{flex:1;min-width:0}
.sm small{display:block;font-size:.76em;color:var(--tg-theme-hint-color)}
.sm b{font-size:1.42em;font-variant-numeric:tabular-nums;white-space:nowrap}
.sp{display:flex;gap:4px;margin:12px 2px 0}
.sp div{flex:1;text-align:center;font-size:.7em;color:var(--tg-theme-hint-color)}
.sp u{display:block;height:5px;border-radius:3px;margin-bottom:6px;background:var(--tg-theme-secondary-bg-color)}
.sp .ok u{background:#d4a64a}
.sp .on u{background:linear-gradient(90deg,#b3122e,#f3d27a);transform-origin:left;animation:pl 1s ease-in-out infinite alternate}
.sp .er u{background:#e5484d}
.sp .ok,.sp .on,.sp .er{color:inherit;font-weight:600}
@keyframes pl{from{transform:scaleX(.35)}to{transform:scaleX(1)}}
.zt{margin:10px 4px 2px;font-size:.88em;font-weight:600;text-align:center}
.sg button:active,.cp:active{transform:scale(.97)}
.tt{position:fixed;left:10px;right:10px;bottom:10px;padding:10px 12px;border-radius:12px;font-size:.84em;text-align:center;color:#fff;background:#2a070e;box-shadow:0 0 0 1px #d4a64a;transform:translateY(170%);transition:transform .3s}
.tt.on{transform:none}
@media (max-width:340px){.bn{font-size:1.1em;letter-spacing:.03em}.hd{padding:11px 13px}.wm{font-size:1em}.sm b{font-size:1.22em}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""

# Holat (`holat()`): id "TOP-n", d olmos, g sovg'a nomi, s/sf summa, h holat,
# x tugash vaqti (unix), z rad sababi, u/v — O'zbekiston / chet el kartasi:
# {n raqam, nf guruhlangan, o egasi, b yuqori yozuv (bank · turi), t/tf telefon}.
_JS = """
var W=window.TelegramWidget,D,Y,Z,a=document.getElementById("a");
function p(s){try{return JSON.parse(s)}catch(e){return null}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function z(n){return(n<10?"0":"")+n}
function tt(s){var t=document.getElementById("tt");if(!t){t=el("div","tt");t.id="tt";document.body.appendChild(t)}
t.textContent=s;t.className="tt on";clearTimeout(t.k);t.k=setTimeout(function(){t.className="tt"},3600)}
function hp(){try{if(W.HapticFeedback)W.HapticFeedback.selectionChanged()}catch(e){}}
function cp(x,b){try{W.copyText(String(x));b.textContent="✓ Nusxa";if(W.HapticFeedback)W.HapticFeedback.notificationOccurred("success")}catch(e){tt(String(x))}}
function bt(x,c){var b=el("button","cp"+(c?" "+c:""),"📋 Nusxa");b.onclick=function(){cp(x,b)};return b}
function ql(){var k=D.h,s=Math.round(D.x-Date.now()/1e3);if(k=="k"&&s<=0)k="e";
if(k=="k")return"⏱ "+Math.floor(s/60)+":"+z(s%60)+" ichida to'lang va chekni shu chatga yuboring";
return{t:"⏳ Chek tekshirilmoqda — admin tasdiqlagach olmos tushadi",a:"💎 "+D.d+" olmos hisobga tushdi!",r:"❌ Tasdiqlanmadi: "+(D.z||"")+". Xato bo'lsa — adminga yozing",b:"✖️ Buyurtma bekor qilindi",e:"⌛️ Vaqt tugadi. To'lagan bo'lsangiz — chek bilan adminga yozing"}[k]||""}
function r(){a.innerHTML="";var h=D.h,f=h=="k"&&D.x>Date.now()/1e3,K=D[Y],c=el("div","bc"),t=el("div","bt");
document.getElementById("st").textContent="💎 "+D.d+" olmos"+(D.g?" → 🎁 "+D.g:"")+" · buyurtma №"+D.id.split("-")[1];
if(f&&D.u&&D.v){var g=el("div","sg");[["u","🇺🇿 O'zbekistondan"],["v","🌍 Chet eldan"]].forEach(function(q){var b=el("button",Y==q[0]?"on":0,q[1]);b.onclick=function(){if(Y!=q[0]){Y=q[0];hp();r()}};g.appendChild(b)});a.appendChild(g)}
t.appendChild(el("span",0,K.b||"BANK KARTASI"));t.appendChild(el("span",0,"ADMIRAL"));c.appendChild(t);c.appendChild(el("div","bn",K.nf));
var o=el("div","bo");o.appendChild(el("span",0,K.o||""));if(f)o.appendChild(bt(K.n));c.appendChild(o);
if(K.t){o=el("div","bo");o.appendChild(el("span",0,"📱 "+K.tf));if(f)o.appendChild(bt(K.t));c.appendChild(o)}a.appendChild(c);
if(f&&Y=="v")a.appendChild(el("div","yo","Bank ilovasida: «O'zbekistonga o'tkazma» → karta raqami."+(K.t?" Telefon so'ralsa — yuqoridagini yozing.":"")));
var m=el("div","sm"),d=el("div");d.appendChild(el("small",0,f?"Aynan shu summani o'tkazing":"Summa"));d.appendChild(el("b",0,D.sf+" so'm"));m.appendChild(d);if(f)m.appendChild(bt(D.s,"l"));a.appendChild(m);
var i={k:0,r:1,t:2,a:4}[h],s=el("div","sp");if(i==null)i=-1;
["To'lang","Chek","Tekshiruv","💎 Olmos"].forEach(function(x,j){var q=el("div",j<i?"ok":j==i?(h=="r"?"er":"on"):"");q.appendChild(el("u"));q.appendChild(document.createTextNode(x));s.appendChild(q)});
a.appendChild(s);Z=el("div","zt",ql());a.appendChild(Z)}
function R(){var x=p(W&&W.chatData);if(x&&x.id){D=x;if(!Y||!D[Y])Y=D.u?"u":"v";r()}}
R();if(W&&W.onEvent)W.onEvent("chatDataChanged",R);
setInterval(function(){if(D){if(D.h=="k"&&D.x<=Date.now()/1e3&&!D.E){D.E=1;r()}else if(Z)Z.textContent=ql()}},1000);
"""

HTML = ("<style>" + _CSS + "</style>"
        '<div class="hd"><div class="vk">ADMIRAL MAFIA</div><div class="wm">OLMOS TO\'LOVI</div>'
        '<div class="st" id="st"></div></div><div id="a"></div><script>' + _JS + "</script>")

STATES = {"new": "k", "paid": "t", "approved": "a", "rejected": "r", "cancelled": "b", "expired": "e"}


def _group(n: str, k: int = 4) -> str:
    return " ".join(n[i:i + k] for i in range(0, len(n), k))


def _phone(t: str) -> str:
    """+998901234567 -> +998 90 123 45 67 (O'zbekiston); boshqasi - o'zgarishsiz."""
    if t.startswith("+998") and len(t) == 13:
        return f"{t[:4]} {t[4:6]} {t[6:9]} {t[9:11]} {t[11:]}"
    return t


def _card(c: dict) -> dict:
    top = " · ".join(x for x in (c.get("b", ""), c.get("k", "")) if x).upper()
    d = {"n": c["n"], "nf": _group(c["n"]), "o": c.get("o", ""), "b": top}
    if c.get("t"):
        d["t"], d["tf"] = c["t"], _phone(c["t"])
    return d


def holat(o, target: str | None = None, reason: str = "") -> dict:
    """Kartaning `chat_data` si. o - CardOrder; target - sovg'a oluvchi (oddiy matn)."""
    from .texts import order_no, som
    cards = config.cards()
    d = {"id": order_no(o.id), "d": o.diamonds, "s": o.amount, "sf": som(o.amount),
         "h": STATES.get(o.status, "k"), "x": int(_ts(o.created_at)) + config.CARD_ORDER_MIN * 60}
    for slot, key in (("uz", "u"), ("xorij", "v")):
        if slot in cards:
            d[key] = _card(cards[slot])
    if target:
        d["g"] = target
    if reason:
        d["z"] = reason
    return d


def _ts(dt) -> float:
    from .db import _aware
    return _aware(dt).timestamp() if dt else time.time()


def dumps(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


class SendWidget(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "sendWidget"
    chat_id: int
    html: str
    chat_data: str
    caption: str | None = None
    parse_mode: str | None = None
    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageWidgetData(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "editMessageWidgetData"
    chat_id: int
    message_id: int
    chat_data: str


async def send(bot, chat_id: int, d: dict, caption: str, kb: InlineKeyboardMarkup | None) -> int | None:
    """Kartani yuboradi; xabar id'si yoki None (chaqiruvchi oddiy matnni yuboradi)."""
    try:
        r = await bot(SendWidget(chat_id=chat_id, html=HTML, chat_data=dumps(d), caption=caption,
                                 parse_mode="HTML", reply_markup=kb))
    except Exception as e:  # eski server, rad etilgan HTML, bot yo'q (testda) - matnli ekran
        log.info("to'lov kartasi yuborilmadi: %s", e)
        return None
    mid = r.get("message_id") if isinstance(r, dict) else getattr(r, "message_id", None)
    return mid if isinstance(mid, int) else None


async def update(bot, chat_id: int, message_id: int | None, d: dict) -> bool:
    """Karta holatini almashtiradi (karta o'zi qayta chiziladi). Bezak: xato — jim."""
    if not message_id:
        return False
    try:
        await bot(EditMessageWidgetData(chat_id=chat_id, message_id=message_id, chat_data=dumps(d)))
        return True
    except Exception as e:
        log.info("to'lov kartasi yangilanmadi: %s", e)
        return False
