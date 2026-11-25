import os

from sqlalchemy.engine import make_url


def integration_url():
    value = os.environ.get("SAGE_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("Set SAGE_TEST_DATABASE_URL to a disposable local sage_test database.")
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg" or url.database != "sage_test"
            or url.host not in ("localhost", "127.0.0.1", "::1")):
        raise RuntimeError("Integration tests require a local PostgreSQL sage_test database.")
    return url
