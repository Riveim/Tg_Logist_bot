import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for


UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class LoadStore:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loads(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    direction TEXT NOT NULL,
                    cargo TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    load_date TEXT NOT NULL,
                    extra TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_loads_status_created_at ON loads(status, created_at DESC)"
            )
            conn.commit()

    def create_load(
        self,
        *,
        direction: str,
        cargo: str,
        transport: str,
        load_date: str,
        extra: str = "",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO loads(direction, cargo, transport, load_date, extra, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (direction, cargo, transport, load_date, extra, now_iso()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_recent(self, limit: int = 30):
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, direction, cargo, transport, load_date, extra, status, created_at
                FROM loads
                WHERE status = 'active'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def latest_updated_at(self) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM loads WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return row["created_at"] if row else None


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")

    db_path = os.getenv("LOADS_DB_PATH", "loads.db")
    api_key = os.getenv("SERVER_API_KEY", "")
    store = LoadStore(db_path)

    def is_authorized(req) -> bool:
        if not api_key:
            return True
        auth_header = req.headers.get("Authorization", "")
        return auth_header == f"Bearer {api_key}"

    def normalize_payload(data: dict) -> dict:
        return {
            "direction": (data.get("direction") or "").strip(),
            "cargo": (data.get("cargo") or "").strip(),
            "transport": (data.get("transport") or "").strip(),
            "load_date": (data.get("date") or data.get("load_date") or "").strip(),
            "extra": (data.get("extra") or "").strip(),
        }

    def validate_payload(data: dict) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not data["direction"]:
            errors["direction"] = "Укажите направление."
        if not data["cargo"]:
            errors["cargo"] = "Укажите карго и тоннаж."
        if not data["transport"]:
            errors["transport"] = "Укажите тип транспорта."
        if not data["load_date"]:
            errors["load_date"] = "Укажите дату загрузки."
        return errors

    @app.get("/")
    def index():
        loads = store.list_recent(limit=20)
        return render_template("index.html", loads=loads, form_data={}, errors={}, success_message=None)

    @app.post("/")
    def create_load_from_form():
        form_data = normalize_payload(request.form.to_dict())
        errors = validate_payload(form_data)
        if errors:
            loads = store.list_recent(limit=20)
            return render_template(
                "index.html",
                loads=loads,
                form_data=form_data,
                errors=errors,
                success_message=None,
            ), 400

        load_id = store.create_load(**form_data)
        return redirect(url_for("index", created=load_id))

    @app.get("/api/loads")
    def list_loads():
        if not is_authorized(request):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        limit_arg = request.args.get("limit", "30")
        try:
            limit = max(1, min(int(limit_arg), 100))
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid limit"}), 400

        loads = store.list_recent(limit=limit)
        return jsonify(
            {
                "ok": True,
                "updated_at": store.latest_updated_at(),
                "loads": [
                    {
                        "id": item["id"],
                        "direction": item["direction"],
                        "cargo": item["cargo"],
                        "transport": item["transport"],
                        "date": item["load_date"],
                        "extra": item["extra"],
                        "created_at": item["created_at"],
                    }
                    for item in loads
                ],
            }
        )

    @app.post("/api/loads")
    def create_load_api():
        if not is_authorized(request):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        payload = request.get_json(silent=True) or request.form.to_dict()
        data = normalize_payload(payload)
        errors = validate_payload(data)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400

        load_id = store.create_load(**data)
        return jsonify({"ok": True, "id": load_id}), 201

    @app.get("/loads/latest")
    def loads_latest():
        if not is_authorized(request):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        limit_arg = request.args.get("limit", "30")
        try:
            limit = max(1, min(int(limit_arg), 100))
        except ValueError:
            limit = 30

        loads = store.list_recent(limit=limit)
        return jsonify(
            {
                "loads": [
                    {
                        "direction": item["direction"],
                        "cargo": item["cargo"],
                        "transport": item["transport"],
                        "date": item["load_date"],
                        "extra": item["extra"],
                    }
                    for item in loads
                ],
                "updated_at": store.latest_updated_at(),
            }
        )

    @app.context_processor
    def inject_query_flags():
        created = request.args.get("created")
        success_message = None
        if created:
            success_message = f"Заявка #{created} успешно сохранена."
        return {"query_success_message": success_message}

    return app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "5004"))
    app.run(host=host, port=port, debug=False)
