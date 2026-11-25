import json

import pytest

from services.printer_status_service import (
    PrinterStatus,
    parse_remaining_time,
)


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (3600, "Remaining time: 1h 0m"),
        (9300, "Remaining time: 2h 35m"),
        (1800, "Remaining time: 0h 30m"),
        (60, "Remaining time: 0h 1m"),
        (30, "Remaining time: 0h 1m"),
        (0, "Remaining time: 0h 0m"),
        (None, "Remaining time: Unavailable"),
    ],
)
def test_remaining_time_format(seconds, expected):
    status = PrinterStatus(
        message="Printer connected — busy",
        busy=True,
        remaining_seconds=seconds,
    )

    assert status.remaining_time_message == expected


def test_idle_remaining_time():
    status = PrinterStatus(
        message="Printer connected — idle",
        ready=True,
    )

    assert (
        status.remaining_time_message
        == "Remaining time: No active print"
    )


@pytest.mark.parametrize(
    "remaining, expected",
    [
        (9300, 9300),
        (None, None),
        (-1, None),
        ("9300", None),
        (True, None),
    ],
)
def test_parse_remaining_time(remaining, expected):
    body = json.dumps({
        "state": "Printing",
        "progress": {
            "printTimeLeft": remaining
        },
    })

    assert parse_remaining_time(200, body) == expected


@pytest.mark.parametrize("code,body", [
    (409, b""), (200, b"invalid"),
    (200, json.dumps({"state": "Operational", "progress": {"printTimeLeft": 9300}})),
])
def test_remaining_time_unavailable(code, body):
    assert parse_remaining_time(code, body) is None
