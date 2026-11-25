# Reads supported straight-line X/Y movements without depending on Qt.

import re


class PreviewCancelled(Exception):
    """The user left this preview request."""


class GcodeTooLargeError(Exception):
    """The preview would exceed its coordinate budget."""


class UnsupportedGcodeError(Exception):
    """Coordinate semantics cannot be represented by this straight-line preview."""


def read_gcode_coordinates(file_path, *, cancel_event=None, max_coordinates=None):
    coordinates = []
    x = y = 0.0

    # Match G0/G1 movement commands, including G00/G01.
    # Check the command boundary so commands such as G10 are excluded.
    movement_pattern = re.compile(r"^G0?[01](?=\s|[XYZEF]|$)")

    # Match X/Y values, including negative numbers and decimal values.
    coordinate_pattern = re.compile(
        r"([XY])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))"
    )

    # Read one line at a time instead of loading the entire file into memory.
    with file_path.open(encoding="utf-8-sig") as gcode_file:
        for line in gcode_file:
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelled
            # Remove semicolon comments and allow lowercase or indented commands.
            command = re.sub(r"\([^)]*\)", "", line.split(";", 1)[0]).strip().upper()
            codes = re.findall(r"G\s*(\d+(?:\.\d+)?)", command)
            if (len(codes) > 1 or re.match(r"N\d", command)
                    or any(float(code) not in (0, 1, 4, 21, 28, 90, 92) for code in codes)):
                raise UnsupportedGcodeError(command.split()[0])
            if codes and float(codes[0]) == 28:
                # Slicer startup commonly homes before its first absolute XY
                # point. Do not invent home coordinates or draw the home move.
                if coordinates:
                    raise UnsupportedGcodeError("G28 homing after XY movement")
                axes = set(re.findall(r"[XYZ]", command)) or {"X", "Y", "Z"}
                if "X" in axes:
                    x = None
                if "Y" in axes:
                    y = None
                continue
            if codes and float(codes[0]) == 92:
                # Extruder-only resets do not affect XY; other resets do.
                if re.search(r"[XYZ]", command) or not re.search(r"E\s*[-+\d.]", command):
                    raise UnsupportedGcodeError("G92 axis reset")

            # Ignore commands that do not describe straight-line movement.
            if not movement_pattern.match(command):
                continue

            values = coordinate_pattern.findall(command)

            # Skip movements that do not change either X or Y.
            if not values:
                continue

            # Keep the previous position for any axis omitted from the command.
            for axis, value in values:
                if axis == "X":
                    x = float(value)
                else:
                    y = float(value)

            if x is None or y is None:
                raise UnsupportedGcodeError("first XY move after homing must specify each homed XY axis")
            coordinates.append((x, y))
            if max_coordinates is not None and len(coordinates) > max_coordinates:
                raise GcodeTooLargeError

    return coordinates
