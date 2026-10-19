# Generates overhead G-code images and caches them independently of widgets.

import hashlib
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from services.gcode_parser import read_gcode_coordinates


class UnreadableGcodeError(Exception):
    """The selected G-code file could not be read or parsed."""


class NoPreviewableMovementError(Exception):
    """The selected file has fewer than two supported X/Y positions."""


class GcodePreviewService:
    def __init__(self, thumbnail_dir):
        self.thumbnail_dir = Path(thumbnail_dir)

    # Return a cached or newly rendered image, or raise a defined preview error.
    def get_preview(self, file_path):
        preview_path = None

        try:
            # Identify this version of the file using its path, modification
            # time, and size. Changed details produce a different PNG filename.
            file_details = file_path.stat()
            preview_key = (
                f"{file_path.resolve()}|"
                f"{file_details.st_mtime_ns}|"
                f"{file_details.st_size}"
            )
            preview_id = hashlib.sha256(
                preview_key.encode("utf-8")
            ).hexdigest()[:16]

            # Create the preview folder if it does not already exist.
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
            preview_path = self.thumbnail_dir / (
                f"{file_path.stem}_{preview_id}.png"
            )

        except OSError:
            # Still allow previews to display if the cache cannot be accessed.
            preview_path = None

        # Try loading the saved image before reading and drawing the G-code.
        image = QImage()
        if preview_path is not None and image.load(str(preview_path)):
            return image

        try:
            coordinates = read_gcode_coordinates(file_path)
        except (OSError, UnicodeError, ValueError) as error:
            raise UnreadableGcodeError from error

        # At least two positions are needed to draw a movement line.
        if len(coordinates) < 2:
            raise NoPreviewableMovementError

        # Create a black image to draw the movement path onto.
        width, height = 800, 600
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))

        # Find the outer edges of the movement path.
        xs, ys = zip(*coordinates)
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Avoid division by zero when the path has no width or height.
        path_width = max_x - min_x or 1.0
        path_height = max_y - min_y or 1.0

        # Fit the path inside the image while preserving its proportions.
        margin = 20
        scale = min(
            (width - margin * 2) / path_width,
            (height - margin * 2) / path_height
        )

        # Center the path within the image.
        offset_x = (width - (max_x - min_x) * scale) / 2
        offset_y = (height - (max_y - min_y) * scale) / 2

        # Convert printer coordinates into image positions.
        # Reverse Y because image coordinates increase downward.
        points = [
            QPointF(
                offset_x + (x - min_x) * scale,
                height - (offset_y + (y - min_y) * scale)
            )
            for x, y in coordinates
        ]

        # Connect each position to the next with a light-gray line.
        painter = QPainter(image)
        painter.setPen(QPen(QColor("lightgray"), 1))
        try:
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
        finally:
            # Finish drawing before converting the image for display.
            painter.end()

        # Save the full-size image for future selections and app launches.
        # A failed save does not prevent the current preview from displaying.
        if preview_path is not None:
            image.save(str(preview_path), "PNG")

        return image
