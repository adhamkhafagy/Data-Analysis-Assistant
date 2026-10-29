from unittest.mock import patch
from types import SimpleNamespace

from pydantic import SecretStr

from sqlalchemy import create_engine, event

from app.core.crypto import CredentialCipher
from app.core.database import get_db
from app.models.data_source import DataSource
from app.services.connectors.base import ConnectorConfig
from app.services.connectors.network_policy import NetworkPolicyError, validate_destination
from app.services.connectors.base import PostgreSQLConnector
from app.services.ai.profile import generate_business_profile, profile_context
from app.services.connectors.factory import create_connector
from app.core.config import Settings
from pydantic import ValidationError


def create_workspace(client, email="owner@example.com"):
    client.post("/api/v1/auth/register", json={"name": "Owner", "email": email, "password": "a-very-strong-password"})
    return client.post("/api/v1/workspaces", json={"name": "Operations"}).json()["id"]


def create_source(client, workspace_id, name="Warehouse"):
    return client.post(f"/api/v1/workspaces/{workspace_id}/data-sources", json={
        "name": name, "database_type": "postgresql", "host": "192.0.2.10", "port": 5432,
        "database_name": "analytics", "username": "reader", "password": "distinct-secret-value",
    })


def test_encryption_round_trip_and_invalid_key():
    cipher = CredentialCipher("F6XUchQdlEmSn9TumuNFv8HSnLjpfLDshyF8Du-KJ-A=")
    encrypted = cipher.encrypt("secret")
    assert encrypted != "secret"
    assert "secret" not in encrypted
    assert cipher.decrypt(encrypted) == "secret"
    try:
        CredentialCipher("bad-key")
    except ValueError:
        pass
    else:
        assert False, "Invalid Fernet key must fail safely"


def test_source_responses_hide_credentials_and_metadata(client):
    workspace_id = create_workspace(client)
    response = create_source(client, workspace_id)
    assert response.status_code == 201
    body = response.json()
    assert "encrypted_password" not in body and "password" not in body
    assert body["status"] == "not_tested"
    assert "distinct-secret-value" not in response.text
    sources = client.get(f"/api/v1/workspaces/{workspace_id}/data-sources")
    assert sources.status_code == 200 and len(sources.json()) == 1
    assert "distinct-secret-value" not in sources.text
    db = next(client.app.dependency_overrides[get_db]())
    stored = db.query(DataSource).filter_by(id=body["id"]).one()
    assert stored.encrypted_password != "distinct-secret-value"
    assert CredentialCipher().decrypt(stored.encrypted_password) == "distinct-secret-value"
    db.close()


