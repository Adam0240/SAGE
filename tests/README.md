# SAGE tests

The suite covers login/logout, account CRUD and permissions, database deadlines,
G-code browsing and asynchronous previews, Markdown retrieval and responses, camera
tracking/calibration, and dwell input across SAGE. Related cases use pytest
parameterization or unittest subtests. Database CRUD is checked through the account-operation wrappers instead of
repeating the same operations in a separate repository test suite.

The test files are grouped by feature:

- `unit/test_account_service.py`: permissions, validation, and safe account display fields.
- `unit/test_authentication_service.py`: accepted/rejected login credentials.
- `unit/test_password_service.py`: hashing, verification, and password changes.
- `unit/test_database_configuration.py`: required settings, environment overrides,
  host/port validation, safe errors, lazy initialization recovery, socket deadlines,
  and rollback/retry using an in-memory database.
- `unit/test_guide_services.py`: section parsing, repeated-heading ancestor isolation,
  ranking, symptom meaning, clarification, document refresh, and source-based responses.
- `unit/test_camera_manager.py`: simulated frames/landmarks, tracking loss, model/camera
  failures, monotonic timestamps, and resource cleanup.
- `unit/test_calibration.py`: mapping, corner/matrix validation, accuracy checks,
  saved-file compatibility, atomic persistence, and lightweight projection.
- `unit/test_dwell.py`: one-second activation, target changes, tracking gaps, and repeat prevention.
- `ui/test_main_window.py`: default UI, login/logout, account access, G-code/Home navigation,
  and repeated staff-dialog password clearing/deletion.
- `ui/test_gcodedisplayapp.py`: G-code discovery, button/keyboard navigation,
  file-list search/selection/cancellation, preview messages/scaling, configurable folder paths,
  responsiveness during slow previews, latest-request handling, cancellation, and viewer destruction.
- `unit/test_gcode_parser.py`: supported movement commands, coordinate formats,
  comments, omitted axes, and file read errors without Qt.
- `ui/test_gcode_preview_service.py`: image rendering, thumbnail caching/invalidation,
  defined file/movement errors, coordinate limits, and cancelled parsing without partial caching.
- `ui/test_account_dialog.py`: account forms, confirmation, assistant self-service
  password changes, and worker recovery after errors/timeouts.
- `ui/test_login_dialog.py`: real login threads, safe errors, retry, missing results,
  session cleanup, timeout recovery, and closing/repeated submissions during login.
- `ui/test_configuration_startup.py`: fresh-process Student Mode startup without
  credentials, recoverable login configuration errors, and automatic camera startup
  without GUI vision imports for missing, invalid, or valid calibration.
- `ui/test_steamguide_app.py`: questions, responses/sources, reference refresh/viewers,
  read failures, and launcher/Home state preservation.
- `ui/test_hand_calibration.py`: capture/verification/save workflow, invalid or stale
  tracking, camera process errors, deadlines, blocked capture, shutdown, and modal event loops.
- `ui/test_home_camera_input.py`: automatic startup, calibrated targeting, dwell navigation,
  modal ownership, fields/dropdowns/tabs/scrolling, staff workflows, and camera failure/closure.
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

Unit/UI tests require the installed project dependencies, but no physical webcam,
projector, downloaded hand model, or saved desk calibration. Camera tests simulate
frames or use fake capture processes; some lifecycle tests spawn real child processes.
They do not establish hardware accuracy, native title-bar behavior, USB-driver recovery,
or production storage/network performance. For projector/webcam acceptance checks,
follow [TouchControls/README.md](../TouchControls/README.md).

The collection guard requires at least one collected test from each module listed in
`REQUIRED_TEST_MODULES` in `tests/conftest.py`. It fails for missing, empty, ignored, or
entirely deselected expected modules. Keep that list current when intentionally adding
or renaming modules. `.github/workflows/tests.yml` runs the guard and the unit/UI suite
on Windows with offscreen Qt; PostgreSQL integration tests require a separate local run.

Database settings come from the root `.env`, with `POSTGRES_*` environment overrides.
Unit/UI imports and Student Mode startup do not read or require those settings. Integration tests
use the same server and credentials with the database changed to `sage_test` and reject a
matching application database name. Account transaction tests roll back each test's data and
use savepoints so operation wrappers can commit their sessions while an outer transaction
still removes all test data afterward. Test tables are created from the ORM models;
these tests do not validate Alembic migration history.

Boss Admin concurrency tests use real commits in a unique temporary schema within
`sage_test`, isolated from existing accounts. They check that overlapping operations
preserve the last active Boss Admin, recheck current permissions after waiting,
release locks on rollback, and acquire account locks consistently to avoid deadlock.
Each schema is dropped after its test. These tests require permission to create
schemas in `sage_test`; they do not start Docker or modify the application's database.
