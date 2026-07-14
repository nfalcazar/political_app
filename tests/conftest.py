import pytest

from research_app.database import Database
from research_app.repository import Repository


@pytest.fixture
def repository(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_schema()
    return Repository(database)

