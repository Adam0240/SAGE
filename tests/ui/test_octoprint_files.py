"""Exercise the real Qt HTTP client and viewer against a local OctoPrint stand-in."""

import json
import tempfile
import threading
import time
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from sage_apps.gcode_display_print_app import GcodeDisplayPrintApp
from sage_apps.octoprint_file_dialog import OctoPrintFileDialog
from services.octoprint_file_service import RemoteFile
from services.session_service import SessionService


class TestOctoPrintFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {
            "parts/model.gcode": b"G1 X0 Y0\nG1 X10 Y10\n",
            "parts/z.gcode": b"G1 X0 Y0\nG1 X20 Y10\n",
            "other/model.gcode": b"G1 X0 Y0\nG1 X20 Y20\n",
            "parts/nested/space % # ü.gcode": b"G1 X0 Y0\nG1 X30 Y10\n",
        }
        self.requests = []
        self.errors = {}
        self.gates = {}
        self.versions = Counter()
        self.invalid_library = False
        self.printer_flags = dict(operational=True, ready=True, printing=False, paused=False,
                                  closedOrError=False, error=False)
        self.posts = []
        self.post_code = None
        self.post_gate = None
        self.post_keep_idle = False
        self.force_busy_on_post = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                url = urlsplit(handler.path)
                path = unquote(url.path)
                owner.requests.append((path, url.query, handler.headers.get("X-Api-Key")))
                gate = owner.gates.get(path)
                if gate:
                    gate.wait(5)
                code = owner.errors.get(path, 200)
                if path == "/octo/api/printer":
                    body = json.dumps({"state": {"flags": owner.printer_flags}}).encode()
                elif path == "/octo/api/job":
                    body = json.dumps({"state": "Printing", "progress": {"printTimeLeft": 9300}}).encode()
                elif path == "/octo/api/files/local":
                    body = b"not json" if owner.invalid_library else json.dumps(owner.library()).encode()
                elif path.startswith("/octo/api/files/local/"):
                    name = path.removeprefix("/octo/api/files/local/")
                    if name not in owner.files:
                        code, body = 404, b""
                    else:
                        body = json.dumps(owner.metadata(name)).encode()
                elif path.startswith("/octo/downloads/files/local/"):
                    name = path.removeprefix("/octo/downloads/files/local/")
                    body = owner.files.get(name, b"")
                    if name not in owner.files:
                        code = 404
                else:
                    code, body = 404, b""
                try:
                    handler.send_response(code)
                    handler.send_header("Content-Length", str(len(body)))
                    handler.end_headers()
                    handler.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def do_POST(handler):
                path = unquote(urlsplit(handler.path).path)
                body = json.loads(handler.rfile.read(int(handler.headers["Content-Length"])))
                owner.posts.append((path, body, handler.headers.get("X-Api-Key")))
                if owner.force_busy_on_post:
                    owner.printer_flags.update(printing=True, ready=False)
                code = owner.post_code
                if code is None:
                    if not owner.printer_flags["ready"] or owner.printer_flags["printing"] or owner.printer_flags["paused"]:
                        code = 409
                    elif path.removeprefix("/octo/api/files/local/") not in owner.files:
                        code = 404
                    else:
                        code = 204
                if code == 204 and not owner.post_keep_idle:
                    owner.printer_flags.update(printing=True, ready=False)
                if owner.post_gate is not None:
                    owner.post_gate.wait(5)
                try:
                    handler.send_response(code)
                    handler.send_header("Content-Length", "0")
                    handler.end_headers()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        config = patch.dict("os.environ", {
            "OCTOPRINT_URL": f"http://127.0.0.1:{self.server.server_port}/octo",
            "OCTOPRINT_API_KEY": "test-secret",
        })
        config.start()
        self.addCleanup(config.stop)
        self.session_service = SessionService()
        permission = patch("services.octoprint_print_service.has_print_permission", return_value=True)
        self.permission = permission.start()
        self.addCleanup(permission.stop)

        self.session_state = self.session_service.log_in(
            user_id=1,
            user_name="Test Specialist",
            role="steam_specialist",
        )

        self.window = GcodeDisplayPrintApp(
            thumbnail_dir=self.root / "cache",
            can_start_print=lambda: self.session_state.can_start_print,
            get_session=lambda: self.session_state,
        )
        self.addCleanup(self.close_window)
        self.wait_until(lambda: not self.window.library_loading)

    def stop_server(self):
        if self.post_gate is not None:
            self.post_gate.set()
        for gate in self.gates.values():
            gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def close_window(self):
        self.window.close()
        worker = self.window.preview_loader.thread
        if worker is not None:
            worker.join(3)
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def metadata(self, path):
        return dict(name=path.rsplit("/", 1)[-1], path=path, type="machinecode", origin="local",
                    size=len(self.files[path]), date=self.versions[path], hash=f"version-{self.versions[path]}")

    def library(self):
        folders = {"": []}
        for path in self.files:
            parent = ""
            for name in path.split("/")[:-1]:
                nested = f"{parent}/{name}" if parent else name
                if nested not in folders:
                    folders[nested] = []
                    folders[parent].append(dict(name=name, path=nested, type="folder", children=folders[nested]))
                parent = nested
            folders[parent].append(self.metadata(path))
        folders[""].append(dict(name="empty", path="empty", type="folder", children=[]))
        folders[""].append(dict(name="notes.txt", type="model", path="notes.txt"))
        return {"files": folders[""]}

    def wait_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def wait_for_preview(self):
        self.wait_until(lambda: not self.window.file_service.active and not self.window.preview_loader.busy)
        self.app.processEvents()

    def select(self, path):
        self.window.select_remote_file(RemoteFile(path))
        self.wait_for_preview()

    def test_folder_browser_search_back_cancel_and_selection(self):
        self.assertIsNone(self.window.gcode_dir)
        self.assertEqual(set(self.window.remote_folders), {"", "parts", "parts/nested", "other", "empty"})
        self.assertTrue(self.window.file_list_button.isEnabled())
        dialog = OctoPrintFileDialog(self.window)
        try:
            dialog.search_box.setText("PART")
            self.assertEqual(dialog.file_list.count(), 1)
            dialog.open_selected()
            self.assertEqual(dialog.path_label.text(), "/parts")
            self.assertEqual(dialog.file_list.count(), 3)
            dialog.search_box.setText("model")
            dialog.open_selected()
            self.assertEqual(dialog.selected_file.path, "parts/model.gcode")
            self.window.select_remote_file(dialog.selected_file)
            self.wait_for_preview()
            self.assertFalse(self.window.preview_label.pixmap().isNull())
            self.assertEqual(self.window.selected_remote_file.origin, "local")
        finally:
            dialog.deleteLater()
        dialog = OctoPrintFileDialog(self.window)
        try:
            dialog.go_back()
            dialog.search_box.setText("empty")
            dialog.open_selected()
            self.assertIn("empty", dialog.message_label.text())
            self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Open).isEnabled())
            dialog.go_back()
            dialog.search_box.setText("missing")
            self.assertIn("No matching", dialog.message_label.text())
            dialog.reject()
            self.assertEqual(self.window.selected_remote_file.path, "parts/model.gcode")
        finally:
            dialog.deleteLater()

    def test_cache_duplicates_changes_and_encoded_paths(self):
        self.select("parts/model.gcode")
        first = self.window._preview_path
        self.select("other/model.gcode")
        self.assertNotEqual(first, self.window._preview_path)
        self.select("parts/model.gcode")
        downloads = [path for path, _, _ in self.requests if path == "/octo/downloads/files/local/parts/model.gcode"]
        self.assertEqual(len(downloads), 1)
        self.files["parts/model.gcode"] = b"G1 X0 Y0\nG1 X99 Y99\n"
        self.versions["parts/model.gcode"] += 1
        self.window.load_gcode_files()
        self.wait_for_preview()
        self.assertNotEqual(first, self.window._preview_path)
        self.assertEqual(self.window._preview_path.read_bytes(), self.files["parts/model.gcode"])
        self.select("parts/nested/space % # ü.gcode")
        self.assertFalse(self.window.preview_label.pixmap().isNull())
        self.assertTrue(all(key == "test-secret" for _, _, key in self.requests))
        self.assertTrue(any("force=true" in query for _, query, _ in self.requests))

    def test_navigation_stays_in_selected_folder(self):
        self.select("parts/model.gcode")
        self.window.next_button.click()
        self.wait_for_preview()
        self.assertEqual(self.window.selected_remote_file.path, "parts/z.gcode")
        self.window.next_button.click()
        self.wait_for_preview()
        self.assertEqual(self.window.selected_remote_file.path, "parts/model.gcode")
        self.window.previous_button.click()
        self.wait_for_preview()
        self.assertEqual(self.window.selected_remote_file.path, "parts/z.gcode")
        self.assertFalse(self.window.start_print_button.isEnabled())

    def test_cache_rechecks_files_without_version_metadata(self):
        original_metadata = self.metadata

        def unversioned_metadata(path):
            data = original_metadata(path)
            del data["hash"]
            del data["date"]
            return data

        with patch.object(self, "metadata", side_effect=unversioned_metadata):
            self.select("parts/model.gcode")
            original = self.files["parts/model.gcode"]
            self.files["parts/model.gcode"] = original.replace(b"10", b"99")
            self.select("parts/model.gcode")
        downloads = [path for path, _, _ in self.requests
                     if path == "/octo/downloads/files/local/parts/model.gcode"]
        self.assertEqual(len(downloads), 2)
        self.assertEqual(self.window._preview_path.read_bytes(), self.files["parts/model.gcode"])

    def test_preview_rejects_server_change_until_library_refresh(self):
        self.select("parts/model.gcode")
        before = len(self.requests)
        with patch.dict("os.environ", {"OCTOPRINT_URL": f"http://127.0.0.1:{self.server.server_port}/different"}):
            self.select("parts/model.gcode")
        self.assertIn("server changed", self.window.preview_label.text())
        self.assertEqual(len(self.requests), before)
        self.assertIsNone(self.window._preview_path)
        self.assertFalse(self.window.start_print_button.isEnabled())

    def test_deleted_file_and_refresh_recover(self):
        self.select("parts/model.gcode")
        del self.files["parts/model.gcode"]
        self.select("parts/model.gcode")
        self.assertIn("no longer exists", self.window.preview_label.text())
        self.assertIsNone(self.window._preview_path)
        self.window.load_gcode_files()
        self.wait_for_preview()
        self.assertEqual(self.window.selected_remote_file.path, "parts/z.gcode")
        self.assertEqual([entry.path for entry in self.window.gcode_files], ["parts/z.gcode"])

    def test_errors_and_retry(self):
        for code in (401, 403, 500):
            self.errors["/octo/api/files/local"] = code
            self.window.load_gcode_files()
            self.wait_until(lambda: not self.window.library_loading)
            self.assertTrue(self.window.library_message)
            self.assertTrue(self.window.file_list_button.isEnabled())
            self.assertFalse(self.window.next_button.isEnabled())
        self.errors.clear()
        self.invalid_library = True
        self.window.load_gcode_files()
        self.wait_until(lambda: not self.window.library_loading)
        self.assertIn("invalid", self.window.library_message)
        self.invalid_library = False
        self.window.load_gcode_files()
        self.wait_until(lambda: not self.window.library_loading)
        self.assertEqual(self.window.library_message, "")
        self.errors["/octo/downloads/files/local/parts/model.gcode"] = 403
        self.select("parts/model.gcode")
        self.assertIn("access denied", self.window.preview_label.text())
        self.assertEqual(list((self.root / "cache" / "gcodes").glob("*.gcode")), [])

    def test_slow_download_cancel_home_and_reopen(self):
        self.window.show()
        path = "/octo/downloads/files/local/parts/model.gcode"
        gate = self.gates[path] = threading.Event()
        self.window.select_remote_file(RemoteFile("parts/model.gcode"))
        self.wait_until(lambda: any(request[0] == path for request in self.requests))
        ticks = []
        QTimer.singleShot(10, lambda: ticks.append(True))
        QTest.qWait(30)
        self.assertTrue(ticks)
        self.window.next_button.click()
        self.wait_for_preview()
        self.assertEqual(self.window.selected_remote_file.path, "parts/z.gcode")
        gate.set()
        QTest.qWait(50)
        self.assertEqual(self.window.filename_label.text(), "parts/z.gcode")
        gate.clear()
        self.window.select_remote_file(RemoteFile("parts/model.gcode"))
        self.wait_until(lambda: len([r for r in self.requests if r[0] == path]) == 2)
        self.window.home_button.click()
        self.assertFalse(self.window.file_service.active)
        gate.set()
        self.window.show()
        self.wait_for_preview()
        self.assertFalse(self.window.preview_label.pixmap().isNull())
        self.assertEqual(self.window.selected_remote_file.path, "parts/model.gcode")

    def test_timeout_and_missing_configuration(self):
        gate = self.gates["/octo/api/files/local"] = threading.Event()
        self.window.file_service.REQUEST_TIMEOUT_MS = 80
        self.window.load_gcode_files()
        self.wait_until(lambda: not self.window.library_loading)
        self.assertIn("timed out", self.window.library_message)
        gate.set()
        with patch.dict("os.environ", {"OCTOPRINT_URL": "", "OCTOPRINT_API_KEY": ""}):
            self.window.load_gcode_files()
        self.assertIn("not configured", self.window.library_message)
        self.assertFalse(self.window.file_service.active)

    def test_replaced_preview_is_rejected_until_reviewed_again(self):
        self.prepare_print()
        path = "parts/model.gcode"
        self.files[path] = b"G1 X0 Y0\nG1 X90 Y90\n"  # Same path and size.
        self.versions[path] += 1
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(self.posts, [])
        self.assertFalse(self.window._file_validated)
        self.assertIsNone(self.window._preview_path)
        self.assertIn("review", self.window.preview_label.text())
        self.window.start_print()
        self.assertEqual(self.posts, [])
        self.prepare_print()
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(len(self.posts), 1)

    def test_date_and_size_version_can_print_but_date_change_requires_review(self):
        original = self.metadata

        def metadata(path):
            data = original(path)
            data.pop("hash")
            return data

        with patch.object(self, "metadata", side_effect=metadata):
            self.prepare_print()
            self.versions["parts/model.gcode"] += 1
            self.window.start_print()
            self.wait_until(lambda: not self.window.print_service.busy)
            self.assertEqual(self.posts, [])
            self.prepare_print()
            self.window.start_print()
            self.wait_until(lambda: not self.window.print_service.busy)
            self.assertEqual(len(self.posts), 1)

    def test_file_replaced_during_permission_check_is_rejected(self):
        self.prepare_print()

        def permission(_):
            self.versions["parts/model.gcode"] += 1
            return True

        self.permission.side_effect = permission
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(self.posts, [])
        self.assertFalse(self.window._file_validated)

    def test_file_metadata_failures_and_unversioned_files_fail_closed(self):
        original = self.metadata
        for failure in ("missing", "denied", "malformed", "unversioned", "date_size"):
            with self.subTest(failure=failure):
                self.prepare_print()

                def metadata(path):
                    data = original(path)
                    if failure == "malformed":
                        return []
                    data.pop("hash", None)
                    if failure == "unversioned":
                        data.pop("date", None)
                    return data

                api_path = "/octo/api/files/local/parts/model.gcode"
                if failure in ("missing", "denied"):
                    self.errors[api_path] = 404 if failure == "missing" else 403
                with patch.object(self, "metadata", side_effect=metadata):
                    # Also exercise previewing a server with no hash/date.
                    if failure == "unversioned":
                        self.select("parts/model.gcode")
                    self.window.start_print()
                    self.wait_until(lambda: not self.window.print_service.busy)
                self.errors.clear()
                self.assertEqual(self.posts, [])
                self.assertFalse(self.window._file_validated)

    def test_metadata_check_cancel_timeout_and_session_change_never_submit(self):
        for action in ("home", "timeout", "logout"):
            with self.subTest(action=action):
                self.session_state = self.session_service.log_in(1, "Staff", "steam_specialist")
                self.prepare_print()
                api_path = "/octo/api/files/local/parts/model.gcode"
                gate = self.gates[api_path] = threading.Event()
                previous = sum(path == api_path for path, _, _ in self.requests)
                verifier = self.window.print_service.file_service
                if action == "timeout":
                    verifier.REQUEST_TIMEOUT_MS = 80
                self.window.start_print()
                self.wait_until(lambda: sum(path == api_path for path, _, _ in self.requests) > previous)
                if action == "home":
                    self.window.home_button.click()
                elif action == "logout":
                    self.session_state = self.session_service.log_out()
                if action != "timeout":
                    gate.set()
                self.wait_until(lambda: not self.window.print_service.busy)
                gate.set()
                self.gates.clear()
                verifier.REQUEST_TIMEOUT_MS = 15000
                QTest.qWait(50)
                self.assertEqual(self.posts, [])
                self.assertFalse(verifier.active)

    def test_cache_budget_preserves_selection_then_evicts_released_version(self):
        cache = self.window.file_service.cache
        cache.max_files = 1
        self.select("parts/model.gcode")
        previous = self.window._preview_path
        cache.max_bytes = 0
        cache.prune()
        self.assertTrue(previous.exists())
        self.select("parts/z.gcode")
        current = self.window._preview_path
        self.assertFalse(previous.exists())
        self.assertTrue(current.exists())
        self.window.file_service.cancel()
        self.assertFalse(current.exists())

    def test_readonly_download_cache_reports_failure_without_validating_file(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("Read-only cache")):
            self.select("parts/model.gcode")
        self.assertFalse(self.window._file_validated)
        self.assertIn("cache", self.window.preview_label.text())
        self.assertFalse(self.window.file_service.active)

    def test_destroyed_file_service_releases_cache_lease(self):
        from shiboken6 import delete

        from services.octoprint_file_service import OctoPrintFileService

        service = OctoPrintFileService(self.root / "isolated-cache")
        service.cache.max_files = 0
        path = service.cache_dir / ("sage-gcode-" + "b" * 64 + ".gcode")
        service._cache_slot[0] = service.cache.pin(path)
        path.write_text("G1 X0 Y0\n")
        delete(service)
        self.assertFalse(path.exists())
        self.assertFalse(Path(str(path) + ".lock").exists())

    def test_remaining_time_http_success_failure_and_cancelled_job(self):
        service = self.window.printer_status_service
        self.printer_flags.update(ready=False, printing=True)
        service.check()
        self.wait_until(lambda: service.reply is None)
        self.assertTrue(service.status.busy)
        self.assertEqual(service.status.remaining_seconds, 9300)
        self.errors["/octo/api/job"] = 500
        service.check()
        self.wait_until(lambda: service.reply is None)
        self.assertTrue(service.status.busy)
        self.assertIsNone(service.status.remaining_seconds)
        self.errors.clear()
        gate = self.gates["/octo/api/job"] = threading.Event()
        previous = sum(path == "/octo/api/job" for path, _, _ in self.requests)
        received = []
        service.completed.connect(received.append)
        service.check()
        self.wait_until(lambda: sum(path == "/octo/api/job" for path, _, _ in self.requests) > previous)
        service.cancel()
        gate.set()
        QTest.qWait(80)
        self.assertEqual(received, [])
        self.assertIsNone(service.reply)
        self.assertFalse(service.status.busy)

    def prepare_print(self, path="parts/model.gcode"):
        self.window.show()
        self.select(path)
        self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.window.check_printer_status()
        self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.assertTrue(self.window.start_print_button.isEnabled())

    def test_print_exact_selected_path_once_and_reenable_after_job(self):
        path = "parts/nested/space % # ü.gcode"
        self.prepare_print(path)
        self.window.start_print_button.click()
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.window.start_print_button.click()
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy and self.window.printer_status_service.reply is None)
        self.assertEqual(self.posts, [("/octo/api/files/local/" + path,
                                      {"command": "select", "print": True}, "test-secret")])
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertIn("busy", self.window.printer_status_label.text())
        self.printer_flags.update(printing=False, ready=True)
        self.window.status_poll_timer.setInterval(30)
        self.wait_until(lambda: self.window.start_print_button.isEnabled())
        self.assertEqual(len(self.posts), 1)

    def test_print_disabled_for_busy_unknown_and_disconnected_states(self):
        self.prepare_print()
        idle = self.printer_flags.copy()
        for change in ({"printing": True}, {"paused": True}, {"pausing": True},
                       {"cancelling": True}, {"finishing": True}, {"resuming": True},
                       {"ready": False}, {"operational": False}, {"error": True},
                       {"printing": "false"}):
            self.printer_flags = idle | change
            self.window.check_printer_status(manual=False)
            self.wait_until(lambda: self.window.printer_status_service.reply is None)
            self.assertFalse(self.window.start_print_button.isEnabled(), change)
            self.window.start_print_button.click()
            self.window.start_print()
        self.printer_flags = idle
        for code in (401, 403, 409, 500):
            self.errors["/octo/api/printer"] = code
            self.window.check_printer_status(manual=False)
            self.wait_until(lambda: self.window.printer_status_service.reply is None)
            self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertEqual(self.posts, [])

    def test_print_rechecks_busy_before_post_and_handles_server_conflict(self):
        self.prepare_print()
        self.printer_flags.update(printing=True, ready=False)
        self.window.start_print_button.click()
        self.wait_until(lambda: not self.window.print_service.busy and self.window.printer_status_service.reply is None)
        self.assertEqual(self.posts, [])
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.printer_flags.update(printing=False, ready=True)
        self.window.check_printer_status()
        self.wait_until(lambda: self.window.start_print_button.isEnabled())
        self.force_busy_on_post = True
        self.window.start_print_button.click()
        self.wait_until(lambda: not self.window.print_service.busy and self.window.printer_status_service.reply is None)
        self.assertEqual(len(self.posts), 1)
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertIn("busy", self.window.print_message_label.text())

    def test_print_request_pending_locks_selection_and_survives_home(self):
        self.prepare_print()
        self.post_gate = threading.Event()
        self.window.start_print_button.click()
        self.wait_until(lambda: len(self.posts) == 1)
        self.assertFalse(self.window.next_button.isEnabled())
        self.assertFalse(self.window.file_list_button.isEnabled())
        self.window.show_next_file()
        self.assertEqual(self.window.selected_remote_file.path, "parts/model.gcode")
        self.window.home_button.click()
        self.assertTrue(self.window.print_service.busy)
        self.post_gate.set()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.window.show()
        self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertEqual(len(self.posts), 1)

    def test_print_preflight_cancel_on_home_never_sends_command(self):
        self.prepare_print()
        gate = self.gates["/octo/api/printer"] = threading.Event()
        previous = len(self.requests)
        self.window.start_print_button.click()
        self.wait_until(lambda: len(self.requests) > previous)
        self.window.home_button.click()
        gate.set()
        QTest.qWait(50)
        self.assertFalse(self.window.print_service.busy)
        self.assertFalse(self.window.status_poll_timer.isActive())
        self.assertIsNone(self.window.printer_status_service.reply)
        self.assertEqual(self.posts, [])

    def test_print_timeout_never_retries_and_requires_status_check(self):
        self.prepare_print()
        self.post_gate = threading.Event()
        self.post_keep_idle = True
        self.window.print_service.TIMEOUT_MS = 80
        self.window.start_print_button.click()
        self.wait_until(lambda: not self.window.print_service.busy and self.window.printer_status_service.reply is None)
        self.assertIn("unknown", self.window.print_message_label.text())
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.window.check_printer_status(manual=False)
        self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.window.start_print()
        self.assertEqual(len(self.posts), 1)
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.post_gate.set()
        self.window.check_printer_status()
        self.wait_until(lambda: self.window.start_print_button.isEnabled())
        self.assertEqual(len(self.posts), 1)

    def test_print_permissions_missing_file_and_server_change(self):
        self.prepare_print()
        for code, expected in ((403, "permissions"), (404, "no longer exists"), (415, "cannot print")):
            self.post_code = code
            self.window.start_print_button.click()
            self.wait_until(lambda: not self.window.print_service.busy and self.window.printer_status_service.reply is None)
            self.assertIn(expected, self.window.print_message_label.text())
            self.assertTrue(self.window.start_print_button.isEnabled())
        count = len(self.posts)
        with patch.dict("os.environ", {"OCTOPRINT_URL": f"http://127.0.0.1:{self.server.server_port}/different"}):
            self.window.start_print_button.click()
            self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.assertIn("server changed", self.window.print_message_label.text())
        self.assertEqual(len(self.posts), count)

    def test_print_stays_disabled_without_file_and_after_status_expires(self):
        self.window.show()
        self.wait_until(lambda: self.window.printer_status_service.reply is None)
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.prepare_print()
        self.window._status_checked_at -= 6
        self.window.start_print()
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertEqual(self.posts, [])

    def test_refresh_updates_open_dialog_and_removed_folder(self):
        self.select("parts/nested/space % # ü.gcode")
        dialog = OctoPrintFileDialog(self.window)
        try:
            del self.files["parts/nested/space % # ü.gcode"]
            self.files["new.gcode"] = b"G1 X0 Y0\nG1 X1 Y1\n"
            dialog.refresh_button.click()
            self.wait_for_preview()
            self.assertEqual(dialog.path_label.text(), "/")
            self.assertTrue(dialog.refresh_button.isEnabled())
            names = [dialog.file_list.item(i).text() for i in range(dialog.file_list.count())]
            self.assertIn("new.gcode", names)
            self.assertEqual(self.window.selected_remote_file.path, "new.gcode")
        finally:
            dialog.deleteLater()

    def test_download_size_limit_and_destroy_during_request(self):
        self.window.file_service.MAX_DOWNLOAD_BYTES = 5
        self.select("parts/model.gcode")
        self.assertIn("download limit", self.window.preview_label.text())
        self.assertFalse(any("/downloads/" in path for path, _, _ in self.requests))
        gate = self.gates["/octo/api/files/local"] = threading.Event()
        self.window.load_gcode_files()
        self.assertTrue(self.window.file_service.active)
        self.window.file_service.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gate.set()
        # Recreate a service only so the usual widget cleanup can call cancel().
        from services.octoprint_file_service import OctoPrintFileService
        self.window.file_service = OctoPrintFileService(self.root / "cache", self.window)
        QTest.qWait(50)

    def test_only_steam_specialist_can_start_print(self):
        self.prepare_print()

        for role in ("student", "base_specialist", "boss_admin"):
            with self.subTest(role=role):

                if role == "student":
                    self.session_state = self.session_service.log_out()
                else:
                    self.session_state = self.session_service.log_in(
                        user_id=2,
                        user_name="Test User",
                        role=role,
                    )

                self.window._update_print_button()

                self.assertFalse(
                    self.window.start_print_button.isEnabled()
                )

                # Verify the UI handler cannot bypass authorization.
                self.window.start_print()

                # Verify the service cannot bypass authorization.
                self.window.print_service.start(
                    self.window.selected_remote_file,
                    self.window.file_service.library_source,
                )

                self.assertFalse(self.window.print_service.busy)
                self.assertEqual(self.posts, [])

        # Verify printing becomes available after specialist login.
        self.session_state = self.session_service.log_in(
            user_id=1,
            user_name="Test Specialist",
            role="steam_specialist",
        )

        # Wait for any existing printer status check to finish.
        self.wait_until(
            lambda: self.window.printer_status_service.reply is None
        )

        # Refresh the printer status.
        self.window.check_printer_status()

        self.wait_until(
            lambda: self.window.printer_status_service.reply is None
        )

        self.window._update_print_button()

        self.assertTrue(
            self.window.start_print_button.isEnabled()
        )

    def test_open_voice_project(self):
        source = self.window.file_service.library_source

        self.window.show()

        self.window.open_voice_project(
            "other/model.gcode",
            source,
        )

        self.wait_for_preview()

        self.assertEqual(
            self.window.selected_remote_file.path,
            "other/model.gcode",
        )

        self.assertFalse(
            self.window.preview_label.pixmap().isNull()
        )

        # Displaying a project must not start a print.
        self.assertEqual(self.posts, [])

    def test_revocation_during_printer_preflight_rejects_print(self):
        self.prepare_print()
        revoked = []
        self.window.print_service.authorization_revoked.connect(revoked.append)
        session = self.session_state
        gate = self.gates["/octo/api/printer"] = threading.Event()
        before = len(self.requests)
        self.window.start_print()
        self.wait_until(lambda: len(self.requests) > before)
        # The user was removed, disabled, or demoted after the cached login.
        self.permission.return_value = False
        gate.set()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(self.posts, [])
        self.assertEqual(revoked, [session])
        self.permission.assert_called_once_with(session.user_id)
        self.assertIn("revoked", self.window.print_message_label.text())

    def test_database_failure_rejects_print_without_retry_and_recovers(self):
        self.prepare_print()
        self.permission.side_effect = RuntimeError("private database details")
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(self.posts, [])
        self.permission.assert_called_once()
        self.assertIn("Unable to verify", self.window.print_message_label.text())
        self.assertNotIn("private", self.window.print_message_label.text())
        self.permission.side_effect = None
        self.prepare_print()
        self.window.start_print()
        self.wait_until(lambda: not self.window.print_service.busy)
        self.assertEqual(len(self.posts), 1)

    def test_slow_authorization_is_responsive_and_abandoned_results_cannot_print(self):
        for action in ("logout", "replacement_login", "home", "timeout"):
            with self.subTest(action=action):
                self.session_state = self.session_service.log_in(1, "Specialist", "steam_specialist")
                self.prepare_print()
                entered, release = threading.Event(), threading.Event()
                worker_ids = []

                def check(_user_id):
                    worker_ids.append(threading.get_ident())
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("Test did not release permission check")
                    return True

                self.permission.side_effect = check
                service = self.window.print_service
                revoked = []
                service.authorization_revoked.connect(revoked.append)
                try:
                    self.window.start_print()
                    self.wait_until(entered.is_set)
                    ticks = []
                    QTimer.singleShot(0, lambda: ticks.append(True))
                    self.wait_until(lambda: bool(ticks))
                    self.assertNotEqual(worker_ids[0], threading.get_ident())
                    self.assertTrue(service.busy)
                    if action == "logout":
                        self.session_state = self.session_service.log_out()
                    elif action == "replacement_login":
                        # Same identity/role still represents a different login.
                        self.session_state = self.session_service.log_in(1, "Specialist", "steam_specialist")
                    elif action == "home":
                        self.window.home_button.click()
                    else:
                        service._authorization_deadline = time.monotonic() - 1
                    self.wait_until(lambda: not service.busy)
                    if action == "home":
                        calls = self.permission.call_count
                        self.prepare_print()
                        self.window.start_print()
                        self.wait_until(lambda: not service.busy)
                        self.assertIn("still finishing", self.window.print_message_label.text())
                        self.assertEqual(self.permission.call_count, calls)
                    release.set()
                    service._authorization_thread.join(3)
                    self.assertFalse(service._authorization_thread.is_alive())
                    QTest.qWait(40)
                    self.assertEqual(self.posts, [])
                    self.assertEqual(revoked, [])
                finally:
                    release.set()
                    service._authorization_thread.join(3)
                    service.authorization_revoked.disconnect(revoked.append)
                    self.permission.side_effect = None

    def test_cached_callback_without_session_cannot_authorize_print(self):
        self.prepare_print()
        self.window.print_service.get_session = lambda: None
        self.window.start_print()
        self.assertFalse(self.window.print_service.busy)
        self.assertEqual(self.posts, [])
        self.permission.assert_not_called()


    def test_open_deleted_voice_project(self):
        source = self.window.file_service.library_source

        del self.files["other/model.gcode"]

        self.window.show()

        self.window.open_voice_project(
            "other/model.gcode",
            source,
        )

        self.wait_for_preview()

        self.assertIsNone(
            self.window.selected_remote_file
        )

        self.assertIn(
            "no longer available",
            self.window.preview_label.text(),
        )

        self.assertFalse(
            self.window.start_print_button.isEnabled()
        )

        self.assertEqual(self.posts, [])
