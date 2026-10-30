# Managed datasets and ingestion

## What is available

- Workspace catalog entries for discovered database tables, uploaded datasets, and manually created datasets.
- CSV, JSON, XLSX, and XLS uploads, with file size, row, and column limits controlled by `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_ROWS`, and `UPLOAD_MAX_COLUMNS`.
- Excel worksheet selection, bounded preview, inferred types, column renaming, and import into a new or existing managed dataset.
- Typed manual tables with row create, read, update, and delete operations.
- Dataset revisions and ingestion run history.
- Database discovery catalog refresh. Database rows are not copied into managed storage.

## API overview

- `GET/POST /api/v1/workspaces/{workspace_id}/datasets`
- `GET/DELETE /api/v1/datasets/{dataset_id}`
- `GET/POST /api/v1/workspaces/{workspace_id}/uploads`
- `GET /api/v1/uploads/{upload_id}/preview?sheet_name=...`
- `POST /api/v1/uploads/{upload_id}/import`
- `GET /api/v1/datasets/{dataset_id}/rows`
- `POST /api/v1/datasets/{dataset_id}/rows`
- `PATCH/DELETE /api/v1/datasets/{dataset_id}/rows/{row_id}`
- `GET /api/v1/datasets/{dataset_id}/history`

All routes require the existing authenticated session and check workspace ownership. Managed table and column identifiers are random generated values; display names are metadata. Uploaded source files are written under the backend's private `.uploads` directory using random names, removed after successful import, and expired after 24 hours. Expired files are removed when the workspace's upload list is accessed or a new upload is submitted.

## Storage and query boundary

Imported/manual datasets use generated PostgreSQL tables with a workspace ID on every row. Database connection catalog entries point to remote table metadata and are not materialized. No SQL generation/execution, cross-source query engine, AI profiling of uploaded rows, or dashboards are part of this phase. Future query execution needs a separate read-only database role and a restricted query service; the current platform database role is not a safe substitute for that role.

## Database connection policy

The existing connector layer supports PostgreSQL, MySQL, and SQL Server metadata discovery subject to its configured destination allowlists and TLS settings. Deployments should grant each configured source credential only metadata/read privileges. The application discovers schema but does not copy or write to those remote databases. Hosted allowlists should be explicit; local and private destinations remain blocked unless an administrator configures a permitted network range.

## Migration

Apply Alembic migrations with `alembic upgrade head` (or the Compose `migrate` service). Revision `0003_unified_datasets` only adds catalog/lineage tables and backfills metadata references for tables already discovered. It does not reset a database or volume. A migration was not automatically run during code changes.
