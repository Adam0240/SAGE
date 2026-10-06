# SAGE code review

Reviewed: October 6, 2026. Scope: the current working tree, following `AI_Testing/agent.md`. The user explicitly deferred Issue #10 and the formal Initializing SAGE use-case comparison.

## Review summary

SAGE has a sensible early architecture for a desktop STEAM-room assistant: PySide6 handles presentation, small services handle authentication and session identity, repositories handle persistence, and Alembic tracks schema changes. Argon2 password hashing, inactive-account rejection, database constraints, worker-owned database sessions, and transactional administrator setup are good foundations.

The implemented product is currently a student-mode interface shell plus staff login/logout. Tutorials, AI guidance, equipment operations, and authenticated account management are not implemented. The principal concerns are database privilege separation, brittle startup configuration, login failure recovery, text visibility, and gaps in onboarding and workflow tests. A framework rewrite is not warranted by this review.

### Files reviewed

- Application/UI: `main.py`, `login_dialog.py`.
- Database: `database/connection.py`, `database/models.py`, `database/user_repository.py`, `database/setup_admin.py`.
- Services: `services/authentication_service.py`, `services/password_service.py`, `services/session_service.py`, `services/__init__.py`.
- Migrations: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/README`, `migrations/versions/fadb4cb3dce0_create_users_table.py`.
- Tests: `tests/test_authentication_service.py`, `tests/test_password_service.py`, `tests/test_session_service.py`, `tests/test_startup.py`, `tests/test_user_repository.py`.
- Configuration/documentation: `compose.yaml`, `requirements.txt`, `README.md`, `.gitignore`, `AI_Testing/agent.md`.

Comments and inactive configuration examples were included. No live database privileges, records, or deployed schema were inspected. Virtual-environment and generated cache contents were excluded from source review.

## Findings ordered by severity

### 1. High before deployment: the application uses the database bootstrap credentials

**Locations:** `compose.yaml:8`; `database/connection.py:16`.

**Problem:** Compose supplies `POSTGRES_USER` and `POSTGRES_PASSWORD` to initialize PostgreSQL, and the desktop application uses those same settings for ordinary runtime connections. The official PostgreSQL image initializes this user as the database superuser on a fresh data volume. There is no separate restricted runtime account in the repository. This is a configuration finding; the privileges of any already-existing local database were not verified.

**Impact:** On the standard fresh setup, database access from the desktop process has privileges far beyond reading accounts. Anyone who can obtain its database credentials can bypass the application's staff login and change accounts or schema directly. Binding the database port to localhost limits remote exposure but does not separate local student access from database administration.

**Suggested fix:** Use distinct credentials for provisioning/migrations and application runtime. Grant the runtime account only the permissions needed by implemented workflows. For student-accessible machines, ensure OS permissions protect credentials; if students can access the client files or shared accounts will be used across machines, put privileged account and equipment operations behind an authenticated backend. Retain localhost binding for local development. This must be addressed before deployment to untrusted users; a trusted developer-only environment can defer it.

**Reference:** The [official PostgreSQL image entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh) initializes the configured user through `initdb` and identifies its password as the superuser password.

### 2. Medium: missing configuration prevents even Student Mode from starting

**Locations:** `database/connection.py:11`; `database/connection.py:16`; `main.py:5`.

**Problem:** Database settings are read and indexed at import time. A missing `.env` file or key raises `KeyError` before the main window can be constructed. Importing `main.py` imports `LoginDialog`, which imports database configuration, so this affects startup even when the user does not attempt staff login. Supplying settings solely through process environment variables also does not satisfy these direct file lookups.

**Impact:** A fresh checkout following the README cannot start without undocumented configuration. Authentication and GUI tests also require that configuration despite not connecting to PostgreSQL. Students cannot reach the default screen if the file is absent.

**Evidence:** Patching configuration loading to return an empty mapping reproduced `KeyError: 'POSTGRES_USER'` in an isolated Python process. No existing configuration file was edited.

**Suggested fix:** Validate configuration explicitly and report missing setting names clearly. Document and provide a non-secret example configuration. Prefer deferring database initialization until a database-backed operation is needed, and separate the model base from runtime connection configuration so model imports and isolated tests do not require credentials. If environment variables are supported, define their precedence over file values.

### 3. Medium: an unexpected worker exception leaves login stuck

**Locations:** `login_dialog.py:30`; `login_dialog.py:51`; `login_dialog.py:132`; `login_dialog.py:145`; `login_dialog.py:166`.

**Problem:** `LoginWorker.run()` catches only `SQLAlchemyError`. A different exception skips the `completed` signal. Thread shutdown is connected to that signal, so the worker thread's event loop remains running after the failing slot returns. `_finish_attempt()` also assumes `_result` is always a tuple.

**Impact:** The login button stays disabled with no explanatory message. Further attempts are rejected, and `reject()` prevents dismissal while `_thread` exists. The UI event loop remains responsive, but the login workflow is stranded.

**Evidence:** An in-memory probe used the actual Qt thread with mocked authentication. Injecting `RuntimeError` left the thread present, the login button disabled, and the error label empty after the worker returned. Success, invalid credentials, and `SQLAlchemyError` all cleaned up correctly. The probe explicitly stopped its remaining thread afterward.

**Suggested fix:** Guarantee a terminal outcome and thread shutdown for every worker execution. Handle unexpected exceptions at the worker boundary, show a generic failure, and log safe diagnostic information without credentials. Make UI cleanup tolerate a missing result and perform cleanup before interpreting the outcome. Add a regression test for the unexpected-exception path.

### 4. Medium: a connected but stalled database can make login indefinitely non-dismissable

**Locations:** `database/connection.py:26`; `login_dialog.py:166`.

**Problem:** The configured three-second `connect_timeout` bounds connection establishment, but there is no application-configured statement or lock-wait timeout. Once connected, a query waiting behind an exclusive schema lock or another database stall can keep the login worker occupied. The dialog deliberately blocks rejection throughout that period.

**Impact:** Students or staff may remain trapped in the modal login dialog even though the UI itself still processes events. An existing server timeout could limit this, but none is established by this repository.

**Suggested fix:** Configure an appropriate login-query timeout and a recoverable timeout outcome. If dismissal during an attempt is supported, retain ownership of the worker until it finishes and safely ignore late results; do not destroy a running thread. A cancellation request alone does not interrupt a blocking database call. Test delayed/timeout behavior with a controlled fake.

**Validation limit:** This finding follows from configuration and control flow; no live blocking query was created. PostgreSQL documents [statement and lock timeouts](https://www.postgresql.org/docs/17/runtime-config-client.html).

### 5. Medium: title and avatar text can be black on black

**Locations:** `main.py:29`; `main.py:44`; `main.py:76`.

**Problem:** The main window specifies a black background, but the title and avatar styles do not specify their foreground colors. Their text therefore depends on the platform palette.

**Impact:** On a light system palette, the title and avatar dots become unreadable against the background. Existing startup tests check visibility of widgets, not visibility of their contents.

**Evidence:** With Qt's offscreen platform, both labels resolved to foreground color `#000000` after the window was shown and styles were applied. This confirms the palette dependency; native display appearance was not visually inspected.

