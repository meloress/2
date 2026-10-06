import os
import tempfile

# Testlar hech qachon haqiqiy mafia.db ga tegmasin
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
