#!/usr/bin/env python3
"""Pass 2 with several candidates: the pass2 model writes three versions, the J1 jury picks one blind.

For every verdict that needs work (rewrite_light, rewrite, critical, and unresolved as a proposal)
  1. the 'pass2' model (prompts/pass2.<locale>.md) gets the English source, the current line, the
     context, the jury rationales and suggestions and the approved TM neighbours, and writes 3 candidates
  2. the three J1 members see only the candidates (seeded order, ids c1..c3) and the context, never the
     source, and each picks the most natural one. Most picks wins, a tie goes to the earlier candidate
  3. the winner is checked with validate_critique (critique schema, placeholder and tag parity with
     the current line). When it fails the next candidate by votes is tried. When none passes, the old
     line stays and the line is flagged

Output rewrites_<locale>_<batch>.json
  {"locale", "source_file", "lines": [{key, en, old, new, status, candidates, picks, chosen, valid, problems}],
   "critique": {fixed critique schema document of the selected lines}}

Usage:
  python pass2_rewrite.py verdicts_tr-TR_01.json --source-table pass1_tr-TR_01.json --locale tr-TR [--dry-run]

Exit codes: 0 every flagged line has a validated rewrite, 1 some lines kept their old text
(no valid candidate), 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, TAG_STYLES, L10nError, add_common_args, add_input_argument, emit_report,
    load_json_data, load_table, normalize_locale, resolve_input, run_main, __version__,
)
import validate_critique  # noqa: E402
from build_language_pack import LANGPACK_DIR, infer_register  # noqa: E402
from llm_tasks import ISSUE_TYPES, add_model_args, default_budget_path, make_router, pass2_candidates, pick_candidates  # noqa: E402
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from text_style import sanitize_prose  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "pass2_rewrite"
DEFAULT_STATUSES = ("rewrite_light", "rewrite", "critical", "unresolved")
CONTEXT_FIELDS = ("register", "category", "speaker", "archetype")


def load_source_table(path: Path, src_field: str, dst_field: Optional[str], key_field: str, locale: str) -> Dict[str, Dict[str, Any]]:
    """key -> {en, target, register, category, speaker, archetype} from the Pass 1 table."""
    candidates = [dst_field] if dst_field else ["dst", locale, "target"]
    last: Optional[L10nError] = None
    for col in candidates:
        try:
            rows = load_table(path, src_field, col, key_field)
            break
        except L10nError as exc:
            last = exc
    else:
        raise L10nError(f"{path}: no target column (tried {', '.join(str(c) for c in candidates)}), pass --dst-field") from last
    out = {}
    for r in rows:
        cat = str(r.meta.get("category") or "")
        out[r.key] = {"en": r.src, "target": r.dst, "category": cat, "speaker": str(r.meta.get("speaker") or ""),
                      "archetype": str(r.meta.get("archetype") or ""),
                      "register": str(r.meta.get("register") or "") or infer_register(cat, r.dst, "game")}
    return out


def final_votes(verdict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Votes of the tier that settled the line."""
    tier = verdict.get("final_tier")
    return [v for v in verdict.get("votes", []) if v.get("tier") == tier]


def main_issue(verdict: Dict[str, Any]) -> str:
    """Most common non-'none' issue type of the settling votes (critique schema value)."""
    types = [v.get("issue_type") for v in final_votes(verdict) if v.get("issue_type") not in (None, "none")]
    it = Counter(types).most_common(1)[0][0] if types else "other"
    return it if it in ISSUE_TYPES and it != "none" else "other"


