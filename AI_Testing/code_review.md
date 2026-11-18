# Review of `main.py`

Reviewed November 18, 2026. Scope: the current working copy of `main.py`; imported services and related tests were inspected only to establish its contracts. No application or test code was changed during this review.

Implementation follow-up, November 18, 2026: all six findings below have now been addressed with user approval. The original findings and line numbers are retained as the review record; each issue's **Solution implemented** describes the subsequent changes. Application changes are confined to `main.py`; regression tests are in `tests/ui/test_home_voice.py`. The speech recognition, AI, and TTS service implementations are unchanged.

Maintainability follow-up: the subsequently approved extraction moves voice lifecycle logic and the capture adapter into `services/home_voice_controller.py`. `HomeVoiceController` owns recognition/AI/TTS coordination, cancellation, shutdown, and both voice timers. It emits button, avatar, and error signals; `main.py` retains layout, accessible button updates, dialogs, navigation, authentication, and camera integration. References below to the original window's voice methods now refer to controller methods; `cancel_speech()` is now `voice_controller.cancel()`, while closing uses `voice_controller.shutdown()`. All six fixes remain in place. The original speech recognition, AI, and TTS service files remain unchanged. Existing lifecycle tests were adapted to the controller boundary, with additional tests for avatar signal wiring and operation without a window.

## Findings

No Critical or High severity defects were established. The following findings are ordered by severity and then recommended priority. “Confirmed” means the behavior follows the current code and was reproduced with controlled dependencies; it does not mean the scenario was reproduced on the physical microphone or Zira engine.

### 1. Pending speech playback is not treated as an interruption

- **Severity:** Medium.
- **Location:** `main.py:320`, `main.py:419`, `main.py:628`.
- **Issue:** The button becomes enabled as soon as an AI response arrives, but interruption checks only `tts_service.is_speaking()`. It does not check `_awaiting_tts_completion`, which is already true after playback is requested. If the engine has accepted the utterance but has not entered Speaking yet, a click starts microphone capture without stopping that pending utterance or applying the 350 ms handoff delay. The old playback-completion handler can subsequently overwrite the microphone button state.
- **Impact:** Pending audio can overlap recording, potentially capturing SAGE's own answer. A later `ready` event can change an initializing or listening button to `Talk to SAGE`, enable it prematurely, and stop its animation. This defeats the intended separation between playback and recording.
- **Recommended fix:** Treat pending playback as interruptible work as well as actively speaking playback. Clear its completion flag, stop playback, stop the animation, and use the existing delayed handoff before starting capture. Ensure completion handlers cannot update a newer microphone session.
- **Evidence:** `TextToSpeechService.speak()` calls the engine's `say()` and returns true; it does not wait for Speaking. `is_speaking()` tests only the engine's current Speaking state. A probe returning true from `speak()` and false from `is_speaking()` produced one microphone start, zero TTS stops, and `_awaiting_tts_completion == True`. Delivering `ready` then produced `_speech_busy == True` with an enabled `Talk to SAGE` button. **Confirmed conditional logic defect; the size/existence of the pending-playback window on the deployed engine remains to be measured.**

**Solution implemented:** `toggle_speech()` now treats `_awaiting_tts_completion` as interruptible playback, even before the engine reports Speaking. It clears that flag before stopping Zira, immediately stops the avatar animation, and schedules microphone initialization through the 350 ms handoff timer. Late completion signals cannot restore the button while that flag is false. The interruption regression test now runs with both pending and active playback and verifies that recording cannot start immediately, the avatar stops, and a late `ready` signal does not overwrite initialization status.

### 2. Opening login leaves the microphone and assistant running behind a modal dialog

