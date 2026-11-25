# Tests G-code coordinate parsing without importing Qt or creating widgets.

import tempfile
import unittest
from pathlib import Path

from services.gcode_parser import UnsupportedGcodeError, read_gcode_coordinates


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
            "; G1 X100 Y100\nG90\nG21\nG92 E0\nG4 P100\n"
            "M104 S200\nG1 Z2 E1 F1000\nG0\n\nG1 Y5\nG1 X7\n"
        ))
        self.assertEqual(read_gcode_coordinates(file_path), [(0.0, 5.0), (7.0, 5.0)])

    def test_unsupported_modes_never_return_partial_geometry(self):
        for command in ("G91", "G20", "G92 X0", "G92", "G2 X5 Y5", "G3 X5", "G10",
                        "G54", "G28", "G90 G1 X2", "N3 G1 X2", "g91.1"):
            with self.subTest(command=command), self.assertRaises(UnsupportedGcodeError):
                read_gcode_coordinates(self.write_gcode("G1 X10 Y10\n" + command + "\nG1 X5 Y0\n"))

    def test_slicer_startup_homing_uses_first_absolute_xy_position(self):
        for home in ("G28", "g28 x y", "G28 X0 Y0 Z0", "G28 Z"):
            with self.subTest(home=home):
                path = self.write_gcode(
                    "M104 S210\nM140 S65\n" + home + "\nG90\nG1 X-10 Y-10 F3000\n"
                    "G1 Z0 F1800\nM109 S210\nM190 S65\nG92 E0\nG1 E20 F200\n"
                    "G92 E0\nM82\nG1 X10 Y20\nG1 X30\n")
                self.assertEqual(read_gcode_coordinates(path), [(-10, -10), (10, 20), (30, 20)])

    def test_startup_homing_does_not_guess_unknown_axis_coordinates(self):
        for home, move in (("G28", "G1 X10"), ("G28 X", "G1 Y20"), ("G28 Y", "G1 X10")):
            with self.subTest(home=home, move=move), self.assertRaisesRegex(
                    UnsupportedGcodeError, "homed XY axis"):
                read_gcode_coordinates(self.write_gcode(home + "\n" + move + "\nG1 X30 Y30\n"))


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
