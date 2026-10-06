# 🎮 Mafia Zone

Telegram uchun o'zbekcha mafiya boti: 29 rol, o'yin ichidagi iqtisod (💵 dollar, 💎 olmos, do'kon), reyting.
Stek: aiogram 3, PostgreSQL (lokalda SQLite).

## Lokal ishga tushirish

```bash
pip install -r requirements.txt pytest
python -m pytest -q            # 62 test, shu jumladan 10 000 ta tasodifiy o'yin
# .env fayliga BOT_TOKEN va ADMIN_IDS ni yozing (namuna: .env.example)
python -m mafia_zone           # DATABASE_URL bo'sh bo'lsa mafia.db (SQLite) yaratiladi
```

## Railway

1. Loyihani GitHubga yuklang. Railwayda **New Project → Deploy from GitHub repo** ni tanlang. Dockerfile avtomatik topiladi.
2. **New → Database → PostgreSQL** ni qo'shing.
3. Bot servisining **Variables** bo'limiga quyidagilarni yozing:
   - `BOT_TOKEN`: @BotFather bergan token
   - `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`
   - `ADMIN_IDS`: sizning Telegram ID'ingiz (bir nechta bo'lsa, vergul bilan: `111,222`)
4. Deploy qiling. Jadvallar birinchi ishga tushishda o'zi yaratiladi.

**Muhim:** bot faqat bitta nusxada (1 replica) ishlashi kerak.

## BotFather sozlamalari

- `/setprivacy` → **Disable**: bot guruh xabarlarini ko'rishi uchun. Bu tunda va o'liklarning xabarlarini o'chirish uchun kerak.
- Guruhda botni **admin** qiling va unga xabarlarni o'chirish huquqini bering.

## Buyruqlar

| Joy | Buyruqlar |
|---|---|
| Guruh | `/game` `/extend` `/begin` `/stop` `/leave` `/next` `/players` `/settings` `/top` `/rules` |
| Shaxsiy chat | `/start` `/profile` `/role` `/shop` `/bonus` `/top` `/rules` |
| Bot egasi (shaxsiy chat) | `/stats` `/broadcast` `/ban` `/unban` `/give` `/emoji` (premium emoji) |
| Bot egasi (guruh) | `/testgame [soni]` — bot-o'yinchilar bilan test o'yin |

## Tuzilma

```
mafia_zone/engine/   # o'yin qoidalari (Telegramsiz): roles.py, game.py, setup.py
mafia_zone/runner.py # faza sikli, taymerlar, saqlash va tiklash, xabar navbati
mafia_zone/handlers.py, texts.py, db.py, config.py
docs/superpowers/specs/  # dizayn spetsifikatsiyasi
```

## Litsenziyalar

Premium emoji to'plamidagi belgilar: [Twemoji](https://github.com/jdecked/twemoji) (c) Twitter / jdecked, CC-BY 4.0.
