from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.data_source import DataSource
from app.repositories.data_sources import for_workspace, with_tables
from app.schemas.data_source import (
    BusinessProfile, BusinessProfileResponse, DataSourceCreate, DataSourceResponse,
    DataSourceUpdate, SchemaResponse,
)
from app.services.data_sources import (
    create_source, discover_source, owned_source, refresh_profile, test_source, update_source,
)

router = APIRouter(tags=["data sources"])


@router.post("/workspaces/{workspace_id}/data-sources", response_model=DataSourceResponse, status_code=201)
def create(workspace_id: int, body: DataSourceCreate, user: CurrentUser, db: DbSession):
    return create_source(db, workspace_id, user.id, body)


@router.get("/workspaces/{workspace_id}/data-sources", response_model=list[DataSourceResponse])
def list_sources(workspace_id: int, user: CurrentUser, db: DbSession):
    from app.repositories.workspaces import get_for_owner
    if not get_for_owner(db, workspace_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return for_workspace(db, workspace_id)


@router.get("/data-sources/{source_id}", response_model=DataSourceResponse)
def detail(source_id: int, user: CurrentUser, db: DbSession):
    return owned_source(db, source_id, user.id)


@router.patch("/data-sources/{source_id}", response_model=DataSourceResponse)
def update(source_id: int, body: DataSourceUpdate, user: CurrentUser, db: DbSession):
    source = owned_source(db, source_id, user.id)
    return update_source(db, source, body)


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(source_id: int, user: CurrentUser, db: DbSession):
    source = owned_source(db, source_id, user.id)
    db.delete(source)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/data-sources/{source_id}/test-connection", response_model=DataSourceResponse)
def connection_test(source_id: int, user: CurrentUser, db: DbSession):
    return test_source(db, owned_source(db, source_id, user.id))


@router.post("/data-sources/{source_id}/discover", response_model=DataSourceResponse)
def discover(source_id: int, user: CurrentUser, db: DbSession):
    return discover_source(db, owned_source(db, source_id, user.id))


@router.get("/data-sources/{source_id}/schema", response_model=SchemaResponse)
def schema(source_id: int, user: CurrentUser, db: DbSession):
    source = with_tables(db, owned_source(db, source_id, user.id).id)
    return SchemaResponse(data_source_id=source.id, status=source.discovery_status,
                          discovered_at=source.last_discovered_at, tables=source.tables)


@router.get("/data-sources/{source_id}/business-profile", response_model=BusinessProfileResponse)
def business_profile(source_id: int, user: CurrentUser, db: DbSession):
    source = owned_source(db, source_id, user.id)
    if source.discovery_status != "completed":
        return BusinessProfileResponse(status="not_generated", profile=None, message="Discover the schema before generating a business profile")
    if source.profile_json:
        return BusinessProfileResponse(status="available", profile=BusinessProfile.model_validate(source.profile_json), message=None)
    state, profile, message = refresh_profile(db, source)
    return BusinessProfileResponse(status=state, profile=profile, message=message)


@router.post("/data-sources/{source_id}/refresh", response_model=DataSourceResponse)
def refresh(source_id: int, user: CurrentUser, db: DbSession):
    source = discover_source(db, owned_source(db, source_id, user.id))
    if source.discovery_status == "completed":
        refresh_profile(db, source)
    return source
