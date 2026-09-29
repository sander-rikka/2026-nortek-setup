from __future__ import annotations

import hashlib
import json
from pathlib import Path


class FileCache:
    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, key: str, suffix: str = ".bin") -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.directory / f"{digest}{suffix}"

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def set_bytes(self, key: str, value: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(key).write_bytes(value)

    def get_json(self, key: str):
        raw = self.get_bytes(key)
        return json.loads(raw) if raw is not None else None

    def set_json(self, key: str, value) -> None:
        self.set_bytes(key, json.dumps(value).encode())
