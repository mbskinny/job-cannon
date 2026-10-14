import pytest
from fastapi.testclient import TestClient

from job_cannon import db
from job_cannon.config import Config
from job_cannon.web.app import create_app


@pytest.fixture
def cfg(tmp_path) -> Config:
    c = Config(tmp_path / "data")
    c.ensure_dirs()
    return c


@pytest.fixture
def conn(cfg):
    connection = db.connect(cfg.db_path)
    db.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def client(cfg):
    with TestClient(create_app(cfg)) as c:
        yield c
