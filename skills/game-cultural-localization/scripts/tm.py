#!/usr/bin/env python3
"""SQLite translation memory with character n-gram retrieval (RAG for Pass 1 and jury evidence).

Store
  segments(locale, key, src, dst, category, speaker, register, status, origin)
  status 'approved' (studio reference, developer accepted lines) or 'candidate' (machine output)
  One row per (locale, key, source text). An approved row is never overwritten by a candidate.

Retrieval (neighbours)
  similarity  Dice coefficient of character trigram sets (case-folded, whitespace collapsed)
  tiers       same category and speaker first, then same category, then any row
  result      the 5 closest rows (approved only by default), similarity >= 0.3, the queried key excluded

Flow back: --mode approve reads a change report (report_changes.py) or a list of
{key, en, old, new, decision} and stores the accepted new line, or the kept old line
of a rejected change, as approved.

Usage:
  python tm.py loc_work/reference/tr.csv --db loc_work/tm.sqlite --locale tr-TR --mode add --status approved
  python tm.py pass1_tr-TR_01.json --db loc_work/tm.sqlite --locale tr-TR --mode query --top 5
  python tm.py changes_tr-TR_01.json --db loc_work/tm.sqlite --locale tr-TR --mode approve
  python tm.py --db loc_work/tm.sqlite --mode stats

Exit codes: 0 done, 1 findings (add skipped rows, query rows without neighbours, approve lines
still without a decision), 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data, load_table,
    normalize_locale, run_main, __version__,
)

TOOL = "tm"
STATUSES = ("approved", "candidate")
DEFAULT_TOP = 5
DEFAULT_MIN_SIMILARITY = 0.3
CANDIDATE_POOL = 300
MAX_QUERY_GRAMS = 900
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
    """NFC, case-folded, whitespace collapsed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def trigrams(text: str) -> List[str]:
    """Sorted unique character trigrams of the padded normalized text."""
    t = f"  {normalize(text)} "
    return sorted({t[i:i + 3] for i in range(len(t) - 2)})


def dice(a: Sequence[str], b: Sequence[str]) -> float:
    """Dice coefficient of two gram sets."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return round(2.0 * len(sa & sb) / (len(sa) + len(sb)), 4)


class TranslationMemory:
    """SQLite backed TM. Use as a context manager so the file is closed."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(str(self.path))
            self.db.executescript(SCHEMA)
        except sqlite3.DatabaseError as exc:
            raise L10nError(f"{path}: not a usable SQLite translation memory ({exc})")

    def __enter__(self) -> "TranslationMemory":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    # ------------------------------------------------------------------ #
    def add(self, locale: str, key: str, src: str, dst: str, *, category: str = "", speaker: str = "", register: str = "",
            status: str = "candidate", origin: str = "") -> str:
        """Insert or update one segment. Returns 'inserted', 'updated' or 'kept' (approved row not replaced by a candidate)."""
        if status not in STATUSES:
            raise L10nError(f"unknown TM status '{status}'; known: {', '.join(STATUSES)}")
        norm = normalize(src)
        cur = self.db.execute("SELECT id, status, dst FROM segments WHERE locale=? AND key=? AND src_norm=?", (locale, key, norm))
        row = cur.fetchone()
        if row is not None:
            seg_id, old_status, old_dst = row
            if old_status == "approved" and status == "candidate":
                return "kept"
            self.db.execute("UPDATE segments SET src=?, dst=?, category=?, speaker=?, register=?, status=?, origin=? WHERE id=?",
                            (src, dst, category, speaker, register, status, origin, seg_id))
            self.db.execute("DELETE FROM grams WHERE seg_id=? AND gram LIKE 'd:%'", (seg_id,))
            self.db.executemany("INSERT INTO grams(gram, seg_id) VALUES (?, ?)", [("d:" + g, seg_id) for g in trigrams(dst)])
            return "updated" if (old_dst != dst or old_status != status) else "kept"
        cur = self.db.execute("INSERT INTO segments(locale, key, src, dst, category, speaker, register, status, origin, src_norm) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?)", (locale, key, src, dst, category, speaker, register, status, origin, norm))
        seg_id = cur.lastrowid
        self.db.executemany("INSERT INTO grams(gram, seg_id) VALUES (?, ?)",
                            [("s:" + g, seg_id) for g in trigrams(src)] + [("d:" + g, seg_id) for g in trigrams(dst)])
        return "inserted"

    def neighbors(self, locale: str, text: str, *, on: str = "src", category: str = "", speaker: str = "", k: int = DEFAULT_TOP,
                  min_similarity: float = DEFAULT_MIN_SIMILARITY, exclude_key: Optional[str] = None,
                  statuses: Sequence[str] = ("approved",)) -> List[Dict[str, Any]]:
        """The k closest segments: same category and speaker first, then same category, then any."""
        if on not in ("src", "dst"):
            raise L10nError("neighbors(on=...) must be 'src' or 'dst'")
        prefix = "s:" if on == "src" else "d:"
        grams = trigrams(text)
        if not grams:
            return []
        query = grams[:MAX_QUERY_GRAMS]  # SQLite parameter limit; similarity below still uses every gram
        qmarks = ",".join("?" * len(query))
        smarks = ",".join("?" * len(statuses))
        rows = self.db.execute(
            f"SELECT s.id, s.key, s.src, s.dst, s.category, s.speaker, s.status, COUNT(*) AS shared FROM grams g "
            f"JOIN segments s ON s.id = g.seg_id WHERE g.gram IN ({qmarks}) AND s.locale=? AND s.status IN ({smarks}) "
            f"GROUP BY s.id ORDER BY shared DESC, s.key ASC LIMIT ?",
            [prefix + g for g in query] + [locale] + list(statuses) + [CANDIDATE_POOL]).fetchall()
        scored = []
        for seg_id, key, src, dst, cat, spk, status, _shared in rows:
            if exclude_key is not None and key == exclude_key:
                continue
            sim = dice(grams, trigrams(src if on == "src" else dst))
            if sim < min_similarity:
                continue
            if category and cat == category and speaker and spk == speaker:
                tier, match = 0, "category+speaker"
            elif category and cat == category:
                tier, match = 1, "category"
            else:
                tier, match = 2, "any"
            scored.append((tier, -sim, key, seg_id, {"key": key, "src": src, "dst": dst, "category": cat, "speaker": spk,
                                                     "status": status, "similarity": sim, "match": match}))
        scored.sort(key=lambda t: t[:4])
        return [t[4] for t in scored[:k]]

    def stats(self) -> Dict[str, Any]:
        rows = self.db.execute("SELECT locale, status, COUNT(*) FROM segments GROUP BY locale, status ORDER BY locale, status").fetchall()
        out: Dict[str, Dict[str, int]] = {}
        for loc, status, n in rows:
            out.setdefault(loc, {})[status] = n
        return {"segments": sum(n for _l, _s, n in rows), "by_locale": out}


