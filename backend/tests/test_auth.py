def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_register_login_me(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert "password" not in r.text
    tok = client.post("/api/v1/auth/login", data={"username": "a@b.com", "password": "password123"})
    assert tok.status_code == 200
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
    assert me.json()["email"] == "a@b.com"


def test_bad_login_and_no_token(client):
    client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert client.post("/api/v1/auth/login", data={"username": "a@b.com", "password": "wrong"}).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_duplicate_email(client):
    body = {"email": "a@b.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=body)
    assert client.post("/api/v1/auth/register", json=body).status_code == 409
