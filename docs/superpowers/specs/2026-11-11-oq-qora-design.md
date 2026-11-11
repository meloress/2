# ⚪⚫ Oq-Qora rejimi — dizayn

## Maqsad
Guruhda ikki jamoa o'yini: o'yinchilar ro'yxatda o'zlari ⚪ Oq yoki ⚫ Qora jamoani tanlaydi, Oq Qoraga, Qora Oqqa qarshi o'ynaydi. Qaysi jamoa yutsa — uning **hamma** a'zosi yutadi, o'lganlari ham.

## Egasi hal qilgan qoidalar
- Jamoani o'yinchi o'zi tanlaydi; kim qaysi jamoada ekani **hammaga ochiq** (ro'yxatda, tiriklar ro'yxatida, ovoz tugmalarida).
- Rollar **har doimgidek** tasodifiy tarqatiladi, jamoaga qaramaydi; har kim o'z rolini o'z jamoasi foydasiga ishlatadi.
- Rollar o'zaro **aralash** ishlaydi: mafiya oilasi odatdagidek (Don + Mafiyalar bir-birini taniydi, oxirgi so'z Donniki), ular boshqa-boshqa jamoada bo'lsa ham. Komissar+Serjant ham shunday.
- Jamoalar **teng** bo'lmasa o'yin boshlanmaydi: vaqt tugasa yoki `/start` bosilsa va son teng emas — o'yin bekor qilinadi.
- G'olib jamoaning hamma a'zosi (tirik va o'lik) g'alaba va g'alaba mukofotini oladi.

## Qarorlar (egasi 2026-11-11 tasdiqladi)
1. **"Teng" = aynan teng** (5:5). 5:4 ham bekor qilinadi.
2. **Kamida 2:2** (4 kishi), ko'pi bilan odatdagidek 60.
3. **O'yin tugashi:** bir jamoaning hamma a'zosi o'lsa — ikkinchisi yutadi; ikkalasi bir vaqtda tugasa yoki kunlar limiti (`max_days`) o'tsa — durang (hech kim yutmaydi).
4. **Rollarning shaxsiy g'alabasi o'chiq:** Suitsid/Tulki o'lib yutmaydi, Qotil/Vampir/G'azabkor yolg'iz yutmaydi, Konchi/Sehrgar/Aferist/Qaroqchi "tirik qolsa yutadi" yo'q, Podshoh tomoni, /couple juftining g'alabasi yo'q. Faqat jamoa natijasi.
5. **Kimni o'ldirsa bo'ladi:** jamoalar aralash bo'lgani uchun qotillar (Don, Qotil, Vampir...) o'zidan boshqa istalgan tirikni tanlay oladi — raqib jamoadagi Mafiyani ham (paralar o'yinidagidek). O'z jamoasini o'ldirish ham mumkin (ahmoqlik, lekin cheklamaymiz).
6. **Ovchi jarimasi yo'q** (egasi: kimni o'ldirsa ham jarima to'lamaydi).
7. **Jamoa almashtirish:** ro'yxat ochiq turganda boshqa jamoa tugmasini bosgan o'yinchi o'sha jamoaga o'tadi.
8. **Buyruqlar** (egasi): `/groupgame` — ro'yxatni ochadi; `/start` va `/stop` — odatdagidek. Menyuga `/groupgame` qo'shiladi. Paralar o'yini bilan bir vaqtda bo'lmaydi (guruhda bitta ro'yxat/o'yin).
9. **Sozlamalar** odatdagidek (vaqtlar, buyumlar, rollar ro'yxati) — yangi sozlama yo'q.

## Ko'rinishi
Ro'yxat:
```
⚪⚫ ADMIRAL MAFIA — Oq-Qora o'yini, ro'yxatdan o'tish boshlandi!

⚪ Oq (3): Ali, Vali, Sobir
⚫ Qora (2): Gani, Olim

Jami: 5 ta | Kutish vaqti: 6 daqiqa
[⚪ Oqqa qo'shilish] [⚫ Qoraga qo'shilish]
```
- Tiriklar ro'yxati va ovoz tugmalarida ismdan oldin ⚪/⚫.
- Rol kartasida: "Jamoangiz: ⚪ Oq".
- Bekor qilinsa: "⚖️ Jamoalar teng emas (⚪ 3 : ⚫ 2). O'yin bekor qilindi."
- O'yin oxiri: "⚪ Oq jamoa yutdi!" va g'oliblar ro'yxati (o'lganlari ham), odatdagi rollar ro'yxati bilan.

## Ish tartibi
1. **Dvigatel** (`engine/game.py`): `Game.sides` (uid → "oq"/"qora", saqlash/tiklashda), `teams_mode`; `targets` (o'zidan boshqa hamma), `_check_win` va `_finish` (jamoa g'alabasi, o'liklar ham), Ovchi jarimasi o'chiq. + testlar (tasodifiy o'yin simulyatsiyasi ham: o'yin doim tugaydi, g'oliblar = bitta jamoa).
2. **Ro'yxat** (`runner.py`): ikki tugma (`join` havolasiga jamoa belgisi), jamoa almashtirish, boshlashda tenglik tekshiruvi va bekor qilish, `restore`.
3. **Buyruq** (`handlers.py`, `__main__.py`): `/groupgame`, shaxsiy chatdagi qo'shilish.
4. **Matnlar** (`texts.py`): ro'yxat, ⚪/⚫ belgilari, rol kartasi, bekor qilish, o'yin oxiri.
5. **Mukofot**: o'zgarish kerak emas — `runner._finish` allaqachon `won=True` bo'lganlarga (o'liklarga ham) mukofot beradi.
6. **CLAUDE.md** va to'liq test to'plami, keyin "push qil".

## Qilinmaydi
- Jamoani bot o'zi tenglashtirmaydi.
- Har jamoaga alohida rol tarqatish yo'q.
- Panelda alohida statistika yo'q (o'yin odatdagi o'yinlar qatorida ko'rinadi).