**Suggested fix:** Explicitly set a contrasting text color for both labels or a suitable shared label style. Check appearance under supported light/dark themes.

### 6. Medium: onboarding and test instructions are incomplete and outdated

**Locations:** `README.md:11`; `README.md:23`; `README.md:31`; `tests/test_user_repository.py:19`.

**Problem:** The README assumes a pre-existing virtual environment and describes a blank window. It omits dependency installation, required environment settings, PostgreSQL provisioning, migrations, initial administrator setup, and the `sage_test` database required by the documented full-suite command. Compose provisions the application database, not the separate test database.

**Impact:** A new contributor cannot reproduce startup or the advertised full test run using the documented steps. The repository presents less functionality than actually exists.

**Suggested fix:** Document Python/environment setup, dependency installation, configuration keys, database startup, `alembic upgrade head`, and `python -m database.setup_admin`. Describe current login/logout and placeholder functionality accurately. Separate quick tests from PostgreSQL integration tests, and explain explicit test-database provisioning and write behavior. Avoid promising a successful full-suite result without its prerequisites.

### 7. Medium: login integration, administrator setup, and migrations lack regression coverage

**Locations:** `tests/test_startup.py:38`; `tests/test_user_repository.py:31`; `database/setup_admin.py:15`; `migrations/versions/fadb4cb3dce0_create_users_table.py:21`.

**Problem:** Startup tests check the default mode and placeholder widgets but do not exercise the login dialog or the main window's authenticated transition/logout path. There are no existing administrator-bootstrap tests. Repository tests build tables from ORM metadata rather than applying Alembic migrations.

**Impact:** The worker failure in finding 3 is not detected by the existing suite. Bootstrap validation/transaction regressions and broken migrations can also escape coverage even if repository tests pass. The model and migration currently agree by static inspection, but that is not an executed migration test.

**Suggested fix:** Prioritize meaningful login lifecycle tests for success, failure, repeated submission, and cleanup, plus main-window login/logout integration with a fake dialog. Add bootstrap tests for existing accounts and invalid inputs; verify its concurrency protection in a disposable PostgreSQL integration environment. Test migration application and essential constraints against a fresh disposable database. Do not replace PostgreSQL-specific checks with SQLite-only tests.



