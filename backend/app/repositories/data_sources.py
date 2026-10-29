from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.data_source import DataSource
from app.models.discovered_table import DiscoveredTable
from app.models.workspace import Workspace


def for_workspace(db: Session, workspace_id: int) -> list[DataSource]:
    return list(db.scalars(select(DataSource).where(DataSource.workspace_id == workspace_id).order_by(DataSource.id)))


def owned(db: Session, source_id: int, owner_id: int) -> DataSource | None:
    statement = (select(DataSource).join(Workspace, DataSource.workspace_id == Workspace.id)
                 .where(DataSource.id == source_id, Workspace.owner_id == owner_id)
                 .options(selectinload(DataSource.tables).selectinload(DiscoveredTable.columns)))
    return db.scalar(statement)


def with_tables(db: Session, source_id: int) -> DataSource | None:
    return db.scalar(select(DataSource).where(DataSource.id == source_id).options(selectinload(DataSource.tables).selectinload(DiscoveredTable.columns)))
