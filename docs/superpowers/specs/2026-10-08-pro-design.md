# PRO tarif — dizayn

Sana: 2026-10-08. Holat: foydalanuvchi bilan kelishilgan.

## Maqsad

Pullik PRO obuna: o'yinchiga obro' (hamma ko'radigan belgi), qulaylik va iqtisodiy ustunlik beradi,
lekin o'yinda kuch bermaydi (rol bilish, o'lmaslik, ikki ovoz — yo'q).

## Belgi

- Ko'rinishi: `[✅ custom emoji 5197557379083804570] <b>PRO</b> <ism-havola>`.
  Zaxira belgi `✅` (custom emoji rad etilsa).
- Ism: PRO faol bo'lsa `nickname` (bo'lsa), aks holda Telegram ismi.
- Tugmalarda: `icon_custom_emoji_id = 5197557379083804570`, matn `PRO <ism>`.
- Joylar: lobbi, tiriklar ro'yxati, ovoz lentasi, ovoz/tun tugmalari, tungi voqealar, osish,
  o'yin oxiri, reyting, tarqatma, para xabarlari, profil.
- Profil: sarlavha `✅ 𝐏𝐑𝐎 · Admiral Mafia`, qator `PRO: <sana>gacha (N kun)`.

## Imkoniyatlar

| Imkoniyat | Qoida |
|---|---|
| Belgi | yuqoridagi joylarda |
| `/nickname <ism>` | 2–20 belgi; `@`, havola (`http`, `t.me`, `www.`), "admin", "bot" so'zlari taqiqlangan; PRO tugasa ko'rinmaydi; `/nickname` bo'sh — o'chiradi; panel admini o'chira oladi |
| O'yinda bo'lmasa ham yozish | faqat DAY/VOTING/CONFIRM; tunda yo'q; o'lgan o'yinchiga yo'q |
| Chiqish limiti | kuniga 5 bepul (oddiylarga 3) |
| G'alaba puli | x1.5 |
| Do'kon | -25% (narx ko'rsatiladi: eski chizilgan, yangi qalin) |
| Eslatma | tugashidan ~24 soat oldin shaxsiy xabar (bir marta) |

## Sotib olish

- Kirish: `/pro`, `/start` menyusida "PRO" tugmasi, profilda tugma.
- Paketlar: 7 kun — 30 💎 / 100 ⭐; 15 kun — 55 💎 / 150 ⭐; 30 kun — 99 💎 / 249 ⭐.
- Olmos: atomar `diamonds >= narx` yechish + muddat uzaytirish (bitta tranzaksiya).
- Stars: `send_invoice(currency="XTR", provider_token="")`, payload `pro:<kun>`;
  `pre_checkout_query` → payload tekshiriladi; `successful_payment` → `telegram_payment_charge_id`
  bo'yicha bir marta hisoblanadi (unique).
- Muddat: `pro_until = max(now, pro_until) + kun`.
- Panel: foydalanuvchi sahifasida PRO holati; owner PRO beradi/oladi (kun bilan), nickname o'chiradi.
  Har biri `admin_log` ga.

## Ma'lumotlar

- `users.pro_until TIMESTAMPTZ NULL`, `users.nickname VARCHAR(32) NULL`, `users.pro_reminded BOOLEAN` (COLUMNS migratsiyasi).
- `payments(id, user_id, method 'stars'|'diamonds'|'admin', days, amount, charge_id UNIQUE NULL, created_at)`.
- `Player.pro: bool = False` (o'yin holati JSON; eski holatlar default bilan o'qiladi).
- Lobbi a'zolari: Runner `pro` to'plami (uid), ism — ko'rsatiladigan ism.

## Custom emoji xavfsizligi

`emoji.py`: matnga qo'yilgan `<tg-emoji>` Telegram rad etsa, middleware qayta yuborishda
`<tg-emoji ...>X</tg-emoji>` → `X` qilib tozalaydi (zaxira ✅). Tugmadagi `icon_custom_emoji_id` ham olib tashlanadi.

## Testlar

Stars to'lovi (bir marta hisoblanishi), olmos bilan olish, muddat qo'shilishi, x1.5, -25%,
nickname qoidalari, kunduzi yozish/tunda yo'q, belgi hamma joyda, eslatma bir marta, migratsiya.
