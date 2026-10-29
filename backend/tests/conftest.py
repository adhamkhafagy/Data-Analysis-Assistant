import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["SESSION_SECRET"] = "test-only-secret-with-more-than-32-characters"
os.environ["DATABASE_URL"] = "sqlite:///./ignored.db"
os.environ["APP_ENV"] = "test"
os.environ["DATA_SOURCE_ENCRYPTION_KEY"] = "F6XUchQdlEmSn9TumuNFv8HSnLjpfLDshyF8Du-KJ-A="

from app.core.database import Base, get_db
from app.main import app


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