# --------------------------------------------------------------------------- #
# Table helpers
# --------------------------------------------------------------------------- #

def load_rows(path: Path, locale: str, src_field: str, dst_field: Optional[str], key_field: str, need_target: bool) -> List[Dict[str, Any]]:
    """Rows {key, en, dst, category, speaker, register} of a table; the target column is probed when not given."""
    if need_target:
        candidates = [dst_field] if dst_field else [locale, "dst", "target", locale.split("-")[0]]
        last: Optional[L10nError] = None
        for col in candidates:
            try:
                rows = load_table(path, src_field, col, key_field)
                break
            except L10nError as exc:
                last = exc
        else:
            raise L10nError(f"{path}: no target column (tried {', '.join(str(c) for c in candidates)}), pass --dst-field") from last
    else:
        rows = [type(r)(r.key, r.dst, "", r.meta) for r in load_table(path, src_field, src_field, key_field, target_only=True)]
    return [{"key": r.key, "en": r.src, "dst": r.dst, "category": str(r.meta.get("category") or ""),
             "speaker": str(r.meta.get("speaker") or ""), "register": str(r.meta.get("register") or "")} for r in rows]


def approvals(data: Any) -> List[Dict[str, Any]]:
    """Lines of a change report ({'lines': [...]}, {'changes': [...]}) or a plain list."""
    if isinstance(data, dict):
        for k in ("lines", "changes"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list):
        raise L10nError("approve input must be a change report or a list of {key, en, old, new, decision}")
    return [d for d in data if isinstance(d, dict)]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="SQLite translation memory: add rows, query n-gram neighbours, approve decisions, stats")
    add_input_argument(ap, "Table to add or query, or a change report to approve (not needed for --mode stats)")
    ap.add_argument("--db", required=True, help="SQLite file of the translation memory (created when missing)")
    ap.add_argument("--locale", default=None, help="Target locale (required except for --mode stats)")
    ap.add_argument("--mode", choices=("add", "query", "approve", "stats"), default="query", help="What to do (default query)")
    ap.add_argument("--status", choices=STATUSES, default="candidate", help="Status of added rows (default candidate, use approved for the studio reference)")
    ap.add_argument("--origin", default="", help="Free text origin label stored with added rows")
    ap.add_argument("--src-field", default="en", help="Source column (default en)")
    ap.add_argument("--dst-field", default=None, help="Target column (default: the locale code, then dst, target)")
    ap.add_argument("--key-field", default="key", help="Key column (default key)")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"Neighbours per row (default {DEFAULT_TOP})")
    ap.add_argument("--min-similarity", type=float, default=DEFAULT_MIN_SIMILARITY, help=f"Lowest Dice similarity (default {DEFAULT_MIN_SIMILARITY})")
    ap.add_argument("--include-candidates", action="store_true", help="Query candidate rows too (default approved only)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    pos, opt = getattr(args, "input_pos", None), getattr(args, "input_opt", None)
    if pos and opt and pos != opt:
        ap.error(f"conflicting values for INPUT: positional '{pos}' vs --input '{opt}'")
    args.input = opt or pos
    if args.mode != "stats":
        if not args.input:
            ap.error("the INPUT file is required (positional INPUT or --input) except with --mode stats")
        if not args.locale:
            ap.error("--locale is required except with --mode stats")
    locale = normalize_locale(args.locale)[0] if args.locale else ""
    lines: List[str] = []
    payload: Dict[str, Any] = {"tool": TOOL, "version": __version__, "db": args.db, "mode": args.mode, "locale": locale}
    exit_code = EXIT_OK
    with TranslationMemory(Path(args.db)) as tm:
        if args.mode == "add":
            rows = load_rows(Path(args.input), locale, args.src_field, args.dst_field, args.key_field, need_target=True)
            counts = {"inserted": 0, "updated": 0, "kept": 0, "skipped": 0}
            for r in rows:
                if not r["en"].strip() or not r["dst"].strip():
                    counts["skipped"] += 1
                    continue
                counts[tm.add(locale, r["key"], r["en"], r["dst"], category=r["category"], speaker=r["speaker"], register=r["register"],
                              status=args.status, origin=args.origin or Path(args.input).name)] += 1
            exit_code = EXIT_FINDINGS if counts["skipped"] else EXIT_OK
            lines.append(f"TM add {locale} ({args.status}): {args.input} -> {args.db}")
            lines.append("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))
            payload["counts"] = counts
        elif args.mode == "query":
            rows = load_rows(Path(args.input), locale, args.src_field, None, args.key_field, need_target=False)
            statuses = STATUSES if args.include_candidates else ("approved",)
            results = []
            empty = 0
            for r in rows:
                nb = tm.neighbors(locale, r["en"], category=r["category"], speaker=r["speaker"], k=args.top,
                                  min_similarity=args.min_similarity, exclude_key=r["key"], statuses=statuses)
                empty += 0 if nb else 1
                results.append({"key": r["key"], "en": r["en"], "neighbors": nb})
            exit_code = EXIT_FINDINGS if empty else EXIT_OK
            lines.append(f"TM query {locale}: {len(rows)} rows, {len(rows) - empty} with neighbours, top {args.top}")
            limit = args.max_report if args.max_report is not None else len(results)
            for res in results[:limit]:
                best = res["neighbors"][0] if res["neighbors"] else None
                lines.append(f"  {res['key']}: " + (f"{best['similarity']:.2f} [{best['match']}] {best['dst']}" if best else "no neighbour"))
            payload["results"] = results
            payload["summary"] = {"rows": len(rows), "without_neighbors": empty}
        elif args.mode == "approve":
            items = approvals(load_json_data(Path(args.input)))
            counts = {"accepted": 0, "rejected_kept_old": 0, "undecided": 0, "no_source": 0}  # no_source: no English or no text
            for it in items:
                decision = str(it.get("decision") or "").lower()
                src = str(it.get("en") or it.get("source") or "")
                if decision not in ("accept", "accepted", "reject", "rejected"):
                    counts["undecided"] += 1
                    continue
                if not src.strip():
                    counts["no_source"] += 1
                    continue
                accepted = decision.startswith("accept")
                text = str((it.get("new") if accepted else it.get("old")) or "")
                if not text.strip():
                    counts["no_source"] += 1
                    continue
                tm.add(locale, str(it["key"]), src, text, category=str(it.get("category") or ""), speaker=str(it.get("speaker") or ""),
                       register=str(it.get("register") or ""), status="approved", origin="developer_" + ("accept" if accepted else "reject"))
                counts["accepted" if accepted else "rejected_kept_old"] += 1
            exit_code = EXIT_FINDINGS if (counts["undecided"] or counts["no_source"]) else EXIT_OK
            lines.append(f"TM approve {locale}: {args.input} -> {args.db}")
            lines.append("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))
            payload["counts"] = counts
        st = tm.stats()
        payload["stats"] = st
        if args.mode == "stats":
            lines.append(f"TM {args.db}: {st['segments']} segments")
            for loc, by in st["by_locale"].items():
                lines.append(f"  {loc}: " + ", ".join(f"{k} {v}" for k, v in by.items()))
    lines.append(f"  Exit code: {exit_code}")
    payload["exit_code"] = exit_code
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
