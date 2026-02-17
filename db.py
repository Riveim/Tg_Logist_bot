import sqlite3
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

def now_utc() -> datetime:
    return datetime.now(tz=UTC)

def dt_to_str(dt: datetime) -> str:
    return dt.isoformat()

def str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)

class DB:
    def __init__(self, path: str = "bot.db"):
        self.path = path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS users(
              tg_id INTEGER PRIMARY KEY,
              created_at TEXT NOT NULL,
              phone TEXT,
              access_until TEXT
            )
            """)

            c.execute("""
            CREATE TABLE IF NOT EXISTS access_requests(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tg_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              phone TEXT NOT NULL,
              status TEXT NOT NULL,        -- pending/approved/rejected
              admin_id INTEGER,
              decided_at TEXT
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_req_status ON access_requests(status)")
            c.commit()

    def ensure_user(self, tg_id: int):
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO users(tg_id, created_at) VALUES(?, ?)",
                (tg_id, dt_to_str(now_utc()))
            )
            c.commit()

    def set_phone(self, tg_id: int, phone: str):
        self.ensure_user(tg_id)
        with self._conn() as c:
            c.execute("UPDATE users SET phone=? WHERE tg_id=?", (phone, tg_id))
            c.commit()

    def get_phone(self, tg_id: int) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT phone FROM users WHERE tg_id=?", (tg_id,)).fetchone()
            return row["phone"] if row and row["phone"] else None

    def get_access_until(self, tg_id: int):
        with self._conn() as c:
            row = c.execute("SELECT access_until FROM users WHERE tg_id=?", (tg_id,)).fetchone()
            if not row or not row["access_until"]:
                return None
            return str_to_dt(row["access_until"])

    def has_access(self, tg_id: int) -> bool:
        until = self.get_access_until(tg_id)
        return bool(until and until > now_utc())

    def grant_access_days(self, tg_id: int, days: int):
        self.ensure_user(tg_id)
        current = self.get_access_until(tg_id)
        base = current if (current and current > now_utc()) else now_utc()
        new_until = base + timedelta(days=days)
        with self._conn() as c:
            c.execute("UPDATE users SET access_until=? WHERE tg_id=?", (dt_to_str(new_until), tg_id))
            c.commit()
        return new_until

    def create_access_request(self, tg_id: int, phone: str) -> int:
        self.ensure_user(tg_id)

        # если уже есть pending-заявка, не плодим новые
        with self._conn() as c:
            row = c.execute(
                "SELECT id FROM access_requests WHERE tg_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (tg_id,)
            ).fetchone()
            if row:
                return int(row["id"])

            cur = c.execute("""
            INSERT INTO access_requests(tg_id, created_at, phone, status)
            VALUES(?, ?, ?, 'pending')
            """, (tg_id, dt_to_str(now_utc()), phone))
            c.commit()
            return int(cur.lastrowid)

    def get_request(self, req_id: int):
        with self._conn() as c:
            return c.execute("SELECT * FROM access_requests WHERE id=?", (req_id,)).fetchone()

    def list_pending(self, limit: int = 20):
        with self._conn() as c:
            return c.execute("""
                SELECT * FROM access_requests
                WHERE status='pending'
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()

    def approve_request(self, req_id: int, admin_id: int):
        with self._conn() as c:
            c.execute("""
                UPDATE access_requests
                SET status='approved', admin_id=?, decided_at=?
                WHERE id=? AND status='pending'
            """, (admin_id, dt_to_str(now_utc()), req_id))
            c.commit()

    def reject_request(self, req_id: int, admin_id: int):
        with self._conn() as c:
            c.execute("""
                UPDATE access_requests
                SET status='rejected', admin_id=?, decided_at=?
                WHERE id=? AND status='pending'
            """, (admin_id, dt_to_str(now_utc()), req_id))
            c.commit()
