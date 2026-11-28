"""SQLite translation memory repository with trigram Dice similarity retrieval."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from gcl.domain.errors import L10nError
from gcl.ports.storage import TMQuery, TMSegment

__layer__ = "infrastructure"
__pattern__ = "Repository"
__owns__ = "SQLite translation memory storage and character n-gram neighbor lookup"

STATUSES = ("approved", "candidate")
DEFAULT_TOP = 5
DEFAULT_MIN_SIMILARITY = 0.3
CANDIDATE_POOL = 300
MAX_QUERY_GRAMS = 900
_ADD_KW = frozenset({"category", "speaker", "register", "status", "origin"})
_NEIGHBOR_KW = frozenset({"on", "category", "speaker", "k", "min_similarity", "exclude_key", "statuses"})
SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY,
  locale TEXT NOT NULL, key TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT '', speaker TEXT NOT NULL DEFAULT '', register TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL, origin TEXT NOT NULL DEFAULT '', src_norm TEXT NOT NULL,
  UNIQUE(locale, key, src_norm)
);
CREATE TABLE IF NOT EXISTS grams (gram TEXT NOT NULL, seg_id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS grams_gram ON grams(gram);
CREATE INDEX IF NOT EXISTS grams_seg ON grams(seg_id);
CREATE INDEX IF NOT EXISTS seg_lookup ON segments(locale, status, category, speaker);
"""


def normalize(text: str) -> str:
    """Normalize with NFC, collapsed whitespace and case folding."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def trigrams(text: str) -> List[str]:
    """Return sorted unique character trigrams of padded normalized text."""
    t = f"  {normalize(text)} "
    return sorted({t[i:i + 3] for i in range(len(t) - 2)})


def dice(a: Sequence[str], b: Sequence[str]) -> float:
    """Compute Dice coefficient between two trigram collections."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return round(2.0 * len(sa & sb) / (len(sa) + len(sb)), 4)


