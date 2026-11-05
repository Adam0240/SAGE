# Reads supported straight-line X/Y movements without depending on Qt.

import re


class PreviewCancelled(Exception):
    """The user left this preview request."""


class GcodeTooLargeError(Exception):
    """The preview would exceed its coordinate budget."""


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
            command = line.split(";", 1)[0].strip().upper()

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

            coordinates.append((x, y))
            if max_coordinates is not None and len(coordinates) > max_coordinates:
                raise GcodeTooLargeError

    return coordinates
