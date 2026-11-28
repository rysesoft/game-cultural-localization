"""Atomic JSON file VerdictRepository implementing batch verdict save and hydration."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError
from gcl.domain.verdict_models import LineVerdict

__layer__ = "infrastructure"
__pattern__ = "Repository"
__owns__ = "atomic JSON batch verdict persistence and LineVerdict hydration"


@dataclass(frozen=True, slots=True)
class JsonVerdictRepository:
    """Implements VerdictRepository via atomic temporary file swap and LineVerdict hydration."""

    def save_batch(self, path: Path, doc: dict[str, Any]) -> dict[str, Any]:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
        return doc

    def load_batch(self, path: Path) -> tuple[dict[str, Any], list[LineVerdict]]:
        target = Path(path)
        try:
            doc = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise L10nError(f"{target}: cannot load verdict batch JSON ({exc})")
        if not isinstance(doc, dict) or not isinstance(doc.get("verdicts"), list):
            raise L10nError(f"{target}: verdict batch JSON must contain a 'verdicts' list")
        return doc, [LineVerdict.from_dict(v) for v in doc["verdicts"]]
