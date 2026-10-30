import io
import json

import pytest

from app.core.config import get_settings
from helpers import create_workspace, register_and_login


PASSWORD = "a-very-strong-password"


def prepare_upload_workspace(client, monkeypatch, tmp_path, email):
    monkeypatch.setattr(get_settings(), "upload_staging_dir", str(tmp_path / "uploads"))
    register_and_login(client, email, PASSWORD)
    return create_workspace(client, "Upload tests")


def upload_file(client, workspace_id, filename, content, content_type="text/csv"):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/uploads",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def csv_preview_body():
    return (
        "name,count,price,active,day\n"
        "Alice,1,1.25,true,2026-10-28\n"
        "Bob,2,2.50,false,2026-10-29\n"
    ).encode("utf-8")


def test_csv_upload_preview_infers_types_and_returns_sample_rows(client, monkeypatch, tmp_path):
    # Checks CSV upload preview columns, inferred types, sample values, and row count.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "csv-preview@example.com")
    uploaded = upload_file(client, workspace["id"], "metrics.csv", csv_preview_body())
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    result = preview.json()
    assert result["rows"] == [
        {"name": "Alice", "count": "1", "price": "1.25", "active": "true", "day": "2026-10-28"},
        {"name": "Bob", "count": "2", "price": "2.50", "active": "false", "day": "2026-10-29"},
    ]
    assert result["total_rows"] == 2
    assert {column["name"]: column["type"] for column in result["columns"]} == {
        "name": "text",
        "count": "integer",
        "price": "decimal",
        "active": "boolean",
        "day": "date",
    }


def test_json_upload_preview_infers_types_and_returns_sample_rows(client, monkeypatch, tmp_path):
    # Checks JSON array preview columns, inferred types, sample values, and row count.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "json-preview@example.com")
    records = [
        {"name": "Alice", "count": 1, "price": 1.25, "active": True, "day": "2026-10-28"},
        {"name": "Bob", "count": 2, "price": 2.5, "active": False, "day": "2026-10-29"},
    ]
    uploaded = upload_file(client, workspace["id"], "metrics.json", json.dumps(records).encode("utf-8"), "application/json")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    result = preview.json()
    assert result["rows"] == records
    assert result["total_rows"] == 2
    assert {column["name"]: column["type"] for column in result["columns"]} == {
        "name": "text",
        "count": "integer",
        "price": "decimal",
        "active": "boolean",
        "day": "date",
    }


def test_csv_upload_keeps_eight_digit_ids_as_integer(client, monkeypatch, tmp_path):
    # Checks an eight-digit numeric CSV identifier is inferred as an integer.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "eight-digit-id@example.com")
    uploaded = upload_file(client, workspace["id"], "ids.csv", b"id\n20261028\n")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert {column["name"]: column["type"] for column in preview.json()["columns"]} == {"id": "integer"}


def test_csv_upload_infers_mixed_integer_and_fractional_values_as_decimal(client, monkeypatch, tmp_path):
    # Checks CSV values containing a fraction and a whole number are inferred as decimal.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "mixed-decimal-csv@example.com")
    uploaded = upload_file(client, workspace["id"], "amounts.csv", b"amount\n1.5\n2\n")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert {column["name"]: column["type"] for column in preview.json()["columns"]} == {"amount": "decimal"}


def test_json_upload_infers_mixed_integer_and_float_values_as_decimal(client, monkeypatch, tmp_path):
    # Checks native JSON integer and fractional float values are inferred as decimal.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "mixed-decimal-json@example.com")
    records = [{"amount": 1}, {"amount": 2.5}]
    uploaded = upload_file(client, workspace["id"], "amounts.json", json.dumps(records).encode("utf-8"), "application/json")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert {column["name"]: column["type"] for column in preview.json()["columns"]} == {"amount": "decimal"}


def test_csv_upload_infers_true_false_strings_as_boolean(client, monkeypatch, tmp_path):
    # Checks the supported true/false CSV strings are inferred as boolean.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "boolean-strings@example.com")
    uploaded = upload_file(client, workspace["id"], "flags.csv", b"active\ntrue\nfalse\n")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert {column["name"]: column["type"] for column in preview.json()["columns"]} == {"active": "boolean"}


