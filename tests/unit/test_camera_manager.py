from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from TouchControls import camera_manager as camera_module
from TouchControls.camera_manager import CameraError, CameraManager


def hand_result(x=0.25, y=0.75):
    return SimpleNamespace(hand_landmarks=[
        [SimpleNamespace(x=x, y=y) for _ in range(21)]
    ])


@pytest.fixture
def devices(tmp_path):
    model = tmp_path / "test.task"
    model.write_bytes(b"fake model; detector is mocked")
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    detector = Mock()
    detector.detect_for_video.return_value = hand_result()
    with patch.object(camera_module.cv2, "VideoCapture", return_value=capture) as factory, \
            patch.object(camera_module.vision.HandLandmarker, "create_from_options",
                         return_value=detector) as detector_factory:
        yield SimpleNamespace(model=model, capture=capture, detector=detector,
                              factory=factory, detector_factory=detector_factory)


def test_tracks_raw_pixels_without_calibration_and_converts_bgr(devices):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[0, 0] = [10, 20, 30]
    devices.capture.read.return_value = True, frame
    with CameraManager(camera_index=2, model_path=devices.model) as camera:
        assert camera.update()
        assert camera.tracking_available
        assert camera.index_fingertip == (160.0, 360.0)
        assert camera.frame is frame
        image, timestamp = devices.detector.detect_for_video.call_args.args
        assert image.numpy_view()[0, 0].tolist() == [30, 20, 10]
        assert timestamp >= 0
        devices.factory.assert_called_once_with(2)
        assert devices.detector_factory.call_args.args[0].num_hands == 1
    devices.capture.release.assert_called_once()
    devices.detector.close.assert_called_once()
    assert not camera.tracking_available


def test_loss_of_hand_clears_old_position_and_can_recover(devices):
    with CameraManager(model_path=devices.model) as camera:
        assert camera.update()
        devices.detector.detect_for_video.return_value = SimpleNamespace(hand_landmarks=[])
        assert camera.update()
        assert not camera.tracking_available
        assert camera.index_fingertip is None
        assert camera.frame is not None
        devices.detector.detect_for_video.return_value = hand_result(0.5, 0.5)
        assert camera.update()
        assert camera.index_fingertip == (320.0, 240.0)


@pytest.mark.parametrize("x,y", [(-0.1, 0.5), (1, 0.5), (0.5, 1.1), (float("nan"), 0.5)])
def test_invalid_landmarks_are_rejected_instead_of_clamped(devices, x, y):
    devices.detector.detect_for_video.return_value = hand_result(x, y)
    with CameraManager(model_path=devices.model) as camera:
        assert camera.update()
        assert camera.index_fingertip is None


@pytest.mark.parametrize("failure", ["read", "exception", "inference"])
def test_processing_failures_clear_stale_data(devices, failure):
    with CameraManager(model_path=devices.model) as camera:
        assert camera.update()
        if failure == "read":
            devices.capture.read.return_value = False, None
        elif failure == "exception":
            devices.capture.read.side_effect = RuntimeError("Disconnected")
        else:
            devices.detector.detect_for_video.side_effect = RuntimeError("Inference failed")
        assert not camera.update()
        assert camera.frame is None
        assert camera.index_fingertip is None
        assert camera.last_error


def test_missing_model_does_not_open_camera(devices):
    with pytest.raises(CameraError, match="model not found"):
        CameraManager(model_path=devices.model.parent / "missing.task")
    devices.factory.assert_not_called()


def test_unavailable_camera_releases_resources(devices):
    devices.capture.isOpened.return_value = False
    with pytest.raises(CameraError, match="Cannot open camera"):
        CameraManager(model_path=devices.model)
    devices.capture.release.assert_called_once()
    devices.detector.close.assert_called_once()


def test_bad_model_does_not_open_camera(devices):
    devices.detector_factory.side_effect = ValueError("Invalid model")
    with pytest.raises(CameraError, match="Invalid model"):
        CameraManager(model_path=devices.model)
    devices.factory.assert_not_called()


def test_monotonic_timestamps_and_idempotent_release(devices):
    with patch.object(camera_module.time, "monotonic_ns", return_value=10_000_000):
        camera = CameraManager(model_path=devices.model)
        try:
            assert camera.update()
            assert camera.update()
            assert [call.args[1] for call in devices.detector.detect_for_video.call_args_list] == [10, 11]
        finally:
            camera.release()
    camera.release()
    assert not camera.update()
    assert "closed" in camera.last_error
    devices.capture.release.assert_called_once()
    devices.detector.close.assert_called_once()


def test_context_exception_still_releases_camera(devices):
    with pytest.raises(RuntimeError, match="caller"):
        with CameraManager(model_path=devices.model):
            raise RuntimeError("caller")
    devices.capture.release.assert_called_once()
    devices.detector.close.assert_called_once()


@pytest.mark.parametrize("exit_method", ["key", "window", "read_failure"])
def test_preview_exit_releases_camera_and_owned_window(devices, exit_method):
    if exit_method == "read_failure":
        devices.capture.read.return_value = False, None
    with patch.object(camera_module.cv2, "namedWindow"), \
            patch.object(camera_module.cv2, "imshow"), \
            patch.object(camera_module.cv2, "waitKey", return_value=27 if exit_method == "key" else -1), \
            patch.object(camera_module.cv2, "getWindowProperty", return_value=0), \
            patch.object(camera_module.cv2, "destroyWindow") as destroy:
        result = camera_module.main(["--model", str(devices.model)])
    assert result == (1 if exit_method == "read_failure" else 0)
    devices.capture.release.assert_called_once()
    devices.detector.close.assert_called_once()
    destroy.assert_called_once()
