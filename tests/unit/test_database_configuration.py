# Tests configuration precedence, safe validation, and retry after failed initialization.

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from database import connection
from database.connection import DatabaseConfigurationError, get_database_url


class TestDatabaseConfiguration(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        file_settings = patch("database.connection.dotenv_values")
        self.file_settings = file_settings.start()
        self.addCleanup(file_settings.stop)
        self.values = dict(POSTGRES_DB="test_db", POSTGRES_USER="test_user",
                           POSTGRES_PASSWORD="fictional secret")
        self.file_settings.side_effect = lambda *_args: self.values.copy()

    # Tests every missing/blank required key produces actionable errors without secret values.
    def test_safe_validation_errors(self):
        for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
            for invalid in (None, "", "   "):
                with self.subTest(key=key, invalid=invalid):
                    self.values[key] = invalid
                    with self.assertRaises(DatabaseConfigurationError) as caught:
                        get_database_url()
                    message = str(caught.exception)
                    self.assertIn(key, message)
                    self.assertIn(".env.example", message)
                    self.assertNotIn("fictional secret", message)
                    self.values[key] = {
                        "POSTGRES_DB": "test_db", "POSTGRES_USER": "test_user",
                        "POSTGRES_PASSWORD": "fictional secret",
                    }[key]

    # Tests environment-only configuration overrides all file settings and preserves passwords.
    def test_environment_settings(self):
        overrides = dict(POSTGRES_DB="other_db", POSTGRES_USER="other_user",
                         POSTGRES_PASSWORD=" p@ss:/?# word ",
                         POSTGRES_HOST="remote.example.org", POSTGRES_PORT="6543")
        for file_values in (self.values.copy(), {}):
            with self.subTest(file_present=bool(file_values)), patch.dict(os.environ, overrides):
                self.values = file_values
                url = get_database_url()
                self.assertEqual((url.database, url.username, url.password, url.host, url.port),
                                 ("other_db", "other_user", " p@ss:/?# word ",
                                  "remote.example.org", 6543))

    # Tests an explicitly empty environment override does not fall back to a file credential.
    def test_empty_environment_override_is_rejected(self):
        with patch.dict(os.environ, {"POSTGRES_PASSWORD": ""}):
            with self.assertRaisesRegex(DatabaseConfigurationError, "POSTGRES_PASSWORD"):
                get_database_url()

    # Tests defaults, valid port boundaries, and invalid host/port settings.
    def test_host_and_port_validation(self):
        url = get_database_url()
        self.assertEqual((url.host, url.port), ("127.0.0.1", 5432))
        for port in ("1", "65535"):
            with self.subTest(port=port):
                self.values["POSTGRES_PORT"] = port
                self.assertEqual(get_database_url().port, int(port))
        for port in (None, "", "invalid", "0", "65536"):
            with self.subTest(port=port):
                self.values["POSTGRES_PORT"] = port
                with self.assertRaisesRegex(DatabaseConfigurationError, "POSTGRES_PORT"):
                    get_database_url()
        self.values.pop("POSTGRES_PORT")
        for host in (None, "", "   "):
            with self.subTest(host=host):
                self.values["POSTGRES_HOST"] = host
                with self.assertRaisesRegex(DatabaseConfigurationError, "POSTGRES_HOST"):
                    get_database_url()

    # Tests failed validation creates no engine and later workers share successful initialization.
    def test_shared_engine_recovery(self):
        valid_values = self.values.copy()
        self.values = {}
        with patch.object(connection, "_engine", None), patch("database.connection.create_engine") as create, patch("database.connection.event.listen") as listen:
            with self.assertRaises(DatabaseConfigurationError):
                connection.get_engine()
            create.assert_not_called()
            self.values = valid_values
            with ThreadPoolExecutor(max_workers=2) as workers:
                engines = list(workers.map(lambda _index: connection.get_engine(), range(2)))
            self.assertIs(engines[0], engines[1])
            create.assert_called_once()
            options = create.call_args.kwargs
            self.assertEqual(options["pool_timeout"], 5)
            self.assertEqual(options["connect_args"]["connect_timeout"], 3)
            for setting in ("statement_timeout=10000", "lock_timeout=3000",
                            "transaction_timeout=20000"):
                self.assertIn(setting, options["connect_args"]["options"])
            listen.assert_called_once_with(create.return_value, "do_connect", connection.connect_with_deadline)


class TestDatabaseDeadline(unittest.TestCase):
    # Exercise the transaction wrapper's real rollback and subsequent retry in an ephemeral database.
    def test_timeout_rolls_back_account_transaction_before_retry(self):
        from unittest.mock import Mock
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.exc import OperationalError
        from psycopg.errors import QueryCanceled
        from database import account_operations

        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        with engine.begin() as db:
            db.execute(text("CREATE TABLE example (value INTEGER)"))
            db.execute(text("INSERT INTO example VALUES (1)"))
        fail = [True]
        def service_for(session):
            def update(*args, **kwargs):
                session.execute(text("UPDATE example SET value=2"))
                if fail[0]:
                    raise OperationalError("update", {}, QueryCanceled("statement timeout"))
            return Mock(update_account=update)
        with patch.object(account_operations, "SessionLocal", sessionmaker(bind=engine)), patch.object(
            account_operations, "_make_service", side_effect=service_for
        ):
            with self.assertRaises(OperationalError):
                account_operations.update_account(1, 2, name="changed")
            with engine.connect() as db:
                self.assertEqual(db.scalar(text("SELECT value FROM example")), 1)
            fail[0] = False
            account_operations.update_account(1, 2, name="changed")
            with engine.connect() as db:
                self.assertEqual(db.scalar(text("SELECT value FROM example")), 2)

    # Exercise psycopg's real socket waiter against a silent local socket, without PostgreSQL.
    def test_silent_connection_times_out_and_is_discarded(self):
        import socket
        import time
        from unittest.mock import Mock
        from psycopg import pq
        from psycopg.waiting import Wait
        from database.timeouts import DeadlineConnection, DatabaseWaitTimeout

        def awaiting_response():
            while True:
                yield Wait.R

        for explicit in (None, 0.02):
            with self.subTest(explicit=explicit):
                reader, writer = socket.socketpair()
                try:
                    pgconn = Mock(socket=reader.fileno(), status=pq.ConnStatus.OK)
                    pgconn.finish.side_effect = lambda: setattr(pgconn, "status", pq.ConnStatus.BAD)
                    client = DeadlineConnection(pgconn)
                    client.wait_timeout = 0.05
                    started = time.monotonic()
                    with self.assertRaises(DatabaseWaitTimeout):
                        client.wait(awaiting_response(), timeout=explicit)
                    self.assertLess(time.monotonic() - started, 1)
                    pgconn.finish.assert_called_once()
                    self.assertTrue(client.closed)
                finally:
                    reader.close()
                    writer.close()

    # Successful waits preserve the connection; do_connect retains SQLAlchemy's connection arguments.
    def test_connection_factory_and_successful_wait(self):
        from unittest.mock import Mock
        import psycopg
        from database.timeouts import DeadlineConnection, connect_with_deadline
        with patch.object(DeadlineConnection, "connect") as connect:
            self.assertIs(connect_with_deadline(None, None, ["dbname=test"], {"connect_timeout": 3}), connect.return_value)
            connect.assert_called_once_with("dbname=test", connect_timeout=3)
        client = DeadlineConnection(Mock())
        with patch.object(psycopg.Connection, "wait", return_value=42) as wait, patch.object(client, "close") as close:
            self.assertEqual(client.wait(iter(()), timeout=1), 42)
            self.assertEqual(wait.call_args.kwargs["timeout"], 1)
            close.assert_not_called()
        client.pgconn.status = psycopg.pq.ConnStatus.BAD
