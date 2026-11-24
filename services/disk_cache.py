"""Owned cache entries with bounded eviction and cross-process active leases."""

import os
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths

_LOCK = threading.RLock()
_ACTIVE = {}


def user_cache_directory():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)) / "SAGE"


class DiskCache:
    MAX_AGE_SECONDS = 30 * 24 * 60 * 60

    def __init__(self, directory, kind, *, max_bytes, max_files):
        self.directory = Path(directory)
        self.pattern = re.compile(rf"sage-{kind}-[0-9a-f]{{64}}\.{'gcode' if kind == 'gcode' else 'png'}")
        self.max_bytes = max_bytes
        self.max_files = max_files

    def pin(self, path):
        """Return an idempotent release function; never share an entry with eviction."""
        path = Path(path)
        self.directory.mkdir(parents=True, exist_ok=True)
        if (path.parent.resolve() != self.directory.resolve()
                or not self.pattern.fullmatch(path.name) or path.is_symlink()):
            raise OSError("Invalid cache entry")
        key = str(path.resolve())
        with _LOCK:
            if key in _ACTIVE:
                _ACTIVE[key][0] += 1
            else:
                lease = QLockFile(str(path) + ".lock")
                lease.setStaleLockTime(0)
                if not lease.tryLock(0):
                    raise OSError("Cache entry is in use by another SAGE process")
                _ACTIVE[key] = [1, lease]
        released = False

        def release():
            nonlocal released
            with _LOCK:
                if released:
                    return
                released = True
                _ACTIVE[key][0] -= 1
                if not _ACTIVE[key][0]:
                    _, lease = _ACTIVE.pop(key)
                    lease.unlock()
            self.prune()
        return release

    def touch(self, path):
        try:
            details = path.stat()
            os.utime(path, ns=(time.time_ns(), details.st_mtime_ns))
        except OSError:
            pass

    def prune(self):
        """Best effort: leave foreign files, symlinks, locks and active entries alone."""
        with _LOCK:
            try:
                entries = []
                for path in self.directory.iterdir():
                    if self.pattern.fullmatch(path.name) and not path.is_symlink() and path.is_file():
                        details = path.stat()
                        entries.append((details.st_atime, details.st_size, path))
            except OSError:
                return
            total = sum(size for _, size, _ in entries)
            count = len(entries)
            cutoff = time.time() - self.MAX_AGE_SECONDS
            for accessed, size, path in sorted(entries):
                if accessed >= cutoff and total <= self.max_bytes and count <= self.max_files:
                    continue
                if str(path.resolve()) in _ACTIVE:
                    continue
                lease = QLockFile(str(path) + ".lock")
                lease.setStaleLockTime(0)
                if not lease.tryLock(0):
                    continue
                try:
                    # Recheck containment after acquiring the entry lease.
                    if not path.is_symlink() and path.resolve().parent == self.directory.resolve():
                        path.unlink()
                        total -= size
                        count -= 1
                except OSError:
                    pass
                finally:
                    lease.unlock()
