# flask web server. the website sends messages to /api/chat and this passes them
# to findit/dialogue.py. the /api/admin routes power the admin dashboard.
# vercel runs this file as our backend.

import os
import re
import sys
from functools import wraps
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # locally the keys come from .env, on vercel from its settings

from findit.admin import dashboard  # noqa: E402
from findit.dialogue import respond  # noqa: E402
from findit.store import STATUSES, get_store  # noqa: E402

PUBLIC = ROOT / "public"
UUID = re.compile(r"^[0-9a-f-]{36}$")

app = Flask(__name__)
# signs the admin login cookie. without a fixed key, logins reset on every restart
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")))
store = get_store()


@app.errorhandler(requests.RequestException)
def database_error(e):
    print("database error:", e)
    return jsonify(error="database is not reachable right now"), 503


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = body.get("message")
    action = body.get("action")
    if message is not None and not isinstance(message, str):
        return jsonify(error="message must be text"), 400
    if action is not None and not isinstance(action, str):
        return jsonify(error="action must be text"), 400

    reply = respond(
        state=body.get("state"),
        message=message,
        action=action[:60] if action else None,
        store=store,
        session_id=str(body.get("session_id", ""))[:64] or None,
    )
    return jsonify(reply)


def admin_only(route):
    @wraps(route)
    def check(*args, **kwargs):
        if not session.get("admin"):
            return jsonify(error="please log in"), 401
        return route(*args, **kwargs)
    return check


@app.post("/api/admin/login")
def admin_login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()[:200]
    password = str(body.get("password", ""))[:200]
    admin = store.sign_in(email, password) if email and password else None
    if not admin:
        return jsonify(error="wrong email or password, or this account isn't an admin"), 401
    session["admin"] = admin
    return jsonify(email=admin)


@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/admin/data")
@admin_only
def admin_data():
    data = dashboard(store.all_found(), store.all_lost(), store.all_matches())
    data["admin"] = session["admin"]
    return jsonify(data)


@app.post("/api/admin/status")
@admin_only
def admin_status():
    body = request.get_json(silent=True) or {}
    kind, record_id, status = body.get("kind"), str(body.get("id", "")), body.get("status")
    if kind not in STATUSES or status not in STATUSES[kind] or not UUID.match(record_id):
        return jsonify(error="bad request"), 400
    if not store.set_status(kind, record_id, status):
        return jsonify(error="report not found"), 404
    return jsonify(ok=True)


@app.get("/api/health")
def health():
    return jsonify(ok=True, store=type(store).__name__)


# vercel serves public/ on its own, these are just for running locally
@app.get("/")
def index():
    return send_from_directory(PUBLIC, "index.html")


@app.get("/admin")
def admin_page():
    return send_from_directory(PUBLIC, "admin.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(PUBLIC, path)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
