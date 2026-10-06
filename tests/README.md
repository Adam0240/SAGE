# SAGE tests

The suite focuses on user login/logout, account CRUD, role permissions, password changes,
and default UI behavior. Related input and role cases use subtests with descriptive case
labels. Database CRUD is checked through the account-operation wrappers instead of
repeating the same operations in a separate repository test suite.

Each test has a comment immediately above it describing the behavior it checks.

The six test files are grouped by feature:

- `unit/test_account_service.py`: permissions, validation, and safe account display fields.
- `unit/test_authentication_service.py`: accepted/rejected login credentials.
- `unit/test_password_service.py`: hashing, verification, and password changes.
- `ui/test_main_window.py`: default UI, login/logout, and account access.
- `ui/test_account_dialog.py`: account forms, confirmation, and worker recovery.
- `integration/test_account_transactions.py`: PostgreSQL CRUD and transaction rollback.

Run commands from the repository root using the project's Python environment:

```powershell
# Fast service tests; no running PostgreSQL server or GUI is needed.
.\.venv\Scripts\python.exe -m pytest tests/unit -q

# Interface tests; database calls are mocked and Qt uses an offscreen platform.
.\.venv\Scripts\python.exe -m pytest tests/ui -q

# Database integration tests; PostgreSQL and the sage_test database must be available.
.\.venv\Scripts\python.exe -m pytest tests/integration -q

# Complete suite.
.\.venv\Scripts\python.exe -m pytest -q
```

Directory names also supply `unit`, `ui`, and `integration` markers for `pytest -m` selection.
Selecting `tests/unit` directly avoids importing UI and integration test modules.

The application database settings still come from the root `.env` file. Integration tests
use the same server and credentials with the database changed to `sage_test`, reject a
matching application database name, and roll back each test's data. Transaction tests
use savepoints so operation wrappers can commit their sessions while an outer transaction
still removes all test data afterward. Test tables are created from the ORM models;
these tests do not validate Alembic migration history.
