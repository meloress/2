"""Reyting matni: ixcham, telefonda bir qatorga sig'adi."""
from mafia_zone import texts


def test_top_compact_two_lines_per_player():
    rows = [(1, "Ali", 120, 340), (2, "B" * 60, 5, 0), (3, "Vali", 0, 7), (4, "G'ani", 1, 3)]
    text = texts.top(rows, "Umumiy reyting")
    lines = text.split("\n")
    assert lines[0] == f"🏆 <b>{texts.bold('Umumiy reyting')}</b>"
    assert "🥇" in text and "🥈" in text and "🥉" in text and "4️⃣" in text
    assert "└ 🏆 120 · 🎮 340 · 35%" in text  # yutish foizi
    assert "· 0%" in text  # 0 o'yin - nolga bo'linmaydi
    assert "B" * 60 not in text and "…" in text  # juda uzun ism qisqaradi
    assert texts.rank(120) in text
    assert "— hali o'yinlar yo'q —" in texts.top([], "X")


def test_top_groups_compact():
    text = texts.top_groups([("Admiral guruh", 1234), ("<b>", 5)])
    assert "🥇 <b>Admiral guruh</b>\n└ 🎮 1 234 ta o'yin" in text and "&lt;b&gt;" in text