- **Severity:** Medium.
- **Location:** `main.py:528`–`main.py:540`.
- **Issue:** `handle_mode_button()` opens `LoginDialog.exec()` without cancelling current voice work. Other application-navigation handlers explicitly call `cancel_speech()`.
- **Impact:** A student or staff member can start recording and then open login. Recording continues while its stop button is inaccessible behind the modal dialog. Transcription, AI completion, and spoken answers can also continue during login. This creates unexpected audio capture during an authentication interaction and prevents immediate interruption through the home button. This is not evidence of typed passwords being recorded or disclosed.
- **Recommended fix:** Call `cancel_speech()` before entering the login dialog. Decide explicitly whether logout should also terminate the previous user's voice interaction; doing so would be consistent with clearing the staff session.
- **Evidence:** The login path has no cancellation call, whereas account management, G-code, and STEAM Guide do. With a recording active, a probe invoking the login path observed `_speech_busy == True` and zero calls to `cancel_recording()`. The speech worker operates independently of the modal dialog. **Confirmed.**

**Solution implemented:** `handle_mode_button()` calls `cancel_speech()` before either opening login or logging out. This cancels microphone/AI work, invalidates speech callbacks, stops playback and animation, and cancels delayed microphone startup. A parametrized regression test covers login and logout during initialization, listening, transcription, thinking, speaking, and delayed handoff, and verifies that late callbacks cannot restart work or display errors.

### 3. TTS errors remain active after navigation or cancellation

- **Severity:** Medium.
- **Location:** `main.py:458`–`main.py:472`, `main.py:474`–`main.py:489`.
- **Issue:** `on_tts_error()` opens a warning dialog unconditionally, even when `_awaiting_tts_completion` is false. Cancellation invalidates speech and AI request IDs, but TTS errors have neither an activity guard nor a closing guard. This differs from `show_camera_error()`, which checks `_camera_closing`.
- **Impact:** An error delivered after stopping playback can open a home-owned warning while the user is in another application, or while the main window is closing. A stale error can disrupt a later interaction. Repeated engine errors can create multiple dialogs.
- **Recommended fix:** Track whether the error belongs to an active home voice interaction and suppress obsolete/cancellation-related notifications. Add a shutdown guard before creating dialogs. Preserve errors for genuine active playback failures and explicit playback attempts when the engine is unavailable.
- **Evidence:** After `cancel_speech()` and `hide()`, invoking the connected error handler created a visible `QMessageBox` while the home window remained hidden. The service forwards engine errors without request IDs. Existing tests check stale recognition callbacks, but not stale TTS errors. **Confirmed handler behavior; occurrence depends on engine error delivery timing.**

**Solution implemented:** `on_tts_error()` ignores notifications when there is no active/pending playback or when shutdown has begun. The first active error clears the playback flag, preventing duplicate dialogs. `show_voice_error()` also rejects dialogs while the home window is hidden or closing. `on_tts_state_changed("error")` stops the animation and restores the button but retains error-reporting eligibility until the engine supplies its error message, so the guard does not swallow legitimate failures. Tests cover error-state-before-error-message ordering, repeated errors, navigation/close, and late errors during a subsequent microphone initialization.

### 4. Deferred shutdown allows new voice work to start

- **Severity:** Medium.
- **Location:** `main.py:311`, `main.py:481`, `main.py:601`–`main.py:608`.
- **Issue:** When a camera worker is present, `closeEvent()` cancels voice work, sets `_camera_closing`, requests camera shutdown, and ignores the close event. `cancel_speech()` enables the talk button, and `toggle_speech()` does not check `_camera_closing`. The window therefore remains visible and interactive while shutdown is pending.
- **Impact:** A user can start a new microphone session after requesting application exit. If camera shutdown is slow, the assistant can continue operating during that interval. The eventual second close cancels it again, so this is not evidence that voice work always survives process exit.
- **Recommended fix:** Disable home interaction once closing starts and guard asynchronous restart/entry points against the closing state. Preserve the existing cooperative camera shutdown and eventual second close.
- **Evidence:** `HomeInputController.stop()` requests interruption rather than synchronously finishing its worker; `stopped` is emitted later. With a worker held pending, a probe observed `_camera_closing == True`, a visible home window, and a successful new microphone start after clicking the talk button. **Confirmed.**

**Solution implemented:** A dedicated `_closing` flag is set before cancellation in `closeEvent()` and the direct Escape shutdown path. The home widget is disabled immediately. Voice activation, delayed microphone startup, TTS handlers, navigation, and session controls reject new work during closing; cancellation leaves the voice button disabled. The existing asynchronous camera shutdown and second close remain intact. A regression test holds the camera worker open after a close request and attempts clicks, direct voice/navigation calls, timer delivery, and late errors, then verifies final closure when the camera stops.

