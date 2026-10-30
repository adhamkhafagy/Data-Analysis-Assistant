from helpers import create_workspace, register_and_login


PASSWORD = "a-very-strong-password"


def make_dataset(client, workspace_id, *, name="Quarterly results", rows=None, columns=None):
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets",
        json={
            "name": name,
            "columns": columns or [
                {"name": "label", "type": "text", "nullable": False},
                {"name": "amount", "type": "integer", "nullable": False},
            ],
            "rows": rows or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def prepare_user_workspace(client, email="dataset-owner@example.com"):
    register_and_login(client, email, PASSWORD)
    return create_workspace(client, "Analytics")


def test_create_dataset_and_read_it_and_its_rows(client):
    # Creates a typed dataset with initial rows, then checks its detail and row values.
    workspace = prepare_user_workspace(client)
    dataset = make_dataset(
        client,
        workspace["id"],
        rows=[{"label": "North", "amount": 12}, {"label": "South", "amount": 8}],
    )

    detail = client.get(f"/api/v1/datasets/{dataset['id']}")
    assert detail.status_code == 200
    assert detail.json()["row_count"] == 2
    assert detail.json()["name"] == "Quarterly results"

    rows = client.get(f"/api/v1/datasets/{dataset['id']}/rows")
    assert rows.status_code == 200
    assert {row["label"]: row["amount"] for row in rows.json()} == {"North": 12, "South": 8}


def test_rows_support_limit_and_offset_pagination(client):
    # Checks pagination pages cover the complete ID-sorted row set without duplicates.
    workspace = prepare_user_workspace(client, "pagination-owner@example.com")
    dataset = make_dataset(client, workspace["id"], rows=[{"label": f"row-{n}", "amount": n} for n in range(1, 11)])

    path = f"/api/v1/datasets/{dataset['id']}/rows"
    full_response = client.get(f"{path}?limit=1000")
    assert full_response.status_code == 200
    full_rows = full_response.json()
    full_ids = [row["id"] for row in full_rows]
    assert full_ids == sorted(full_ids)

    pages = []
    for offset in (0, 3, 6, 9):
        response = client.get(f"{path}?limit=3&offset={offset}")
        assert response.status_code == 200
        pages.append(response.json())

    assert [len(page) for page in pages] == [3, 3, 3, 1]
    page_ids = [row["id"] for page in pages for row in page]
    assert len(page_ids) == len(set(page_ids))
    assert set(page_ids) == set(full_ids)


def test_rows_can_be_added_updated_and_deleted_with_row_count_updates(client):
    # Exercises row create, update, and delete while checking the dataset row count after each write.
    workspace = prepare_user_workspace(client, "crud-owner@example.com")
    dataset = make_dataset(client, workspace["id"], rows=[{"label": "first", "amount": 1}])
    path = f"/api/v1/datasets/{dataset['id']}"

    added = client.post(f"{path}/rows", json={"rows": [{"label": "second", "amount": 2}]})
    assert added.status_code == 201
    assert added.json()["row_count"] == 2

    rows = client.get(f"{path}/rows").json()
    second = next(row for row in rows if row["label"] == "second")
    updated = client.patch(f"{path}/rows/{second['id']}", json={"values": {"amount": 7}})
    assert updated.status_code == 204
    assert client.get(f"{path}/rows").json()
    updated_row = next(row for row in client.get(f"{path}/rows").json() if row["id"] == second["id"])
    assert updated_row["amount"] == 7
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["row_count"] == 2

    removed = client.delete(f"{path}/rows/{second['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["row_count"] == 1


def prepare_validation_dataset(client, email):
    workspace = prepare_user_workspace(client, email)
    dataset = make_dataset(
        client,
        workspace["id"],
        rows=[{"label": "kept", "amount": 4}],
        columns=[
            {"name": "label", "type": "text", "nullable": False},
            {"name": "amount", "type": "integer", "nullable": False},
        ],
    )
    path = f"/api/v1/datasets/{dataset['id']}"
    row_id = client.get(f"{path}/rows").json()[0]["id"]
    return path, row_id


def test_patch_unknown_column_returns_422_and_names_column(client):
    # Checks that PATCH rejects and identifies an unknown column.
    path, row_id = prepare_validation_dataset(client, "unknown-column@example.com")
    response = client.patch(f"{path}/rows/{row_id}", json={"values": {"unknown": "x"}})
    assert response.status_code == 422
    assert "unknown" in response.text


def test_patch_empty_values_returns_422_and_names_values_field(client):
    # Checks that PATCH rejects an empty values mapping and identifies that field.
    path, row_id = prepare_validation_dataset(client, "empty-patch@example.com")
    response = client.patch(f"{path}/rows/{row_id}", json={"values": {}})
    assert response.status_code == 422
    assert "values" in response.text


def test_patch_wrong_value_type_returns_422_and_names_column(client):
    # Checks that PATCH rejects an invalid integer and identifies its column.
    path, row_id = prepare_validation_dataset(client, "wrong-type@example.com")
    response = client.patch(f"{path}/rows/{row_id}", json={"values": {"amount": "not-an-integer"}})
    assert response.status_code == 422
    assert "amount" in response.text


def test_add_null_to_non_nullable_column_returns_422_and_names_column(client):
    # Checks that inserting null into a required column returns a field-specific validation error.
    path, _ = prepare_validation_dataset(client, "null-required@example.com")
    response = client.post(f"{path}/rows", json={"rows": [{"label": "null amount", "amount": None}]})
    assert response.status_code == 422
    assert "amount" in response.text


def test_add_more_than_1000_rows_returns_422_and_names_rows_field(client):
    # Checks that a batch over the API row limit is rejected and identifies the rows field.
    path, _ = prepare_validation_dataset(client, "oversized-batch@example.com")
    oversized = [{"label": f"row-{n}", "amount": n} for n in range(1001)]
    response = client.post(f"{path}/rows", json={"rows": oversized})
    assert response.status_code == 422
    assert "rows" in response.text


def test_second_user_cannot_access_or_delete_another_users_dataset(client):
    # Verifies dataset detail, rows, history, and delete are all workspace-owner scoped.
    workspace = prepare_user_workspace(client, "first-owner@example.com")
    dataset = make_dataset(client, workspace["id"], rows=[{"label": "private", "amount": 3}])
    client.post("/api/v1/auth/logout")
    register_and_login(client, "second-owner@example.com", PASSWORD)
    path = f"/api/v1/datasets/{dataset['id']}"

    assert client.get(path).status_code == 404
    assert client.get(f"{path}/rows").status_code == 404
    assert client.get(f"{path}/history").status_code == 404
    assert client.delete(path).status_code == 404


def test_dataset_routes_reject_unauthenticated_requests(client):
    # Checks that dataset reads, writes, history, and deletion require a logged-in session.
    dataset_id = 1
    path = f"/api/v1/datasets/{dataset_id}"

    assert client.get(path).status_code == 401
    assert client.get(f"{path}/rows").status_code == 401
    assert client.get(f"{path}/history").status_code == 401
    assert client.post(f"{path}/rows", json={"rows": []}).status_code == 401
    assert client.delete(path).status_code == 401


def test_history_records_create_add_update_and_delete_revisions(client):
    # Checks that each successful dataset or row mutation creates a new revision.
    workspace = prepare_user_workspace(client, "history-owner@example.com")
    dataset = make_dataset(client, workspace["id"], rows=[{"label": "initial", "amount": 1}])
    path = f"/api/v1/datasets/{dataset['id']}"
    row_id = client.get(f"{path}/rows").json()[0]["id"]

    assert client.post(f"{path}/rows", json={"rows": [{"label": "added", "amount": 2}]}).status_code == 201
    assert client.patch(f"{path}/rows/{row_id}", json={"values": {"amount": 3}}).status_code == 204
    assert client.delete(f"{path}/rows/{row_id}").status_code == 204

    history = client.get(f"{path}/history")
    assert history.status_code == 200
    revisions = history.json()["revisions"]
    assert [revision["version"] for revision in revisions] == [4, 3, 2, 1]
    assert [revision["row_count"] for revision in revisions] == [1, 2, 2, 1]
    assert {run["operation"] for run in history.json()["runs"]} == {
        "manual_create", "manual_edit", "manual_update", "manual_delete"
    }


def test_dataset_delete_returns_204_and_then_detail_is_not_found(client):
    # Checks that deleting a managed dataset succeeds and removes its catalog record.
    workspace = prepare_user_workspace(client, "delete-owner@example.com")
    dataset = make_dataset(client, workspace["id"])
    path = f"/api/v1/datasets/{dataset['id']}"

    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
