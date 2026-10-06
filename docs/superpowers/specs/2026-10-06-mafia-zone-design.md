# Mafia Zone — Dizayn spetsifikatsiyasi

Sana: 2026-10-06 · Manba: `Mafia Zone - Game Guide & Technical Specification.pdf` (PROD SPEC v1.0)

## 0. Maqsad va cheklovlar

- **Maqsad:** ommaviy, bepul, ko'p guruhda bir vaqtda ishlaydigan o'zbekcha Telegram mafiya boti. 29 rolning hammasi birinchi versiyada bo'ladi.
- **Infratuzilma:** Railway (bitta servis) + Railway PostgreSQL. Redis yo'q.
- **Stek:** Python 3.12, aiogram 3.x, SQLAlchemy 2 (async) + asyncpg, Alembic, pytest.
- **Telegram:** long polling (keyin webhookka bitta sozlama bilan o'tiladi).
- **Iqtisod:** o'ynab topiladi (dollar 💵, olmos 💎). To'lov yo'q, lekin sxema keyin Stars qo'shishga tayyor.
- **Muvaffaqiyat mezoni:** 29 rolning barcha o'zaro ta'siri testlar bilan qoplangan; 10 000 ta tasodifiy o'yin simulyatsiyasi xatosiz tugaydi; bot qayta ishga tushganda faol o'yinlar davom etadi; Telegram cheklovlariga urilmaydi.

PDFdagi rollar va ularning vazifalari asos qilib olingan. PDFda noaniq qolgan joylar quyida **[Qaror]** belgisi bilan hal qilingan.

## 1. Arxitektura

```
mafia_zone/
  engine/          # toza Python, Telegramdan bexabar
    state.py       # Game, Player dataclass'lari, JSON (de)serializatsiya
    roles.py       # 29 rol ta'rifi: jamoa, harakat turi, navbat, bayroqlar
    night.py       # tungi hisob-kitob (navbat bo'yicha)
    day.py         # ovoz berish va osish
    win.py         # g'alaba shartlari
    setup.py       # rol taqsimoti
    events.py      # natija hodisalari
  bot/
    handlers/      # lobby, night, day, shop, profile, settings, admin
    texts.py       # barcha o'zbekcha matnlar
    runner.py      # GameRunner: dvijok <-> Telegram, taymerlar, lock
    sender.py      # rate-limited xabar navbati
  db/              # modellar, repo, Alembic
  tests/
```

- Dvijok xabar yubormaydi: `submit_action()`, `resolve_night()`, `cast_vote()`, `resolve_vote()`, `check_win()` faqat `Event` ro'yxatini qaytaradi. Bot qatlami ularni matnga aylantiradi.
- Tasodif faqat `random.Random(game.seed)` orqali, shuning uchun har bir o'yin aynan qayta tiklanadi.
- Har o'yin bitta `GameRunner` ga ega, unga `asyncio.Lock` biriktirilgan. Callback'lar o'yin, faza va kun raqamini o'z ichiga oladi, shuning uchun eski tugmalar rad etiladi.
- Holat `games.state` (JSONB) ustuniga har faza o'zgarishida va har harakatdan keyin saqlanadi. Ishga tushganda `status='running'` o'yinlar tiklanadi va taymer `phase_deadline` dan davom etadi.

## 2. O'yin sikli

`LOBBY → NIGHT → MORNING → DAY → VOTING → NIGHT …`

- **LOBBY:** `/game` buyrug'i. Ro'yxatga olish xabari "Qo'shilish" tugmasi bilan chiqadi; tugma deep-link orqali PMga yuboradi, chunki bot PMga yozolmasa o'yinchi qo'shilmaydi. Muddat: 120 s. `/extend` +30 s, `/begin` admin uchun darhol boshlaydi. Kamida 4, ko'pi bilan 30 o'yinchi.
- **O'yin tundan boshlanadi.** Rollar PMda e'lon qilinadi. Jamoadoshlar bir-birini taniydi: mafiya jamoasining hammasi (Sotqindan tashqari) va Komissar + Serjant.
- **NIGHT:** 60 s. Harakatli rollar PMda inline tugmalar oladi. Hammasi harakat qilsa, tun muddatidan oldin tugaydi. Tun davomida guruhdagi o'yinchi xabarlari o'chiriladi (bot admin bo'lsa).
- **Tungi chatlar:** mafiya a'zolari PMda botga yozgan xabarlar boshqa mafiyadoshlarga uzatiladi. Komissar va Serjant o'rtasida ham xuddi shunday. Donishmand ikkala chatni ismlarsiz oladi.
- **MORNING:** tungi hodisalar guruhda e'lon qilinadi. Tunda o'lgan o'yinchi 30 s ichida botga 1 ta "so'nggi so'z" yubora oladi.
- **DAY:** 60 s muhokama. O'lgan o'yinchilarning xabarlari doim o'chiriladi.
- **VOTING:** 45 s. Guruhda tirik o'yinchilar tugmalari va "⏭ O'tkazib yuborish" tugmasi chiqadi. Ovozlar ochiq e'lon qilinadi. Eng ko'p ovoz olgan osiladi. Teng ovoz yoki hamma o'tkazib yuborsa, hech kim osilmaydi. Ovozni o'zgartirish mumkin; Tulki uchun "birinchi ovoz" deb vaqt bo'yicha birinchi berilgan ovoz hisoblanadi.
- **Kun limiti:** 20-kundan keyin durang.
- **Taymerlar** guruh sozlamalarida o'zgartiriladi (`/settings`).

## 3. Tungi hisob-kitob tartibi

PDFdagi 5 ta navbat saqlangan, ichida aniq tartib belgilangan:

| # | Bosqich | Rollar |
|---|---|---|
| 1a | Bloklash | Kezuvchi |
| 1b | O'g'irlash | Aferist, keyin Qaroqchi |
| 2 | Himoya va niqob | Doktor, Qorovul, Advokat; buyumlar: Qalqon, Verbena, Hujjat |
| 3 | Tekshiruv va axborot | Komissar (tekshiruv), Ovchi (tekshiruv), Daydi, Jurnalist, Donishmand, Konchi (qazish) |
| 4 | Hujumlar | Mafiya/Don, Yollanma qotil, Aka/Uka, Qotil, Vampir, Ovchi (otish), Komissar (otish), Sehrgar, G'azabkor |
| 5 | O'limdan keyin | Voris (aylanish), Afsungar va Suitsid (qasos), Aka/Uka bog'lanishi, vorislik (Serjant → Komissar, Mafiya → Don) |

**Umumiy qoidalar:**
- Bloklangan o'yinchining harakati bekor bo'ladi va unga "💤 Sizga uyqu dori berildi" deb xabar boriladi. Passiv rollarga blok ta'sir qilmaydi.
- Bir nishonga bir nechta hujum bo'lsa, u bir marta o'ladi. Uni o'ldirganlar ro'yxati (`killers`) Afsungar va Daydi uchun saqlanadi.
- Doktor davolasa yoki Qalqon bo'lsa, istalgan tungi hujumdan saqlaydi. Verbena faqat Vampirdan saqlaydi. Immunitet hujumni hech qanday davolashsiz bekor qiladi.
- 5-bosqichdagi qasos o'limlarini to'xtatib bo'lmaydi.
- Kezuvchi Aferistdan oldin hisoblanadi: Kezuvchi bloklagan Aferist hech narsa qila olmaydi. Aferist Kezuvchini tanlasa, blok allaqachon bajarilgan bo'ladi va Aferist faqat Kezuvchi rolini bilib oladi.

## 4. Rollar

### 4.1 Tinch aholi
| Rol | Qoida |
|---|---|
| 👨 Tinch aholi | Harakat yo'q. |
| 🕵️‍♂️ Komissar Katani | Har tun tanlaydi: **Tekshirish** (jamoani ko'radi: Mafiya / Tinch / Neytral) yoki **Otish** (hujum). **[Qaror]** Otish varianti qo'shildi, chunki PDFda Sehrgarning "Komissar hujumidan immuniteti" va Vorisning "Komissar o'ldirsa" qoidalari bor. |
| 👮 Serjant | Komissarni taniydi va tekshiruv natijalarini oladi. Komissar o'lsa, Komissar bo'ladi. |
| 👨‍⚕️ Doktor | 1 kishini davolaydi. Bir kishini ketma-ket 2 tun davolay olmaydi. **[Qaror]** O'zini o'yinda 1 marta davolay oladi. |
| 🧙‍♂️ Daydi | X ning uyiga boradi. X o'sha tunda o'ldirilsa, Daydi qotil(lar)ni ko'radi. |
| 💃 Kezuvchi | Nishonni bloklaydi (1a). Bir kishini ketma-ket 2 tun bloklay olmaydi. |
| 💣 Afsungar | Tunda o'ldirilsa, uni o'ldirgan(lar) ham o'ladi. Mafiya o'ldirgan bo'lsa, qarorni bergan o'ladi (Don). Osilganda ta'sir qilmaydi. |
| 👥 Voris | Mafiya o'ldirsa, o'lmaydi va **Mafiya** bo'ladi (mafiya chatiga qo'shiladi). Komissar otsa, o'lmaydi va **Serjant** bo'ladi. **[Qaror]** Boshqa hujumda oddiy o'ladi. |
| 🎖 Janob | Ovozi 2 ta hisoblanadi. |
| 🏹 Ovchi | Har tun **Tekshirish** yoki **Otish**ni tanlaydi. **[Qaror]** Tinch jamoa a'zosini otsa (jarima), qobiliyatini yo'qotadi va oddiy Tinch aholi bo'lib qoladi. |
| 👨‍🏫 Donishmand | Tungi mafiya va komissar chatlarini ismlarsiz oladi. |
| 🤦 Suitsid | Mafiya tunda o'ldirsa, qarorni bergan mafiya (Don) ham o'ladi va Suitsid g'olib deb belgilanadi. |
| 🤓 Sotqin | Kodda neytral jamoada (tinchlar g'alabasida yutmaydi), tekshiruvda "Tinch" bo'lib ko'rinadi. Mafiya uni tanimaydi. Mafiya yutsa va Sotqin tirik bo'lsa, u ham yutadi. |
| 👨‍🦳 Qorovul | 1 kishini himoyalaydi: o'sha odam ertangi kun osilmaydi. Ketma-ket bir kishini himoyalay olmaydi. |
| 🤴 Podshoh | Qorovul himoyasisiz osilsa, mafiya va tirik neytrallar darhol yutadi. Faqat Qorovul bor o'yinda chiqadi. |

### 4.2 Mafiya
| Rol | Qoida |
|---|---|
| 🤵 Mafiya | Mafiya chatida ishtirok etadi va nishonga ovoz beradi. |
| 🤵‍♂️ Don | Mafiya nishonini yakuniy hal qiladi. **[Qaror]** Don tanlamasa, mafiya ovozlarining ko'pchiligi hal qiladi, teng bo'lsa tasodifiy tanlanadi. Don bloklansa, mafiya hujumi bekor bo'ladi. Don o'lsa, Don bo'ladi: avval oddiy Mafiya, u bo'lmasa istalgan mafiyadosh. |
| 👩‍💻 Jurnalist | X ni intervyu qiladi va o'sha tunda X ga kelganlarning hammasini ko'radi. |
| 🕴 Yollanma qotil | Dondan mustaqil, qo'shimcha 1 kishini o'ldiradi. Mafiyadoshlarni tanlay olmaydi. |
| 👨‍💼 Advokat | 1 mafiyadoshni (o'zini ham) niqoblaydi: o'sha tunda Komissar va Ovchi tekshiruvida "Tinch" ko'rinadi. |
| 👥 Aka / Uka | Ikki o'yinchi. Ikkalasi bir nishonni tanlasa, nishon o'ladi (Don hujumidan alohida). Biri o'lsa, ikkinchisi ham o'ladi (5-bosqichda yoki osilganda darhol). Faqat 2 ta mafiya o'rni bo'sh bo'lsa chiqadi. |

### 4.3 Neytrallar
| Rol | Qoida |
|---|---|
| 🔪 Qotil | Har tun 1 kishini o'ldiradi. **[Qaror]** "Bolta/pichoq tegmaydi" degani Mafiya va Yollanma qotil hujumidan immunitet. |
| 🧟 G'azabkor | Har tun 1 kishini o'ldiradi. O'zi qilgan 3 ta muvaffaqiyatli qotillikdan keyin "🔥 O'zini qurbon qilish" tugmasi ochiladi. Bossa, o'ladi va yakka g'olib deb belgilanadi. **[Qaror]** O'yin boshqalar uchun davom etadi. |
| 🧙 Sehrgar | Har tun 1 uyni la'natlaydi (o'ldiradi). Don/Mafiya, Qotil va Komissar hujumlari unga ta'sir qilmaydi. Oxirigacha tirik qolsa yutadi. |
| 🧛 Vampir | Tishlaydi: nishon shu tun o'ladi, agar Doktor davolamasa yoki Verbena bo'lmasa. |
| 🦹‍♂️ Qaroqchi | Nishondan tasodifan bittasini o'g'irlaydi (1b, himoyadan oldin): dollar (balansning 20%, ko'pi bilan 50 💵), 1 ta buyum yoki ertangi ovoz huquqi. Dollar va buyum Qaroqchining doimiy hisobiga o'tadi. |
| 👷‍♂️ Konchi | Har tun qazadi: 10–30 💵, 5% ehtimol bilan 1 💎 (doimiy hisobga). Oxirigacha tirik qolsa yutadi. |
| 🦊 Tulki | Kunduzi osilsa, unga birinchi ovoz bergan ham o'ladi va Tulki g'olib deb belgilanadi. |
| 🤹 Aferist | X ni tanlaydi (1b): X ning harakati bekor bo'ladi, Aferist esa uni X ning nishoniga bajaradi va natijani o'zi oladi. Hujumni Aferist qilgan hisoblanadi. Oxirigacha tirik qolsa, g'olib tomon bilan birga yutadi. |

## 5. G'alaba shartlari

Har tundan va har osishdan keyin quyidagi tartibda tekshiriladi:

1. Podshoh qoidasi (osishda) → mafiya va tirik neytrallar yutadi.
2. Tirik qolganlar 0 ta → durang.
3. Tirik qolganlar ≤ 2 ta va ular orasida Qotil yoki Vampir bor → o'sha rol yakka yutadi.
4. Mafiya 0 ta, Qotil va Vampir o'lgan → **Tinch aholi yutadi**.
5. Mafiya soni ≥ qolgan tiriklar soni, Qotil va Vampir o'lgan → **Mafiya yutadi** (Sotqin tirik bo'lsa, u ham).
6. Kun limiti → durang.

**Qo'shimcha g'oliblar** (asosiy g'olibdan qat'i nazar): Konchi, Sehrgar va Aferist (tirik bo'lsa), Suitsid, Tulki, G'azabkor (shartini bajargan bo'lsa).

## 6. Rol taqsimoti (`setup.py`)

`n` o'yinchilar soni, guruh sozlamalarida o'chirilgan rollar hisobga olinmaydi.

- **Mafiya soni:** `max(1, n // 4)`. Don har doim bor. Qolgan o'rinlar mafiya hovuzidan tasodifiy to'ldiriladi: Mafiya, Advokat, Jurnalist, Yollanma qotil, Aka/Uka (juftlik).
- **Neytrallar:** n ≥ 8 → 1, n ≥ 14 → 2, n ≥ 20 → 3, n ≥ 26 → 4 ta. Neytral hovuzdan tasodifiy, takrorlanmaydi.
- **Tinch aholi:** Komissar har doim. Doktor n ≥ 5 dan. Serjant n ≥ 8 dan. Qolgan joylarning taxminan 70% ga tinch hovuzidan maxsus rollar, kamida 1 ta oddiy Tinch aholi qoladi. Podshoh faqat Qorovul bilan birga chiqadi.

## 7. Iqtisod

- **Topish:** ishtirok uchun +10 💵, g'alaba uchun +30 💵, Konchi qazishi, kunlik `/bonus` +20 💵 (24 soatda 1 marta).
- **Do'kon** (`/shop`, PMda):
  - 🛡 Qalqon, 100 💵: tungi o'limdan 1 marta saqlaydi.
  - 🧄 Verbena, 80 💵: Vampir tishlashidan 1 marta saqlaydi.
  - 📄 Hujjat, 120 💵: tekshiruvda 1 marta "Tinch" ko'rsatadi.
- **Buyumlarni ishlatish:** o'yinchi `/profile` da buyumni yoqib yoki o'chirib qo'yadi. Yoqilgan buyum kerak bo'lganda avtomatik sarflanadi.
- **Olmos 💎:** hozircha 1 💎 = 50 💵 ga almashtiriladi. Keyinchalik Stars orqali premium narsalar uchun ishlatiladi.
- Guruh sozlamasi: buyumlar shu guruh o'yinlarida yoqilgan yoki o'chirilgan.

## 8. Ma'lumotlar bazasi (PostgreSQL)

| Jadval | Ustunlar |
|---|---|
| `users` | telegram_id PK, full_name, username, dollars, diamonds, games, wins, last_bonus_at, banned, created_at |
| `inventory` | user_id, item, qty, enabled (PK: user_id + item) |
| `groups` | chat_id PK, title, settings JSONB (taymerlar, o'chirilgan rollar, buyumlar), created_at |
| `games` | id PK, chat_id, status (lobby/running/finished/aborted), state JSONB, phase_deadline, started_at, finished_at, winner |
| `game_players` | game_id, user_id, role, team, alive, won — o'yin yakunida yoziladi (statistika va `/top` uchun) |

- PDFdagi `protected` va `blocked` bitta tungi vaqtinchalik holat, shuning uchun ular alohida ustun emas, `games.state` ichida saqlanadi.
- Balans o'zgarishlari bitta tranzaksiyada `UPDATE … SET dollars = dollars + :d` ko'rinishida bajariladi, shuning uchun poyga holati (race condition) bo'lmaydi.

## 9. Telegram qatlami

- **Guruh buyruqlari:** `/game`, `/extend`, `/begin` (admin), `/stop` (admin), `/leave`, `/settings` (admin), `/top`, `/rules`.
- **PM buyruqlari:** `/start`, `/profile`, `/shop`, `/bonus`, `/top`, `/help`.
- **Bot egasi** (`ADMIN_IDS` env): `/stats` (foydalanuvchilar, guruhlar, faol o'yinlar), `/broadcast` (PMlarga, cheklov bilan), `/ban`, `/unban`, `/give`.
- **Ruxsatlar:** bot guruhda admin bo'lishi kerak (xabar o'chirish va pin). Admin bo'lmasa, `/game` ogohlantirish beradi va o'yin xabarlarni o'chirmasdan o'tkaziladi.
- **`sender.py`:** har chat uchun 20 xabar/daqiqa va umumiy 25 xabar/s token bucket. `TelegramRetryAfter` bo'lsa kutib qayta yuboriladi. Bot bloklangan PM (`Forbidden`) bo'lsa, o'yinchi o'sha harakatni o'tkazib yuborgan hisoblanadi.
- **O'yinchi guruhdan chiqsa yoki `/leave` qilsa,** keyingi hisob-kitobda o'lgan hisoblanadi.
- **Matnlar:** hammasi `texts.py` da, o'zbekcha (lotin), PDFdagi emojilar bilan.

## 10. Xatolar va tiklanish

- Handlerdagi istisno loglanadi va o'yinni to'xtatmaydi. Faza o'tishi xato bilan tugasa, o'yin `aborted` qilinadi va guruhga xabar beriladi.
- Ishga tushganda faol o'yinlar tiklanadi. `phase_deadline` o'tib ketgan bo'lsa, faza darhol hisoblanadi.
- Bitta guruhda bir vaqtda faqat bitta faol o'yin bo'ladi (`games` da qisman unique indeks).

## 11. Testlash

- **Dvijok birlik testlari:** har bir rol va 3-bo'limdagi har bir o'zaro ta'sir uchun stsenariy testi. Masalan: Kezuvchi Donni bloklaydi; Afsungar + Doktor; Voris + Komissar otishi; Aka/Uka bog'lanishi; Podshoh + Qorovul; Tulki birinchi ovoz; Advokat + Komissar; Sehrgar immuniteti.
- **Simulyator testi:** 10 000 seed, 4–30 o'yinchi, tasodifiy harakatlar. Invariantlar: o'yin har doim tugaydi; o'lik o'yinchi harakat qilmaydi; rol taqsimoti `n` ga mos; g'olib aniqlanadi yoki durang bo'ladi.
- **Bot qatlami:** `texts.py` hamma `Event` turini qoplaganini tekshiruvchi test, qolgani test guruhida qo'lda tekshiriladi.

## 12. Deploy (Railway)

- `Dockerfile` (python:3.12-slim). Ishga tushirish: `python -m mafia_zone` (jadvallar `create_all` bilan; Alembic sxema birinchi marta o'zgarganda qo'shiladi).
- Env: `BOT_TOKEN`, `DATABASE_URL` (Railway beradi; `postgresql+asyncpg://` ga moslanadi), `ADMIN_IDS`.
- Loglar stdout'ga yoziladi (Railway logs).

## 13. Keyingi bosqichlarga qoldirilgan (YAGNI)

Telegram Stars to'lovlari, webhook, ko'p nusxada ishlash va Redis, ko'p tillilik, veb admin panel, reklama.
