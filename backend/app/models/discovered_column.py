from sqlalchemy import Boolean, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DiscoveredColumn(Base):
    __tablename__ = "discovered_columns"
    __table_args__ = (UniqueConstraint("table_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("discovered_tables.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    data_type: Mapped[str] = mapped_column(String(255))
    nullable: Mapped[bool] = mapped_column(Boolean)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False)
    foreign_key: Mapped[str | None] = mapped_column(String(600), nullable=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    table: Mapped["DiscoveredTable"] = relationship(back_populates="columns")
