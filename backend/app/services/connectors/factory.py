from app.services.connectors.base import (
    ConnectorConfig, DatabaseConnector, MySQLConnector, PostgreSQLConnector, SQLServerConnector,
)
from app.core.config import get_settings


def create_connector(config: ConnectorConfig) -> DatabaseConnector:
    config.validate()
    settings = get_settings()
    cls = {"postgresql": PostgreSQLConnector, "mysql": MySQLConnector, "sqlserver": SQLServerConnector}.get(config.database_type)
    if cls is None:
        raise ValueError("Unsupported database type")
    return cls(config, settings.data_source_connect_timeout_seconds)
