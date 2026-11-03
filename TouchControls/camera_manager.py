"""Capture one hand's index fingertip in camera pixels, before calibration.

Run directly or with ``python -m TouchControls.camera_manager`` for a preview.
This synchronous component must run in a worker when later integrated with Qt.
"""

import argparse
import math
from pathlib import Path
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"
INDEX_FINGERTIP = 8


class CameraError(RuntimeError):
    """The camera or tracker could not start or process a frame."""


class CameraManager:
    """Own the camera and detector; no screen dimensions or mapping required.

    ``update()`` returns True when a frame was processed, even if no hand was
    detected. ``tracking_available`` distinguishes that case. Coordinates use
    the unmirrored image's top-left origin (x right, y down). Nothing is saved.
    Create, update, and release this object on the same thread.
    """

    def __init__(self, camera_index=0, model_path=DEFAULT_MODEL_PATH):
        if camera_index < 0:
            raise ValueError("Camera index must be zero or greater.")
        self.camera_index = camera_index
        self.model_path = Path(model_path).resolve()
        self.frame = None
        self.index_fingertip = None
        self.last_error = None
        self._capture = None
        self._detector = None
        self._timestamp_ms = -1
        self._closed = False
        if not self.model_path.is_file():
            raise CameraError(
                f"Hand model not found: {self.model_path}. "
                "See TouchControls/README.md for the model download command."
            )
        try:
            options = vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(self.model_path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._detector = vision.HandLandmarker.create_from_options(options)
            self._capture = cv2.VideoCapture(camera_index)
            if not self._capture.isOpened():
                raise CameraError(
                    f"Cannot open camera {camera_index}. Check the camera index, "
                    "camera permissions, and whether another application is using it."
                )
        except Exception as error:
            self.release()
            raise CameraError(f"Unable to start camera tracking: {error}") from error

    @property
    def tracking_available(self):
        return self.index_fingertip is not None

    def update(self):
        # Clear prior observations before any operation that could fail.
        self.frame = None
        self.index_fingertip = None
        self.last_error = None
        if self._closed:
            self.last_error = "Camera manager is closed."
            return False
        try:
            success, frame = self._capture.read()
            if not success or frame is None or frame.size == 0:
                raise CameraError("Camera frame unavailable. Check the camera connection.")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            # MediaPipe VIDEO timestamps must increase even within one clock tick.
            self._timestamp_ms = max(self._timestamp_ms + 1, time.monotonic_ns() // 1_000_000)
            result = self._detector.detect_for_video(image, self._timestamp_ms)
            self.frame = frame
            if result.hand_landmarks:
                tip = result.hand_landmarks[0][INDEX_FINGERTIP]
                # Ignore out-of-image landmarks; clamping would create false edge hits.
                if (math.isfinite(tip.x) and math.isfinite(tip.y)
                        and 0 <= tip.x < 1 and 0 <= tip.y < 1):
                    height, width = frame.shape[:2]
                    self.index_fingertip = (tip.x * width, tip.y * height)
            return True
        except Exception as error:
            self.frame = None
            self.index_fingertip = None
            self.last_error = f"Camera tracking failed: {error}"
            return False

    def release(self):
        """Release owned resources; safe to call more than once."""
        self._closed = True
        self.frame = None
        self.index_fingertip = None
        capture, detector = self._capture, self._detector
        self._capture = self._detector = None
        try:
            if capture is not None:
                capture.release()
        finally:
            if detector is not None:
                detector.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview SAGE index-fingertip tracking.")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args(argv)
    title = "SAGE Camera Preview - Esc or Q to close"
    window_created = False
    try:
        with CameraManager(args.camera, args.model) as camera:
            cv2.namedWindow(title, cv2.WINDOW_NORMAL)
            window_created = True
            while True:
                if not camera.update():
                    print(camera.last_error, file=sys.stderr)
                    return 1
                preview = camera.frame.copy()
                message = "No hand detected"
                if camera.tracking_available:
                    x, y = camera.index_fingertip
                    cv2.circle(preview, (int(x), int(y)), 10, (0, 255, 0), 2)
                    message = f"Index fingertip: x={x:.0f}, y={y:.0f}"
                cv2.putText(preview, message, (15, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, (0, 255, 0), 2)
                cv2.imshow(title, preview)
                if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                    break
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break
        return 0
    except (CameraError, ValueError, cv2.error) as error:
        print(error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if window_created:
            try:
                cv2.destroyWindow(title)
            except cv2.error:
                # The user may already have closed the native preview window.
                pass


if __name__ == "__main__":
    sys.exit(main())
