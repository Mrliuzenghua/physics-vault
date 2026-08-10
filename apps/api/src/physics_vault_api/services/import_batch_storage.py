from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..paths import default_import_batches_dir, project_root


class StaleBatchVersionError(RuntimeError):
    """Raised when late worker output would overwrite newer user edits."""


class _BatchProcessLock:
    """Re-entrant process and filesystem lock for one import batch."""

    def __init__(self, batch_id: str, batches_dir: Path) -> None:
        self._batch_id = batch_id
        self._batches_dir = batches_dir
        self._thread_lock = threading.RLock()
        self._local = threading.local()
        self._handle: Any | None = None

    def __enter__(self) -> "_BatchProcessLock":
        self._thread_lock.acquire()
        depth = int(getattr(self._local, "depth", 0))
        try:
            if depth == 0:
                lock_path = self._batches_dir / self._batch_id / ".pipeline.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = lock_path.open("a+b")
                self._acquire_file_lock(self._handle)
            self._local.depth = depth + 1
            return self
        except Exception:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        depth = int(getattr(self._local, "depth", 1)) - 1
        self._local.depth = depth
        try:
            if depth == 0 and self._handle is not None:
                self._release_file_lock(self._handle)
                self._handle.close()
                self._handle = None
        finally:
            self._thread_lock.release()

    @staticmethod
    def _acquire_file_lock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for import batch lock")
                    time.sleep(0.05)
        else:  # pragma: no cover - exercised on non-Windows deployments
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _release_file_lock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - exercised on non-Windows deployments
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ImportBatchStorage:
    """Owns import-batch files, metadata consistency and version checks."""

    _locks: dict[tuple[str, str], _BatchProcessLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, batches_dir: Path | None = None) -> None:
        self._batches_dir = batches_dir or default_import_batches_dir()

    def lock(self, batch_id: str) -> _BatchProcessLock:
        key = (str(self._batches_dir.resolve()), batch_id)
        with self._locks_guard:
            return self._locks.setdefault(key, _BatchProcessLock(batch_id, self._batches_dir))

    def metadata_path(self, batch_id: str) -> Path:
        return self._batches_dir / batch_id / "status.json"

    def read_metadata(self, batch_id: str) -> dict[str, Any]:
        metadata_path = self.metadata_path(batch_id)
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail=f"Import batch not found: {batch_id}")
        with self.lock(batch_id):
            return json.loads(metadata_path.read_text(encoding="utf-8"))

    def write_metadata(self, batch_id: str, metadata: dict[str, Any]) -> None:
        with self.lock(batch_id):
            atomic_write_json(self.metadata_path(batch_id), metadata)

    @staticmethod
    def content_version(metadata: dict[str, Any]) -> int:
        return max(1, int(metadata.get("content_version") or 1))

    def assert_input_version(self, batch_id: str, expected_version: int) -> dict[str, Any]:
        metadata = self.read_metadata(batch_id)
        actual = self.content_version(metadata)
        if actual != expected_version:
            raise StaleBatchVersionError(
                f"Import batch {batch_id} changed from version {expected_version} to {actual}; late output was discarded"
            )
        return metadata

def safe_filename(filename: str) -> str:
    source = Path(filename).name
    stem = Path(source).stem.strip() or "document"
    suffix = Path(source).suffix.lower()
    stem = re.sub(r"[^\w\-.()\u4e00-\u9fff]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{stem[:80] or 'document'}{suffix}"


def relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root().resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_DEFAULT_STORAGE = ImportBatchStorage()


def batch_lock(batch_id: str) -> _BatchProcessLock:
    """Compatibility helper for callers that only need the batch lock."""
    return _DEFAULT_STORAGE.lock(batch_id)