def test_csv_upload_infers_mixed_date_and_text_as_text(client, monkeypatch, tmp_path):
    # Checks a column mixing an ISO date with ordinary text is inferred as text.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "mixed-date-text@example.com")
    uploaded = upload_file(client, workspace["id"], "events.csv", b"event\n2026-10-28\nnot-a-date\n")
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert {column["name"]: column["type"] for column in preview.json()["columns"]} == {"event": "text"}


def test_csv_import_creates_dataset_rows_and_invalidates_preview(client, monkeypatch, tmp_path):
    # Checks new-dataset import, imported values and count, and staged-upload invalidation.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "csv-import@example.com")
    uploaded = upload_file(client, workspace["id"], "members.csv", b"name,count\nAda,3\nLin,5\n")
    assert uploaded.status_code == 201, uploaded.text

    imported = client.post(f"/api/v1/uploads/{uploaded.json()['id']}/import", json={"name": "Members"})
    assert imported.status_code == 201, imported.text
    dataset = client.get(f"/api/v1/datasets/{imported.json()['id']}")
    assert dataset.status_code == 200
    assert dataset.json()["row_count"] == 2
    rows = client.get(f"/api/v1/datasets/{imported.json()['id']}/rows")
    assert rows.status_code == 200
    assert {(row["name"], row["count"]) for row in rows.json()} == {("Ada", 3), ("Lin", 5)}
    assert client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview").status_code == 404


def test_csv_import_column_mapping_renames_column(client, monkeypatch, tmp_path):
    # Checks import mapping renames a source column in the managed dataset schema and rows.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "mapping-import@example.com")
    uploaded = upload_file(client, workspace["id"], "contacts.csv", b"source_name,score\nMina,8\n")
    assert uploaded.status_code == 201, uploaded.text

    imported = client.post(
        f"/api/v1/uploads/{uploaded.json()['id']}/import",
        json={
            "name": "Renamed contacts",
            "mapping": {
                "source_name": {"name": "contact", "type": "text", "nullable": False},
                "score": {"name": "rating", "type": "integer", "nullable": False},
            },
        },
    )
    assert imported.status_code == 201, imported.text
    rows = client.get(f"/api/v1/datasets/{imported.json()['id']}/rows")
    assert rows.status_code == 200
    assert rows.json()[0]["contact"] == "Mina"
    assert rows.json()[0]["rating"] == 8
    assert "source_name" not in rows.json()[0]


def test_csv_append_import_sums_rows_and_rejects_mismatched_schema(client, monkeypatch, tmp_path):
    # Checks append into a matching schema and reports the response status for a mismatch.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "append-import@example.com")
    first = upload_file(client, workspace["id"], "first.csv", b"name,count\nAda,1\n")
    assert first.status_code == 201, first.text
    created = client.post(f"/api/v1/uploads/{first.json()['id']}/import", json={"name": "People"})
    assert created.status_code == 201, created.text
    dataset_id = created.json()["id"]

    second = upload_file(client, workspace["id"], "second.csv", b"name,count\nLin,2\nSol,3\n")
    assert second.status_code == 201, second.text
    appended = client.post(
        f"/api/v1/uploads/{second.json()['id']}/import",
        json={"dataset_id": dataset_id, "append": True},
    )
    assert appended.status_code == 201, appended.text
    assert client.get(f"/api/v1/datasets/{dataset_id}").json()["row_count"] == 3

    mismatch = upload_file(client, workspace["id"], "mismatch.csv", b"name,other\nTao,4\n")
    assert mismatch.status_code == 201, mismatch.text
    mismatched_import = client.post(
        f"/api/v1/uploads/{mismatch.json()['id']}/import",
        json={"dataset_id": dataset_id, "append": True},
    )
    assert mismatched_import.status_code == 422


def test_upload_rejects_unsupported_extension_with_415(client, monkeypatch, tmp_path):
    # Checks the endpoint rejects a file extension outside the supported formats.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "unsupported-file@example.com")
    response = upload_file(client, workspace["id"], "notes.txt", b"plain text")
    assert response.status_code == 415


def test_upload_rejects_empty_file_with_422(client, monkeypatch, tmp_path):
    # Checks an empty supported file is rejected with 422.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "empty-file@example.com")
    response = upload_file(client, workspace["id"], "empty.csv", b"")
    assert response.status_code == 422


