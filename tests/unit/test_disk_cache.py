"""Cache cleanup operates only on owned, inactive entries in temporary folders."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QLockFile

from services.disk_cache import DiskCache, user_cache_directory


def entry(directory, index, size=4, age=0):
    path = directory / f"sage-gcode-{index:064x}.gcode"
    path.write_bytes(b"x" * size)
    timestamp = time.time() - age
    os.utime(path, (timestamp, timestamp))
    return path


@pytest.mark.parametrize("limit", ["bytes", "count", "age"])
def test_evicts_oldest_owned_entries_only(tmp_path, limit):
    cache = DiskCache(tmp_path, "gcode", max_bytes=100, max_files=100)
    old = entry(tmp_path, 1, age=100)
    new = entry(tmp_path, 2)
    foreign = tmp_path / "my_project.gcode"
    foreign.write_text("keep")
    temporary = tmp_path / (old.name + ".temporary")
    temporary.write_text("in progress")
    if limit == "bytes":
        cache.max_bytes = 4
    elif limit == "count":
        cache.max_files = 1
    else:
        cache.MAX_AGE_SECONDS = 50
    cache.prune()
    assert not old.exists()
    assert new.exists() and foreign.exists() and temporary.exists()


def test_nested_active_leases_protect_until_last_release(tmp_path):
    cache = DiskCache(tmp_path, "gcode", max_bytes=0, max_files=0)
    path = entry(tmp_path, 1)
    first, second = cache.pin(path), cache.pin(path)
    cache.prune()
    assert path.exists()
    first()
    first()
    assert path.exists()
    second()
    assert not path.exists()
    assert not Path(str(path) + ".lock").exists()


def test_external_lock_blocks_eviction_and_new_ownership(tmp_path):
    cache = DiskCache(tmp_path, "gcode", max_bytes=0, max_files=0)
    path = entry(tmp_path, 1)
    lease = QLockFile(str(path) + ".lock")
    assert lease.tryLock(0)
    try:
        cache.prune()
        assert path.exists()
        with pytest.raises(OSError, match="another SAGE"):
            cache.pin(path)
    finally:
        lease.unlock()
    cache.prune()
    assert not path.exists()


def test_permission_failures_do_not_break_cleanup(tmp_path):
    cache = DiskCache(tmp_path, "gcode", max_bytes=0, max_files=0)
    path = entry(tmp_path, 1)
    with patch.object(Path, "unlink", side_effect=PermissionError):
        cache.prune()
    assert path.exists()
    with patch.object(Path, "iterdir", side_effect=PermissionError):
        cache.prune()


def test_touch_preserves_version_mtime_and_eviction_uses_recent_access(tmp_path):
    cache = DiskCache(tmp_path, "gcode", max_bytes=4, max_files=1)
    old = entry(tmp_path, 1, age=100)
    newer = entry(tmp_path, 2, age=50)
    modified = old.stat().st_mtime_ns
    cache.touch(old)
    assert old.stat().st_mtime_ns == modified
    cache.prune()
    assert old.exists() and not newer.exists()


def test_default_cache_uses_user_location_and_never_cwd(tmp_path):
    with patch("services.disk_cache.QStandardPaths.writableLocation", return_value=str(tmp_path)):
        assert user_cache_directory() == tmp_path / "SAGE"
    with patch("services.disk_cache.QStandardPaths.writableLocation", return_value=""):
        assert user_cache_directory() == Path.home() / ".cache" / "SAGE"


def test_cleanup_leaves_symlink_target_untouched(tmp_path):
    target = tmp_path / "original.gcode"
    target.write_text("user file")
    link = tmp_path / ("sage-gcode-" + "f" * 64 + ".gcode")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privileges")
    cache = DiskCache(tmp_path, "gcode", max_bytes=0, max_files=0)
    cache.prune()
    assert link.is_symlink() and target.read_text() == "user file"
    with pytest.raises(OSError, match="Invalid cache entry"):
        cache.pin(link)


def test_pin_rejects_paths_outside_cache_and_unowned_names(tmp_path):
    cache = DiskCache(tmp_path / "cache", "gcode", max_bytes=100, max_files=10)
    for path in (tmp_path / ("sage-gcode-" + "a" * 64 + ".gcode"),
                 cache.directory / "user.gcode"):
        with pytest.raises(OSError, match="Invalid cache entry"):
            cache.pin(path)
