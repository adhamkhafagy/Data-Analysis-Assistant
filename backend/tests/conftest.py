import os
from pathlib import Path
from datetime import timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import set_committed_value

os.environ["SESSION_SECRET"] = "test-only-secret-with-more-than-32-characters"
os.environ["DATABASE_URL"] = "sqlite:///./ignored.db"
os.environ["APP_ENV"] = "test"
os.environ["DATA_SOURCE_ENCRYPTION_KEY"] = "F6XUchQdlEmSn9TumuNFv8HSnLjpfLDshyF8Du-KJ-A="

from app.core.database import Base, get_db
from app.main import app
from app.models.dataset import UploadSession


@event.listens_for(UploadSession, "load")
def _make_sqlite_upload_expiry_aware(upload: UploadSession, _context) -> None:
    """Restore UTC tzinfo lost by SQLite for timezone-aware DateTime columns."""
    expires_at = upload.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        set_committed_value(upload, "expires_at", expires_at.replace(tzinfo=timezone.utc))


@pytest.fixture()
def client(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