def test_owner_can_update_test_and_delete_source_with_sanitized_failure(client):
    workspace_id = create_workspace(client)
    response = create_source(client, workspace_id)
    source_id = response.json()["id"]
    updated = client.patch(f"/api/v1/data-sources/{source_id}", json={"name": "Reporting replica", "host": "8.8.8.8"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Reporting replica"
    assert updated.json()["status"] == "not_tested"

    class BrokenConnector:
        def test_connection(self):
            raise RuntimeError("database password distinct-secret-value at internal host")

    with patch("app.services.data_sources.create_connector", return_value=BrokenConnector()):
        tested = client.post(f"/api/v1/data-sources/{source_id}/test-connection")
    assert tested.status_code == 200
    assert tested.json()["status"] == "failed"
    assert "distinct-secret-value" not in tested.text
    assert "internal host" not in tested.text
    assert tested.json()["safe_error_code"] == "connection_failed"
    assert client.delete(f"/api/v1/data-sources/{source_id}").status_code == 204
    assert client.get(f"/api/v1/data-sources/{source_id}").status_code == 404


def test_data_source_ownership_all_routes(client):
    workspace_id = create_workspace(client)
    source_id = create_source(client, workspace_id).json()["id"]
    client.post("/api/v1/auth/logout")
    other_workspace = create_workspace(client, "other@example.com")
    assert client.get(f"/api/v1/data-sources/{source_id}").status_code == 404
    assert client.patch(f"/api/v1/data-sources/{source_id}", json={"name": "Changed"}).status_code == 404
    assert client.post(f"/api/v1/data-sources/{source_id}/test-connection").status_code == 404
    assert client.post(f"/api/v1/data-sources/{source_id}/discover").status_code == 404
    assert client.post(f"/api/v1/data-sources/{source_id}/refresh").status_code == 404
    assert client.get(f"/api/v1/data-sources/{source_id}/schema").status_code == 404
    assert client.get(f"/api/v1/data-sources/{source_id}/business-profile").status_code == 404
    assert client.get(f"/api/v1/workspaces/{other_workspace}/data-sources").json() == []
    assert client.delete(f"/api/v1/data-sources/{source_id}").status_code == 404


def test_missing_auth_rejected_and_input_validation(client):
    assert client.get("/api/v1/workspaces/1/data-sources").status_code == 401
    for method, path in [("get", "/api/v1/data-sources/1"), ("patch", "/api/v1/data-sources/1"),
                         ("delete", "/api/v1/data-sources/1"), ("post", "/api/v1/data-sources/1/test-connection"),
                         ("post", "/api/v1/data-sources/1/discover"), ("post", "/api/v1/data-sources/1/refresh"),
                         ("get", "/api/v1/data-sources/1/schema"), ("get", "/api/v1/data-sources/1/business-profile")]:
        assert getattr(client, method)(path).status_code == 401
    client.post("/api/v1/auth/register", json={"name": "Owner", "email": "owner@example.com", "password": "a-very-strong-password"})
    invalid = client.post("/api/v1/workspaces/1/data-sources", json={
        "name": "Broken", "database_type": "sqlite", "host": "localhost", "port": 70000,
        "database_name": "x", "username": "x", "password": "x",
    })
    assert invalid.status_code == 422


def test_connector_rejects_unsupported_type_and_invalid_port():
    for config in (ConnectorConfig("sqlite", "localhost", 5432, "db", "u", "p"),
                   ConnectorConfig("postgresql", "localhost", 0, "db", "u", "p")):
        try:
            config.validate()
        except ValueError:
            pass
        else:
            assert False, "Invalid connector configuration must be rejected"


def test_factory_builds_supported_adapters_without_connecting():
    configs = [ConnectorConfig("postgresql", "203.0.113.10", 5432, "db", "reader", "pw"),
               ConnectorConfig("mysql", "203.0.113.10", 3306, "db", "reader", "pw"),
               ConnectorConfig("sqlserver", "203.0.113.10", 1433, "db", "reader", "pw")]
    assert [type(create_connector(config)).__name__ for config in configs] == ["PostgreSQLConnector", "MySQLConnector", "SQLServerConnector"]


def test_connection_engine_disposed_when_connect_raises():
    connector = PostgreSQLConnector(ConnectorConfig("postgresql", "203.0.113.10", 5432, "db", "reader", "pw"), 2)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def exec_driver_sql(self, _):
            raise RuntimeError("network failed")

    class FakeEngine:
        disposed = False

        def connect(self):
            return FakeConnection()

        def dispose(self):
            self.disposed = True

    engine = FakeEngine()
    with patch.object(connector, "engine", return_value=engine):
        try:
            connector.test_connection()
        except RuntimeError:
            pass
    assert engine.disposed


def test_policy_blocks_loopback_by_default(monkeypatch):
    with patch("app.services.connectors.network_policy.get_settings") as settings:
        settings.return_value.app_env = "production"
        settings.return_value.data_source_allowed_hosts = ""
        settings.return_value.data_source_allowed_cidrs = "10.0.0.0/8"
        settings.return_value.data_source_allow_localhost = False
        settings.return_value.data_source_allow_private_networks = False
        try:
            validate_destination("127.0.0.1")
        except NetworkPolicyError:
            pass
        else:
            assert False, "Loopback must be blocked"


def test_metadata_discovery_uses_inspection_without_fetching_rows(tmp_path):
    database = tmp_path / "metadata.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id))")
        connection.exec_driver_sql("INSERT INTO customers VALUES (1, 'private@example.test')")
    engine.dispose()
    statements = []

    class SQLiteMetadataConnector(PostgreSQLConnector):
        def engine(self):
            result = create_engine(f"sqlite:///{database}")
            event.listen(result, "before_cursor_execute", lambda conn, cursor, statement, params, context, many: statements.append(statement))
            return result

        def _catalog_row_estimate(self, connection, schema, table):
            return None

    config = ConnectorConfig("postgresql", "192.0.2.10", 5432, "metadata", "reader", "secret")
    tables = SQLiteMetadataConnector(config, 2).discover(max_tables=10, max_columns=20)
    assert {table["name"] for table in tables} == {"customers", "orders"}
    assert any(column["is_primary_key"] for table in tables for column in table["columns"])
    assert any(column["foreign_key"] for table in tables for column in table["columns"])
    assert all("private@example.test" not in str(table) for table in tables)
    normalized = " ".join(statements).lower()
    assert "select * from customers" not in normalized and 'select * from "orders"' not in normalized
    assert "from customers" not in normalized and "from orders" not in normalized


def test_ai_profile_only_receives_schema_metadata_and_missing_key_degrades(monkeypatch):
    source = SimpleNamespace(tables=[SimpleNamespace(schema_name="public", name="orders", table_type="table", foreign_keys=[], columns=[SimpleNamespace(name="order_id", data_type="INTEGER", nullable=False, is_primary_key=True, foreign_key=None, profile={})])])
    context = profile_context(source)
    assert "metadata_only" in context and "orders" in context and "password" not in context
    with patch("app.services.ai.profile.get_settings", return_value=SimpleNamespace(ai_provider="groq", groq_api_key=SecretStr(""))), patch("app.services.ai.profile.GroqProvider") as provider:
        state, profile, message = generate_business_profile(source)
    assert state == "not_configured" and profile is None and "not configured" in message
    provider.assert_not_called()


def test_missing_or_invalid_encryption_key_fails_configuration():
    for key in ("", "not-a-fernet-key"):
        try:
            Settings(_env_file=None, session_secret="test-session-secret-long-enough-123456", data_source_encryption_key=key, app_env="test")
        except ValidationError:
            continue
        assert False, "Missing or invalid encryption key must fail closed"


def test_invalid_ai_profile_response_does_not_create_success():
    source = SimpleNamespace(tables=[])
    settings = SimpleNamespace(ai_provider="groq", groq_api_key=SecretStr("configured"))
    with patch("app.services.ai.profile.get_settings", return_value=settings), patch("app.services.ai.profile.GroqProvider") as provider:
        provider.return_value.generate_structured_profile.return_value = '{"business_domain_hypothesis":"fabricated incomplete"}'
        state, profile, message = generate_business_profile(source)
    assert state == "failed" and profile is None and message
