# Tests G-code coordinate parsing without importing Qt or creating widgets.

import tempfile
import unittest
from pathlib import Path

from services.gcode_parser import read_gcode_coordinates


class TestGcodeParser(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.gcode_dir = Path(temporary.name)

    def write_gcode(self, content):
        file_path = self.gcode_dir / "model.gcode"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    # Tests supported move spellings, lowercase, comments, signed decimals, and omitted-axis retention.
    def test_coordinate_parsing(self):
        file_path = self.write_gcode(content=(
            "\ufeff; Header\n g0 X1 Y2 ; X999 Y999\n"
            "g00 X-3.5\nG01 Y+.5\nG1X.25Y-2.\nG1 X +4 Y -6\n"
        ))
        self.assertEqual(read_gcode_coordinates(file_path),
                         [(1.0, 2.0), (-3.5, 2.0), (-3.5, 0.5),
                          (0.25, -2.0), (4.0, -6.0)])

    # Tests the first move defaults an omitted axis to zero and ignores commands without X/Y moves.
    def test_coordinate_defaults_and_ignored_commands(self):
        file_path = self.write_gcode(content=(
            "; G1 X100 Y100\nG10 X90 Y90\nG11 X80 Y80\nG100 X70 Y70\n"
            "G2 X60 Y60\nM104 S200\nG1 Z2 E1 F1000\nG0\n\nG1 Y5\nG1 X7\n"
        ))
        self.assertEqual(read_gcode_coordinates(file_path), [(0.0, 5.0), (7.0, 5.0)])


    # Tests empty files and files containing only unsupported commands return no positions.
    def test_no_supported_movements(self):
        for content in ("", "; Comment only\n", "M104 S200\nG1 Z2 E1\n"):
            with self.subTest(content=content):
                self.assertEqual(read_gcode_coordinates(self.write_gcode(content)), [])

    # Tests missing files and invalid UTF-8 are reported to callers for preview error handling.
    def test_file_read_errors_propagate(self):
        with self.assertRaises(OSError):
            read_gcode_coordinates(self.gcode_dir / "missing.gcode")
        file_path = self.gcode_dir / "invalid.gcode"
        file_path.write_bytes(b"\xff\xfe\xff")
        with self.assertRaises(UnicodeError):
            read_gcode_coordinates(file_path)
