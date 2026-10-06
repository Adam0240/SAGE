# SAGE code review

Reviewed October 6, 2026. This review makes no application, configuration, test, or database changes.

Follow-up: the user subsequently authorized implementing all six findings and
validating the fixes. That work and its validation are recorded under **Solution Implemented**
below each finding; the original review and its test results remain historical findings.

## Summary and scope

The implementation provides a Student Mode startup screen, asynchronous staff authentication, logout, and account creation/editing/deletion with service-level role checks. Passwords use salted Argon2 hashes, account display results exclude hashes, and account writes use transaction context managers. The ORM model and initial migration agree on columns, defaults, unique usernames, and allowed roles.

The main concerns are concurrent account changes that can invalidate permission checks or remove every active Boss Admin, login failures that leave the dialog waiting indefinitely, configuration-dependent startup, and an account screen that gives Work Study Assistants no usable controls. The root README also directs users to a test command that discovers no tests.

Files reviewed:

- Application/UI: `main.py`, `login_dialog.py`, `sage_apps/account_management_app.py`.
- Database: `database/connection.py`, `database/models.py`, `database/user_repository.py`, `database/account_operations.py`, `database/setup_admin.py`.
- Services: `services/account_service.py`, `services/authentication_service.py`, `services/password_service.py`, `services/session_service.py`, `services/__init__.py`.
- Migrations: `migrations/env.py`, `migrations/versions/fadb4cb3dce0_create_users_table.py`, `migrations/script.py.mako`, `migrations/README`, `alembic.ini`.
- Tests: `tests/conftest.py`, `tests/ui/conftest.py`, all six test modules in `tests/unit`, `tests/ui`, and `tests/integration`, and `tests/README.md`.
- Configuration/documentation: `compose.yaml`, `requirements.txt`, `pytest.ini`, `README.md`, `.gitignore`, and the task instructions in `AI_Testing/agent.md`. Comments were reviewed with their surrounding code. Secret values in `.env` were not printed or included in this report.

## Findings, ordered by severity

### 1. High — Concurrent operations can remove the last active Boss Admin

**Location:** `services/account_service.py:207` and `services/account_service.py:251`; `database/user_repository.py:16` and `database/user_repository.py:25`.

**Problem:** Deletion and demotion count active bosses using ordinary unlocked reads. A transaction groups the check and write but does not serialize competing transactions. With two active bosses, two concurrent self-demotions can each observe two bosses, each pass the check, and commit changes to different rows. Concurrent removal operations can produce the same invariant failure. The database has no constraint enforcing an active boss.

**Impact:** SAGE can end up with no active Boss Admin. If lower-role accounts remain, `database/setup_admin.py` refuses bootstrap because the users table is nonempty, so normal administration cannot restore access.

**Suggested fix:** Serialize all operations that can remove active Boss Admin status with a shared PostgreSQL transaction advisory lock or another common lock. Acquire it before reading the boss count, then re-read and validate before writing. Ensure deletion, demotion, and any future deactivation use the same lock. Add a two-connection concurrency test that forces both operations to overlap and verifies one is rejected.

**Evidence limit:** This is a source-based concurrency finding; it was not exercised against PostgreSQL during this read-only review.

**Solution Implemented**

Deletion and role changes now share a PostgreSQL transaction lock, so only one operation at a time can check and remove active Boss Admin status. Accounts are refreshed after acquiring the lock, and a shared check prevents removing the final active Boss Admin; future deactivation must follow the same locking rule. Concurrency and rollback tests confirmed the protection, with 50 tests and 104 subtests passing when this fix was completed.

### 2. High — Account permissions can become stale between validation and the write

**Location:** `services/account_service.py:111`, `services/account_service.py:172`, `services/account_service.py:181`, and `database/user_repository.py:16`.

**Problem:** Reading actor and target roles from the database protects against an already-stale UI, but neither record is locked. For example, a STEAM Specialist can read a target as a Work Study Assistant, begin hashing a replacement password, and then write it after another transaction has promoted the target to Boss Admin. The password update does not condition its write on the target's original role. Actor demotion or deactivation during an operation has a similar gap.

**Impact:** An operation may commit using permissions that no longer apply, including resetting a newly promoted administrator's password.

**Suggested fix:** Lock actor and target rows in a consistent order before authorizing mutations, and hold those locks through commit. Coordinate this with the shared Boss Admin invariant lock from finding 1. Alternatively, use conditional/versioned writes and reject/retry when authorization-relevant values change. Add an overlapping promotion/password-reset test; the existing sequential stale-target test does not cover this interleaving.

**Evidence limit:** Inferred from the unlocked reads and unconditional ORM writes; no database concurrency test was run.

**Solution Implemented**

Account mutations now lock the actor and target rows in ascending account-ID order before checking permissions, keeping those locks until commit or rollback. Deletion and role changes acquire the Boss Admin lock first, and waiting operations refresh account values before deciding whether they are allowed. Overlapping promotion/password-reset, actor-demotion, and opposing-update tests verified the behavior, with the full suite passing 56 tests and 108 subtests.

### 3. Medium — Unexpected login exceptions leave the dialog stuck

**Location:** `login_dialog.py:51`, `login_dialog.py:133`, `login_dialog.py:145`, and `login_dialog.py:166`.

**Problem:** `LoginWorker.run()` catches only `SQLAlchemyError`. An unexpected non-database exception exits without emitting `completed`. Thread shutdown depends on that signal, leaving the QThread event loop running, the login button disabled, and `reject()` unable to close the dialog. Additionally, `_finish_attempt()` unpacks `_result` before cleanup and assumes a result always exists.

**Impact:** A staff login can leave the modal interface permanently waiting until the application is forcibly terminated. AccountWorker already handles unexpected exceptions more defensively.

