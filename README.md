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
Python dependencies are listed in `requirements.txt`, including `ollama==0.6.3`
(the Ollama Python client).
Camera controls start automatically when Home opens. On each new device, follow
the [camera setup and calibration guide](TouchControls/README.md): download the
Hand Landmarker model, check the webcam, and save a calibration for the desk/display
setup. Dependencies and the model are installed once per environment/device;
calibration is reused until the physical setup or display settings change.
Close the calibration/preview tool before launching SAGE so it releases the webcam.
Missing calibration/model files or a camera failure display a dismissible error;
mouse and physical-keyboard controls remain available.

Student Mode can open without database credentials or a running database:

```powershell
.\.venv\Scripts\python.exe main.py
```

The window starts in Student Mode with a title, avatar placeholder, and application
buttons. Staff login enables account management, including a My Password form for
Work Study Assistants. The second application button opens the G-code viewer;
its Home button returns to the existing SAGE screen and preserves the current session
and file selection. The third application button opens STEAM Guide; its Home button
preserves the current question, response, and session.
Close the home window or press Escape on the home screen to exit.

The G-code viewer loads your uploaded OctoPrint library. **View File List** opens
its folders; select a folder and press **Open** to enter it, use **Back** to go up,
and select a G-code to preview it. The dialog shows the current folder path.
Search filters names in that folder, and **Refresh** reloads the library from
OctoPrint. The viewer's previous/next arrows browse G-codes within the selected
file's folder. Supported extensions are `.gcode`, `.gco`, and `.g`.

G-code previews load in the background, so navigation and Home remain available
while a preview is generated. Rapid file changes keep only the latest queued
selection. Returning Home cancels the current preview; reopening the viewer resumes
it if needed. Uncached files exceeding 500,000 X/Y positions display a size-limit
message rather than a partial preview. Previews support straight-line X/Y movements.

**Start Print** starts the selected file already stored in OctoPrint. It is enabled
only after the selected file has downloaded successfully and a fresh status check
confirms the printer is connected and idle. Status updates automatically every three
seconds while the viewer is open. Printing, paused jobs, transitions, disconnected
printers, and unknown states disable the button. Clicking Start Print disables it
immediately, rechecks the printer, then sends one select-and-print request; OctoPrint
also rejects the command if another job starts between the check and submission.
File navigation is disabled during submission so the chosen file stays fixed.

Print requests are never retried automatically. After acceptance, Start Print stays
disabled until the job is seen as busy and later idle. If a request times out, its
outcome may be unknown: check OctoPrint, then click **Printer Status** to confirm the
printer is idle before retrying. The same manual check can release the button if a
very short job finishes between status updates. Returning Home cancels a pending
preflight check, but does not cancel a print command already sent or an active print.

Configure `OCTOPRINT_URL` (the server's base URL, including any hosting subpath)
and `OCTOPRINT_API_KEY` in the repository-root `.env`. The API user needs
`FILES_LIST` and `FILES_DOWNLOAD` for browsing and previews, `STATUS` for
Printer Status, and `FILES_SELECT` and `PRINT` to start printing. Environment variables override these values. No separate PC
G-code folder is required. This browser uses files uploaded to OctoPrint; it does
not browse the printer's SD card. See the [OctoPrint file API](https://docs.octoprint.org/en/main/api/files.html).

Selected files are downloaded to `sage_apps/thumbnails/gcodes/`; generated images
are cached in `sage_apps/thumbnails/`. Cache names include the server, full remote
path, and version metadata, so identically named files in different folders stay
separate. Metadata is checked before cache reuse, and Refresh rechecks the selected
file. The cache can be removed while SAGE is closed and will be recreated as needed.
File-list/metadata requests time out after 15 seconds; downloads time out after
120 seconds and are limited to 128 MB per file. Returning Home cancels pending
requests; reopening rechecks the selection. Missing files, permission failures,
and connection errors display a message; use Refresh to retry.

The **Printer Status** button above Start Print checks OctoPrint and reports whether
the printer is connected and idle or busy (including paused prints). Set
`OCTOPRINT_URL` to your OctoPrint server's base URL and `OCTOPRINT_API_KEY` to a key
with `STATUS` permission in the repository-root `.env`; environment variables override
these values. Settings are read on each check. The check runs without blocking the
interface and times out after eight seconds. Results are a snapshot; click again
to refresh. Unreachable servers, authentication failures, and unavailable printer
states show an explanation instead of claiming the printer is idle.

Camera input uses a one-second index-finger hover over SAGE controls. It works
across Home, the G-code viewer, STEAM Guide, and owned dialogs. Text fields use a
physical keyboard after being focused. Use in-dialog Close/Cancel buttons: the
camera pointer does not extend into native Windows title bars or other applications.

## STEAM Guide document search

Type a question and press Enter or select Ask SAGE to search the Markdown files in `STEAM_Tutorials`.
For example, try "Why won't OctoPrint connect?" or "My print isn't sticking."
Clear matches display the original instructions and the source filename and heading.
Similar matches request clarification; unsupported questions return no clear answer.
This version uses local keyword search with a small synonym list, not AI-generated
answers or a diagnosis. Specific equipment names and symptoms improve results.
Mixed printer/laser questions request clarification, and searches naming one machine
exclude documents explicitly titled for the other. Recognized phrases such as
"not dark enough" preserve their meaning; other negated wording asks for rephrasing
instead of silently dropping the negation. This is a limited keyword-search system,
so unfamiliar wording may still require a more specific question or browsing the
reference documents directly.

Use `#` for a document title and `##` / `###` for descriptive topic and troubleshooting
headings. Keep each procedure and its cautions together under the relevant heading.
Parent-section guidance is included with matching subsections. Added, edited, and
removed files are picked up on the next question without restarting the application.

`services/document_retrieval_service.py` loads and ranks sections independently of
the interface. `services/guide_response_service.py` formats matches and handles
uncertainty; a future AI responder can use the same retrieved sections and sources.
No AI credentials, network service, or database are required for document search.

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

Staff operations have database timeouts. After timeout cleanup, the dialog permits
closing or retrying. Reopen account management to check the result before retrying
a change; losing the connection does not prove the change failed.

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
