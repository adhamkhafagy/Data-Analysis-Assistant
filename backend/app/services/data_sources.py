import logging
import hashlib
import threading
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import CredentialCipher
from app.models.data_source import DataSource
from app.models.discovered_column import DiscoveredColumn
from app.models.discovered_table import DiscoveredTable
from app.models.dataset import Dataset
from app.repositories.data_sources import owned, with_tables
from app.repositories.workspaces import get_for_owner
from app.schemas.data_source import DataSourceCreate, DataSourceUpdate
from app.services.ai.profile import generate_business_profile
from app.services.connectors.base import ConnectorConfig
from app.services.connectors.factory import create_connector
from app.services.connectors.network_policy import NetworkPolicyError, validate_destination

logger = logging.getLogger(__name__)
_job_slots = threading.BoundedSemaphore(get_settings().data_source_max_concurrent_jobs)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")


def owned_source(db: Session, source_id: int, owner_id: int) -> DataSource:
    source = owned(db, source_id, owner_id)
    if source is None:
        raise _not_found()
    return source


def connector_for(source: DataSource):
    validate_destination(source.host)
    password = CredentialCipher().decrypt(source.encrypted_password)
    config = ConnectorConfig(
        database_type=source.database_type, host=source.host, port=source.port,
        database_name=source.database_name, username=source.username, password=password,
        schema_name=source.schema_name, options=source.options,
    )
    return create_connector(config)


def create_source(db: Session, workspace_id: int, owner_id: int, body: DataSourceCreate) -> DataSource:
    if not get_for_owner(db, workspace_id, owner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    try:
        cipher = CredentialCipher()
    except ValueError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Data-source credential encryption is unavailable") from None
    source = DataSource(
        workspace_id=workspace_id, name=body.name, database_type=body.database_type,
        host=body.host, port=body.port, database_name=body.database_name,
        schema_name=body.schema_name, username=body.username,
        encrypted_password=cipher.encrypt(body.password), options=body.options,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source: DataSource, body: DataSourceUpdate) -> DataSource:
    values = body.model_dump(exclude_unset=True)
    password = values.pop("password", None)
    if password is not None:
        try:
            values["encrypted_password"] = CredentialCipher().encrypt(password)
        except ValueError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Data-source credential encryption is unavailable") from None
    for key, value in values.items():
        setattr(source, key, value)
    source.status = "not_tested"
    source.discovery_status = "not_discovered"
    source.safe_error_code = None
    source.safe_error_message = None
    source.profile_json = None
    db.query(DiscoveredTable).filter(DiscoveredTable.data_source_id == source.id).delete(synchronize_session=False)
    db.commit()
    db.refresh(source)
    return source


def test_source(db: Session, source: DataSource) -> DataSource:
    if not _job_slots.acquire(blocking=False):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Connection test capacity is busy; retry shortly")
    source.last_tested_at = datetime.now(timezone.utc)
    try:
        connector_for(source).test_connection()
        source.status = "connected"
        source.safe_error_code = None
        source.safe_error_message = None
    except NetworkPolicyError:
        source.status = "failed"
        source.safe_error_code = "destination_blocked"
        source.safe_error_message = "Host is not permitted by the configured network policy. Ask an administrator to allow this destination."
    except ValueError:
        source.status = "failed"
        source.safe_error_code = "invalid_configuration"
        source.safe_error_message = "Connection settings are invalid or unsupported."
    except Exception:
        source.status = "failed"
        source.safe_error_code = "connection_failed"
        source.safe_error_message = "Connection failed. Check the host, port, database, credentials, drivers, and backend network access."
        logger.warning("Database connection test failed for source_id=%s", source.id)
    finally:
        _job_slots.release()
        db.commit()
        db.refresh(source)
    return source


def discover_source(db: Session, source: DataSource) -> DataSource:
    if not _job_slots.acquire(blocking=False):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Discovery capacity is busy; retry shortly")
    source.discovery_status = "in_progress"
    db.commit()
    try:
        settings = get_settings()
        records = connector_for(source).discover(settings.data_source_max_tables, settings.data_source_max_columns)
        db.query(DiscoveredTable).filter(DiscoveredTable.data_source_id == source.id).delete(synchronize_session=False)
        tables = []
        for record in records:
            table = DiscoveredTable(
                data_source_id=source.id, schema_name=record["schema_name"], name=record["name"],
                table_type=record["table_type"], row_count_estimate=record.get("row_count_estimate"),
                foreign_keys=record.get("foreign_keys", []), profile=record.get("profile", {}),
            )
            table.columns = [DiscoveredColumn(**column) for column in record["columns"]]
            tables.append(table)
        source.tables = tables
        db.flush()
        catalog = db.query(Dataset).filter(Dataset.data_source_id == source.id).all()
        by_identity = {(str((item.source_ref or {}).get("schema")), str((item.source_ref or {}).get("table"))): item for item in catalog}
        for item in catalog:
            item.status = "stale"
        for table in tables:
            identity = (table.schema_name, table.name)
            schema_json = [{"name": column.name, "data_type": column.data_type, "type": "text",
                            "nullable": column.nullable, "is_primary_key": column.is_primary_key,
                            "foreign_key": column.foreign_key} for column in table.columns]
            item = by_identity.get(identity)
            if item is None:
                identity = f"{table.schema_name}.{table.name}"
                suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
                display_name = f"{source.id}:{identity[-140:]}:{suffix}"[:160]
                if db.query(Dataset.id).filter(Dataset.workspace_id == source.workspace_id, Dataset.name == display_name).first():
                    display_name = f"{source.id}:{identity[-132:]}:{table.id}:{suffix}"[:160]
                item = Dataset(workspace_id=source.workspace_id, name=display_name, source_type="database",
                               status="ready", schema_json=schema_json,
                               row_count=table.row_count_estimate or 0, source_ref={"schema": table.schema_name, "table": table.name},
                               data_source_id=source.id)
                db.add(item)
            else:
                item.status = "ready"
                item.schema_json = schema_json
                item.row_count = table.row_count_estimate or 0
            item.discovered_table_id = table.id
        source.discovery_status = "completed"
        source.last_discovered_at = datetime.now(timezone.utc)
        source.status = "connected"
        source.safe_error_code = None
        source.safe_error_message = None
        db.commit()
        db.refresh(source)
    except NetworkPolicyError:
        db.rollback()
        source.discovery_status = "failed"
        source.safe_error_code = "destination_blocked"
        source.safe_error_message = "Host is not permitted by the configured network policy. Ask an administrator to allow this destination."
        db.commit()
    except Exception:
        db.rollback()
        source = db.get(DataSource, source.id)
        source.discovery_status = "failed"
        source.safe_error_code = "discovery_failed"
        source.safe_error_message = "Schema discovery failed. Check database permissions, limits, drivers, and backend network access."
        logger.warning("Schema discovery failed for source_id=%s", source.id)
        db.commit()
    finally:
        _job_slots.release()
    return with_tables(db, source.id)


def refresh_profile(db: Session, source: DataSource):
    source = with_tables(db, source.id)
    state, profile, message = generate_business_profile(source)
    source.profile_json = profile.model_dump() if profile else None
    db.commit()
    return state, profile, message