def test_upload_rejects_bytes_over_configured_limit_with_413(client, monkeypatch, tmp_path):
    # Checks upload size enforcement using a tiny per-test limit and in-memory bytes.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "oversize-file@example.com")
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 4)
    response = upload_file(client, workspace["id"], "large.csv", b"12345")
    assert response.status_code == 413


def test_preview_rejects_csv_over_configured_row_limit_with_413(client, monkeypatch, tmp_path):
    # Checks preview rejects a CSV containing more records than its configured row limit.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "row-limit@example.com")
    monkeypatch.setattr(get_settings(), "upload_max_rows", 2)
    uploaded = upload_file(client, workspace["id"], "too-many.csv", b"name\na\nb\nc\n")
    assert uploaded.status_code == 201, uploaded.text
    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 413


def test_preview_rejects_duplicate_csv_headers_with_422(client, monkeypatch, tmp_path):
    # Checks duplicate headers are rejected during CSV preview.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "duplicate-header@example.com")
    uploaded = upload_file(client, workspace["id"], "duplicate.csv", b"value,value\n1,2\n")
    assert uploaded.status_code == 201, uploaded.text
    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 422


def test_preview_rejects_empty_csv_header_with_422(client, monkeypatch, tmp_path):
    # Checks an empty header is rejected during CSV preview.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "empty-header@example.com")
    uploaded = upload_file(client, workspace["id"], "empty-header.csv", b",value\n,2\n")
    assert uploaded.status_code == 201, uploaded.text
    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 422


@pytest.mark.parametrize(
    "filename",
    ["../../evil.csv", r"C:\Windows\evil.csv"],
    ids=["unix-traversal", "windows-path"],
)
def test_upload_filename_is_stored_without_path_separators(client, monkeypatch, tmp_path, filename):
    # Checks traversal-like and Windows client filenames are reduced to safe basenames.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, f"filename-{len(filename)}@example.com")
    response = upload_file(client, workspace["id"], filename, b"name\nvalue\n")
    assert response.status_code == 201, response.text
    stored = response.json()["original_filename"]
    assert stored == "evil.csv"
    assert "/" not in stored
    assert "\\" not in stored


def test_second_user_cannot_preview_or_import_another_users_upload(client, monkeypatch, tmp_path):
    # Checks an upload is workspace-owner scoped for preview and import operations.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "upload-owner@example.com")
    uploaded = upload_file(client, workspace["id"], "private.csv", b"name\nsecret\n")
    assert uploaded.status_code == 201, uploaded.text
    client.post("/api/v1/auth/logout")
    register_and_login(client, "other-upload-user@example.com", PASSWORD)

    upload_id = uploaded.json()["id"]
    assert client.get(f"/api/v1/uploads/{upload_id}/preview").status_code == 404
    assert client.post(f"/api/v1/uploads/{upload_id}/import", json={"name": "Stolen"}).status_code == 404


def test_upload_preview_and_import_require_authentication(client):
    # Checks unauthenticated preview and import requests are rejected with 401.
    assert client.get("/api/v1/uploads/1/preview").status_code == 401
    assert client.post("/api/v1/uploads/1/import", json={"name": "No auth"}).status_code == 401


def test_utf8_bom_csv_preserves_arabic_headers_and_values(client, monkeypatch, tmp_path):
    # Checks UTF-8 BOM handling preserves Arabic CSV headers and cell values.
    workspace = prepare_upload_workspace(client, monkeypatch, tmp_path, "arabic-bom@example.com")
    content = "\ufeffالمدينة,القيمة\nالقاهرة,١٢\nالإسكندرية,٢٥\n".encode("utf-8")
    uploaded = upload_file(client, workspace["id"], "arabic.csv", content)
    assert uploaded.status_code == 201, uploaded.text

    preview = client.get(f"/api/v1/uploads/{uploaded.json()['id']}/preview")
    assert preview.status_code == 200
    assert [column["name"] for column in preview.json()["columns"]] == ["المدينة", "القيمة"]
    assert preview.json()["rows"] == [
        {"المدينة": "القاهرة", "القيمة": "١٢"},
        {"المدينة": "الإسكندرية", "القيمة": "٢٥"},
    ]
