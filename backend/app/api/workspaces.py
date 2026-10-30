from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.workspace import Workspace
from app.models.dataset import Dataset, UploadSession
from app.repositories.workspaces import get_for_owner, list_for_owner
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.services.managed_data import managed_table, staging_path

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(user: CurrentUser, db: DbSession):
    return list_for_owner(db, user.id)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, user: CurrentUser, db: DbSession):
    workspace = Workspace(name=body.name, owner_id=user.id)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: int, user: CurrentUser, db: DbSession):
    workspace = get_for_owner(db, workspace_id, user.id)
    if not workspace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def rename_workspace(workspace_id: int, body: WorkspaceUpdate, user: CurrentUser, db: DbSession):
    workspace = get_for_owner(db, workspace_id, user.id)
    if not workspace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    workspace.name = body.name
    db.commit()
    db.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: int, user: CurrentUser, db: DbSession):
    workspace = get_for_owner(db, workspace_id, user.id)
    if not workspace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    datasets = db.query(Dataset).filter(Dataset.workspace_id == workspace_id).all()
    uploads = db.query(UploadSession).filter(UploadSession.workspace_id == workspace_id).all()
    connection = db.connection()
    for dataset in datasets:
        if dataset.storage_table_key:
            managed_table(dataset).drop(connection, checkfirst=True)
    for upload in uploads:
        if upload.staging_key:
            staging_path(upload.staging_key).unlink(missing_ok=True)
    db.delete(workspace)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