**Suggested fix:** Guarantee exactly one completion result and worker shutdown on all ordinary exception paths, return a generic safe error to the interface, and clean up/re-enable controls before interpreting the result. Handle a missing result defensively. Add real QThread login tests for success, invalid credentials, SQLAlchemy errors, unexpected exceptions, retry, and closing during an attempt.

**Evidence:** A read-only probe replaced `login_dialog.SessionLocal` with a callable raising `RuntimeError`. Calling the worker directly propagated the exception and emitted zero completion signals. Existing main-window login tests mock the entire LoginDialog and therefore do not test its worker lifecycle.

**Solution Implemented**

The login worker now emits one completion result after database session cleanup, catches unexpected exceptions with a safe error message, and clears its stored password. The dialog cleans up the stopped thread and restores controls before handling the result, permits retry even if no result arrives, and blocks closing while a worker is active. Six new tests cover real login threads, success, invalid credentials, database/unexpected/session-close errors, retry, missing results, and closing or repeated submissions during login; all 45 unit/UI tests and 117 subtests passed.

### 4. Medium — Missing local configuration prevents even Student Mode startup

**Location:** `database/connection.py:11` and `database/connection.py:16`; `main.py:16`; `README.md:11`.

**Problem:** Importing the UI imports the database connection module, which indexes mandatory values from the root `.env` immediately. That file is ignored by Git, no example configuration is provided, and the root README does not explain how to create it. Missing configuration raises `KeyError` before QApplication or the Student Mode window is created. Process environment settings alone do not supply these values because the code reads `dotenv_values()` directly.

**Impact:** A fresh checkout cannot follow the documented launch instructions successfully, and anonymous startup depends on staff database configuration even though constructing Student Mode does not query the database. Unit tests also inherit this configuration dependency through imports.

**Suggested fix:** Validate settings explicitly with a useful configuration message and support documented environment overrides. Initialize database-dependent components when needed so the anonymous interface can open without credentials, if that is the intended startup contract. Provide a secret-free `.env.example` and document environment creation, dependency installation, Compose startup, `alembic upgrade head`, and `python -m database.setup_admin` for a new installation.

**Evidence:** A read-only probe mocked `dotenv.dotenv_values` to return an empty dictionary and evaluated `database/connection.py`; it raised `KeyError('POSTGRES_USER')` without opening a database connection.

**Solution Implemented**

Database settings and sessions now initialize only when requested, with explicit validation, environment overrides, and actionable messages that never reveal passwords, allowing Student Mode to open without database credentials. Added a secret-free `.env.example` and installation instructions covering the virtual environment, dependencies, Compose startup, migrations, and first-admin bootstrap, while updating login, bootstrap, and Alembic to use the lazy configuration. All 68 tests and 138 subtests passed, including startup without credentials and configuration recovery; Compose validation and offline migration SQL generation also succeeded without starting containers or applying migrations.

### 5. Medium — Work Study Assistants cannot change their own password through the UI

**Location:** `sage_apps/account_management_app.py:98`, `sage_apps/account_management_app.py:100`, and `sage_apps/account_management_app.py:192`; `services/account_service.py:132`.

**Problem:** The main window enables Account Management for every staff role. For `base_specialist`, that dialog builds only a Create Account tab, disables its Create button, and never builds any self-edit/password controls. AccountService explicitly permits an assistant to update their own account, but the interface provides no route to that operation.

**Impact:** Assistants get a nonfunctional account screen and must ask another staff member to change their password. Current tests verify the disabled creation button but do not require usable self-service controls.

**Suggested fix:** Add a self-service form for assistants that submits `update_account(actor_id, actor_id, password=...)` without listing other accounts. Keep staff creation and account-list permissions restricted. Add a UI test exercising an assistant's password change.

**Evidence:** An offscreen probe constructed the assistant dialog and found exactly one tab, `Create Account`, with creation disabled.

**Solution Implemented**

Work Study Assistants now get a My Password form with password confirmation and a minimum-length check, submitting only their own account ID through the existing threaded update operation. Their screen neither lists other accounts nor exposes creation/deletion controls, and successful updates clear the password fields while failures permit retry. Three new UI tests verified validation, a real threaded password change that accepts the new password and rejects the old one, and recovery after failure; the full suite passed 71 tests and 141 subtests.

### 6. Medium — The documented test command discovers zero tests

**Location:** `README.md:31` and `README.md:34`; test subdirectories under `tests/`.

**Problem:** The root README recommends `python -m unittest discover -s tests -v`. In the available environment it does not recurse into the current test directories and runs zero tests. The README's description of one startup test and an `OK` result is outdated. The project now uses pytest configuration and directory markers, and `tests/README.md` already documents the appropriate runner.

**Impact:** Developers following the main README receive no application validation and may miss regressions.

**Suggested fix:** Replace the command with pytest instructions, distinguishing the safe unit/UI suite from integration tests that require and modify `sage_test`. Update the UI description at `README.md:23`, which still describes a blank window, and link to `tests/README.md` for details. Add a CI collection check that fails when expected tests are absent.

**Evidence:** Running the exact documented discovery command reported `Ran 0 tests` and `NO TESTS RAN`.

**Solution Implemented**

The root README now uses pytest commands, distinguishes database-free unit/UI tests from PostgreSQL integration tests, and describes the current interface. Added a Windows GitHub Actions workflow that checks test collection from every expected module before running unit/UI tests, plus a `--check-collection` guard that fails when any required module contributes no tests. Local validation collected all 71 tests, correctly rejected an intentionally excluded module, and passed 71 tests with 141 subtests; the new workflow has not yet run on GitHub.