### 5. A cancelled handoff timer can consume a later handoff

- **Severity:** Low.
- **Location:** `main.py:329`, `main.py:371`–`main.py:378`, `main.py:476`.
- **Issue:** The static `QTimer.singleShot()` callback is neither stopped on cancellation nor tied to a request identifier. `_tts_handoff_pending` is one reusable Boolean. An old callback correctly does nothing while that Boolean stays false, but it can act on a subsequent handoff that sets it true again.
- **Impact:** If another interruption is initiated before the old timer fires, the old callback can start capture earlier than 350 ms after the newer interruption, defeating the playback-to-microphone settling delay. This requires a rapid cancel/new-interaction sequence; ordinary cancellation alone is already handled correctly.
- **Recommended fix:** Use a parent-owned single-shot timer that is stopped on cancellation and restarted for each handoff, or capture and validate a monotonically increasing handoff identifier in each callback.
- **Evidence:** A controlled probe scheduled handoff A, cancelled it, scheduled handoff B, and then invoked A's retained callback. That callback cleared B's pending flag and started the microphone. Existing tests invoke an old callback only when no newer handoff is pending. **Confirmed stale-callback behavior; practical frequency is unmeasured and likely low.**

**Solution implemented:** The anonymous `QTimer.singleShot()` was replaced by a parent-owned, single-shot `_tts_handoff_timer` with a 350 ms interval. `cancel_speech()` stops it; subsequent interruptions restart the same timer with a new deadline. Its timeout runs on the GUI thread, so cancellation/restart removes the obsolete timer registration instead of leaving an independent callback to consume another handoff. A real-event-loop regression test cancels one handoff, starts another, crosses the original deadline, and verifies that capture starts only after the replacement delay.

### 6. The button's accessible name does not communicate its changing state

- **Severity:** Low.
- **Location:** `main.py:181`, `main.py:335`, `main.py:362`, `main.py:368`, `main.py:396`.
- **Issue:** The explicit accessible name remains `Talk to SAGE` while the visible text changes to initializing, listening, transcribing, and thinking. State communication now resides entirely in the button, making that discrepancy meaningful rather than cosmetic.
- **Impact:** Accessibility clients reading the explicit name receive no indication of the current operation, particularly that the enabled listening button stops recording instead of initiating it. Actual announcements depend on the assistive technology.
- **Recommended fix:** Update the accessible name alongside state changes, or remove the explicit fixed name if Qt's default text-derived name gives the required behavior. Verify the deployed accessibility client before relying on announcements.
- **Evidence:** A probe observed visible text `Starting microphone...` while `accessibleName()` still returned `Talk to SAGE`. Every later transition changes text/enabled state only. **Confirmed property mismatch; assistive-technology impact was not exercised.**

**Solution implemented:** `set_talk_button_text()` updates both the visible text and explicit accessible name. All voice-state text changes use this helper, including interruption, failure, completion, and cancellation. The shared button assertion in the voice UI tests now checks accessible-name equality at each tested state. Screen-reader announcement behavior still requires a deployment-device check.

## Overall assessment

The ordinary voice cycle is coherent and well covered for a small application. Worker callbacks emit Qt signals rather than directly manipulating widgets. Speech and AI request IDs reject obsolete results after cancellation. Microphone readiness still comes from the existing three successful 100 ms reads; the adapter does not replace that warm-up with a UI timer. Both manual and automatic capture completion reach transcription status. Thinking and speaking share the existing avatar animation, and standard interruption stops it.

Widget/layout ownership, parent-owned animation/startup timers, `WA_DeleteOnClose` warning dialogs, and explicit deletion of modal dialogs are generally sound. The imported application windows cancel their work on hide, so hiding them during main-window closure is not itself a demonstrated cleanup defect. Cooperative speech cancellation does not synchronously interrupt an in-progress device/model call; that is an existing service contract, not proof of a leak. No definite memory leak, cross-thread widget mutation, authentication bypass, command injection, or equipment-control security defect was established in this file.

