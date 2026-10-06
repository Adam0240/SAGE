# SAGE tests

The suite focuses on user login/logout, account CRUD, role permissions, password changes,
and default UI behavior. Related input and role cases use subtests with descriptive case
labels. Database CRUD is checked through the account-operation wrappers instead of
repeating the same operations in a separate repository test suite.

Each test has a comment immediately above it describing the behavior it checks.

The test files are grouped by feature:

- `unit/test_account_service.py`: permissions, validation, and safe account display fields.
- `unit/test_authentication_service.py`: accepted/rejected login credentials.
- `unit/test_password_service.py`: hashing, verification, and password changes.
- `unit/test_database_configuration.py`: required settings, environment overrides,
  host/port validation, safe errors, and lazy initialization recovery.
- `ui/test_main_window.py`: default UI, login/logout, and account access.
- `ui/test_account_dialog.py`: account forms, confirmation, assistant self-service
  password changes, and worker recovery.
- `ui/test_login_dialog.py`: real login threads, safe errors, retry, missing results,
  session cleanup, and closing/repeated submissions during login.
- `ui/test_configuration_startup.py`: fresh-process Student Mode startup without
  credentials and recoverable login configuration errors.
- `integration/test_account_transactions.py`: PostgreSQL CRUD and transaction rollback.
- `integration/test_boss_admin_concurrency.py`: overlapping boss removals on independent
  connections, promotion/password-reset and actor-demotion races, consistent row-lock
  ordering, stale account refresh, and lock release after rollback.

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

# CI collection guard; imports all test modules without executing database tests.
.\.venv\Scripts\python.exe -m pytest --collect-only --check-collection -q
```

Directory names also supply `unit`, `ui`, and `integration` markers for `pytest -m` selection.
Selecting `tests/unit` directly avoids importing UI and integration test modules.

The collection guard requires at least one collected test from each module listed in
`REQUIRED_TEST_MODULES` in `tests/conftest.py`. It fails for missing, empty, ignored, or
entirely deselected expected modules. Keep that list current when intentionally adding
or renaming modules. `.github/workflows/tests.yml` runs the guard and the unit/UI suite
on Windows with offscreen Qt; PostgreSQL integration tests require a separate local run.

Database settings come from the root `.env`, with `POSTGRES_*` environment overrides.
Unit/UI imports and Student Mode startup do not read or require those settings. Integration tests
use the same server and credentials with the database changed to `sage_test`, reject a
matching application database name. Account transaction tests roll back each test's data and
use savepoints so operation wrappers can commit their sessions while an outer transaction
still removes all test data afterward. Test tables are created from the ORM models;
these tests do not validate Alembic migration history.

Boss Admin concurrency tests use real commits in a unique temporary schema within
`sage_test`, with two active bosses isolated from existing accounts. They confirm the
second connection is blocked by the first before allowing its removal to commit, then
verify the second removal is rejected and one boss remains. Each schema is dropped
after its test. These tests require permission to create schemas in `sage_test` and
use bounded connection, statement, and synchronization waits; they do not start Docker
or modify the application's database.

Permission concurrency tests in the same module overlap promotions/password resets
in both orders and actor demotion with creation/reset attempts. They verify a waiter
uses current locked account values, denied operations leave passwords/accounts unchanged,
and operations authorized first commit before a conflicting role change proceeds.
Opposing actor/target updates overlap between the first and second row acquisitions to
check that ascending account-ID order avoids a deadlock. Deletion and role changes
acquire the shared Boss Admin advisory lock before account row locks; creation and
identity/password updates acquire only the account row locks. All locks remain held
through commit or rollback by the account-operation transaction wrappers.
