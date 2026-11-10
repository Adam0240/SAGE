"""Start a selected remote file after a fresh idle check; never retry a POST."""

import json

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from services.octoprint_config import make_octoprint_request, read_octoprint_config
from services.printer_status_service import PrinterStatusService


class OctoPrintPrintService(QObject):
    # Result: accepted, rejected (definite failure), or unknown (may have started).
    completed = Signal(str, str)
    TIMEOUT_MS = 10000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_service = PrinterStatusService(self)
        self.status_service.completed.connect(self._checked)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.entry = None
        self.config = None

    def start(self, entry, expected_source):
        if self.busy:
            return
        if (entry is None or entry.is_folder or entry.origin != "local" or not entry.path
                or any(part in ("", ".", "..") for part in entry.path.split("/"))
                or "\\" in entry.path or "\x00" in entry.path):
            self.completed.emit("rejected", "Select an OctoPrint G-code file first.")
            return
        try:
            self.config = read_octoprint_config()
        except ValueError as error:
            self.completed.emit("rejected", str(error))
            return
        if not expected_source or self.config[0].toString() != expected_source:
            self.completed.emit("rejected", "OctoPrint server changed. Refresh the file list before printing.")
            return
        self.entry = entry
        self.busy = True
        self.status_service.check(self.config)

    def cancel_preflight(self):
        # Leaving the viewer can cancel the check, but cannot undo a sent command.
        if self.busy and self.reply is None:
            self.status_service.cancel()
            self._complete("rejected", "")

    def _checked(self, message):
        if not self.busy:
            return
        if not self.status_service.status.ready:
            self._complete("rejected", message)
            return
        request = make_octoprint_request(self.config, "/api/files/local/" + self.entry.path)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        self.reply = self.manager.post(request, json.dumps({"command": "select", "print": True}).encode())
        self.reply.finished.connect(self._finished)
        self.timer.start(self.TIMEOUT_MS)

    def _timeout(self):
        if self.reply is not None:
            self.reply.abort()

    def _finished(self):
        self.timer.stop()
        reply, self.reply = self.reply, None
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        reply.deleteLater()
        if code == 204 and error == QNetworkReply.NetworkError.NoError:
            self._complete("accepted", "")
        elif code in (401, 403):
            self._complete("rejected", "Print access denied. The API user needs FILES_SELECT and PRINT permissions.")
        elif code == 409:
            self._complete("rejected", "Printer is busy or not ready.")
        elif code == 404:
            self._complete("rejected", "The selected file no longer exists. Refresh the file list.")
        elif code in (400, 415):
            self._complete("rejected", "OctoPrint cannot print the selected file.")
        else:
            self._complete("unknown", "Print result unknown. Check OctoPrint, then use Printer Status before retrying.")

    def _complete(self, result, message):
        self.busy = False
        self.completed.emit(result, message)
