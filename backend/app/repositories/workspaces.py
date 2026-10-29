from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace import Workspace


def list_for_owner(db: Session, owner_id: int) -> list[Workspace]:
    return list(db.scalars(select(Workspace).where(Workspace.owner_id == owner_id).order_by(Workspace.created_at)))


def get_for_owner(db: Session, workspace_id: int, owner_id: int) -> Workspace | None:
    return db.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == owner_id))
