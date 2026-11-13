# 🛡 Guruh moderatsiyasi — reja

## Maqsad
Admiral Mafia faqat o'yin emas, guruhni boshqaradigan universal bot bo'lsin: adminlar bitta bot bilan mute/ban qiladi, reklama va so'kinish avtomatik tozalanadi, qoidabuzarlar ogohlantiriladi.

**Tanlangan funksiyalar (egasi, 2026-11-12):**
1. Moderatsiya buyruqlari (`.mute`, `.ban` ...)
2. Reklama tozalash
3. So'kinish → avtomatik 30 daqiqa mute
4. Ogohlantirish (warn): 3 ta → ban
5. `/report`
6. `/settings` da "🛡 Moderatsiya" bo'limi

**Shart:** bot guruhda admin bo'lishi va 3 ta huquqi bo'lishi kerak: *xabarlarni o'chirish*, *foydalanuvchilarni cheklash*, *foydalanuvchilarni bloklash*. Huquq yetishmasa, bot buni aytadi (pastda).

---

## 1. Moderatsiya buyruqlari

Xabarga **reply** qilib yoziladi. Nuqta bilan ham, slesh bilan ham ishlaydi: `.mute` = `/mute`.

| Buyruq | Nima qiladi |
|---|---|
| `.mute 30m sabab` | Yozolmaydi. Muddat: `10m`, `2h`, `1d`, `7d`; yozilmasa — **1 soat**. Sabab ixtiyoriy |
| `.unmute` | Mute olib tashlanadi |
| `.ban sabab` | Guruhdan chiqariladi va qaytib kira olmaydi |
| `.unban` | Ban olib tashlanadi (qaytib kira oladi) |
| `.kick` | Chiqarib yuboriladi, lekin qaytib kira oladi |
| `.warn sabab` | Ogohlantirish (4-bo'lim) |
| `.unwarn` | Oxirgi ogohlantirish olib tashlanadi |
| `.warns` | Shu odamning ogohlantirishlari soni |

- **Kim ishlata oladi:** guruh adminlari (Telegram'da "foydalanuvchilarni cheklash" huquqi borlar) va bot egalari. Oddiy a'zo yozsa — buyruq o'chiriladi, javob faqat unga ko'rinadi: "⚠️ Bu buyruq faqat adminlar uchun".
- **Kimga ishlatib bo'lmaydi:** guruh adminlariga, bot egalariga, botning o'ziga — "⚠️ Adminni jazolab bo'lmaydi".
- Reply qilinmasa — faqat yozganga: "Xabarga reply qilib yozing: `.mute 30m sabab`".
- Buyruq xabari o'chiriladi; natija guruhga **hammaga ko'rinadi**:
  ```
  🔇 Ali 30 daqiqaga mute qilindi.
  Sabab: haqorat · Admin: Vali
  ```
  ```
  🚫 Ali guruhdan ban qilindi.
  Sabab: reklama · Admin: Vali
  ```
- Mute muddati Telegram'ning o'zida qo'yiladi (`until_date`) — bot o'chib-yonsa ham muddat tugagach o'zi ochiladi.
- Telegram 30 soniyadan qisqa yoki 366 kundan uzun mute'ni "abadiy" deb biladi — shuning uchun chegara **1 daqiqa … 365 kun**.

## 2. Reklama tozalash

Yoqilgan guruhda quyidagilar **o'chiriladi**:
- havolalar: `t.me/...`, `telegram.me/...`, `http(s)://...`, `www....`, matn ichiga yashirilgan havolalar;
- boshqa kanal/guruh/botning `@username`'i (oddiy odamning @username'i — **mumkin**);
- kanaldan forward qilingan xabarlar;
- tugmali (inline button) xabarlar (reklama botlari).

**Mustasno (o'chirilmaydi):** guruh adminlari va bot egalari, guruhning o'z havolasi/`@username`'i, Admiral Mafia bot havolalari, guruhga bog'langan kanal postlari.

**Jazo:** o'chiriladi + **1 ta ogohlantirish** (4-bo'lim) → 3-sida ban. Guruhga:
```
🧹 Ali, reklama mumkin emas — xabar o'chirildi. Ogohlantirish: 1/3
```

## 3. So'kinish → 30 daqiqa mute

Yoqilgan guruhda so'kinish bo'lgan xabar **o'chiriladi** va yozgan odam **darhol 30 daqiqa mute** bo'ladi (egasining talabi). Guruhga:
```
🔇 Ali so'kingani uchun 30 daqiqa mute qilindi.
```
- **Lug'at:** o'zbekcha (lotin + kirill) va ruscha so'kinishlar — boshlang'ich ro'yxat kodda, egasi paneldan **qo'shadi/olib tashlaydi** (repo ochiq — qo'shimchalar faqat bazada).
- **Yashirib yozishni ham tutadi:** katta-kichik harf, lotin↔kirill, raqam o'rniga harf (`0→o`, `1→i`, `3→e`, `4→a`...), cho'zish (`ahmoooq`), orasiga belgi (`a.h.m.o.q`, `a h m o q`).
- So'z **butun so'z sifatida** tekshiriladi — boshqa so'z ichida kelsa (masalan "**sik**l" ichidagi) xato ushlanmaydi; shubhali so'zlar ro'yxatga qo'shilmaydi.
- Adminlar va bot egalari jazolanmaydi (xabar o'chiriladi, mute yo'q).
- So'kinish **ogohlantirish bermaydi** — to'g'ridan-to'g'ri mute (qayta so'kinsa yana 30 daqiqa).
- O'yin paytida ham ishlaydi (o'liklar chati, so'nggi so'z — guruhga botning o'zi yuboradi, ular tekshirilmaydi).

## 4. Ogohlantirish (warn)

- Manba: `.warn` (admin) va reklama (avtomatik).
- **3 ta ogohlantirish → ban** (egasining talabi), ogohlantirishlar nolga tushadi.
  ```
  ⚠️ Ali ogohlantirildi (2/3). Sabab: spam · Admin: Vali
  🚫 Ali 3 ta ogohlantirish oldi va guruhdan ban qilindi.
  ```
- Har bir guruhda alohida hisoblanadi.
- **Mening qarorim:** ogohlantirish **30 kundan keyin o'z-o'zidan o'chadi** (bir yil oldingi xato uchun ban bo'lmasin). Egasi xohlasa — muddatsiz.
- `.unwarn` — oxirgisini olib tashlaydi; `.warns` — nechta ekanini ko'rsatadi.

