"""Add encrypted data sources and discovered metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0002_data_sources"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("database_type", sa.String(20), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database_name", sa.String(255), nullable=False),
        sa.Column("schema_name", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("discovery_status", sa.String(30), nullable=False),
        sa.Column("safe_error_code", sa.String(50), nullable=True),
        sa.Column("safe_error_message", sa.String(300), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_data_sources_workspace_id", "data_sources", ["workspace_id"])
    op.create_table(
        "discovered_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_name", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("table_type", sa.String(30), nullable=False),
        sa.Column("row_count_estimate", sa.Integer(), nullable=True),
        sa.Column("foreign_keys", sa.JSON(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("data_source_id", "schema_name", "name"),
    )
    op.create_index("ix_discovered_tables_data_source_id", "discovered_tables", ["data_source_id"])
    op.create_table(
        "discovered_columns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("discovered_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(255), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), nullable=False),
        sa.Column("foreign_key", sa.String(600), nullable=True),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.UniqueConstraint("table_id", "name"),
    )
    op.create_index("ix_discovered_columns_table_id", "discovered_columns", ["table_id"])


def downgrade():
    op.drop_index("ix_discovered_columns_table_id", table_name="discovered_columns")
    op.drop_table("discovered_columns")
    op.drop_index("ix_discovered_tables_data_source_id", table_name="discovered_tables")
    op.drop_table("discovered_tables")
    op.drop_index("ix_data_sources_workspace_id", table_name="data_sources")
    op.drop_table("data_sources")
