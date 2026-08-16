import os
import sys

# Ensures `import app.xyz` works when pytest runs from the project root,
# same as how the app itself is structured — no separate src/ layout to
# fight with.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Dummy DATABASE_URL/REDIS_URL so importing app modules doesn't crash on
# missing env vars during test collection — actual DB/Redis calls in
# these tests are mocked, never real connections.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
