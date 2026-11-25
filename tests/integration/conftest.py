import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from tests.integration.database_support import integration_url


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    engine = create_engine(integration_url(), connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
        yield
    finally:
        engine.dispose()
