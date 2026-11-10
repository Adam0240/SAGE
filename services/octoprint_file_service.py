"""Asynchronous, read-only access to OctoPrint's uploaded G-code library."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, QTimer, QSaveFile, QIODevice, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from services.octoprint_config import make_octoprint_request, read_octoprint_config


@dataclass(frozen=True)
class RemoteFile:
    path: str
    is_folder: bool = False
    origin: str = "local"

    @property
    def name(self):
        return PurePosixPath(self.path).name

    @property
    def parent(self):
        parent = str(PurePosixPath(self.path).parent)
        return "" if parent == "." else parent


def parse_library(payload):
    """Build folder contents without trusting remote paths as local filenames."""
    folders = {"": []}
    seen = set()

    def visit(nodes, parent="", depth=0):
        if not isinstance(nodes, list) or depth > 64:
            raise ValueError("Invalid file tree")
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError("Invalid file entry")
            name = node.get("name")
            if (not isinstance(name, str) or not name or name in (".", "..")
                    or any(char in name for char in ("/", "\\", "\x00"))):
                raise ValueError("Invalid filename")
            path = f"{parent}/{name}" if parent else name
            if node.get("path", path) not in (path, name) or path in seen:
                raise ValueError("Invalid file path")
            seen.add(path)
            if node.get("origin", "local") != "local":
                continue
            if node.get("type") == "folder":
                folders[parent].append(RemoteFile(path, True))
                folders[path] = []
                visit(node.get("children", []), path, depth + 1)
            elif node.get("type") == "machinecode" and PurePosixPath(name).suffix.lower() in (".gcode", ".gco", ".g"):
                folders[parent].append(RemoteFile(path))

    if not isinstance(payload, dict) or "files" not in payload:
        raise ValueError("Invalid file response")
    visit(payload["files"])
    for entries in folders.values():
        entries.sort(key=lambda entry: (not entry.is_folder, entry.name.casefold()))
    return folders


class OctoPrintFileService(QObject):
    library_loaded = Signal(object)
    file_ready = Signal(object, object)
    failed = Signal(str, str)
    REQUEST_TIMEOUT_MS = 15000
    DOWNLOAD_TIMEOUT_MS = 120000
    MAX_JSON_BYTES = 16 * 1024 * 1024
    MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024

    def __init__(self, cache_dir, parent=None):
        super().__init__(parent)
        self.cache_dir = Path(cache_dir)
        self.manager = QNetworkAccessManager(self)
        self.active = {}
        self.library_source = ""

    def cancel(self, kind=None):
        for name in list(self.active):
            if kind is None or name == kind:
                task = self.active.pop(name)
                task["timer"].stop()
                if task["sink"] is not None:
                    task["sink"].cancelWriting()
                task["reply"].abort()

    def load_library(self):
        self.cancel("library")
        try:
            config = read_octoprint_config()
        except ValueError as error:
            self.failed.emit("library", str(error))
            return
        self._get("library", config, "/api/files/local",
                  lambda body: self._library_received(body, config[0].toString()),
                  query="recursive=true&force=true")

    def _library_received(self, body, source):
        folders = parse_library(json.loads(body))
        self.library_source = source
        self.library_loaded.emit(folders)

    def fetch_file(self, entry):
        self.cancel("file")
        try:
            config = read_octoprint_config()
        except ValueError as error:
            self.failed.emit("file", str(error))
            return
        if config[0].toString() != self.library_source:
            self.failed.emit("file", "OctoPrint server changed. Refresh the file list before previewing.")
            return
        # Always recheck metadata so deleted or changed remote files don't silently
        # reuse stale cache entries. The API key stays in headers, never cache names.
        def metadata_received(body):
            data = json.loads(body)
            if (not isinstance(data, dict) or data.get("type") != "machinecode"
                    or data.get("path") != entry.path or data.get("origin", "local") != "local"):
                raise ValueError("Invalid file metadata")
            version = [data.get(key) for key in ("hash", "date", "size")]
            identity = [config[0].toString(), entry.origin, entry.path, version]
            digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            destination = self.cache_dir / (digest + ".gcode")
            size = data.get("size")
            if type(size) is int and size > self.MAX_DOWNLOAD_BYTES:
                self.failed.emit("file", "This G-code exceeds the 128 MB preview download limit.")
                return
            # Size alone cannot distinguish two different versions of a file.
            version_known = bool(data.get("hash")) or type(data.get("date")) in (int, float)
            if version_known and destination.is_file():
                if type(size) is not int or destination.stat().st_size == size:
                    self.file_ready.emit(entry, destination)
                    return
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._get("file", config, "/downloads/files/local/" + entry.path,
                      lambda _: self.file_ready.emit(entry, destination),
                      destination=destination, expected_size=size)

        self._get("file", config, "/api/files/local/" + entry.path, metadata_received)

    def _get(self, kind, config, path, callback, *, query="", destination=None, expected_size=None):
        request = make_octoprint_request(config, path, query=query)
        sink = None
        if destination is not None:
            sink = QSaveFile(str(destination), self)
            if not sink.open(QIODevice.OpenModeFlag.WriteOnly):
                sink.deleteLater()
                self.failed.emit(kind, "Unable to write the preview cache.")
                return
        reply = self.manager.get(request)
        reply.setReadBufferSize(256 * 1024)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        task = dict(reply=reply, timer=timer, sink=sink, body=bytearray(), size=0, error="")
        self.active[kind] = task

        def fail(message):
            task["error"] = message
            reply.abort()

        def consume():
            if self.active.get(kind) is not task or task["error"]:
                return
            chunk = bytes(reply.readAll())
            task["size"] += len(chunk)
            limit = self.MAX_DOWNLOAD_BYTES if sink is not None else self.MAX_JSON_BYTES
            if task["size"] > limit:
                fail("OctoPrint response is too large to preview.")
            elif sink is not None:
                if sink.write(chunk) != len(chunk):
                    fail("Unable to write the preview cache.")
            else:
                task["body"].extend(chunk)

        def finished():
            timer.stop()
            if self.active.get(kind) is not task:
                if sink is not None:
                    sink.cancelWriting()
                    sink.deleteLater()
                reply.deleteLater()
                return
            consume()
            self.active.pop(kind, None)
            code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            message = task["error"]
            if not message:
                if code in (401, 403):
                    message = "OctoPrint access denied. Check the API key and file permissions."
                elif code == 404:
                    message = "File or folder no longer exists. Refresh the file list."
                elif code != 200 or reply.error() != QNetworkReply.NetworkError.NoError:
                    message = "Unable to reach the OctoPrint library. Check the server address and connection."
                elif sink is not None:
                    if type(expected_size) is int and task["size"] != expected_size:
                        message = "The file changed or its download was incomplete. Refresh and try again."
                    elif not sink.commit():
                        message = "Unable to save the preview cache."
            if sink is not None:
                if message:
                    sink.cancelWriting()
                sink.deleteLater()
            reply.deleteLater()
            if message:
                self.failed.emit(kind, message)
                return
            try:
                callback(bytes(task["body"]))
            except (ValueError, TypeError, KeyError, RecursionError):
                self.failed.emit(kind, "OctoPrint returned an invalid file response.")
            except OSError:
                self.failed.emit(kind, "Unable to access the preview cache.")

        reply.readyRead.connect(consume)
        reply.finished.connect(finished)
        timer.timeout.connect(lambda: fail("OctoPrint request timed out. Try again."))
        timer.start(self.DOWNLOAD_TIMEOUT_MS if sink is not None else self.REQUEST_TIMEOUT_MS)