def rewrite_lines(verdicts: Sequence[Dict[str, Any]], sources: Dict[str, Dict[str, Any]], locale: str, router: Any, *,
                  pass2_system: str, pick_system: str, n: int = 3, seed: int = 1234, ph_style: str = "auto",
                  tag_style: str = "auto", statuses: Sequence[str] = DEFAULT_STATUSES, source_file: str = "",
                  workers: int = 1) -> Dict[str, Any]:
    """Generate, pick blind, validate. Returns {'lines', 'critique'}.

    workers > 1 sends up to `workers` batches at once and lets the three J1 pickers run side by side.
    """
    todo = [v for v in verdicts if v.get("status") in statuses]
    missing = [v["key"] for v in todo if v["key"] not in sources]
    if missing:
        raise L10nError(f"keys missing from the source table: {', '.join(missing[:5])}")
    rows = []
    for v in todo:
        s = sources[v["key"]]
        fv = final_votes(v)
        rows.append({"key": v["key"], "source": s["en"], "target": s["target"], **{k: s[k] for k in CONTEXT_FIELDS if s.get(k)},
                     "rationales": [r for r in v.get("rationales", []) if r],
                     "suggestions": [x.get("suggested") for x in fv if x.get("suggested")],
                     "suggested": next((x.get("suggested") for x in fv if x.get("suggested")), ""),
                     "tm": [{"target": t.get("dst", ""), "category": t.get("category", "")} for t in (v.get("evidence", {}).get("tm_neighbors") or [])[:3]]})
    cands = pass2_candidates(router.for_role("pass2"), rows, locale, n=n, system=pass2_system, workers=workers) if rows else {}
    rng = random.Random(seed)
    items: List[Dict[str, Any]] = []
    id_maps: Dict[str, Dict[str, int]] = {}
    for r in rows:
        texts = cands[r["key"]]
        order = list(range(len(texts)))
        rng.shuffle(order)
        id_maps[r["key"]] = {f"c{i + 1}": idx for i, idx in enumerate(order)}
        items.append({"key": r["key"], **{k: r[k] for k in CONTEXT_FIELDS if r.get(k)},
                      "candidates": [{"id": f"c{i + 1}", "text": texts[idx]} for i, idx in enumerate(order)]})
    picks_by_member: List[Tuple[Any, Dict[str, str]]] = []
    if items:
        pickers = router.jury("J1")

        def pick(m: Any) -> Dict[str, str]:
            return pick_candidates(m.provider, items, locale, system=pick_system, workers=workers)
        if int(workers) > 1 and len(pickers) > 1:
            with ThreadPoolExecutor(max_workers=len(pickers)) as ex:
                picks_by_member = list(zip(pickers, ex.map(pick, pickers)))
        else:
            picks_by_member = [(m, pick(m)) for m in pickers]
    lines: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    for v, r in zip(todo, rows):
        key = r["key"]
        texts = cands[key]
        id_map = id_maps[key]
        votes = Counter(id_map[p[key]] for _m, p in picks_by_member)
        ranking = sorted(range(len(texts)), key=lambda i: (-votes.get(i, 0), i))
        chosen, problems_all, entry = None, [], None
        for idx in ranking:
            e = {"key": key, "score": min(int(v.get("score", 4)), 4), "issue_type": main_issue(v),
                 "reason": sanitize_prose((v.get("rationales") or ["jury flagged the line"])[0] or "jury flagged the line") or "jury flagged the line",
                 "suggested": texts[idx]}
            doc = {"locale": locale, "source_file": source_file, "entries": [e],
                   "summary": {"total": 1, "flagged": 1, "critical": 1 if e["score"] <= 2 else 0}}
            problems = validate_critique.validate(doc, {key: r["target"]}, ph_style, tag_style, locale)
            if not problems:
                chosen, entry = idx, e
                break
            problems_all.extend(f"{texts[idx]!r}: {p}" for p in problems)
        if entry is not None:
            entries.append(entry)
        lines.append({"key": key, "en": r["source"], "old": r["target"], "new": texts[chosen] if chosen is not None else r["target"],
                      "status": v.get("status"), "final_tier": v.get("final_tier"), "score": v.get("score"),
                      "candidates": texts, "picks": {f"{m.family}:{m.provider.model}": texts[id_map[p[key]]] for m, p in picks_by_member},
                      "votes_per_candidate": [votes.get(i, 0) for i in range(len(texts))],
                      "chosen": chosen, "valid": chosen is not None, "problems": problems_all,
                      "selected_by": "J1 blind pick"})
    critique = {"locale": locale, "source_file": source_file, "entries": entries,
                "summary": {"total": len(verdicts), "flagged": len(entries), "critical": sum(1 for e in entries if e["score"] <= 2)}}
    return {"lines": lines, "critique": critique}


def build_systems(locale: str, pack_dir: Path, registers: Sequence[str], *, warmup: bool, seed: int) -> Tuple[str, str]:
    """(pass2 prompt, critic prompt) with the pack's warm-up and contrastive few-shots."""
    warm, contrast = "", ""
    if pack_dir.is_dir():
        if warmup and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
            warm = render_warmup(load_warmup(pack_dir, list(registers) or list(REGISTERS), 40, seed))
        cfile = pack_dir / "contrastive.json"
        if cfile.is_file():
            data = load_json_data(cfile)
            contrast = render_contrastive(data.get("pairs", []) if isinstance(data, dict) else [], count=6, seed=seed)
    return (render_prompt("pass2", locale, warmup=warm, contrastive=contrast),
            render_prompt("critic", locale, warmup=warm, contrastive=contrast))


