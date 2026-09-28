## SAGE

## STEAM Artificial Guidance Expert

SAGE is an AI-assisted STEAM guidance application currently in development. Its purpose is to support the operations of a STEAM/STEM Room by providing tutorials, troubleshooting assistance, and helping operate some of the technology available in the space.

STATUS: In Development

## Launching SAGE

Open PowerShell in the SAGE project folder. Activate the virtual environment if it is not already active:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run the application:

```powershell
python main.py
```

Currently, SAGE displays a blank black window titled "SAGE".
Click the window's close button to exit.

## Running Tests

With the virtual environment active, run this from the SAGE project folder:

```powershell
python -m unittest discover -s tests -v
```

The startup test verifies that the SAGE window opens, has the correct title, and is no longer visible after closing. A successful test run ends with "OK".