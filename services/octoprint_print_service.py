"""Start a selected remote file after a fresh idle check; never retry a POST."""

import json
import time
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from database.account_operations import has_print_permission
from services.octoprint_config import make_octoprint_request, read_octoprint_config
from services.octoprint_file_service import OctoPrintFileService
from services.printer_status_service import PrinterStatusService


def _check_print_permission(user_id, results):
    # The daemon owns only Python data; cancellation/destruction cannot leave it
    # calling a deleted Qt object. Never expose database details in the UI.
    try:
        result = "allowed" if has_print_permission(user_id) else "revoked"
    except Exception:
        result = "unavailable"
    results.put(result)


class OctoPrintPrintService(QObject):
    # file_changed also rejects submission and invalidates the viewer's preview.
    # Other results: accepted, rejected, or unknown (may have started).
    completed = Signal(str, str)
    authorization_revoked = Signal(object)
    TIMEOUT_MS = 10000
    AUTHORIZATION_TIMEOUT_SECONDS = 20
    
    def __init__(self, parent=None, *, can_start_print=None, get_session=None):
        super().__init__(parent)
        self.can_start_print = (
                can_start_print if can_start_print is not None
                else lambda: False
            )
        self.status_service = PrinterStatusService(self)
        self.status_service.completed.connect(self._checked)
        # This instance only reads metadata; it never downloads or writes a cache.
        self.file_service = OctoPrintFileService(".", self)
        self.file_service.version_checked.connect(self._version_checked)
        self.file_service.failed.connect(self._version_failed)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.entry = None
        self.config = None
        self.get_session = get_session or (lambda: None)
        self._session = None
        self._authorization_thread = None
        self._authorization_results = None
        self._authorization_timer = QTimer(self)
        self._authorization_timer.setInterval(25)
        self._authorization_timer.timeout.connect(self._poll_authorization)

    def start(self, entry, expected_source, expected_version=None):
        if self.busy:
            return

        # Only the STEAM Specialist can start a print.
        self._session = self.get_session()
        if (not self.can_start_print() or self._session is None
                or not self._session.can_start_print):
            self.completed.emit(
                "rejected",
                "Only the STEAM Specialist can start a 3D print."
            )
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
        self.expected_version = expected_version
        self.busy = True
        self.status_service.check(self.config)

    def cancel_preflight(self):
        # Leaving the viewer can cancel the check, but cannot undo a sent command.
        if self.busy and self.reply is None:
            self.status_service.cancel()
            self.file_service.cancel()
            self._complete("rejected", "")

    def _checked(self, message):
        if not self.busy:
            return

        # Verify permissions again before sending the print command.
        if not self._session_is_current():
            self._complete(
                "rejected",
                "Only the STEAM Specialist can start a 3D print."
            )
            return

        if not self.status_service.status.ready:
            self._complete("rejected", message)
            return

        # Revalidate after printer preflight, before the final file check.
        # Keep one database worker even when a previous request was abandoned.
        if self._authorization_thread is not None and self._authorization_thread.is_alive():
            self._complete("rejected", "Previous permission check is still finishing. Try again.")
            return
        self._authorization_results = Queue()
        self._authorization_deadline = time.monotonic() + self.AUTHORIZATION_TIMEOUT_SECONDS
        self._authorization_thread = Thread(
            target=_check_print_permission,
            args=(self._session.user_id, self._authorization_results), daemon=True,
        )
        try:
            self._authorization_thread.start()
        except Exception:
            self._complete("rejected", "Unable to verify print permission. Try again later.")
            return
        self._authorization_timer.start()

    def _session_is_current(self):
        # Identity, not value equality: logging out and back in is a new session.
        return (self._session is not None and self.get_session() is self._session
                and self._session.can_start_print and self.can_start_print())

    def _poll_authorization(self):
        if not self.busy or self._authorization_results is None:
            return
        if not self._session_is_current():
            self._complete("rejected", "Staff session changed. Sign in and try again.")
            return
        if time.monotonic() >= self._authorization_deadline:
            self._complete("rejected", "Print permission check timed out. No print was submitted.")
            return
        try:
            result = self._authorization_results.get_nowait()
        except Empty:
            return
        self._authorization_timer.stop()
        self._authorization_results = None
        if result == "revoked":
            self.authorization_revoked.emit(self._session)
            self._complete("rejected", "Print permission was revoked. Please sign in again.")
            return
        if result != "allowed":
            self._complete("rejected", "Unable to verify print permission. No print was submitted. Try again later.")
            return

        self.file_service.verify_version(self.entry, self.expected_version, self.config)

    def _version_failed(self, kind, message):
        if self.busy:
            self._complete("file_changed", "Unable to verify the previewed file. "
                           "Refresh and review the file again. " + message)

    def _version_checked(self, matches):
        if not self.busy:
            return
        if not matches:
            self._complete("file_changed", "The file changed or its version cannot be verified. "
                           "Refresh and review the file again before printing.")
            return
        if not self._session_is_current():
            self._complete("rejected", "Staff session changed. Sign in and try again.")
            return
        request = make_octoprint_request(
            self.config,
            "/api/files/local/" + self.entry.path
        )

        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/json"
        )

        self.reply = self.manager.post(
            request,
            json.dumps({"command": "select", "print": True}).encode()
        )

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
        self._authorization_timer.stop()
        self._authorization_results = None
        self.busy = False
        self.completed.emit(result, message)
