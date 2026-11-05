import json
from unittest.mock import patch

import numpy as np
import pytest

from TouchControls.calibration import Calibration, check_points, fit_mapping, project, target_points


def valid_calibration():
    source = [[100, 100], [540, 80], [560, 400], [80, 420]]
    matrix = fit_mapping(source, target_points(1280, 720))
    return Calibration(0, (640, 480), (0, 0, 1280, 720), 1.25,
                       matrix.tolist(), source, [2, 3, 5, 1, 4])


def test_perspective_mapping_and_independent_checks():
    calibration = valid_calibration()
    for source, target in zip(calibration.camera_points, target_points(1280, 720)):
        assert project(calibration.matrix, source) == pytest.approx(target, abs=0.001)
    inverse = np.linalg.inv(calibration.matrix)
    for point in check_points(1280, 720):
        camera_point = project(inverse, point)
        assert calibration.map_point(camera_point) == pytest.approx(point)
    assert calibration.map_point(project(inverse, (-20, 100))) is None


@pytest.mark.parametrize("points", [
    [[10, 10]] * 4,
    [[0, 0], [100, 100], [200, 200], [300, 300]],
    [[0, 0], [100, 100], [100, 0], [0, 100]],
    [[0, 0], [float("nan"), 0], [100, 100], [0, 100]],
    [[0, 0], [100, 0], [100, 100]],
])
def test_bad_corner_samples_are_rejected(points):
    with pytest.raises(ValueError):
        fit_mapping(points, target_points(1280, 720))


def test_save_load_round_trip_and_setup_compatibility(tmp_path):
    calibration = valid_calibration()
    path = tmp_path / "calibration.json"
    calibration.save(path)
    loaded = Calibration.load(path)
    assert loaded.map_point((320, 240)) == pytest.approx(calibration.map_point((320, 240)))
    assert loaded.matches_setup(0, (640, 480), (0, 0, 1280, 720), 1.25)
    assert not loaded.matches_setup(1, (640, 480), (0, 0, 1280, 720), 1.25)
    assert not loaded.matches_setup(0, (1280, 720), (0, 0, 1280, 720), 1.25)
    assert not loaded.matches_setup(0, (640, 480), (0, 0, 1920, 1080), 1.25)
    assert not loaded.matches_setup(0, (640, 480), (0, 0, 1280, 720), 1.5)


@pytest.mark.parametrize("errors", [[], [1] * 4, [1, 2, 3, 4, 26], [float("nan")] * 5])
def test_unverified_calibration_cannot_overwrite_previous_file(tmp_path, errors):
    path = tmp_path / "calibration.json"
    path.write_text("previous calibration", encoding="utf-8")
    calibration = valid_calibration()
    calibration.verification_errors = errors
    with pytest.raises(ValueError):
        calibration.save(path)
    assert path.read_text() == "previous calibration"


def test_failed_atomic_save_preserves_previous_file(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text("previous calibration", encoding="utf-8")
    with patch("TouchControls.calibration.os.replace", side_effect=PermissionError):
        with pytest.raises(PermissionError):
            valid_calibration().save(path)
    assert path.read_text() == "previous calibration"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("change", [
    {"version": 99}, {"matrix": [[0, 0, 0]] * 3}, {"device_pixel_ratio": 0},
    {"camera_size": [0, 480]}, {"verification_errors": [30] * 5},
])
def test_invalid_saved_files_are_rejected(tmp_path, change):
    path = tmp_path / "calibration.json"
    valid_calibration().save(path)
    payload = json.loads(path.read_text())
    payload.update(change)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        Calibration.load(path)


@pytest.mark.parametrize("change", [
    {"matrix": [[1, 0, 0], [2, 0, 0], [0, 0, 1]]},
    {"matrix": [[1, 0], [0, 1]]},
    {"matrix": [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]]},
    {"matrix": [[1, 0, 50], [0, 1, 0], [0, 0, 1]]},
    {"camera_points": [[10, 10]] * 4},
    {"camera_points": [[0, 0], [100, 100], [100, 0], [0, 100]]},
    {"camera_points": [[0, 0], [100, 0], [10, 10], [0, 100]]},
    {"camera_points": [[0, 0], [float("inf"), 0], [100, 100], [0, 100]]},
])
def test_lightweight_validation_rejects_corrupt_matrix_and_corners(change):
    calibration = valid_calibration()
    for name, value in change.items():
        setattr(calibration, name, value)
    with pytest.raises(ValueError):
        calibration.validate()


def test_lightweight_projection_matches_numpy_for_perspective_points():
    calibration = valid_calibration()
    calibration.validate()
    matrix = np.asarray(calibration.matrix)
    for x in range(80, 561, 40):
        for y in range(80, 421, 40):
            expected = matrix @ np.array([x, y, 1.0])
            assert project(calibration.matrix, (x, y)) == pytest.approx(expected[:2] / expected[2])
