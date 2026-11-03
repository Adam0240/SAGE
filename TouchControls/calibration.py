"""Calibration mathematics and persistence, independent of the camera and UI."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np


DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration.json"


def target_points(width, height):
    """Four inset corners in clockwise order, in Qt logical screen coordinates."""
    return [(width * x, height * y) for x, y in
            ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))]


def check_points(width, height):
    # Independent points: four fitted corners alone cannot validate accuracy.
    return [(width * x, height * y) for x, y in
            ((0.5, 0.5), (0.5, 0.1), (0.9, 0.5), (0.5, 0.9), (0.1, 0.5))]


def project(matrix, point):
    values = np.asarray(matrix, dtype=float) @ np.array([*point, 1.0])
    if not np.all(np.isfinite(values)) or abs(values[2]) < 1e-10:
        raise ValueError("Point cannot be mapped with this calibration.")
    return tuple(float(value) for value in values[:2] / values[2])


def fit_mapping(camera_points, screen_points):
    source = np.asarray(camera_points, dtype=np.float32)
    destination = np.asarray(screen_points, dtype=np.float32)
    for points in (source, destination):
        if points.shape != (4, 2) or not np.all(np.isfinite(points)):
            raise ValueError("Calibration requires four finite coordinate pairs.")
        if not cv2.isContourConvex(points) or abs(cv2.contourArea(points)) < 100:
            raise ValueError("Targets are too close together or out of order. Press R to retry.")
    matrix = cv2.getPerspectiveTransform(source, destination)
    if not np.all(np.isfinite(matrix)) or np.linalg.matrix_rank(matrix) != 3:
        raise ValueError("Calibration points do not define a valid mapping.")
    return matrix


@dataclass
class Calibration:
    camera_index: int
    camera_size: tuple[int, int]
    display_geometry: tuple[int, int, int, int]
    device_pixel_ratio: float
    matrix: list
    camera_points: list
    verification_errors: list
    max_error: float = 25.0

    def validate(self):
        if type(self.camera_index) is not int or self.camera_index < 0:
            raise ValueError("Invalid camera index.")
        if (len(self.camera_size) != 2 or len(self.display_geometry) != 4
                or any(type(v) is not int for v in (*self.camera_size, *self.display_geometry))
                or min(*self.camera_size, *self.display_geometry[2:]) <= 0):
            raise ValueError("Invalid camera or display dimensions.")
        if not math.isfinite(self.device_pixel_ratio) or self.device_pixel_ratio <= 0:
            raise ValueError("Invalid display scaling.")
        matrix = np.asarray(self.matrix, dtype=float)
        if (matrix.shape != (3, 3) or not np.all(np.isfinite(matrix))
                or np.linalg.matrix_rank(matrix) != 3):
            raise ValueError("Invalid calibration matrix.")
        width, height = self.display_geometry[2:]
        expected = fit_mapping(self.camera_points, target_points(width, height))
        for point in self.camera_points:
            if not np.allclose(project(matrix, point), project(expected, point), atol=0.1):
                raise ValueError("Calibration matrix does not match the captured points.")
        if (not math.isfinite(self.max_error) or self.max_error <= 0
                or len(self.verification_errors) != 5
                or any(not math.isfinite(error) or not 0 <= error <= self.max_error
                       for error in self.verification_errors)):
            raise ValueError("Calibration has not passed all five accuracy checks.")

    def map_point(self, point):
        """Return screen-local logical coordinates; reject outside points, not clamp."""
        x, y = project(self.matrix, point)
        width, height = self.display_geometry[2:]
        return (x, y) if 0 <= x < width and 0 <= y < height else None

    def matches_setup(self, camera_index, camera_size, display_geometry, device_pixel_ratio):
        return (self.camera_index == camera_index and tuple(self.camera_size) == tuple(camera_size)
                and tuple(self.display_geometry) == tuple(display_geometry)
                and math.isclose(self.device_pixel_ratio, device_pixel_ratio, abs_tol=1e-6))

    def save(self, path=DEFAULT_CALIBRATION_PATH):
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "coordinate_space": "qt_screen_local_logical", **vars(self)}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path=DEFAULT_CALIBRATION_PATH):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if (payload.pop("version") != 1
                    or payload.pop("coordinate_space") != "qt_screen_local_logical"):
                raise ValueError("Unsupported calibration format.")
            calibration = cls(**payload)
            calibration.validate()
            return calibration
        except (KeyError, TypeError, AttributeError, OverflowError) as error:
            raise ValueError("Invalid calibration file.") from error
