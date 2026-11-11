"""Reyting matni: ixcham, telefonda bir qatorga sig'adi."""
from mafia_zone import texts


def test_top_compact_two_lines_per_player():
    rows = [(1, "Ali", 120, 340), (2, "B" * 60, 5, 0), (3, "Vali", 0, 7), (4, "G'ani", 1, 3)]
    text = texts.top(rows, "Umumiy reyting")
    lines = text.split("\n")
    assert lines[0] == "🏆 <b>Umumiy reyting</b>"
    assert "🥇" in text and "🥈" in text and "🥉" in text and "4️⃣" in text
    assert "└ 🏆 120 · 🎮 340 · 35%" in text  # yutish foizi
    assert "· 0%" in text  # 0 o'yin - nolga bo'linmaydi
    assert "B" * 60 not in text and "…" in text  # juda uzun ism qisqaradi
    assert texts.rank(120) in text
    assert "— hali o'yinlar yo'q —" in texts.top([], "X")


def test_top_groups_compact():
    row = lambda p, t, u="", inv="": {"place": p, "title": t, "username": u, "invite": inv, "points": 9, "games": 4, "gems": 4}
    text = texts.top_groups([row(1, "Admiral guruh", "adm"), row(2, "<b>"), row(4, "A, B", inv="https://t.me/+x")])
    text = text.replace(texts.USER_MARK, "")
    assert '🥇 <a href="https://t.me/adm">Admiral guruh</a> — <b>9 ball</b>' in text and "&lt;b&gt;" in text
    assert '4. <a href="https://t.me/+x">A, B</a>' in text  # havolasiz guruh - oddiy qalin nom
