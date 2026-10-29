from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DiscoveredTable(Base):
    __tablename__ = "discovered_tables"
    __table_args__ = (UniqueConstraint("data_source_id", "schema_name", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    table_type: Mapped[str] = mapped_column(String(30))
    row_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    foreign_keys: Mapped[list] = mapped_column(JSON, default=list)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped["DataSource"] = relationship(back_populates="tables")
    columns: Mapped[list["DiscoveredColumn"]] = relationship(back_populates="table", cascade="all, delete-orphan")
