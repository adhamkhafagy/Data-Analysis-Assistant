def register_and_login(client, email, password):
    name = email.split("@", 1)[0].replace(".", " ").title() or "Test User"
    response = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response


def create_workspace(client, name):
    response = client.post("/api/v1/workspaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()
