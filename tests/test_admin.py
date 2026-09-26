# tests the admin dashboard api: you must log in first, the numbers for the charts
# add up, and marking an item as claimed actually saves.

import pytest

import api.index as server
from findit.store import MemoryStore


@pytest.fixture
def client(monkeypatch):
    # use a fresh in-memory store so tests never touch the real database
    store = MemoryStore()
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pass")
    store.add_found({"item": "PHONE", "location": "GYM", "zone": "SPORTS", "date": "2026-09-26"})
    store.add_found({"item": "UMBRELLA", "location": "LIBRARY", "zone": "LRC", "date": "2026-09-25"})
    store.add_lost({"item": "PHONE", "location": "GYM", "zone": "SPORTS", "date": "2026-09-26"})
    return server.app.test_client()


def login(client, password="test-pass"):
    return client.post("/api/admin/login", json={"email": "staff@nu.edu.ph", "password": password})


def test_needs_login(client):
    assert client.get("/api/admin/data").status_code == 401
    assert login(client, "wrong").status_code == 401
    assert client.get("/api/admin/data").status_code == 401


def test_dashboard_numbers(client):
    login(client)
    data = client.get("/api/admin/data").get_json()
    assert data["summary"] == {"lost": 1, "found": 2, "claimed": 0, "return_rate": 0}
    assert sum(data["charts"]["items"]["values"]) == 3
    assert data["charts"]["status"]["labels"] == ["Waiting for drop-off"]


def test_mark_claimed(client):
    login(client)
    found = client.get("/api/admin/data").get_json()["found"]
    res = client.post("/api/admin/status", json={"kind": "found", "id": found[0]["id"], "status": "claimed"})
    assert res.status_code == 200

    data = client.get("/api/admin/data").get_json()
    assert data["summary"]["claimed"] == 1
    assert data["summary"]["return_rate"] == 50
    assert server.store.found[1]["claimed_at"]


def test_rejects_bad_status(client):
    login(client)
    found = client.get("/api/admin/data").get_json()["found"]
    res = client.post("/api/admin/status", json={"kind": "found", "id": found[0]["id"], "status": "stolen"})
    assert res.status_code == 400


def test_vercel_style_paths(client):
    # on vercel every api call arrives as /api/index?route=...
    assert client.get("/api/index?route=health").get_json()["ok"] is True
    res = client.post("/api/index?route=chat", json={"message": "hello"})
    assert "FindIt" in res.get_json()["messages"][0]["text"]


def test_logout(client):
    login(client)
    client.post("/api/admin/logout")
    assert client.get("/api/admin/data").status_code == 401
