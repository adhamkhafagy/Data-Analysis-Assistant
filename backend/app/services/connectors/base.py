from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine


SUPPORTED_TYPES = {"postgresql", "mysql", "sqlserver"}


@dataclass(frozen=True)
class ConnectorConfig:
    database_type: str
    host: str
    port: int
    database_name: str
    username: str
    password: str
    schema_name: str | None = None
    options: dict[str, Any] | None = None

    def validate(self) -> None:
        if self.database_type not in SUPPORTED_TYPES:
            raise ValueError("Unsupported database type")
        if not self.host or len(self.host) > 255:
            raise ValueError("Invalid host")
        if not (1 <= self.port <= 65535):
            raise ValueError("Invalid port")
        if not self.database_name or len(self.database_name) > 255:
            raise ValueError("Invalid database name")
        if not self.username or len(self.username) > 255:
            raise ValueError("Invalid username")
        if len(self.password) > 2048:
            raise ValueError("Invalid password")
        if self.options and (set(self.options) - {"encrypt", "trust_server_certificate"} or any(not isinstance(value, bool) for value in self.options.values())):
            raise ValueError("Unsupported connection options")


class DatabaseConnector(Protocol):
    config: ConnectorConfig

    def engine(self) -> Engine: ...
    def test_connection(self) -> None: ...
    def discover(self, max_tables: int, max_columns: int) -> list[dict[str, Any]]: ...


class SQLAlchemyConnector:
    DRIVER = ""

    def __init__(self, config: ConnectorConfig, connect_timeout: int):
        config.validate()
        self.config = config
        self.connect_timeout = connect_timeout

    def engine(self) -> Engine:
        from sqlalchemy.engine import URL

        query: dict[str, str] = {}
        from app.core.config import get_settings
        tls_mode = get_settings().data_source_tls_mode
        if self.config.database_type == "postgresql":
            query["sslmode"] = {"verify-full": "verify-full", "require": "require", "disable": "disable"}[tls_mode]
        if self.config.database_type == "sqlserver":
            options = self.config.options or {}
            query = {
                "driver": "ODBC Driver 18 for SQL Server",
                "Encrypt": "yes" if tls_mode != "disable" or options.get("encrypt", True) else "no",
                "TrustServerCertificate": "no" if tls_mode == "verify-full" else ("yes" if options.get("trust_server_certificate", False) else "no"),
                "Connection Timeout": str(self.connect_timeout),
            }
        url = URL.create(
            self.DRIVER,
            username=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database_name,
            query=query,
        )
        connect_args = {}
        if self.config.database_type in {"postgresql", "mysql"}:
            connect_args["connect_timeout"] = self.connect_timeout
        if self.config.database_type == "postgresql":
            connect_args["options"] = f"-c statement_timeout={self.connect_timeout * 1000}"
        elif self.config.database_type == "mysql":
            connect_args["read_timeout"] = self.connect_timeout
            connect_args["write_timeout"] = self.connect_timeout
            connect_args["ssl_disabled"] = tls_mode == "disable"
            connect_args["ssl_verify_cert"] = tls_mode == "verify-full"
            connect_args["ssl_verify_identity"] = tls_mode == "verify-full"
        engine = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0, pool_timeout=self.connect_timeout,
                               connect_args=connect_args, hide_parameters=True)
        if self.config.database_type == "sqlserver":
            @event.listens_for(engine, "connect")
            def set_statement_timeout(dbapi_connection, _):
                dbapi_connection.timeout = self.connect_timeout
        return engine

    def test_connection(self) -> None:
        engine = self.engine()
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        finally:
            engine.dispose()

    def _catalog_row_estimate(self, connection, schema: str, table: str) -> int | None:
        if self.config.database_type == "postgresql":
            statement = text("SELECT GREATEST(c.reltuples, 0)::bigint FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relname=:table")
        elif self.config.database_type == "mysql":
            statement = text("SELECT TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA=:schema AND TABLE_NAME=:table")
        elif self.config.database_type == "sqlserver":
            statement = text("SELECT SUM(row_count) FROM sys.dm_db_partition_stats WHERE object_id=OBJECT_ID(QUOTENAME(:schema)+'.'+QUOTENAME(:table)) AND index_id IN (0,1)")
        else:
            return None
        value = connection.execute(statement, {"schema": schema, "table": table}).scalar_one_or_none()
        return int(value) if value is not None else None

    def discover(self, max_tables: int, max_columns: int) -> list[dict[str, Any]]:
        engine = self.engine()
        try:
            inspector = inspect(engine)
            schema = self.config.schema_name
            schemas = [schema] if schema else inspector.get_schema_names()
            records: list[dict[str, Any]] = []
            total_columns = 0
            if not self.config.schema_name:
                schemas = [name for name in schemas if name.lower() not in {"information_schema", "pg_catalog", "mysql", "performance_schema", "sys"} and not name.lower().startswith("pg_toast")]
            for schema_name in schemas:
                for table_info in inspector.get_table_names(schema=schema_name):
                    if len(records) >= max_tables:
                        return records
                    columns = inspector.get_columns(table_info, schema=schema_name)
                    if total_columns + len(columns) > max_columns:
                        continue
                    total_columns += len(columns)
                    pk_names = set(inspector.get_pk_constraint(table_info, schema=schema_name).get("constrained_columns") or [])
                    fk_metadata = inspector.get_foreign_keys(table_info, schema=schema_name)
                    foreign_keys = []
                    fk_by_column: dict[str, str] = {}
                    for fk in fk_metadata:
                        referred = f"{fk.get('referred_schema') or schema_name}.{fk.get('referred_table')}"
                        for local_column, remote_column in zip(fk.get("constrained_columns") or [], fk.get("referred_columns") or []):
                            fk_by_column[local_column] = f"{referred}.{remote_column}"
                        foreign_keys.append({
                            "columns": fk.get("constrained_columns") or [],
                            "referred_schema": fk.get("referred_schema"),
                            "referred_table": fk.get("referred_table"),
                            "referred_columns": fk.get("referred_columns") or [],
                        })
                    row_count_estimate = None
                    try:
                        with engine.connect() as metadata_connection:
                            row_count_estimate = self._catalog_row_estimate(metadata_connection, schema_name, table_info)
                    except Exception:
                        # Catalog estimates are optional and never fall back to scanning business rows.
                        row_count_estimate = None
                    records.append({
                        "schema_name": schema_name,
                        "name": table_info,
                        "table_type": "table",
                        "row_count_estimate": row_count_estimate,
                        "foreign_keys": foreign_keys,
                        "columns": [{
                            "name": column["name"],
                            "data_type": str(column["type"])[:255],
                            "nullable": bool(column.get("nullable", True)),
                            "is_primary_key": column["name"] in pk_names,
                            "foreign_key": fk_by_column.get(column["name"]),
                            "profile": {},
                        } for column in columns],
                    })
            return records
        finally:
            engine.dispose()


class PostgreSQLConnector(SQLAlchemyConnector):
    DRIVER = "postgresql+psycopg"


class MySQLConnector(SQLAlchemyConnector):
    DRIVER = "mysql+pymysql"


class SQLServerConnector(SQLAlchemyConnector):
    DRIVER = "mssql+pyodbc"
