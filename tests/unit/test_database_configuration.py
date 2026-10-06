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
    def test_required_settings_are_validated_without_exposing_values(self):
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
    def test_environment_overrides_file_and_supports_no_file(self):
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
    def test_initialization_recovers_and_workers_share_one_engine(self):
        valid_values = self.values.copy()
        self.values = {}
        with patch.object(connection, "_engine", None), patch("database.connection.create_engine") as create:
            with self.assertRaises(DatabaseConfigurationError):
                connection.get_engine()
            create.assert_not_called()
            self.values = valid_values
            with ThreadPoolExecutor(max_workers=2) as workers:
                engines = list(workers.map(lambda _index: connection.get_engine(), range(2)))
            self.assertIs(engines[0], engines[1])
            create.assert_called_once()
