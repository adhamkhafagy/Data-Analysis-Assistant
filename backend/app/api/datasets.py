from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.models.dataset import Dataset, DatasetRevision, IngestionRun, UploadSession
from app.schemas.datasets import DatasetCreate, DatasetResponse, ImportRequest, PreviewResponse, RowBatch, RowUpdate, UploadResponse
from app.services.managed_data import (
    create_manual_dataset, delete_dataset_row, import_upload, insert_rows, managed_table, owned_dataset,
    expire_workspace_uploads, owned_upload, read_dataset_rows, record_revision, save_upload, update_dataset_row,
    upload_preview, workspace_for_user,
)

router = APIRouter(tags=["datasets and uploads"])


@router.get("/workspaces/{workspace_id}/datasets", response_model=list[DatasetResponse])
def list_datasets(workspace_id: int, user: CurrentUser, db: DbSession):
    workspace_for_user(db, workspace_id, user.id)
    return db.query(Dataset).filter(Dataset.workspace_id == workspace_id).order_by(Dataset.created_at.desc()).all()


@router.post("/workspaces/{workspace_id}/datasets", response_model=DatasetResponse, status_code=201)
def create_dataset(workspace_id: int, body: DatasetCreate, user: CurrentUser, db: DbSession):
    workspace_for_user(db, workspace_id, user.id)
    return create_manual_dataset(db, workspace_id, user.id, body.name,
                                 [column.model_dump() for column in body.columns], body.rows)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def dataset_detail(dataset_id: int, user: CurrentUser, db: DbSession):
    return owned_dataset(db, dataset_id, user.id)


@router.get("/datasets/{dataset_id}/rows")
def list_rows(dataset_id: int, user: CurrentUser, db: DbSession,
              limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    dataset = owned_dataset(db, dataset_id, user.id)
    if dataset.source_type == "database":
        raise HTTPException(409, "Database rows are not copied into managed storage")
    return read_dataset_rows(db, dataset, dataset.workspace_id, limit, offset)


@router.post("/datasets/{dataset_id}/rows", status_code=201)
def add_rows(dataset_id: int, body: RowBatch, user: CurrentUser, db: DbSession):
    dataset = owned_dataset(db, dataset_id, user.id, for_update=True)
    if dataset.source_type == "database": raise HTTPException(409, "Database-backed datasets are read-only references")
    if len(body.rows) > 1000: raise HTTPException(422, "At most 1000 rows can be added at once")
    insert_rows(db, dataset, dataset.workspace_id, body.rows)
    record_revision(db, dataset)
    db.add(IngestionRun(workspace_id=dataset.workspace_id, dataset=dataset, actor_user_id=user.id,
                        operation="manual_edit", status="completed", rows_seen=len(body.rows), rows_written=len(body.rows), error_report=[]))
    db.commit()
    return {"rows_written": len(body.rows), "row_count": dataset.row_count}


@router.patch("/datasets/{dataset_id}/rows/{row_id}", status_code=204)
def edit_row(dataset_id: int, row_id: str, body: RowUpdate, user: CurrentUser, db: DbSession):
    dataset = owned_dataset(db, dataset_id, user.id, for_update=True)
    if dataset.source_type == "database": raise HTTPException(409, "Database-backed datasets are read-only references")
    update_dataset_row(db, dataset, dataset.workspace_id, row_id, body.values)
    db.add(IngestionRun(workspace_id=dataset.workspace_id, dataset=dataset, actor_user_id=user.id,
                        operation="manual_update", status="completed", rows_seen=1, rows_written=1, error_report=[]))
    db.commit()
    return Response(status_code=204)


@router.delete("/datasets/{dataset_id}/rows/{row_id}", status_code=204)
def remove_row(dataset_id: int, row_id: str, user: CurrentUser, db: DbSession):
    dataset = owned_dataset(db, dataset_id, user.id, for_update=True)
    if dataset.source_type == "database": raise HTTPException(409, "Database-backed datasets are read-only references")
    delete_dataset_row(db, dataset, dataset.workspace_id, row_id)
    db.add(IngestionRun(workspace_id=dataset.workspace_id, dataset=dataset, actor_user_id=user.id,
                        operation="manual_delete", status="completed", rows_seen=1, rows_written=0, error_report=[]))
    db.commit()
    return Response(status_code=204)


@router.delete("/datasets/{dataset_id}", status_code=204)
def remove_dataset(dataset_id: int, user: CurrentUser, db: DbSession):
    dataset = owned_dataset(db, dataset_id, user.id, for_update=True)
    if dataset.source_type == "database": raise HTTPException(409, "Remove the database connection to remove its catalog entries")
    table = managed_table(dataset)
    table.drop(db.connection(), checkfirst=True)
    db.delete(dataset)
    db.commit()
    return Response(status_code=204)


@router.get("/datasets/{dataset_id}/history")
def dataset_history(dataset_id: int, user: CurrentUser, db: DbSession):
    owned_dataset(db, dataset_id, user.id)
    revisions = db.query(DatasetRevision).filter(DatasetRevision.dataset_id == dataset_id).order_by(DatasetRevision.version.desc()).all()
    runs = db.query(IngestionRun).filter(IngestionRun.dataset_id == dataset_id).order_by(IngestionRun.created_at.desc()).all()
    return {"revisions": [{"version": r.version, "schema": r.schema_snapshot, "row_count": r.row_count, "created_at": r.created_at} for r in revisions],
            "runs": [{"id": r.id, "operation": r.operation, "status": r.status, "rows_seen": r.rows_seen,
                      "rows_written": r.rows_written, "errors": r.error_report, "created_at": r.created_at} for r in runs]}


@router.post("/workspaces/{workspace_id}/uploads", response_model=UploadResponse, status_code=201)
async def upload_file(workspace_id: int, user: CurrentUser, db: DbSession, file: UploadFile = File(...)):
    workspace_for_user(db, workspace_id, user.id)
    expire_workspace_uploads(db, workspace_id)
    return await save_upload(db, workspace_id, user.id, file)


@router.get("/workspaces/{workspace_id}/uploads", response_model=list[UploadResponse])
def list_uploads(workspace_id: int, user: CurrentUser, db: DbSession):
    workspace_for_user(db, workspace_id, user.id)
    expire_workspace_uploads(db, workspace_id)
    return db.query(UploadSession).filter_by(workspace_id=workspace_id).order_by(UploadSession.created_at.desc()).all()


@router.get("/uploads/{upload_id}/preview", response_model=PreviewResponse)
def preview_upload(upload_id: int, user: CurrentUser, db: DbSession, sheet_name: str | None = None):
    return upload_preview(owned_upload(db, upload_id, user.id), sheet_name)


@router.post("/uploads/{upload_id}/import", response_model=DatasetResponse, status_code=201)
def import_file(upload_id: int, body: ImportRequest, user: CurrentUser, db: DbSession):
    session = owned_upload(db, upload_id, user.id)
    return import_upload(db, session, user.id, body.name, body.dataset_id, body.sheet_name, body.append,
                         {key: value.model_dump() for key, value in body.mapping.items()} if body.mapping is not None else None)

