# SAGE code review — November 3, 2026

## Summary and scope

Read-only review of the current working tree, including its uncommitted changes, as requested by `AI_Testing/agent.md`. Only this report was changed. No dependencies were installed, Docker was not started, and no database operations, commits, branches, or remote changes were made.

The service/repository separation, database-side authorization, ordered account locks, calibration validation, and simulated dwell coverage provide a useful foundation. All existing unit/UI tests pass. The application still has lifecycle and responsiveness problems that prevent treating those passing tests as proof of deployment readiness. No confirmed critical vulnerability was identified in this review.

Reviewed application files: `main.py`, `login_dialog.py`, all three modules in `sage_apps/`, the modules in `database/` and `services/`, and `TouchControls/{camera_manager,camera_worker,calibration,hand_calibration,dwell,home_input,widgets}.py`. Reviewed migration/configuration files: `migrations/env.py`, the initial users migration, `pytest.ini`, `requirements.txt`, `compose.yaml`, `.gitignore`, and `.github/workflows/tests.yml`. Reviewed documentation: root `README.md`, `TouchControls/README.md`, `tests/README.md`, and the Markdown retrieval/document conventions. Reviewed test organization, fixtures, collection enforcement, and relevant unit/UI/integration regression cases. Legacy implementations, third-party environment files, and model binaries were not audited. This is a source review and offscreen test run, not a hardware or penetration test.

## Findings, ordered by severity

### 1. P2 — Camera shutdown can wait indefinitely for a blocked capture

**Locations:** `TouchControls/home_input.py:321`, `TouchControls/camera_worker.py:20`, `TouchControls/camera_manager.py:86`, `main.py:279`.

Stopping requests thread interruption, but the worker checks that request only between synchronous camera updates. Camera opening and frame acquisition have no application-level deadline. If a camera driver blocks during opening or `read()`, closing Home continually waits for worker completion; application shutdown additionally calls an unbounded `worker.wait()` on the GUI thread. The calibration window uses the same cooperative-stop approach.

**Impact:** A stalled/disconnected camera can prevent SAGE from closing normally. Normal successful cleanup tests do not exercise a capture call that never returns. This is a source-level failure path; no camera-driver hang was induced during this review.

**Suggested fix:** Establish bounded capture and shutdown behavior. Use backend-supported timeouts where they actually apply; if reliable interruption of the chosen webcam backend is unavailable, isolate capture in a process that can be stopped after a deadline. Keep GUI shutdown asynchronous and do not destroy or forcibly terminate a running QThread as a shortcut. Add a stalled-capture lifecycle regression test and verify unplug/reconnect/exit behavior on the target device.

### 2. P2 — Database operations can leave staff dialogs impossible to dismiss

**Locations:** `database/connection.py:61`, `database/user_repository.py:23`, `login_dialog.py:196`, `sage_apps/account_management_app.py:495`.

The engine configures a connection timeout, but no statement or lock deadline. Account operations explicitly wait for advisory and row locks. Login and account-management dialogs reject Cancel/Close while their worker exists. A long-lived conflicting transaction can therefore leave account management open indefinitely; an established connection stalled during a query can similarly strand login. A connection timeout does not bound these later operations.

**Impact:** The GUI event loop may remain responsive, but the user cannot leave the modal staff workflow or return to the rest of SAGE.

**Suggested fix:** Configure suitable database statement and lock timeouts, handle timeout errors with rollback and a retry message, and define safe cancellation/connection-failure behavior. Keep the dialog/thread alive until cleanup finishes. Add bounded-operation tests; the concurrency integration test already uses a statement timeout, whereas production does not.

### 3. P2 — Closed staff dialogs accumulate and retain entered passwords

**Locations:** `main.py:228`, `main.py:248`, `login_dialog.py:196`.

Each login/account-management visit creates a new dialog parented to Home, calls `exec()`, and never deletes that dialog after it returns. Closing a dialog hides it; its Qt parent keeps it alive. Login clears the password after an attempted login, but cancelling before submitting leaves the field populated. Account forms can similarly retain unsubmitted values.

**Evidence:** An offscreen reproduction opened and cancelled login three times with a synthetic password. After processing events, Home still owned three `LoginDialog` instances, all with nonempty password fields. No real credentials were used or printed.

**Impact:** Repeated visits accumulate hidden widgets and unnecessarily retain sensitive form contents for the Home window's lifetime.

**Suggested fix:** Copy successful login result values, clear sensitive fields, and schedule each completed staff dialog for deletion after `exec()` returns. Respect existing worker-close guards. Add a regression that repeatedly opens/cancels the dialogs and checks deferred deletion and password clearing. The document/file dialogs already demonstrate explicit `deleteLater()` cleanup.

### 4. P2 — Uncached G-code previews block the entire GUI

**Locations:** `sage_apps/gcode_display_print_app.py:375`, `services/gcode_preview_service.py:25`.

File selection calls `get_preview()` synchronously from the GUI handler. A cache miss reads the full toolpath, stores all coordinates, creates additional coordinate/point collections, draws every segment, and saves the image before returning. There is no file-size or work bound. Reading a line at a time in the parser does not make the overall preview streaming or nonblocking.

**Impact:** Large files or slow storage can freeze navigation, painting, and camera observation processing. Short fixture files and cached-image tests do not establish responsiveness for realistic large toolpaths.

