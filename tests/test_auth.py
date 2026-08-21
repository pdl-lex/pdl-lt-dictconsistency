"""Login/Logout/Session-Cookie sowie der lokale Admin-Bereich (Phase 2 + 4)."""
from __future__ import annotations


# ── Login / Logout / Session ────────────────────────────────────────────────

def test_login_success_returns_user_and_sets_httponly_cookie(client, make_user):
    make_user("bob", "bobpass123", principal="anon")
    resp = client.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "bob"
    assert body["wbdb_principal_id"] == "anon"
    assert body["is_admin"] is False
    assert isinstance(body["id"], int)

    set_cookie = resp.headers.get("set-cookie", "")
    assert "lt_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_login_wrong_password_401(client, make_user):
    make_user("bob", "bobpass123")
    resp = client.post("/api/auth/login", json={"username": "bob", "password": "falsch"})
    assert resp.status_code == 401


def test_login_unknown_user_401(client):
    resp = client.post("/api/auth/login", json={"username": "geist", "password": "irgendwas"})
    assert resp.status_code == 401


def test_login_inactive_user_401(client, make_user):
    make_user("inaktiv", "passwort123", active=False)
    resp = client.post("/api/auth/login", json={"username": "inaktiv", "password": "passwort123"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_session_persists_across_requests(logged_in_client):
    first = logged_in_client.get("/api/auth/me")
    second = logged_in_client.get("/api/auth/me")
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_logout_clears_session(logged_in_client):
    assert logged_in_client.get("/api/auth/me").status_code == 200
    logout_resp = logged_in_client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    assert logged_in_client.get("/api/auth/me").status_code == 401


# ── Admin-Bereich: Zugriffsschutz ───────────────────────────────────────────

def test_admin_endpoints_require_auth_401(client):
    assert client.get("/api/admin/users").status_code == 401


def test_admin_endpoints_require_admin_403(logged_in_client):
    assert logged_in_client.get("/api/admin/users").status_code == 403


# ── Admin-Bereich: lokale Nutzerverwaltung ──────────────────────────────────

def test_admin_list_users(admin_client, make_user):
    make_user("zweiter", "zweitpass123")
    body = admin_client.get("/api/admin/users").json()
    usernames = {u["username"] for u in body}
    assert {"admin1", "zweiter"} <= usernames


def test_admin_create_user(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "neu", "password": "neupass123", "wbdb_principal_id": "anon", "is_admin": False},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "neu"
    assert body["wbdb_principal_id"] == "anon"
    assert body["active"] is True

    listed = {u["username"] for u in admin_client.get("/api/admin/users").json()}
    assert "neu" in listed


def test_admin_create_user_missing_fields_422(admin_client):
    resp = admin_client.post("/api/admin/users", json={"username": "", "password": ""})
    assert resp.status_code == 422


def test_admin_create_duplicate_username_409(admin_client):
    admin_client.post("/api/admin/users", json={"username": "doppelt", "password": "erstespass123"})
    resp = admin_client.post("/api/admin/users", json={"username": "doppelt", "password": "zweitespass123"})
    assert resp.status_code == 409


def test_admin_update_user_principal(admin_client, make_user):
    make_user("editme", "editpass123")
    user_id = next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == "editme")

    resp = admin_client.patch(f"/api/admin/users/{user_id}", json={"wbdb_principal_id": "bwb-reader"})
    assert resp.status_code == 200
    assert resp.json()["wbdb_principal_id"] == "bwb-reader"


def test_admin_update_no_fields_422(admin_client, make_user):
    make_user("editme", "editpass123")
    user_id = next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == "editme")
    resp = admin_client.patch(f"/api/admin/users/{user_id}", json={})
    assert resp.status_code == 422


def test_admin_update_unknown_user_404(admin_client):
    resp = admin_client.patch("/api/admin/users/999999", json={"active": False})
    assert resp.status_code == 404


def test_admin_toggle_active_and_admin_flags(admin_client, make_user):
    make_user("target", "targetpass123")
    user_id = next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == "target")

    deactivated = admin_client.patch(f"/api/admin/users/{user_id}", json={"active": False})
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    promoted = admin_client.patch(f"/api/admin/users/{user_id}", json={"is_admin": True})
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True


def test_admin_cannot_deactivate_self(admin_client):
    me = admin_client.get("/api/auth/me").json()
    resp = admin_client.patch(f"/api/admin/users/{me['id']}", json={"active": False})
    assert resp.status_code == 400


def test_admin_cannot_demote_self(admin_client):
    me = admin_client.get("/api/auth/me").json()
    resp = admin_client.patch(f"/api/admin/users/{me['id']}", json={"is_admin": False})
    assert resp.status_code == 400


def test_admin_can_edit_own_principal(admin_client):
    """Die Selbstschutz-Regel gilt nur für active/is_admin, nicht für andere Felder."""
    me = admin_client.get("/api/auth/me").json()
    resp = admin_client.patch(f"/api/admin/users/{me['id']}", json={"wbdb_principal_id": "anon"})
    assert resp.status_code == 200
    assert resp.json()["wbdb_principal_id"] == "anon"


def test_admin_password_reset_then_login(admin_client, client, make_user):
    make_user("resetme", "altespasswort123")
    user_id = next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == "resetme")

    resp = admin_client.post(f"/api/admin/users/{user_id}/password", json={"password": "neuespasswort456"})
    assert resp.status_code == 200

    login_resp = client.post("/api/auth/login", json={"username": "resetme", "password": "neuespasswort456"})
    assert login_resp.status_code == 200

    old_login_resp = client.post("/api/auth/login", json={"username": "resetme", "password": "altespasswort123"})
    assert old_login_resp.status_code == 401


def test_admin_password_reset_empty_422(admin_client, make_user):
    make_user("resetme", "altespasswort123")
    user_id = next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == "resetme")
    resp = admin_client.post(f"/api/admin/users/{user_id}/password", json={"password": ""})
    assert resp.status_code == 422


def test_admin_password_reset_unknown_user_404(admin_client):
    resp = admin_client.post("/api/admin/users/999999/password", json={"password": "irgendwas123"})
    assert resp.status_code == 404


def test_admin_test_principal_requires_nonempty(admin_client):
    resp = admin_client.post("/api/admin/test-principal", json={"principal_id": "   "})
    assert resp.status_code == 422
