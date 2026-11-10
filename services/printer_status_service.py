"""Read OctoPrint status asynchronously without issuing printer commands."""

import json
from dataclasses import dataclass
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from services.octoprint_config import make_octoprint_request, read_octoprint_config


@dataclass(frozen=True)
class PrinterStatus:
    message: str
    ready: bool = False
    busy: bool = False


def parse_status(code, body):
    if code in (401, 403):
        return PrinterStatus("Status unavailable: check the OctoPrint API key and STATUS permission.")
    if code == 409:
        return PrinterStatus("Printer disconnected or not operational. Busy status unavailable.")
    if code != 200:
        return PrinterStatus("Unable to check printer status. Check the OctoPrint address and connection.")
    try:
        flags = json.loads(body)["state"]["flags"]
        required = ("operational", "printing", "paused", "ready", "closedOrError", "error")
        if not isinstance(flags, dict) or any(type(flags.get(key)) is not bool for key in required):
            raise ValueError
        transitions = ("pausing", "cancelling", "finishing", "resuming", "starting")
        if any(key in flags and type(flags[key]) is not bool for key in transitions):
            raise ValueError
        if flags["closedOrError"] or flags["error"] or not flags["operational"]:
            return PrinterStatus("Printer disconnected or not operational. Busy status unavailable.")
        if any(flags.get(key) is True for key in ("paused", "printing", *transitions)):
            return PrinterStatus("Printer connected — busy", busy=True)
        if flags["ready"]:
            return PrinterStatus("Printer connected — idle", ready=True)
        return PrinterStatus("Printer connected — not ready; busy status unknown.")
    except (ValueError, TypeError, KeyError):
        return PrinterStatus("Status unavailable: OctoPrint returned an invalid response.")


def status_message(code, body):
    return parse_status(code, body).message


class PrinterStatusService(QObject):
    completed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(8000)
        self.timer.timeout.connect(self._timeout)
        self.timed_out = False
        self.status = PrinterStatus("Printer status not checked.")
        self.source = ""

    def check(self, config=None):
        if self.reply is not None:
            return
        self.status = PrinterStatus("Checking printer status…")
        try:
            config = config if config is not None else read_octoprint_config()
        except ValueError as error:
            self.status = PrinterStatus(str(error))
            self.source = ""
            self.completed.emit(str(error))
            return
        self.source = config[0].toString()
        request = make_octoprint_request(config, "/api/printer")
        self.timed_out = False
        self.reply = self.manager.get(request)
        reply = self.reply
        self.reply.finished.connect(lambda: self._finished(reply))
        self.timer.start()

    def cancel(self):
        self.timer.stop()
        reply, self.reply = self.reply, None
        self.status = PrinterStatus("Printer status not checked.")
        if reply is not None:
            reply.abort()

    def _timeout(self):
        if self.reply is not None:
            self.timed_out = True
            self.reply.abort()

    def _finished(self, reply):
        if reply is not self.reply:
            reply.deleteLater()
            return
        self.timer.stop()
        self.reply = None
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if self.timed_out:
            status = PrinterStatus("Printer status check timed out. Connection and busy status unknown.")
        elif code is None or (code == 200 and reply.error() != QNetworkReply.NetworkError.NoError):
            status = PrinterStatus("Cannot reach OctoPrint. Printer connection and busy status unknown.")
        else:
            status = parse_status(code, bytes(reply.readAll()))
        reply.deleteLater()
        self.status = status
        self.completed.emit(status.message)