def default_out(inp: Path) -> Path:
    m = re.match(r"verdicts_(.+)\.json$", inp.name)
    return inp.with_name(f"rewrites_{m.group(1)}.json") if m else inp.with_name(inp.stem + ".rewrites.json")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Pass 2 with three candidates, blind J1 pick and validate_critique check")
    add_input_argument(ap, "Verdict file written by jury.py")
    ap.add_argument("--source-table", required=True, help="Pass 1 table with key, English source and current target")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--out", default=None, help="Rewrite file (default: rewrites_<locale>_<batch>.json next to the verdicts)")
    ap.add_argument("--critique-out", default=None, help="Also write the selected lines as a critique file (fixed critique schema)")
    ap.add_argument("--src-field", default="en", help="Source column of --source-table (default en)")
    ap.add_argument("--dst-field", default=None, help="Target column of --source-table (default: dst, the locale code, target)")
    ap.add_argument("--key-field", default="key", help="Key column of --source-table (default key)")
    ap.add_argument("--candidates", type=int, default=3, help="Candidates per line (default 3)")
    ap.add_argument("--statuses", default=",".join(DEFAULT_STATUSES), help=f"Verdict statuses to rewrite (default {','.join(DEFAULT_STATUSES)})")
    ap.add_argument("--placeholder-style", choices=PLACEHOLDER_STYLES, default="auto", help="Placeholder syntax for the parity check (default auto)")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default="auto", help="Rich-text tag syntax for the parity check (default auto)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for warm-up and few-shots (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Leave the warm-up block out of the prompts")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of the candidate order and the warm-up sample (default 1234)")
    ap.add_argument("--workers", type=int, default=4, help="Batches in flight per model, the three J1 pickers run in parallel (default 4, 1 = one call at a time)")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    if not 1 <= args.candidates <= 6:
        raise L10nError("--candidates must be between 1 and 6")
    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    for s in statuses:
        if s not in ("pass",) + DEFAULT_STATUSES:
            raise L10nError(f"unknown status '{s}'")
    inp = Path(args.input)
    doc = load_json_data(inp)
    if not isinstance(doc, dict) or not isinstance(doc.get("verdicts"), list):
        raise L10nError(f"{inp}: not a jury verdict file (no 'verdicts' list)")
    sources = load_source_table(Path(args.source_table), args.src_field, args.dst_field, args.key_field, locale)
    out = Path(args.out) if args.out else default_out(inp)
    router = make_router(args, ["pass2", "J1"], default_budget_path(out))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    regs = sorted({sources[v["key"]]["register"] for v in doc["verdicts"] if v.get("key") in sources and v.get("status") in statuses})
    pass2_system, pick_system = build_systems(locale, pack_dir, regs, warmup=not args.no_warmup, seed=args.seed)
    res = rewrite_lines(doc["verdicts"], sources, locale, router, pass2_system=pass2_system, pick_system=pick_system, n=args.candidates,
                        seed=args.seed, ph_style=args.placeholder_style, tag_style=args.tag_style, statuses=statuses,
                        source_file=str(doc.get("source_file") or Path(args.source_table).name), workers=args.workers)
    result = {"locale": locale, "source_file": doc.get("source_file"), "verdicts": str(inp), "lines": res["lines"], "critique": res["critique"],
              "notes": router.notes}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.critique_out:
        Path(args.critique_out).write_text(json.dumps(res["critique"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    invalid = [l for l in res["lines"] if not l["valid"]]
    exit_code = EXIT_FINDINGS if invalid else EXIT_OK
    lines = [f"Pass 2 {locale}: {len(res['lines'])} lines rewritten with {args.candidates} candidates each -> {out}"]
    limit = args.max_report if args.max_report is not None else len(res["lines"])
    for l in res["lines"][:limit]:
        mark = "ok " if l["valid"] else "KEPT OLD"
        lines.append(f"  {mark} {l['key']} [{l['status']}] {l['old']!r} -> {l['new']!r} votes {l['votes_per_candidate']}")
    if invalid:
        lines.append(f"  {len(invalid)} line(s) without a valid candidate kept their old text")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "out": str(out), "lines": len(res["lines"]), "invalid": [l["key"] for l in invalid],
               "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
