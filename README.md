# SAGE — STEAM Artificial Guidance Expert

**Status:** In development

SAGE is a Windows desktop application designed to assist visitors and staff in the STEAM Room. It provides equipment tutorials, troubleshooting help, voice-based questions and answers, and access to OctoPrint G-code files.

## Features

- **STEAM Guide:** Searches local Markdown tutorials and uses a local Ollama model to answer questions grounded in those documents. If Ollama is unavailable, SAGE falls back to the documentation.
- **Talk to SAGE:** Records a spoken question, transcribes it locally with faster-whisper, and reads the answer aloud using Microsoft Zira.
- **G-code viewer:** Browses and previews files uploaded to OctoPrint, checks printer status, and starts a print when the printer is available.
- **Camera controls:** Supports index-finger hover navigation after webcam setup and calibration. Mouse and keyboard remain available.
- **Staff accounts:** Provides login and account management through PostgreSQL. SAGE starts in Student Mode without a database.

## Install and run

**Requirements:** Windows and Python 3.14. Docker Desktop is needed only for staff accounts. Ollama, speech recognition, and camera controls require the additional setup below.

Open PowerShell in the SAGE project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

SAGE opens in **Student Mode** by default. The commands use the virtual environment directly, so activating it is optional.

### Local AI (Ollama)

Install and start [Ollama for Windows](https://docs.ollama.com/windows), then download the model:

```powershell
ollama pull qwen3:1.7b
```

Leave the Ollama application running while using AI-generated answers. SAGE can still retrieve documentation when Ollama is offline. Optional `.env` settings are `SAGE_OLLAMA_MODEL`, `SAGE_OLLAMA_HOST`, and `SAGE_OLLAMA_TIMEOUT`.

### Voice assistant

Install the speech dependencies and download the transcription model using the **same Windows account and Python environment** that run SAGE:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('base.en'))"
```

Select a working default microphone in Windows and enable microphone access for desktop apps. Speech playback requires the Windows **Microsoft Zira** voice and Qt's `winrt` speech engine. Click **Talk to SAGE** to start recording; recording stops after silence or when you click again. Click during spoken playback to interrupt it and ask another question.

See [speech setup and troubleshooting](services/SPEECH.md) for device checks, offline requirements, and voice lifecycle details.

### OctoPrint

Staff sessions use manual logout. Staff should return SAGE to Student Mode before leaving the workstation; navigation between apps preserves the signed-in session.

Add these settings to the project-root `.env` file:

```dotenv
OCTOPRINT_URL=http://YOUR_OCTOPRINT_SERVER:5000
OCTOPRINT_API_KEY=YOUR_API_KEY
```

The API key needs `FILES_LIST` and `FILES_DOWNLOAD` for browsing, `STATUS` for printer status, and `FILES_SELECT` and `PRINT` to start printing. The viewer uses files uploaded to OctoPrint, not files on the printer's SD card.

**Print safety:** **Start Print** is available only when the printer is connected and idle. Requests are not automatically retried. If a print request times out, check OctoPrint and confirm printer status before trying again; leaving the viewer does not stop a print already submitted.

Downloaded G-code and preview images are cached under `SAGE` in Qt's per-user cache location, so normal use does not require writes to the installation directory. Cache cleanup retains up to 512 MiB/128 downloaded files and 64 MiB/512 preview images, expiring inactive entries after 30 days. Active downloads, selections, and rendering sources are protected with entry locks and may temporarily exceed those budgets. Cleanup runs during cache use and release; it only removes SAGE-owned entries, leaving legacy caches and unrelated files alone. If storage is full or unavailable, downloads report a cache error; image previews can still render without saving a PNG.

### Camera controls

Follow the [camera installation and calibration guide](TouchControls/README.md) before using hand tracking on a new computer. The camera pointer works within SAGE, not in Windows title bars or other applications. If camera setup is incomplete or the device fails, mouse and keyboard controls remain available.

### Staff login (optional)

Install Docker Desktop, start it, and configure the PostgreSQL credentials in `.env`. To create `.env` from the example without overwriting an existing file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`, then initialize the database and first administrator:

```powershell
docker compose up -d --wait db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m database.setup_admin
```

The administrator setup is interactive and creates the first account only when no users exist. **Keep `.env` out of Git**; changing its database credentials later does not automatically update an existing PostgreSQL volume.

## Using the documentation

STEAM Guide searches the local Markdown files in `STEAM_Tutorials`. Ask specific questions such as *“Why won't OctoPrint connect?”* or *“My print isn't sticking.”* SAGE requests clarification when a question is ambiguous and avoids inventing undocumented numerical equipment settings.

To add instructions, use `#` for the document title and `##` or `###` for each topic. Keep safety warnings alongside the relevant procedure. Updates are picked up on the next question.

## Tests and code quality

Run unit and UI tests from the project root (UI tests first):

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest tests/ui tests/unit -q
```

Database integration tests require the separate configured test database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

To generate fresh coverage data for SonarQube:

```powershell
.\.venv\Scripts\python.exe -m coverage erase
.\.venv\Scripts\python.exe -m coverage run -m pytest tests/ui tests/unit -q
.\.venv\Scripts\python.exe -m coverage report -m
.\.venv\Scripts\python.exe -m coverage xml -o coverage.xml
```

Run the report and XML steps separately even if tests fail. `.coveragerc` measures `main`, `sage_apps`, and `services`; its 75% local threshold is separate from SonarQube's quality gate. With Pysonar installed and `SONAR_TOKEN` configured in `.env`, run:

```powershell
dotenv run -- pysonar
```

See [test documentation](tests/README.md) for test categories, isolation, and database requirements.

## Project layout

- `main.py` — home screen, navigation, and application startup
- `sage_apps/` — STEAM Guide, G-code viewer, and account management
- `services/` — voice input/output, AI, document retrieval, and background workers
- `STEAM_Tutorials/` — equipment instructions and troubleshooting reference material
- `TouchControls/` — webcam controls and calibration
- `tests/` — automated tests
