"""Calibration mathematics and persistence, independent of the camera and UI."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile

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
    matrix = _finite_rows(matrix, 3, 3, "Invalid calibration matrix.")
    x, y = _finite_rows([point], 1, 2, "Invalid camera point.")[0]
    values = [row[0] * x + row[1] * y + row[2] for row in matrix]
    if not all(math.isfinite(value) for value in values) or abs(values[2]) < 1e-10:
        raise ValueError("Point cannot be mapped with this calibration.")
    return values[0] / values[2], values[1] / values[2]


def _finite_rows(values, rows, columns, message):
    try:
        result = [[float(value) for value in row] for row in values]
        if (len(result) != rows or any(len(row) != columns for row in result)
                or any(not math.isfinite(value) for row in result for value in row)):
            raise ValueError(message)
        return result
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(message) from error


def _validate_corners(points):
    points = _finite_rows(points, 4, 2, "Calibration requires four finite coordinate pairs.")
    turns = []
    area = 0
    for index, (x, y) in enumerate(points):
        nx, ny = points[(index + 1) % 4]
        tx, ty = points[(index + 2) % 4]
        area += x * ny - y * nx
        turns.append((nx - x) * (ty - ny) - (ny - y) * (tx - nx))
    if (not math.isfinite(area) or abs(area) < 200
            or not (all(turn > 0 for turn in turns) or all(turn < 0 for turn in turns))):
        raise ValueError("Targets are too close together or out of order. Press R to retry.")
    return points


def fit_mapping(camera_points, screen_points):
    # Only the calibration tool fits a new matrix. Loading and using an existing
    # calibration in SAGE must not import native vision libraries on the GUI thread.
    import cv2
    import numpy as np

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
        matrix = _finite_rows(self.matrix, 3, 3, "Invalid calibration matrix.")
        # Row normalization keeps the determinant check independent of row scale.
        if any(not any(row) for row in matrix):
            raise ValueError("Invalid calibration matrix.")
        a, b, c = [[value / max(abs(v) for v in row) for value in row] for row in matrix]
        determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                       - a[1] * (b[0] * c[2] - b[2] * c[0])
                       + a[2] * (b[0] * c[1] - b[1] * c[0]))
        if abs(determinant) < 1e-15:
            raise ValueError("Invalid calibration matrix.")
        width, height = self.display_geometry[2:]
        source = _validate_corners(self.camera_points)
        destination = _validate_corners(target_points(width, height))
        for point, expected in zip(source, destination):
            if any(abs(actual - target) > 0.1 + 1e-5 * abs(target)
                   for actual, target in zip(project(matrix, point), expected)):
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