**Suggested fix:** Generate previews in a worker and return a QImage to the GUI for QPixmap/display updates. Associate results with the selected file/request so stale completions cannot replace a newer selection. Consider bounded/downsampled preview geometry and add a slow-service responsiveness test.

### 5. P2 — Repeated Markdown parent headings mix unrelated guidance

**Location:** `services/document_retrieval_service.py:143`.

Ancestor context is reconstructed by comparing heading-text tuples against every record in the document. Distinct occurrences of the same parent heading therefore look like the same ancestor, including occurrences later in the file.

**Evidence:** For a document containing `## Setup` with a first caution and `### Alpha`, followed by another `## Setup` with a second caution and `### Beta`, the parsed Alpha section receives both cautions. The read-only reproduction returned `First setup caution.\n\nSecond setup caution.` as Alpha's context.

**Impact:** A retrieved procedure can be returned with instructions from a different section. Unique result identifiers do not prevent this context error.

**Suggested fix:** Track structural heading instances, or capture the actual ancestor bodies while building the section tree, rather than matching ancestor names globally. Add repeated-heading tests proving each child receives only its own ancestors' guidance.

### 6. P2 — Camera dependency imports still run on the GUI thread

**Location:** `main.py:193`; related module imports in `TouchControls/calibration.py:10` and `TouchControls/camera_manager.py:13`.

The zero-delay startup timer calls `start_camera_controls()` on the GUI thread. Importing `HomeInputController` synchronously loads OpenCV, MediaPipe, and their dependency chain before the worker starts. Moving model creation/capture to a worker does not move these imports. The cold-start duration was not benchmarked in this review.

**Impact:** On a fresh process or slower device, camera startup can temporarily prevent Home from painting/responding, even before calibration validity is checked. Tests that have already imported these modules do not reproduce cold-import cost.

**Suggested fix:** Keep the GUI/controller import path lightweight and perform heavy vision imports/initialization inside the worker. Avoid loading vision libraries merely to report missing calibration. Measure first-launch event-loop responsiveness in a fresh process.

### 7. P3 — Setup and test documentation has fallen behind the implementation

**Locations:** `README.md:9`, `TouchControls/README.md:3`, `tests/README.md:3`.

The root installation path starts SAGE without explaining that camera controls now start automatically and require a separately downloaded model plus calibration. The TouchControls introduction says it does not click buttons or connect to SAGE yet, contradicting its later integration section. The test inventory omits the guide, camera, calibration, and dwell modules despite those modules being collected and run.

**Impact:** A new-device setup follows the documented root steps into a camera error, and maintainers receive conflicting descriptions of implemented behavior and coverage.

**Suggested fix:** Link camera installation/calibration from the root setup instructions, distinguish the standalone camera preview from the integrated controller, and update the test inventory and obsolete future-tense comments. No documentation other than this report was edited.

## Reported popup behavior and other limits

- The disappearing pointer near the popup's native X is explained by `TouchControls/home_input.py:283`: points outside the active window's client rectangle are explicitly discarded. `PointerOverlay` is a child widget and cannot paint on the Windows title bar. This is a current capability limit, not loss of camera tracking. The simplest SAGE-local solution is to use consistent, prominent Close/Cancel controls inside each dialog; supporting native title-bar interaction would require additional design. The existing internal buttons should remain available while a modal dialog is active; background controls should remain blocked.
- Text dwell now focuses an editable field and requires physical keyboard input, matching the requested removal of the popup keyboard.
- The hardcoded default G-code directory is specific to the development machine. Constructor injection supports tests, but deployment still needs an intentional directory configuration. G-code preview is limited to the implemented straight-line parsing; printing remains disabled. These are scope/deployment limitations, not newly implemented features.
- Retrieval and response generation remain separate. Current keyword matching and explicit clarification are not an AI assistant, and passing existing examples does not prove general-language understanding.
- No missing required test module was detected. Important coverage gaps remain for the findings above, native-window behavior, actual camera latency, and physical calibration accuracy. No numerical code-coverage claim is made.

## Test results

Existing Python environment was available. Commands were run from the repository root, with `QT_QPA_PLATFORM=offscreen` for Qt execution.

| Check | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -B -m pytest tests/unit tests/ui -q -p no:cacheprovider --tb=short` | **195 passed, 165 subtests passed**, 6.27 seconds; no skips reported. |
| `.\.venv\Scripts\python.exe -B -m pytest --collect-only --check-collection -q -p no:cacheprovider` | **212 tests collected**, required-module check passed. Collection does not run database fixtures. |
| `.\.venv\Scripts\python.exe -B -m pip check` | **No broken requirements found** in the installed environment. This does not independently verify clean installation on another device or GitHub Actions execution. |
| Cancelled-dialog reproduction | Confirmed three retained login dialogs with three nonempty synthetic password fields. |
| Repeated-heading reproduction | Confirmed unrelated sibling-parent guidance included in a child's context. |
| PostgreSQL integration execution | **Not run:** 17 tests collected but intentionally excluded because they create/write database state, prohibited by the review instructions. |
| Webcam/projector and native Windows interaction | **Not run:** offscreen/simulated tests do not verify physical tracking, title bars, driver stalls, or display duplication. |

The initial sandboxed unit/UI attempt reported 128 passed, 67 fixture-setup errors, and 165 subtests passed due to temporary-directory access restrictions. After the approved rerun with access to pytest's temporary folder, all 195 tests passed. The initial errors are not presented as application regressions. No application or test code was changed to obtain the passing run.