The important weaknesses occur at boundaries between voice work and login, playback startup, navigation, and deferred shutdown. The combination of Boolean flags, request IDs, and a visible-text comparison makes those boundaries harder to enforce consistently. A small explicit voice-state representation could help if the interface grows, but a broad controller rewrite is not necessary to address these findings. No changes are recommended merely for formatting, import order, or style.

## Three most important improvements

1. Treat pending and active TTS playback as one lifecycle when starting a new recording, and prevent stale completion events from changing the new session.
2. Cancel voice interaction before login so microphone control never becomes inaccessible behind authentication UI.
3. Enforce an inactive/closing boundary for voice entry points and TTS notifications, addressing both late dialogs and new recording during deferred shutdown.

## Validation and significant testing gaps

The existing focused suite was rerun during this review: **105 tests passed, plus 9 subtests**, covering home voice, main-window behavior, camera interaction, speech recognition, and TTS. Additional in-memory probes used mocked audio/AI dependencies and real Qt widgets to establish the findings above. No permanent tests were added. Physical microphone capture, live Ollama, Zira timing, and screen-reader behavior were not exercised. The full suite was not rerun for this review; previous full-suite results should not be confused with this review's validation.

Highest-value additional tests:

- Accept a TTS utterance while its engine still reports non-Speaking; click the button, then deliver delayed state/error signals. Assert no recording/playback overlap, preserved 350 ms delay, and no overwritten microphone state.
- Open login during initialization, listening, transcription, thinking, speaking, and delayed handoff. Assert cancellation and rejection of late work, including when login is cancelled.
- Cancel and navigate away, then emit TTS errors and completion events. Assert no obsolete dialogs or changes to a subsequent microphone session.
- Keep the camera worker alive after a close request. Attempt button activation and deliver timer callbacks while shutdown is pending; assert no new voice work.
- Schedule, cancel, and replace a handoff, then deliver the old callback before the new timer. Assert that only the current timer can start recording.
- Exercise callbacks from a real background thread into the Qt event loop, including deferred widget deletion. Existing UI voice tests primarily invoke callbacks directly on the UI thread and mock the service, so they do not fully validate queued signal ordering or destruction races.
- Verify accessible state names, plus one hardware smoke test covering the 300 ms microphone warm-up, immediate clicks after AI completion, playback interruption, and slow shutdown.

## Deployment decision

**Fix before public deployment:** findings 1–4. These affect predictable microphone control, authentication interactions, cancellation, and shutdown. For timing-dependent findings, add deterministic regression tests and confirm the relevant engine behavior rather than dismissing the gap because current happy-path tests pass.

**Lower-priority improvements:** finding 5's stale timer protection and finding 6's accessible-name synchronization. Move finding 6 into the deployment requirements if accessibility clients are part of the supported installation. An explicit voice-state helper is optional; its value would be enforcing these invariants, not cosmetic consolidation.

All six findings have now been implemented and covered by regression tests. The deployment recommendations above describe the original review priorities, not remaining unimplemented fixes. Physical-device timing and assistive-technology checks remain appropriate before deployment.

## Implementation validation

- Focused lifecycle regression run: **125 tests passed, plus 9 subtests**.
- Full unit/UI run (`tests/ui tests/unit`, with UI first to avoid the existing QCoreApplication test-order conflict): **382 tests passed, 173 subtests passed, and 3 subtests failed**.
- The three failures are the previously observed `test_camera_startup_does_not_import_vision_libraries` cases (`missing`, `invalid`, `valid`): the test forbids NumPy imports, while the existing speech recognition service imports NumPy through `main.py`. These failures are unchanged by the six fixes and were not modified as part of this work.
- `git diff --check` reported no whitespace errors. Live microphone/Zira and screen-reader checks remain unperformed.

After the controller extraction, the full unit/UI run completed with **384 tests passed, 173 subtests passed, and the same 3 NumPy-import startup subtest failures**. The existing lifecycle regressions and both new controller/signal-wiring tests passed. `main.py` is now 398 lines, with the voice lifecycle isolated in the new controller module.
