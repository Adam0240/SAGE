# Camera controls, setup, and calibration

SAGE tracks one index fingertip and activates an enabled control after a one-second
hover. The shared input controller follows Home, SAGE apps, and their owned dialogs.
This is hover-based input, not physical contact detection. Windows duplicate-display
mode shares the screen with the projector; SAGE does not detect projector connection.

For a new device, install dependencies, download the model, optionally check tracking
with the standalone preview, then calibrate the desk and close the tool before
starting SAGE. The model and calibration are excluded from Git. The model is reusable;
calibration belongs to the physical camera/projector/display setup.

## Install dependencies and the model

From the SAGE repository root, install the dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download Google's Hand Landmarker model once (internet is not needed at runtime):

```powershell
New-Item -ItemType Directory -Force TouchControls/models
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile TouchControls/models/hand_landmarker.task
```

Model source: [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker).
The preview and calibration tools accept `--model PATH` for another local copy.
Integrated SAGE uses `TouchControls/models/hand_landmarker.task`, so keep a model at
that default path when running the main application.

## Check tracking with the standalone preview

The preview only shows tracking in camera coordinates; it does not activate SAGE
controls or require a projector. Run it with:

```powershell
.\.venv\Scripts\python.exe -m TouchControls.camera_manager
```

Use `--camera 1` (or another index) if the desired webcam is not camera 0. The preview
is unmirrored. A green marker follows the index fingertip; its coordinates are in
the original camera frame, not screen pixels. Press Esc or Q, or close the window,
to release the camera. On camera failure the preview exits with an error instead
of continuing to use an old fingertip position. Close other camera applications
and check Windows camera permissions if the camera cannot open.

Verify on the actual camera that the marker follows your index
finger across the image, disappears when your hand leaves, and the camera is
available again after closing the preview. Automated tests use simulated frames;
they do not establish physical tracking accuracy.

## Calibrate the projected desk

Close SAGE and the camera preview first so the calibration tool can use the webcam. Keep
Windows in duplicate-display mode and leave the camera, projector, desk, display
resolution, and scaling in their intended operating positions/settings.

```powershell
.\.venv\Scripts\python.exe -m TouchControls.hand_calibration
```

Use `--camera 1` if needed, matching the preview's camera selection. The tool runs
full screen on the primary display; Windows duplicates it onto the projector.

1. Put your index fingertip at each red target, close to the desk and at the height
   you intend to use for interaction. Hold steady for about a second and press
   **Enter**. Four corner targets establish the mapping.
2. Repeat for five independent accuracy-check targets. The green pointer shows
   the mapped fingertip position. Each check must be within 25 Qt logical pixels.
   If a check fails, reposition on the red target and retry Enter, or press **R**
   to restart all calibration points. Do not move to the green pointer to pass a check.
3. After all checks pass, inspect the pointer alignment and press **S** to save.
4. Press **Esc** to close. Cancelling before saving leaves any previous file intact.

The default output is `TouchControls/calibration.json`, excluded from Git because
it belongs to this physical setup. `--output PATH` selects a different file.
Integrated SAGE loads the default path; use the default output for normal setup.
Saving replaces the file only after validation; merely capturing points does not
overwrite previous calibration. A camera failure disables capture and saving;
close the tool, fix the camera connection, and run it again.

Recalibrate if the camera/projector moves, the projection changes, or display
resolution/scaling changes. Software cannot automatically detect every physical
movement, so check alignment before reuse. The mapping assumes a flat desk and
does not detect contact or correct for fingers held substantially above the surface.

Home loads this file automatically on startup. A successful hardware
calibration must be performed on your desk; automated tests verify the workflow
and mathematics with simulated input.

## Automatic one-second dwell throughout SAGE

Close the standalone calibration/preview tool and start SAGE normally. Camera
controls start automatically when Home first appears, using the saved calibration's
camera index. There is no enable/disable button or status row. Missing/invalid calibration,
changed camera resolution, or changed display geometry/scaling prevents activation
and displays a dismissible error dialog; mouse and keyboard input remain available.
Restart SAGE after correcting a camera/setup failure. Run calibration again if the setup changes.

A white pointer follows your index fingertip. Hold it over an enabled Home button
for one continuous second; a green ring shows progress. Move away before activating
the same button again. Losing tracking cancels pending progress, and brief tracking
loss does not rearm an already activated button.

The same camera session follows the active SAGE window. Home, G-code viewer,
STEAM Guide, login/account dialogs, document viewers, and confirmation dialogs use
their existing handlers and account permissions. Modal dialogs take priority over
the screen behind them. Disabled controls remain unavailable. Circular Home
launchers only respond inside their circular area. Coordinates account for each
window's position; keep SAGE windows on the calibrated display. Windows duplicate
mode continues to handle projector output.

Hold over an editable text field to focus it, then type using the physical keyboard.
No pop-up keyboard is displayed. Password fields remain masked. Hold over a dropdown to open a
larger option picker, select a row, then choose Select. File-list rows are selected
by dwell and opened using the existing Open button. Account tabs can be selected
by dwell; their scroll arrows work if labels do not all fit.

Use Up/Down buttons to scroll answers, reference documents, option lists, and file
lists; Left/Right scrolls the reference cards. Each activation advances half a page,
and requires departure before repeating. STEAM Guide has an Ask SAGE button.
Document viewers have Close buttons; login has Cancel and account management has
Close. Existing busy-operation restrictions still apply when closing staff dialogs.
The pointer is confined to the active SAGE window's content area. It disappears
outside a modal dialog and over its native Windows title bar; use the internal
Close/Cancel button instead of the title-bar X. Underlying windows remain inactive
until the modal dialog closes.

Opening/closing windows or changing tabs resets pending dwell.
Another full dwell is required on the newly active screen. Camera activation pauses
when an external application has focus; the system mouse is never moved. Closing
SAGE requests camera cleanup before closing the window. Capture runs in a supervised
process so stalled camera calls can be stopped while the UI remains responsive.
Startup times out after 30 seconds; a running camera that produces no observations
for 5 seconds is stopped with an error. Verify unplugging/reconnecting and closing
on your webcam; automated tests simulate blocked capture in child processes.

Hardware checks (the automated suite simulates camera input):

- Open G-code, select files with arrows and the searchable list, and return Home.
- Enter a STEAM Guide question with the physical keyboard, select Ask SAGE, scroll the
  answer, open/scroll/close a reference, and return Home.
- Log in, navigate account tabs and dropdowns, cancel confirmation dialogs, close
  account management, and log out. Use test accounts when checking account changes.
- Check that removing your hand cancels dwell and holding over a control only
  activates it once. Confirm no underlying screen reacts while a dialog is open.
