import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from database import setup_admin
from database.models import User
from tests.integration.database_support import integration_url


def test_only_one_initial_admin_is_created(capsys):
    engine = create_engine(integration_url(), connect_args={
        "connect_timeout": 3, "options": "-c statement_timeout=5000 -c lock_timeout=3000"})
    sessions = sessionmaker(bind=engine)
    prefix = "bootstrap_" + uuid4().hex[:12]
    barrier = threading.Barrier(2)

    def hash_password(_):
        barrier.wait(3)  # Both initial empty-table checks have completed.
        return "fake-hash"

    def prompt(label):
        return "Test Admin" if label == "Full name: " else prefix + str(threading.get_ident())

    try:
        with sessions() as session:
            assert not session.scalars(select(User)).all()
        with patch.object(setup_admin, "SessionLocal", sessions), \
                patch.object(setup_admin.PasswordService, "hash_password", side_effect=hash_password), \
                patch.object(setup_admin, "getpass", return_value="valid-test-password"), \
                patch("builtins.input", side_effect=prompt), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(setup_admin.main) for _ in range(2)]
            for future in futures:
                future.result(8)
        with sessions() as session:
            users = session.scalars(select(User)).all()
            assert len(users) == 1 and users[0].role == "boss_admin"
        output = capsys.readouterr().out
        assert output.count("created successfully") == 1
        assert output.count("accounts already exist") == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(User).where(User.username.startswith(prefix)))
        engine.dispose()
