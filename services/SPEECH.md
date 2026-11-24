# Speech setup and lifecycle

SAGE's home **Talk to SAGE** button uses `supervised_speech_service.py` to run
`speech_recognition_service.py` in a reusable child process, recording mono
microphone audio and transcribing it locally with faster-whisper.
`home_voice_controller.py` connects recognition to the shared AI response worker
and Microsoft Zira playback. The recognition service remains GUI-independent and
can also be used directly. There is no wake-word activation. See the
[home voice assistant](../README.md#home-voice-assistant) for button states and
[Ollama setup](../README.md#ollama-setup) for generated answers.

## Dependencies

From the repository root, install speech dependencies into the environment used
to launch SAGE:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import sounddevice; from faster_whisper import WhisperModel; print(sounddevice.query_devices())"
```

The optional requirements are separate from the application's pinned requirements;
the mocked tests do not establish a working combination of native dependency
versions. Validate installation and actual transcription on the deployment Python
before pinning its speech dependencies. In particular, Python 3.14 compatibility
must be checked rather than inferred from a package's minimum Python version.
A separate environment can run the service directly, but the home button's child
process uses the same Python environment as `main.py`.

- **NumPy:** audio arrays and RMS amplitude calculation.
- **sounddevice:** microphone capture. Windows pip installations include PortAudio;
  Linux may need the system PortAudio package. Select a working default input
  device in the OS and allow desktop applications microphone access.
- **faster-whisper:** transcription, including dependencies such as CTranslate2
  and PyAV. The service requests CPU `int8`; CUDA is not required. PyAV wheels
  include FFmpeg libraries, so a separate FFmpeg executable is not required.

NumPy and sounddevice are imported when capture begins; faster-whisper is imported
when the transcription model is first loaded.
Missing imports during a request are delivered through `on_error`.

For spoken answers, SAGE uses `TextToSpeechService` with Qt's `winrt` engine and the
exact voice name `Microsoft Zira`. Ensure that engine and voice are available to
the Windows account running SAGE. A missing voice does not prevent Home from
opening, but an attempted spoken response reports that playback is unavailable.

Upstream setup references:
[sounddevice installation](https://python-sounddevice.readthedocs.io/en/latest/installation.html)
and [faster-whisper requirements](https://github.com/SYSTRAN/faster-whisper#requirements).

## Prepare the model while online

The default model is `base.en`. Runtime loading uses `local_files_only=True`:
the service will report an error if the model is missing, rather than download it.
Package installation and model download are separate steps.

To populate the default Hugging Face cache for the same OS account/environment:

```powershell
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('base.en'))"
```

Alternatively, download a portable model directory outside the repository:

```powershell
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; download_model('base.en', output_dir='D:/SAGE-models/base.en')"
```

Copy the **entire directory**, including tokenizer/configuration/vocabulary files
and model weights, to an offline computer with the speech dependencies installed.
Do not copy just `model.bin`, and do not commit models or caches to Git.
Pass the actual model directory as `model_size`:

```python
from services.speech_recognition_service import SpeechRecognitionService

service = SpeechRecognitionService(model_size="D:/SAGE-models/base.en")
```

An explicit directory avoids dependence on another user's Hugging Face cache.
The example above configures a direct service instance. The home controller uses
the default cached `base.en` model; it has no model-path environment setting.
To check model loading without accessing the microphone, disconnect networking
and run:

```powershell
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('D:/SAGE-models/base.en', device='cpu', compute_type='int8', local_files_only=True); print('Local model loaded')"
```

See the upstream [model download helper](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py).

## Home recovery and process ownership

Home owns one speech child process. Successful requests reuse its loaded model.
The supervisor runs outside the Qt thread and applies a 30-second capture/startup
deadline (the configured maximum recording duration plus 10 seconds), then a
120-second deadline for model loading and transcription after capture ends.
These deadlines do not depend on a blocked native operation returning.

Navigation cancels the request immediately in the UI and gives the child one
second to finish cooperatively. If it remains blocked, the supervisor terminates
it, waits up to one second, and, if necessary, kills it and waits another second.
No replacement starts until the previous process is confirmed dead. If termination
fails, voice stays disabled in the service until SAGE is restarted. Timeout reports
an error and allows a manual retry using a fresh worker; it does not retry a recording
automatically. A retry can briefly be rejected while cleanup is still finishing.
Shutdown and controller destruction also dispose of the child without waiting in Qt.

The ready/captured/result/error callbacks are delivered from the supervisor thread
and retain Home's request-ID filtering. Cancelled requests do not deliver transcripts
or errors. Native model state is lost only when the child exits; idle and normally
completed requests preserve it. Windows packaged entry points use `freeze_support()`.

Before enabling public voice use on the deployment machine, test microphone
disconnect/reconnect during capture, cancellation during transcription, timeout
recovery, a successful retry, and closing SAGE during each stage. Confirm there is
no remaining speech child and no competing microphone owner. Process tests cannot
prove that a specific device driver releases hardware after process termination;
if it does not, restart SAGE/device services and resolve that device issue before
public use.

## Direct engine lifecycle contract

The following describes direct use of `SpeechRecognitionService`. Home wraps this
engine in the supervised process above; direct callers do not get process recovery.

- `start_recording(on_result=None, on_error=None, on_ready=None)` returns `True` when a worker starts, or
  `False` while a previous request is still busy. Model loading is lazy and the
  loaded model is reused. A thread-start failure raises synchronously and restores
  the idle state.
- `is_recording()` means **busy**, including model loading, transcription, and
  callback execution, not just microphone capture.
- Capture uses 16 kHz mono float32 audio by default, in 100 ms reads. It stops
  after 1.5 seconds of silence following detected speech, 10 seconds without
  speech, or 20 seconds overall. RMS amplitude above 0.015 counts as speech;
  this is an amplitude heuristic, not a learned speech detector. Room noise may
  trigger it, so hardware testing and threshold tuning are necessary.
- The home controller overrides silence duration to **2.5 seconds** and RMS
  threshold to **0.005**. The service defaults above still apply to direct callers
  that do not override them.
- `on_ready()` fires after three successful 100 ms audio reads, unless capture has
  been stopped or cancelled. Home keeps the button disabled as
  `Starting microphone...` until that callback is delivered, then enables
  `Listening...`. Audio captured during warm-up is preserved.
- `stop_recording()` requests the end of capture and transcription of detected
  speech. Silence or no captured audio produces `on_result("")` without loading
  the model. Stop during transcription lets that transcription finish.
- `cancel_recording()` requests the end of capture and suppresses subsequent
  results/errors when cancellation is observed. It is safe to repeat. A callback
  already executing cannot be retracted. Cancel does not interrupt a native
  audio read, model load, or decoding call; the service remains busy until that
  operation returns. Timing limits are checked between reads, so a hung audio
  driver can exceed them. This is not a bounded hardware-shutdown guarantee.
- Input stream failures, audio overflow, missing models, and transcription errors
  call `on_error(str(error))` unless cancelled. The stream context is exited and
  busy state is reset when the worker finishes, allowing a retry. No automatic
  retry or model download occurs.
- All three callbacks run on the **worker thread**. Keep them short and do not update
  Qt widgets directly. Callback exceptions still reset busy state; a result
  callback failure is forwarded to `on_error`. An error callback should not raise.
- There is no public blocking wait/shutdown API. The worker is a daemon; a direct
  caller must keep its process alive until work finishes. `HomeVoiceController`
  marshals callbacks through Qt signals, invalidates cancelled request IDs, and
  calls `cancel_recording()` during navigation and `shutdown()` on the supervisor
  during shutdown. The engine's `on_captured` callback signals the transition to
  transcription after manual or automatic capture ends.
- Home stops active or pending Zira playback before starting another recording,
  waits 350 ms using a cancellable timer, and stops the avatar animation immediately
  on interruption. Login/logout, application navigation, and closing cancel voice
  work; late recognition results and inactive TTS errors are ignored.

## Automated verification

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -B -m pytest tests/ui/test_home_voice.py tests/unit/test_speech_recognition_service.py tests/unit/test_supervised_speech_service.py tests/unit/test_text_to_speech_service.py -q -p no:cacheprovider
```

Tests inject fake audio streams and transcription models, use deterministic
clocks and event gates, and never open a microphone, load weights, or contact the
network. They check stop/cancel, automatic limits, errors and retries, duplicate
starts, stream cleanup, model reuse, and worker-thread callbacks. They require
only the project's test dependencies and NumPy, not the optional speech stack.
Home voice tests also check button/accessibility states, queued readiness,
interruption, handoff cancellation, late errors, login/navigation/shutdown, avatar
signals, and controller operation without a window. TTS tests use a fake engine.
Physical microphone behavior, native-library compatibility, recognition accuracy,
latency, and offline deployment still require a real-device acceptance check.

Supervisor tests spawn real processes with fake engines that permanently block in
capture, model loading, transcription, and segment iteration. They verify deadlines,
cancellation, child termination before retry, model reuse, unexpected worker exit,
and prompt shutdown without opening a microphone or loading model weights.
