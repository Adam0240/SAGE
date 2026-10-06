## SAGE

## STEAM Artificial Guidance Expert

SAGE is an AI-assisted STEAM guidance application currently in development. Its purpose is to support the operations of a STEAM/STEM Room by providing tutorials, troubleshooting assistance, and helping operate some of the technology available in the space.

STATUS: In Development

## First installation

Install Python 3.14 for Windows. For staff login and account management, also install
Docker Desktop with Docker Compose and start Docker Desktop. Open PowerShell in the
SAGE repository root and create the Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The commands below use the environment's Python directly, so activation is optional.
Student Mode can open without database credentials or a running database:

```powershell
.\.venv\Scripts\python.exe main.py
```

The window starts in Student Mode with a title, avatar placeholder, and application
buttons. Staff login enables account management, including a My Password form for
Work Study Assistants; the other two application buttons
are currently placeholders. Close the window or press Escape to exit.

## Set up staff login

For a new installation, copy the configuration template without overwriting an existing
`.env`, then edit it and choose a nonempty database password:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
notepad .env
```

`POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` are required for database
operations. The optional `POSTGRES_HOST` defaults to `127.0.0.1`; `POSTGRES_PORT`
defaults to `5432` and must be an integer between 1 and 65535. The application reads
the `.env` at the repository root regardless of the working directory.

Start the local PostgreSQL service and wait for its health check, apply the migration,
then create the first Boss Admin interactively:

```powershell
docker compose up -d --wait db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m database.setup_admin
.\.venv\Scripts\python.exe main.py
```

The setup command asks for a name, username, and confirmed password of at least
12 characters; it creates an account only when the users table is empty. Later accounts
are created through authenticated account management. Adminer is optional:
`docker compose up -d adminer` exposes it at `http://127.0.0.1:8080`.

The Compose database uses a persistent volume. Editing `.env` does not change credentials
already initialized in that volume; use the existing database credentials for an existing
installation. The migration and bootstrap commands modify the selected database.

## Environment overrides

Environment variables with the same five `POSTGRES_*` names override `.env` values,
including empty values, which fail validation for required settings. For example, to
use a different database host for the current PowerShell session:

```powershell
$env:POSTGRES_HOST = "database.example.org"
.\.venv\Scripts\python.exe main.py
Remove-Item Env:POSTGRES_HOST
```

All required credentials may be supplied through the environment without a `.env`.
Docker Compose honors environment overrides for its database name, user, password,
and published port; `POSTGRES_HOST` selects the application's database server and does
not relocate the local Compose container. Credentials and connection settings are
cached once valid settings initialize the connection pool, so restart SAGE after changing them.
If configuration validation fails, correct the settings and retry login; missing or invalid settings
are reported without printing passwords.

## Running tests

Unit and UI tests do not require database credentials or a running PostgreSQL service:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/ui -q
```

Database integration tests require the configured PostgreSQL server and a separate
`sage_test` database, and write test data or create temporary schemas in that database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

See [tests/README.md](tests/README.md) for test categories, isolation, and schema permissions.

GitHub Actions checks collection from every expected test module, then runs the unit/UI
suite on Windows with Python 3.14 and offscreen Qt, without database credentials.
Run the same collection check locally without connecting to PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only --check-collection -q
```

The check fails if an expected module is missing or collects no tests; update the
`REQUIRED_TEST_MODULES` list in `tests/conftest.py` when intentionally adding or renaming
test modules. Use pytest for this directory layout; `unittest discover -s tests` does
not discover the nested test suite.
