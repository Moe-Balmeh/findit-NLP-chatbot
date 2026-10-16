# saves reports and gives each one a reference code like L-2609-7KQ3.
# SupabaseStore saves to our real database; MemoryStore keeps everything in
# lists and is used for tests or when the supabase keys aren't set.

import os
import random
import uuid
from datetime import datetime, timezone

import requests

from .dates import today_ph

RECORD_FIELDS = ["item", "brand", "color", "description", "location", "location_detail",
                 "zone", "room", "floor", "date", "time"]
OPEN_FOUND = ("pending_surrender", "in_custody")
TABLES = {"found": "found_items", "lost": "lost_reports"}
STATUSES = {"found": ("pending_surrender", "in_custody", "claimed", "disposed"),
            "lost": ("open", "matched", "returned", "closed")}


def make_ref_code(prefix):
    # no 0/O or 1/I so codes are easy to read out loud
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return f"{prefix}-{today_ph():%y%m}-" + "".join(random.choice(chars) for _ in range(4))


def new_record(slots, prefix, status):
    rec = {f: slots.get(f) for f in RECORD_FIELDS}
    if rec["date"] == "unknown":
        rec["date"] = None
    rec["id"] = str(uuid.uuid4())
    rec["ref_code"] = make_ref_code(prefix)
    rec["status"] = status
    rec["created_at"] = datetime.now(timezone.utc).isoformat()
    return rec


def status_update(kind, status):
    # also remember when an item was claimed / a report was closed
    done = status in ("claimed", "disposed", "returned", "closed")
    stamp = datetime.now(timezone.utc).isoformat() if done else None
    return {"status": status, ("claimed_at" if kind == "found" else "resolved_at"): stamp}


def get_store():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    if url.startswith("https://") and "your-project-id" not in url and key.startswith(("sb_secret_", "eyJ")):
        return SupabaseStore(url, key)
    print("supabase keys not set, using MemoryStore (reports are lost on restart)")
    return MemoryStore()


class MemoryStore:
    def __init__(self):
        self.lost = []
        self.found = []
        self.matches = []
        self.logs = []

    def add_lost(self, slots):
        rec = new_record(slots, "L", "open")
        self.lost.append(rec)
        return rec

    def add_found(self, slots):
        rec = new_record(slots, "F", "pending_surrender")
        self.found.append(rec)
        return rec

    def open_found(self, item=None):
        return [f for f in self.found if f["status"] in OPEN_FOUND and item in (None, f["item"])]

    def open_lost(self, item=None):
        return [r for r in self.lost if r["status"] == "open" and item in (None, r["item"])]

    def add_match(self, lost_id, found_id, score):
        self.matches.append({"lost_id": lost_id, "found_id": found_id, "score": score})

    def log(self, session_id, message, intent, confidence):
        self.logs.append({"session_id": session_id, "message": message,
                          "intent": intent, "confidence": confidence})

    def all_found(self):
        return list(reversed(self.found))

    def all_lost(self):
        return list(reversed(self.lost))

    def all_matches(self):
        return list(self.matches)

    def set_status(self, kind, record_id, status):
        for rec in self.found if kind == "found" else self.lost:
            if rec["id"] == record_id:
                rec.update(status_update(kind, status))
                return True
        return False

    def sign_in(self, email, password):
        # only for local testing without supabase, set ADMIN_PASSWORD yourself
        admin_password = os.environ.get("ADMIN_PASSWORD")
        return email if admin_password and password == admin_password else None


class SupabaseStore:
    # talks to supabase's REST api (postgrest), so each method is one http request

    def __init__(self, url, key):
        self.api = url.rstrip("/") + "/rest/v1/"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        # old style keys are JWTs and also go in the Authorization header
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"

    def insert(self, table, row, prefer="return=minimal"):
        res = requests.post(self.api + table, json=row, timeout=10,
                            headers={**self.headers, "Prefer": prefer})
        res.raise_for_status()

    def select(self, table, params):
        res = requests.get(self.api + table, params={"select": "*", **params},
                           headers=self.headers, timeout=10)
        res.raise_for_status()
        return res.json()

    def add_lost(self, slots):
        rec = new_record(slots, "L", "open")
        self.insert("lost_reports", rec)
        return rec

    def add_found(self, slots):
        rec = new_record(slots, "F", "pending_surrender")
        self.insert("found_items", rec)
        return rec

    def open_found(self, item=None):
        params = {"status": f"in.({','.join(OPEN_FOUND)})", "order": "created_at.desc", "limit": 200}
        if item:
            params["item"] = f"eq.{item}"
        return self.select("found_items", params)

    def open_lost(self, item=None):
        params = {"status": "eq.open", "order": "created_at.desc", "limit": 200}
        if item:
            params["item"] = f"eq.{item}"
        return self.select("lost_reports", params)

    def add_match(self, lost_id, found_id, score):
        # the same pair can come up twice, so ignore duplicates
        row = {"lost_id": lost_id, "found_id": found_id, "score": score}
        res = requests.post(self.api + "matches?on_conflict=lost_id,found_id", json=row, timeout=10,
                            headers={**self.headers, "Prefer": "resolution=ignore-duplicates"})
        res.raise_for_status()

    def log(self, session_id, message, intent, confidence):
        # logging should never break the chat
        try:
            self.insert("chat_logs", {"session_id": session_id, "message": message,
                                      "intent": intent, "confidence": confidence})
        except requests.RequestException as e:
            print("chat log failed:", e)

    def all_found(self):
        return self.select("found_items", {"order": "created_at.desc", "limit": 500})

    def all_lost(self):
        return self.select("lost_reports", {"order": "created_at.desc", "limit": 500})

    def all_matches(self):
        return self.select("matches", {"limit": 2000})

    def set_status(self, kind, record_id, status):
        res = requests.patch(self.api + TABLES[kind], params={"id": f"eq.{record_id}"},
                             json=status_update(kind, status), timeout=10,
                             headers={**self.headers, "Prefer": "return=representation"})
        res.raise_for_status()
        return bool(res.json())

    def sign_in(self, email, password):
        # check the password with supabase auth, then make sure they're in the admins table
        res = requests.post(self.api.replace("/rest/v1/", "/auth/v1/token"), timeout=10,
                            params={"grant_type": "password"}, headers=self.headers,
                            json={"email": email, "password": password})
        if res.status_code != 200:
            return None
        email = res.json()["user"]["email"].lower()
        return email if self.select("admins", {"email": f"eq.{email}"}) else None
