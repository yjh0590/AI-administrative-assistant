import base64
import hmac
import json
import logging
import mimetypes
import os
import secrets
import sqlite3
import subprocess
import threading
from contextlib import closing, contextmanager
from datetime import datetime, time, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, session
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from waitress import serve

from sources import SEOUL, build_briefing
from timetable import classes_today, read_photo, validate_classes

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)
PUSH_HOSTS = {"fcm.googleapis.com", "updates.push.services.mozilla.com"}


def subscription_data(data):
    endpoint = data.get("endpoint")
    keys = data.get("keys")
    if not isinstance(endpoint, str) or not isinstance(keys, dict):
        abort(400)
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ""
        if (
            url.scheme != "https" or url.username or url.password or url.fragment
            or url.port not in (443, None) or not url.path.strip("/")
            or not (host in PUSH_HOSTS or host.endswith(".push.apple.com") or host.endswith(".notify.windows.com"))
        ):
            abort(400)
        for key, size in (("p256dh", 65), ("auth", 16)):
            value = keys[key]
            if len(value) > 100 or len(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)) != size:
                abort(400)
    except (KeyError, TypeError, ValueError):
        abort(400)
    return {"endpoint": endpoint, "keys": {key: keys[key] for key in ("p256dh", "auth")}}


class Assistant:
    def __init__(self, directory, briefing_time, collect=build_briefing):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / "assistant.db"
        self.briefing_time = briefing_time
        self.collect = collect
        self.generation_lock = threading.Lock()
        self.photo_lock = threading.Lock()
        self.generation_failed = False
        self.key_file = directory / "vapid.pem"
        if not self.key_file.exists():
            vapid = Vapid()
            vapid.generate_keys()
            vapid.save_key(str(self.key_file))
        public_bytes = Vapid.from_file(str(self.key_file)).public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS briefings (day TEXT PRIMARY KEY, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS timetable (id INTEGER PRIMARY KEY CHECK (id = 1), content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS devices (endpoint TEXT PRIMARY KEY, subscription TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    day TEXT NOT NULL, endpoint TEXT NOT NULL REFERENCES devices(endpoint) ON DELETE CASCADE,
                    attempted TEXT NOT NULL, sent INTEGER NOT NULL,
                    PRIMARY KEY (day, endpoint)
                );
            """)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection

    def briefing(self, day):
        with self.db() as db:
            row = db.execute("SELECT content FROM briefings WHERE day = ?", (day,)).fetchone()
        return json.loads(row[0]) if row else None

    def timetable(self):
        with self.db() as db:
            row = db.execute("SELECT content FROM timetable WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else []

    def save_timetable(self, rows):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO timetable VALUES (1, ?)", (json.dumps(rows, ensure_ascii=False),))

    def refresh(self, now, background=False):
        if not self.generation_lock.acquire(blocking=False):
            return False
        self.generation_failed = False
        if background:
            threading.Thread(target=self.generate, args=(now,), daemon=True).start()
        else:
            self.generate(now)
        return True

    def generate(self, now):
        try:
            content = self.collect(now)
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO briefings VALUES (?, ?)", (content["date"], json.dumps(content, ensure_ascii=False)))
                db.execute("DELETE FROM briefings WHERE day < ?", ((now.date() - timedelta(days=7)).isoformat(),))
                db.execute("DELETE FROM deliveries WHERE day < ?", ((now.date() - timedelta(days=7)).isoformat(),))
        except Exception as error:
            self.generation_failed = True
            LOG.error("Briefing generation failed (%s)", type(error).__name__)
        finally:
            self.generation_lock.release()

    def register(self, subscription):
        with self.db() as db:
            db.execute("""
                INSERT INTO devices VALUES (?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET subscription = excluded.subscription
            """, (subscription["endpoint"], json.dumps(subscription)))

    def unregister(self, endpoint):
        with self.db() as db:
            db.execute("DELETE FROM devices WHERE endpoint = ?", (endpoint,))

    def notify(self, subscription, title, body, tag):
        try:
            webpush(
                subscription, json.dumps({"title": title, "body": body, "tag": tag}, ensure_ascii=False),
                vapid_private_key=str(self.key_file),
                vapid_claims={"sub": os.getenv("VAPID_CONTACT", "mailto:assistant@example.invalid")},
                ttl=3600, timeout=10,
            )
            return True
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in (404, 410):
                self.unregister(subscription["endpoint"])
            LOG.warning("Web Push failed (%s)", status or type(error).__name__)
        except (OSError, ValueError) as error:
            LOG.warning("Web Push failed (%s)", type(error).__name__)
        return False

    def run_due(self, now):
        due = datetime.combine(now.date(), self.briefing_time, SEOUL)
        if not due <= now < due + timedelta(hours=2):
            return
        day = now.date().isoformat()
        existing = self.briefing(day)
        # Refresh a draft made earlier that day before sending the morning report.
        if not existing or datetime.fromisoformat(existing["generated"]) < due:
            self.refresh(now)
            existing = self.briefing(day)
        if not existing or datetime.fromisoformat(existing["generated"]) < due:
            return
        retry_before = (now - timedelta(minutes=5)).isoformat()
        with self.db() as db:
            devices = db.execute("""
                SELECT devices.subscription FROM devices
                LEFT JOIN deliveries ON deliveries.endpoint = devices.endpoint AND deliveries.day = ?
                WHERE deliveries.endpoint IS NULL OR (deliveries.sent = 0 AND deliveries.attempted <= ?)
            """, (day, retry_before)).fetchall()
        for (value,) in devices:
            sub = json.loads(value)
            sent = self.notify(sub, "오늘의 아침 브리핑", "카이온에서 오늘 브리핑을 확인하세요.", f"briefing-{day}")
            with self.db() as db:
                db.execute("""
                    INSERT OR REPLACE INTO deliveries
                    SELECT ?, endpoint, ?, ? FROM devices WHERE endpoint = ?
                """, (day, now.isoformat(), int(sent), sub["endpoint"]))

    def schedule(self):
        while True:
            try:
                self.run_due(datetime.now(SEOUL))
            except Exception as error:
                LOG.error("Scheduler failed (%s)", type(error).__name__)
            threading.Event().wait(20)


def create_app(assistant, code, origin=""):
    mimetypes.add_type("image/webp", ".webp")
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.config.update(
        SECRET_KEY=code, SESSION_COOKIE_NAME="ai_assistant_session",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=bool(origin), MAX_CONTENT_LENGTH=8192,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30), SESSION_REFRESH_EACH_REQUEST=False,
    )

    @app.before_request
    def reject_cross_origin_post():
        if request.method == "POST":
            request_origin = request.headers.get("Origin")
            if request_origin and request_origin != (origin or request.host_url.rstrip("/")):
                abort(403)
            if not request.is_json and request.endpoint != "scan_timetable":
                abort(415)

    @app.after_request
    def protect_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    def require_login(handler):
        @wraps(handler)
        def checked(*args, **kwargs):
            if not session.get("signed_in"):
                return jsonify(error="접속 코드를 입력해 주세요."), 401
            return handler(*args, **kwargs)
        return checked

    def json_object():
        value = request.get_json()
        if not isinstance(value, dict):
            abort(400)
        return value

    @app.get("/")
    def home():
        return app.send_static_file("index.html")

    @app.post("/api/session")
    def login():
        provided = json_object().get("code")
        if not isinstance(provided, str) or not hmac.compare_digest(provided.encode(), code.encode()):
            return jsonify(error="접속 코드가 맞지 않아요."), 401
        session.clear()
        session["signed_in"] = True
        session.permanent = True
        return jsonify(ok=True)

    @app.post("/api/logout")
    @require_login
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/briefing")
    @require_login
    def current():
        now = datetime.now(SEOUL)
        today = now.date().isoformat()
        busy = assistant.generation_lock.locked()
        timetable = assistant.timetable()
        return jsonify(
            date=today, briefing=assistant.briefing(today), schedule=assistant.briefing_time.strftime("%H:%M"),
            busy=busy, failed=assistant.generation_failed, school=classes_today(timetable, now) if timetable else None,
        )

    @app.get("/api/timetable")
    @require_login
    def get_timetable():
        return jsonify(classes=assistant.timetable())

    @app.post("/api/timetable")
    @require_login
    def save_timetable():
        request.max_content_length = 64 * 1024
        try:
            rows = validate_classes(json_object().get("classes"))
        except (KeyError, TypeError, ValueError):
            return jsonify(error="과목, 요일, 시작·종료 시간을 확인해 주세요."), 400
        assistant.save_timetable(rows)
        return jsonify(classes=rows)

    @app.post("/api/timetable/photo")
    @require_login
    def scan_timetable():
        request.max_content_length = 4 * 1024 * 1024
        if request.mimetype != "image/png":
            return jsonify(error="PNG 시간표 사진을 선택해 주세요."), 415
        photo = request.get_data()
        if not photo.startswith(b"\x89PNG\r\n\x1a\n"):
            return jsonify(error="시간표 사진을 열 수 없어요."), 400
        if not assistant.photo_lock.acquire(blocking=False):
            return jsonify(error="다른 사진을 읽는 중입니다. 잠시 뒤 다시 시도해 주세요."), 429
        try:
            return jsonify(read_photo(photo))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            LOG.warning("Timetable OCR failed (%s)", type(error).__name__)
            return jsonify(error="사진 인식에 실패했어요. 시간표를 보면서 수업을 직접 추가할 수 있어요."), 422
        finally:
            assistant.photo_lock.release()

    @app.post("/api/briefing/refresh")
    @require_login
    def refresh():
        assistant.refresh(datetime.now(SEOUL), background=True)
        return jsonify(ok=True), 202

    @app.get("/api/push/key")
    @require_login
    def push_key():
        return jsonify(key=assistant.public_key)

    @app.post("/api/push/subscribe")
    @require_login
    def subscribe():
        assistant.register(subscription_data(json_object()))
        return jsonify(ok=True)

    @app.post("/api/push/unsubscribe")
    @require_login
    def unsubscribe():
        endpoint = json_object().get("endpoint")
        if not isinstance(endpoint, str):
            abort(400)
        assistant.unregister(endpoint)
        return jsonify(ok=True)

    @app.post("/api/push/test")
    @require_login
    def test_push():
        endpoint = json_object().get("endpoint")
        if not isinstance(endpoint, str):
            abort(400)
        with assistant.db() as db:
            row = db.execute("SELECT subscription FROM devices WHERE endpoint = ?", (endpoint,)).fetchone()
        if row and assistant.notify(json.loads(row[0]), "AI 비서 알림 테스트", "휴대폰 알림이 연결됐어요.", "briefing-test"):
            return jsonify(ok=True)
        return jsonify(error="알림이 전송되지 않았어요. 알림을 다시 켜고 시도해 주세요."), 502

    return app


def main():
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    directory = ROOT / ".data"
    directory.mkdir(exist_ok=True)
    code = os.getenv("ASSISTANT_ACCESS_CODE", "").strip()
    if not code:
        code_file = directory / "access-code.txt"
        if not code_file.exists():
            code_file.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        code = code_file.read_text(encoding="utf-8").strip()
    if len(code) < 16:
        raise SystemExit("ASSISTANT_ACCESS_CODE는 16자 이상이어야 합니다.")
    origin = os.getenv("ASSISTANT_ORIGIN", "").strip().rstrip("/")
    if origin:
        address = urlsplit(origin)
        if address.scheme != "https" or not address.hostname or address.path or address.query or address.fragment or address.username:
            raise SystemExit("ASSISTANT_ORIGIN에는 https://로 시작하는 사이트 주소만 지정하세요.")
    port = int(os.getenv("ASSISTANT_PORT", "8080"))
    briefing_time = datetime.strptime(os.getenv("BRIEFING_TIME", "07:30"), "%H:%M").time()
    assistant = Assistant(directory, briefing_time)
    app = create_app(assistant, code, origin)
    if not origin:
        app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1"]
    threading.Thread(target=assistant.schedule, daemon=True).start()
    print(f"AI 비서 접속 주소: {origin or f'http://localhost:{port}'}", flush=True)
    print("접속 코드는 .env 또는 .data/access-code.txt에서 확인하세요.", flush=True)
    serve(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
