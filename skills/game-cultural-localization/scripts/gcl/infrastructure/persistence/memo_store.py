"""Atomic JSON file repository implementing MemoRepository for crash safe batch resume."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from gcl.domain.errors import L10nError

__layer__ = "infrastructure"
__pattern__ = "Repository"
__owns__ = "atomic JSON file persistence for batch memoization and resume"


class AtomicJsonMemoRepository:
    """Thread safe MemoRepository storing completed batch answers atomically in JSON."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.hits = 0
        self._data: Dict[str, Any] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise L10nError(f"{self.path}: batch cache is not valid JSON ({exc.msg}), delete it to start over")
            self._data = data if isinstance(data, dict) else {}

    @staticmethod
    def key(*parts: Any) -> str:
        """Stable SHA256 digest of JSON serializable batch tag and payload parts."""
        return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def make_key(self, *parts: Any) -> str:
        """MemoRepository interface method delegating to AtomicJsonMemoRepository.key."""
        return self.key(*parts)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self.hits += 1
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._flush()

    def put_many(self, items: Dict[str, Any]) -> None:
        """Persist multiple memo entries atomically with a single disk write."""
        if not items:
            return
        with self._lock:
            self._data.update(items)
            self._flush()

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def __len__(self) -> int:
        return len(self._data)


BatchMemo = AtomicJsonMemoRepository
