def register(client, email="one@example.com", name="One User", password="a-very-strong-password"):
    return client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})


def test_register_login_me_logout(client):
    created = register(client)
    assert created.status_code == 201
    assert "password_hash" not in created.json()
    assert "httponly" in created.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["email"] == "one@example.com"
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "one@example.com", "password": "a-very-strong-password"})
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_duplicate_and_invalid_credentials(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    client.post("/api/v1/auth/logout")
    bad = client.post("/api/v1/auth/login", json={"email": "one@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_workspaces_and_ownership(client):
    assert client.get("/api/v1/workspaces").status_code == 401
    assert register(client, "one@example.com").status_code == 201
    workspace = client.post("/api/v1/workspaces", json={"name": "  Revenue team  "})
    assert workspace.status_code == 201
    item = workspace.json()
    assert item["name"] == "Revenue team"
    workspace_id = item["id"]
    assert client.get(f"/api/v1/workspaces/{workspace_id}").status_code == 200
    assert client.patch(f"/api/v1/workspaces/{workspace_id}", json={"name": "Growth"}).json()["name"] == "Growth"
    assert client.get("/api/v1/workspaces").json()[0]["name"] == "Growth"

    client.post("/api/v1/auth/logout")
    register(client, "two@example.com", "Two User")
    assert client.get(f"/api/v1/workspaces/{workspace_id}").status_code == 404
    assert client.patch(f"/api/v1/workspaces/{workspace_id}", json={"name": "Hijack"}).status_code == 404
    assert client.delete(f"/api/v1/workspaces/{workspace_id}").status_code == 404
    assert client.get("/api/v1/workspaces").json() == []

    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"email": "one@example.com", "password": "a-very-strong-password"}).status_code == 200
    assert client.delete(f"/api/v1/workspaces/{workspace_id}").status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace_id}").status_code == 404


def test_validation(client):
    assert client.post("/api/v1/auth/register", json={"name": "X", "email": "bad", "password": "short"}).status_code == 422
    register(client)
    assert client.post("/api/v1/workspaces", json={"name": "  "}).status_code == 422

