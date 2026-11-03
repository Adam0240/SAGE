# Camera tracking and standalone calibration

This standalone component tracks one index fingertip in the webcam image. It does
not calibrate the desk, detect surface contact, click buttons, or connect to SAGE's
UI yet. A projector is not required for this preview.

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
The downloaded model is excluded from Git. Use `--model PATH` for another local copy.

Run the preview:

```powershell
.\.venv\Scripts\python.exe -m TouchControls.camera_manager
```

Use `--camera 1` (or another index) if the desired webcam is not camera 0. The preview
is unmirrored. A green marker follows the index fingertip; its coordinates are in
the original camera frame, not screen pixels. Press Esc or Q, or close the window,
to release the camera. On camera failure the preview exits with an error instead
of continuing to use an old fingertip position. Close other camera applications
and check Windows camera permissions if the camera cannot open.

## Interface for the next milestone

`CameraManager(camera_index=0, model_path=...)` opens the camera and local model.
Call `update()` to process a frame, then read `frame`, `tracking_available`, and
`index_fingertip` (a floating-point `(x, y)` pair or `None`). A successful update
without a hand returns `True`; acquisition/inference failure returns `False` with
`last_error`. Use a context manager or call `release()` when finished.

Processing is synchronous to keep each result paired with its frame. When this is
integrated into Qt, create and use the manager in a worker thread, not the GUI
thread. The standalone calibration tool uses a worker thread for this purpose.

Before moving on, verify on the actual camera that the marker follows your index
finger across the image, disappears when your hand leaves, and the camera is
available again after closing the preview. Automated tests use simulated frames;
they do not establish physical tracking accuracy.

## Calibrate the projected desk

Close the camera preview first so the calibration tool can use the webcam. Keep
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
Saving replaces the file only after validation; merely capturing points does not
overwrite previous calibration. A camera failure disables capture and saving;
close the tool, fix the camera connection, and run it again.

The file records the mapping, camera index/resolution, display geometry/scaling,
and accuracy-check errors. `Calibration.load()` validates the file, `map_point()`
returns screen-local Qt logical coordinates, and `matches_setup()` lets future
input code check compatibility. Future widget targeting must account for the
stored display origin and window position; these are not physical display pixels.

Recalibrate if the camera/projector moves, the projection changes, or display
resolution/scaling changes. Software cannot automatically detect every physical
movement, so check alignment before reuse. The mapping assumes a flat desk and
does not detect contact or correct for fingers held substantially above the surface.

SAGE does not load or act on this file yet. Home-screen dwell activation is a
separate next step. A successful hardware calibration still needs to be performed
on your desk; automated tests verify the workflow and mathematics with simulated input.