## 5. `/report`

- Har qanday a'zo qoidabuzar xabarga reply qilib `/report sabab` yozadi.
- Buyruq o'chiriladi; yozganga (faqat unga ko'rinadi): "✅ Adminlarga yuborildi".
- Guruh adminlariga **shaxsiy chatda** (botni ochgan bo'lsa): kim, kimni, sabab, xabar matni va **"Xabarga o'tish"** havolasi; ostida tugmalar: `🔇 Mute 30m` · `🚫 Ban` · `🗑 O'chirish` · `✅ Hammasi joyida`. Bitta admin bossa — boshqalarniki "allaqachon ko'rib chiqildi" bo'ladi.
- Spamga qarshi: bir odam 5 daqiqada ko'pi bilan 1 ta report.

## 6. `.info` — odam haqida ma'lumot (egasi, 2026-11-12)

Reply qilib `.info` (yoki reply'siz — o'zi haqida). **Hamma** ishlata oladi; javob guruhga **hammaga ko'rinadi**:
```
ℹ️ Ma'lumot: Ali
🆔 ID: 123456789 · @ali_uz
👤 Holati: a'zo / admin / 🔇 mute (14:30 gacha)
⚠️ Ogohlantirish: 1/3 (oxirgisi: reklama, 2 kun oldin)
📅 Guruhga qo'shilgan: 2026-10-14
🎮 Shu guruhda: 120 o'yin, 48 g'alaba
```
- **Qo'shilgan sana:** Telegram botlarga buni bermaydi — bot o'zi yozib boradi (yangi a'zo kirganda). Bot bu funksiyadan **oldin** guruhda bo'lgan a'zolar uchun: "ma'lum emas" o'rniga botning ma'lumotidagi **eng birinchi o'yini yoki xabari** sanasi ("📅 Botda birinchi ko'rilgan: ..."). Sanalar o'tgan sari aniqlashadi.
- Holat (a'zo/admin/mute/ban) — Telegram'dan shu payt so'raladi.

## 7. `.admins` — adminlarni chaqirish (egasi, 2026-11-12)

Har qanday a'zo `.admins` yozadi (biror xabarga reply qilib — "shu xabarga qarang" ma'nosida — yoki reply'siz).
- **Guruhga bitta xabar** — barcha adminlar **metka** qilinadi (ism bosiladigan, Telegram ularga bildirishnoma yuboradi):
  ```
  📣 Adminlar chaqirildi! Chaqirgan: Ali
  👮 Vali, Gani, Olim
  ```
  Reply bilan chaqirilsa — shu xabar o'sha xabarga javob sifatida chiqadi.
- **Har bir adminga shaxsiy chatda** (botni ochgan bo'lsa) ogohlantirish: "📣 «Guruh nomi» guruhida Ali adminlarni chaqirdi" + **"Xabarga o'tish"** tugmasi.
- Botlar va yashirin (anonim) adminlar metka qilinmaydi (Telegram ularni belgilashga ruxsat bermaydi).
- **Spamga qarshi:** bir odam bir guruhda **5 daqiqada 1 marta**; ortig'i — faqat unga ko'rinadigan "⏳ Adminlar yaqinda chaqirilgan" javobi.

## 8. `/settings` → 🛡 Moderatsiya

`/settings` ga yangi tugma; ichida (faqat adminga ko'rinadi, hozirgi sozlamalar kabi):
```
🛡 Moderatsiya

🔗 Reklama tozalash: ✅
🤬 So'kinish → mute: ✅
⏱ So'kinish muddati: 30 daqiqa   [➖] [➕]
⚠️ Warn → ban: 3 ta              [➖] [➕]
📣 /report: ✅
⬅️ Orqaga
```
- Buyruqlar (`.mute`, `.ban` ...) har doim ishlaydi — ularni admin o'zi ishlatadi.
- **Mening qarorim:** avtomatik funksiyalar (reklama, so'kinish) **standart o'chiq** — har guruh admini o'zi yoqadi. Sabab: bot o'yin uchun qo'shilgan guruhlarda kutilmaganda odamlarni mute qila boshlamasin. Egasi xohlasa — hamma guruhda standart yoqiq.

## Bot huquqi yetmasa
Bot admin emas yoki huquqi yo'q bo'lsa — buyruq yozgan adminga: "⚠️ Botga «foydalanuvchilarni cheklash» huquqini bering". Avtomatik tozalashda xato jim o'tkaziladi (guruhga spam bo'lmasin), `/settings` → 🛡 bo'limida esa qaysi huquq yetishmasligi ko'rsatiladi.

## Ma'lumotlar
- `mod_warns` jadvali: guruh, odam, sabab, admin, vaqt (30 kundan eskisi hisoblanmaydi).
- `group_members` jadvali: guruh, odam, qo'shilgan vaqt (yangi a'zo kirganda yoziladi) — `.info` uchun.
- `mod_log` jadvali: har bir mute/ban/kick/warn/avtomatik o'chirish — panelda ko'rish uchun (keyingi bosqich).
- Guruh sozlamalari — mavjud `groups.settings` ichida (`mod` kaliti).
- Qo'shimcha so'kinish so'zlari — `settings` jadvalida, paneldan.

## O'yin bilan
O'yin paytidagi qoidalar (kim yoza oladi) avvalgidek. Moderatsiya ulardan **oldin** tekshiriladi: reklama/so'kinish o'yin paytida ham tozalanadi. Mute qilingan o'yinchi o'yindan chiqmaydi — tungi/ovoz tugmalari botning shaxsiy chatida, ular ishlaydi.

## Ish tartibi
1. So'kinish/reklama aniqlagich (sof funksiyalar) + testlar (yashirib yozilgan so'zlar, xato ushlanmaslik).
2. Buyruqlar (`.mute` ... `.warns`) + warn → ban + testlar.
3. Avtomatik tozalash (reklama, so'kinish) — guruh xabarlari oqimiga.
4. `/report` va admin tugmalari; `.admins` (metka + shaxsiy ogohlantirish); `.info` (+ qo'shilgan sanani yozib borish).
5. `/settings` → 🛡 Moderatsiya; panelda so'zlar ro'yxati.
6. Hujjat (CLAUDE.md), to'liq testlar, egasining "push qil"i.

## Qilinmaydi (hozircha)
Flood himoyasi, captcha, yangi a'zoga havola taqiqi, panelda moderatsiya jurnali sahifasi — keyingi bosqich.
