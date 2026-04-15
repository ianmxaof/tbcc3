import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tbcc.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # Wait longer for the write lock when the dashboard loads many thumbnails while approving in bulk.
    connect_args["timeout"] = 120

# SQLite is effectively single-file; QueuePool + long async handlers (Telegram downloads)
# exhausts pool_size+overflow. NullPool opens a connection per request and returns it immediately.
_engine_kw: dict = {"connect_args": connect_args}
if DATABASE_URL.startswith("sqlite"):
    _engine_kw["poolclass"] = NullPool

engine = create_engine(DATABASE_URL, **_engine_kw)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_wal_and_busy(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=120000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
