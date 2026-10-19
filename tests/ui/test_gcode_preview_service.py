# Tests preview rendering and thumbnail caching without creating interface widgets.

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QColor, QImage

from services.gcode_parser import read_gcode_coordinates
from services.gcode_preview_service import (
    GcodePreviewService, NoPreviewableMovementError, UnreadableGcodeError,
)


class TestGcodePreviewService(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gcode_dir = self.root / "gcodes"
        self.gcode_dir.mkdir()
        self.thumb_dir = self.root / "thumbnails"
        self.service = GcodePreviewService(self.thumb_dir)

    def write_gcode(self, name="model.gcode", content="G1 X0 Y0\nG1 X10 Y10\n"):
        file_path = self.gcode_dir / name
        file_path.write_text(content, encoding="utf-8")
        return file_path

    # Tests rendering produces a readable cached image containing the path on a black background.
    def test_preview_rendering_and_cache_creation(self):
        file_path = self.write_gcode()
        image = self.service.get_preview(file_path)
        previews = list(self.thumb_dir.glob("*.png"))
        self.assertEqual(len(previews), 1)
        cached = QImage(str(previews[0]))
        self.assertEqual(image, cached)
        self.assertFalse(image.isNull())
        self.assertEqual((image.width(), image.height()), (800, 600))
        self.assertEqual(image.pixelColor(0, 0), QColor("black"))
        self.assertEqual(image.pixelColor(400, 300), QColor("lightgray"))
        self.assertFalse(image.isNull())

    # Tests an unchanged file reuses its cached image without parsing the G-code again.
    def test_cached_preview_skips_parsing(self):
        file_path = self.write_gcode()
        image = self.service.get_preview(file_path)
        with patch("services.gcode_preview_service.read_gcode_coordinates") as read:
            image = self.service.get_preview(file_path)
            read.assert_not_called()
        self.assertFalse(image.isNull())

    # Tests changed content and same-named files in different folders receive separate cache entries.
    def test_cache_distinguishes_changed_files_and_paths(self):
        file_path = self.write_gcode()
        image = self.service.get_preview(file_path)
        file_path.write_text("G1 X0 Y0\nG1 X100 Y200\nG1 X200 Y300\n", encoding="utf-8")
        with patch("services.gcode_preview_service.read_gcode_coordinates",
                          wraps=read_gcode_coordinates) as read:
            image = self.service.get_preview(file_path)
            read.assert_called_once_with(file_path)
        other = self.root / "model.gcode"
        other.write_bytes(file_path.read_bytes())
        image = self.service.get_preview(other)
        self.assertEqual(len(list(self.thumb_dir.glob("*.png"))), 3)

    # Tests a damaged cached image is regenerated from the original G-code.
    def test_corrupted_cache_is_regenerated(self):
        file_path = self.write_gcode()
        image = self.service.get_preview(file_path)
        preview_path = next(self.thumb_dir.glob("*.png"))
        preview_path.write_bytes(b"not a PNG")
        with patch("services.gcode_preview_service.read_gcode_coordinates",
                          wraps=read_gcode_coordinates) as read:
            image = self.service.get_preview(file_path)
            read.assert_called_once_with(file_path)
        self.assertFalse(QImage(str(preview_path)).isNull())

    # Tests preview generation still works when the thumbnail directory cannot be created.
    def test_unavailable_cache_directory(self):
        file_path = self.write_gcode()
        with patch.object(Path, "mkdir", side_effect=PermissionError("Read-only cache")):
            image = self.service.get_preview(file_path)
        self.assertFalse(image.isNull())
        self.assertFalse(self.thumb_dir.exists())

    # Tests an unsuccessful PNG save still returns the generated preview image.
    def test_cache_save_failure(self):
        file_path = self.write_gcode()
        with patch.object(QImage, "save", return_value=False) as save:
            image = self.service.get_preview(file_path)
            save.assert_called_once()
        self.assertFalse(image.isNull())

    # Tests horizontal, vertical, and repeated positions render without division-by-zero errors.
    def test_zero_width_or_height_paths(self):
        for content in ("G1 X0 Y5\nG1 X10 Y5\n", "G1 X5 Y0\nG1 X5 Y10\n",
                        "G1 X5 Y5\nG1 X5 Y5\n"):
            with self.subTest(content=content):
                image = self.service.get_preview(self.write_gcode(content=content))
                self.assertFalse(image.isNull())


    # Tests modification time alone invalidates the cached preview when file size is unchanged.
    def test_modification_time_invalidates_cache(self):
        file_path = self.write_gcode()
        self.service.get_preview(file_path)
        details = file_path.stat()
        os.utime(file_path, ns=(details.st_atime_ns, details.st_mtime_ns + 2_000_000_000))
        with patch("services.gcode_preview_service.read_gcode_coordinates",
                   wraps=read_gcode_coordinates) as read:
            self.service.get_preview(file_path)
            read.assert_called_once_with(file_path)
        self.assertEqual(len(list(self.thumb_dir.glob("*.png"))), 2)

    # Tests file access, decoding, and parsing failures become the defined unreadable-file error.
    def test_read_errors_have_defined_outcome(self):
        file_path = self.write_gcode()
        for error in (OSError("Access denied"), UnicodeError("Invalid text"), ValueError("Invalid value")):
            with self.subTest(error=type(error).__name__), \
                    patch("services.gcode_preview_service.read_gcode_coordinates", side_effect=error):
                with self.assertRaises(UnreadableGcodeError) as caught:
                    self.service.get_preview(file_path)
                self.assertIs(caught.exception.__cause__, error)

    # Tests fewer than two supported positions produce the defined no-movement error without caching.
    def test_insufficient_movement_has_defined_outcome(self):
        for content in ("", "; Comments only\nM104 S200\n", "G1 X10 Y20\n"):
            with self.subTest(content=content):
                file_path = self.write_gcode(content=content)
                with self.assertRaises(NoPreviewableMovementError):
                    self.service.get_preview(file_path)
        self.assertEqual(list(self.thumb_dir.glob("*.png")), [])
