"""Add a workspace-scoped dataset catalog and ingestion lineage."""
import json
import hashlib

from alembic import op
import sqlalchemy as sa

revision = "0003_unified_datasets"
down_revision = "0002_data_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_table_key", sa.String(80), unique=True),
        sa.Column("source_ref", sa.JSON(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE")),
        sa.Column("discovered_table_id", sa.Integer(), sa.ForeignKey("discovered_tables.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_datasets_workspace_name"),
    )
    op.create_index("ix_datasets_workspace_id", "datasets", ["workspace_id"])
    op.create_index("ix_datasets_data_source_id", "datasets", ["data_source_id"])
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("staging_key", sa.String(80), unique=True),
        sa.Column("sheet_names", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_upload_sessions_workspace_id", "upload_sessions", ["workspace_id"])
    op.create_table(
        "dataset_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_revisions_version"),
    )
    op.create_index("ix_dataset_revisions_dataset_id", "dataset_revisions", ["dataset_id"])
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="SET NULL")),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("upload_sessions.id", ondelete="SET NULL")),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    for table, column in (("ingestion_runs", "workspace_id"), ("ingestion_runs", "dataset_id"), ("ingestion_runs", "upload_id")):
        op.create_index(f"ix_{table}_{column}", table, [column])

    # Existing discovered tables become catalog entries; underlying customer data stays remote.
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT ds.workspace_id, ds.name AS source_name, dt.id AS table_id, ds.id AS source_id, dt.schema_name, dt.name,
               dt.row_count_estimate,
               COALESCE((SELECT json_agg(json_build_object('name', dc.name, 'data_type', dc.data_type,
                   'nullable', dc.nullable, 'is_primary_key', dc.is_primary_key,
                   'foreign_key', dc.foreign_key) ORDER BY dc.id)
                   FROM discovered_columns dc WHERE dc.table_id = dt.id), '[]'::json) AS columns_json
        FROM discovered_tables dt JOIN data_sources ds ON ds.id = dt.data_source_id
        ORDER BY ds.workspace_id, ds.id, dt.id
    """)).mappings().all()
    insert = sa.text("""
        INSERT INTO datasets (workspace_id, name, source_type, status, schema_json, row_count,
                             source_ref, data_source_id, discovered_table_id, created_at, updated_at)
        VALUES (:workspace_id, :name, 'database', 'ready', CAST(:schema_json AS json),
                COALESCE(:row_count, 0), CAST(:source_ref AS json), :source_id, :table_id, now(), now())
        ON CONFLICT (workspace_id, name) DO NOTHING
    """)
    for row in rows:
        identity = f"{row['schema_name']}.{row['name']}"
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
        name = f"{row['source_id']}:{identity[-140:]}:{suffix}"[:160]
        bind.execute(insert, {
            "workspace_id": row["workspace_id"], "name": name,
            "schema_json": row["columns_json"] if isinstance(row["columns_json"], str) else json.dumps(row["columns_json"]),
            "row_count": row["row_count_estimate"], "source_ref": json.dumps({"schema": row["schema_name"], "table": row["name"]}),
            "source_id": row["source_id"], "table_id": row["table_id"],
        })


def downgrade():
    op.drop_table("ingestion_runs")
    op.drop_table("dataset_revisions")
    op.drop_table("upload_sessions")
    op.drop_table("datasets")
