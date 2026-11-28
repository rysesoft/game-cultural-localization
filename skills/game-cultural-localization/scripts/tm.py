#!/usr/bin/env python3
"""SQLite translation memory CLI facade delegating storage to gcl.infrastructure.persistence.sqlite_tm."""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.infrastructure.persistence.sqlite_tm import (  # noqa: E402
    CANDIDATE_POOL, DEFAULT_MIN_SIMILARITY, DEFAULT_TOP, MAX_QUERY_GRAMS, SCHEMA, STATUSES,
    TranslationMemory, dice, normalize, trigrams,
)
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data, load_table,
    normalize_locale, run_main, __version__,
)

TOOL = "tm"


def load_rows(path: Path, locale: str, src_field: str, dst_field: str | None, key_field: str, need_target: bool) -> list[dict[str, Any]]:
    """Load table rows with fallback target column probing."""
    if need_target:
        candidates = [dst_field] if dst_field else [locale, "dst", "target", locale.split("-")[0]]
        last: L10nError | None = None
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
    return [
        {
            "key": r.key, "en": r.src, "dst": r.dst,
            "category": str(r.meta.get("category") or ""),
            "speaker": str(r.meta.get("speaker") or ""),
            "register": str(r.meta.get("register") or ""),
        }
        for r in rows
    ]


def approvals(data: Any) -> list[dict[str, Any]]:
    """Extract decision records from a change report or list payload."""
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
    lines: list[str] = []
    payload: dict[str, Any] = {"tool": TOOL, "version": __version__, "db": args.db, "mode": args.mode, "locale": locale}
    exit_code = EXIT_OK
    with TranslationMemory(Path(args.db)) as tm:
        if args.mode == "add":
            rows = load_rows(Path(args.input), locale, args.src_field, args.dst_field, args.key_field, need_target=True)
            counts = {"inserted": 0, "updated": 0, "kept": 0, "skipped": 0}
            for r in rows:
                if not r["en"].strip() or not r["dst"].strip():
                    counts["skipped"] += 1
                    continue
                res = tm.add(locale, r["key"], r["en"], r["dst"], category=r["category"], speaker=r["speaker"], register=r["register"],
                             status=args.status, origin=args.origin or Path(args.input).name)
                counts[res] += 1
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
            counts = {"accepted": 0, "rejected_kept_old": 0, "undecided": 0, "no_source": 0}
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