class SqliteTMRepository:
    """SQLite backed TM repository implementing TMReader and TMWriter."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._gram_cache: Dict[Tuple[str, int], FrozenSet[str]] = {}
        try:
            self.db = sqlite3.connect(str(self.path))
            self.db.executescript(SCHEMA)
        except sqlite3.DatabaseError as exc:
            raise L10nError(f"{path}: not a usable SQLite translation memory ({exc})")

    def _seg_grams(self, side: str, seg_id: int, text: str) -> FrozenSet[str]:
        ckey = (side, seg_id)
        cached = self._gram_cache.get(ckey)
        if cached is None:
            cached = frozenset(trigrams(text))
            self._gram_cache[ckey] = cached
        return cached

    def __enter__(self) -> "SqliteTMRepository":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    def store_segment(self, seg: TMSegment) -> str:
        """Persist TMSegment honoring approved segment immutability over candidates."""
        if seg.status not in STATUSES:
            raise L10nError(f"unknown TM status '{seg.status}'; known: {', '.join(STATUSES)}")
        norm = normalize(seg.src)
        row = self.db.execute(
            "SELECT id, status, dst FROM segments WHERE locale=? AND key=? AND src_norm=?",
            (seg.locale, seg.key, norm),
        ).fetchone()
        if row is not None:
            return self._update_existing(row, seg)
        cur = self.db.execute(
            "INSERT INTO segments(locale, key, src, dst, category, speaker, register, status, origin, src_norm) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (seg.locale, seg.key, seg.src, seg.dst, seg.category, seg.speaker, seg.register, seg.status, seg.origin, norm),
        )
        seg_id = cur.lastrowid
        s_grams = trigrams(seg.src)
        d_grams = trigrams(seg.dst)
        if seg_id is not None:
            self._gram_cache[("src", int(seg_id))] = frozenset(s_grams)
            self._gram_cache[("dst", int(seg_id))] = frozenset(d_grams)
        grams = [("s:" + g, seg_id) for g in s_grams] + [("d:" + g, seg_id) for g in d_grams]
        self.db.executemany("INSERT INTO grams(gram, seg_id) VALUES (?, ?)", grams)
        return "inserted"

    def _update_existing(self, row: Tuple[int, str, str], seg: TMSegment) -> str:
        seg_id, old_status, old_dst = row
        if old_status == "approved" and seg.status == "candidate":
            return "kept"
        self.db.execute(
            "UPDATE segments SET src=?, dst=?, category=?, speaker=?, register=?, status=?, origin=? WHERE id=?",
            (seg.src, seg.dst, seg.category, seg.speaker, seg.register, seg.status, seg.origin, seg_id),
        )
        d_grams = trigrams(seg.dst)
        self._gram_cache[("src", int(seg_id))] = frozenset(trigrams(seg.src))
        self._gram_cache[("dst", int(seg_id))] = frozenset(d_grams)
        self.db.execute("DELETE FROM grams WHERE seg_id=? AND gram LIKE 'd:%'", (seg_id,))
        self.db.executemany("INSERT INTO grams(gram, seg_id) VALUES (?, ?)", [("d:" + g, seg_id) for g in d_grams])
        return "updated" if (old_dst != seg.dst or old_status != seg.status) else "kept"

    def add(self, locale: str, key: str, src: str, dst: str, **kw: Any) -> str:
        """Legacy keyword compatible wrapper around store_segment(TMSegment)."""
        bad = set(kw) - _ADD_KW
        if bad:
            raise TypeError(f"unexpected TM.add keyword(s): {', '.join(sorted(bad))}")
        return self.store_segment(TMSegment(
            locale=locale, key=key, src=src, dst=dst,
            category=str(kw.get("category", "")), speaker=str(kw.get("speaker", "")),
            register=str(kw.get("register", "")), status=str(kw.get("status", "candidate")),
            origin=str(kw.get("origin", "")),
        ))

    def query_neighbors(self, query: TMQuery) -> List[Dict[str, Any]]:
        """Retrieve closest segments matching TMQuery sorted by category/speaker tier then Dice score."""
        if query.on not in ("src", "dst"):
            raise L10nError("neighbors(on=...) must be 'src' or 'dst'")
        prefix = "s:" if query.on == "src" else "d:"
        grams = trigrams(query.text)
        if not grams:
            return []
        qgrams = grams[:MAX_QUERY_GRAMS]
        qmarks, smarks = ",".join("?" * len(qgrams)), ",".join("?" * len(query.statuses))
        rows = self.db.execute(
            f"SELECT s.id, s.key, s.src, s.dst, s.category, s.speaker, s.status, COUNT(*) AS shared FROM grams g "
            f"JOIN segments s ON s.id = g.seg_id WHERE g.gram IN ({qmarks}) AND s.locale=? AND s.status IN ({smarks}) "
            f"GROUP BY s.id ORDER BY shared DESC, s.key ASC LIMIT ?",
            [prefix + g for g in qgrams] + [query.locale] + list(query.statuses) + [CANDIDATE_POOL],
        ).fetchall()
        scored = self._score_candidates(rows, grams, query)
        scored.sort(key=lambda t: t[:4])
        return [t[4] for t in scored[: query.k]]

    def _score_candidates(self, rows: Sequence[Tuple[Any, ...]], grams: Sequence[str], query: TMQuery) -> List[Tuple[Any, ...]]:
        scored: List[Tuple[Any, ...]] = []
        qset = frozenset(grams)
        if not qset:
            return scored
        qlen = len(qset)
        for seg_id, key, src, dst, cat, spk, status, _shared in rows:
            if query.exclude_key is not None and key == query.exclude_key:
                continue
            cset = self._seg_grams(query.on, int(seg_id), src if query.on == "src" else dst)
            if not cset:
                continue
            sim = round(2.0 * len(qset & cset) / (qlen + len(cset)), 4)
            if sim < query.min_similarity:
                continue
            if query.category and cat == query.category and query.speaker and spk == query.speaker:
                tier, match = 0, "category+speaker"
            elif query.category and cat == query.category:
                tier, match = 1, "category"
            else:
                tier, match = 2, "any"
            scored.append((tier, -sim, key, seg_id, {
                "key": key, "src": src, "dst": dst, "category": cat, "speaker": spk,
                "status": status, "similarity": sim, "match": match,
            }))
        return scored

    def exact_approved(self, locale: str, src: str, *, category: str = "", speaker: str = "") -> Optional[Dict[str, Any]]:
        """Return an unambiguous context compatible approved TM match for src, else None."""
        norm = normalize(src)
        if not norm:
            return None
        rows = self.db.execute(
            "SELECT key, src, dst, category, speaker, status FROM segments "
            "WHERE locale=? AND src_norm=? AND status='approved' ORDER BY id ASC",
            (locale, norm),
        ).fetchall()
        exact_ctx = [r for r in rows if r[3] == category and r[4] == speaker]
        pool = exact_ctx if exact_ctx else [
            r for r in rows if (not category or r[3] == category) and (not speaker or r[4] == speaker)
        ]
        if not pool or len({r[2] for r in pool}) != 1:
            return None
        key, rsrc, dst, cat, spk, status = pool[0]
        return {
            "key": key, "src": rsrc, "dst": dst, "category": cat,
            "speaker": spk, "status": status, "similarity": 1.0, "match": "exact",
        }

    def neighbors(self, locale: str, text: str, **kw: Any) -> List[Dict[str, Any]]:
        """Legacy keyword compatible wrapper around query_neighbors(TMQuery)."""
        bad = set(kw) - _NEIGHBOR_KW
        if bad:
            raise TypeError(f"unexpected TM.neighbors keyword(s): {', '.join(sorted(bad))}")
        return self.query_neighbors(TMQuery(
            locale=locale, text=text,
            on=str(kw.get("on", "src")), category=str(kw.get("category", "")),
            speaker=str(kw.get("speaker", "")), k=int(kw.get("k", DEFAULT_TOP)),
            min_similarity=float(kw.get("min_similarity", DEFAULT_MIN_SIMILARITY)),
            exclude_key=kw.get("exclude_key"),
            statuses=tuple(kw.get("statuses", ("approved",))),
        ))

    def stats(self) -> Dict[str, Any]:
        rows = self.db.execute("SELECT locale, status, COUNT(*) FROM segments GROUP BY locale, status ORDER BY locale, status").fetchall()
        out: Dict[str, Dict[str, int]] = {}
        for loc, status, n in rows:
            out.setdefault(loc, {})[status] = n
        return {"segments": sum(n for _l, _s, n in rows), "by_locale": out}


TranslationMemory = SqliteTMRepository
