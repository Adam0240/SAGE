# Standalone speech recognition

`speech_recognition_service.py` records mono microphone audio with sounddevice
and transcribes it locally with faster-whisper. It has no GUI, AI assistant,
STEAM Guide, text-to-speech, or wake-word integration.

## Dependencies

From the repository root, using the Python environment intended to run speech:

```powershell
python -m pip install -r requirements-speech.txt
python -m pip check
python -c "import sounddevice; from faster_whisper import WhisperModel; print(sounddevice.query_devices())"
```

Use that environment's Python executable explicitly if it is not activated.
For SAGE's existing environment this is `.\.venv\Scripts\python.exe`.
The optional requirements are separate from the application's pinned requirements;
the mocked tests do not establish a working combination of native dependency
versions. Validate installation and actual transcription on the deployment Python
before pinning its speech dependencies. In particular, Python 3.14 compatibility
must be checked rather than inferred from a package's minimum Python version.
A separate environment can run this standalone service, but communicating with
SAGE across environments would require a future process integration.

- **NumPy:** audio arrays and RMS amplitude calculation.
- **sounddevice:** microphone capture. Windows pip installations include PortAudio;
  Linux may need the system PortAudio package. Select a working default input
  device in the OS and allow desktop applications microphone access.
- **faster-whisper:** transcription, including dependencies such as CTranslate2
  and PyAV. The service requests CPU `int8`; CUDA is not required. PyAV wheels
  include FFmpeg libraries, so a separate FFmpeg executable is not required.

Dependencies are imported lazily: importing the service requires NumPy, while
sounddevice and faster-whisper are needed only for actual recording/transcription.
Missing imports during a request are delivered through `on_error`.

Upstream setup references:
[sounddevice installation](https://python-sounddevice.readthedocs.io/en/latest/installation.html)
and [faster-whisper requirements](https://github.com/SYSTRAN/faster-whisper#requirements).

## Prepare the model while online

The default model is `base.en`. Runtime loading uses `local_files_only=True`:
the service will report an error if the model is missing, rather than download it.
Package installation and model download are separate steps.

To populate the default Hugging Face cache for the same OS account/environment:

```powershell
python -c "from faster_whisper.utils import download_model; print(download_model('base.en'))"
```

Alternatively, download a portable model directory outside the repository:

```powershell
python -c "from faster_whisper.utils import download_model; download_model('base.en', output_dir='D:/SAGE-models/base.en')"
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
To check model loading without accessing the microphone, disconnect networking
and run:

```powershell
python -c "from faster_whisper import WhisperModel; WhisperModel('D:/SAGE-models/base.en', device='cpu', compute_type='int8', local_files_only=True); print('Local model loaded')"
```

See the upstream [model download helper](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py).

## Lifecycle contract

- `start_recording(on_result, on_error)` returns `True` when a worker starts, or
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
- Both callbacks run on the **worker thread**. Keep them short and do not update
  Qt widgets directly. Callback exceptions still reset busy state; a result
  callback failure is forwarded to `on_error`. An error callback should not raise.
- There is no public blocking wait/shutdown API. The worker is a daemon; a
  standalone caller must keep its process alive until work finishes. A later GUI
  integration must manage shutdown and marshal results to the GUI thread.

## Automated verification

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/unit/test_speech_recognition_service.py -q -p no:cacheprovider
```

Tests inject fake audio streams and transcription models, use deterministic
clocks and event gates, and never open a microphone, load weights, or contact the
network. They check stop/cancel, automatic limits, errors and retries, duplicate
starts, stream cleanup, model reuse, and worker-thread callbacks. They require
only the project's test dependencies and NumPy, not the optional speech stack.
Physical microphone behavior, native-library compatibility, recognition accuracy,
latency, and offline deployment still require a real-device acceptance check.
