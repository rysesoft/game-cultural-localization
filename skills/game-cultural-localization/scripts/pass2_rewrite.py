#!/usr/bin/env python3
"""Pass 2 candidate tournament CLI facade delegating to gcl.application.rewrite."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_context_map import ContextPack, load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR, infer_register  # noqa: E402
from gcl.application.rewrite import (  # noqa: E402
    CONTEXT_FIELDS, DEFAULT_STATUSES, TournamentOptions, final_votes, main_issue, run_tournament,
)
from gcl.infrastructure.formats.critique_validator import DefaultCritiqueValidatorAdapter  # noqa: E402
from gcl.infrastructure.persistence.context_views import BlindContextAdapter, WriterContextAdapter  # noqa: E402
from gcl.infrastructure.tokens.parity_adapter import DefaultTokenParityAdapter  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, PLACEHOLDER_STYLES, TAG_STYLES, L10nError, add_common_args, add_input_argument,
    apply_config, emit_report, load_json_data, load_table, normalize_locale, resolve_input, run_main, __version__,
)
from llm_tasks import (  # noqa: E402
    BatchMemo, add_model_args, default_budget_path, make_router, pass2_candidates, pick_candidates, score_entries,
)
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "pass2_rewrite"
_VALIDATOR = DefaultCritiqueValidatorAdapter()
_PARITY = DefaultTokenParityAdapter()


def load_source_table(path: Path, src_field: str, dst_field: Optional[str], key_field: str, locale: str) -> Dict[str, Dict[str, Any]]:
    """Load source and Pass 1 targets keyed by key."""
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
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cat = str(r.meta.get("category") or "")
        out[r.key] = {
            "en": r.src, "target": r.dst, "category": cat,
            "speaker": str(r.meta.get("speaker") or ""),
            "archetype": str(r.meta.get("archetype") or ""),
            "register": str(r.meta.get("register") or "") or infer_register(cat, r.dst, "game"),
        }
    return out


def rewrite_lines(
    verdicts: Sequence[Dict[str, Any]], sources: Dict[str, Dict[str, Any]], locale: str, router: Any, *,
    pass2_system: str, pick_system: str, n: int = 3, seed: int = 1234, ph_style: str = "auto",
    tag_style: str = "auto", statuses: Sequence[str] = DEFAULT_STATUSES, source_file: str = "",
    workers: int = 1, context: Optional[ContextPack] = None, memo: Any = None,
    tiered: bool = False, unanimous_skip_recheck: bool = False,
) -> Dict[str, Any]:
    """Generate Pass 2 candidates, pick blind with J1, validate and recheck."""
    ctx = context if context is not None and context.text else None
    opts = TournamentOptions(
        pass2_system=pass2_system, pick_system=pick_system, n=n, seed=seed,
        ph_style=ph_style, tag_style=tag_style, statuses=tuple(statuses), source_file=source_file, workers=workers,
        writer_context=WriterContextAdapter(ctx) if ctx is not None else None,
        blind_context=BlindContextAdapter(ctx) if ctx is not None else None,
        memo=memo, tiered=tiered, unanimous_skip_recheck=unanimous_skip_recheck,
    )
    return run_tournament(
        verdicts, sources, locale, router, opts, _VALIDATOR, _PARITY,
        pass2_fn=pass2_candidates, pick_fn=pick_candidates, score_fn=score_entries,
    )


def build_systems(locale: str, pack_dir: Path, registers: Sequence[str], *, warmup: bool, seed: int) -> Tuple[str, str]:
    """Return (pass2 system prompt, critic system prompt) with pack warm-up and few-shots."""
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
    ap.add_argument("--src-field", default=None, help="Source column of --source-table (default en, or src_field of --config)")
    ap.add_argument("--dst-field", default=None, help="Target column of --source-table (default: dst_field of --config, else dst, the locale code, target)")
    ap.add_argument("--key-field", default=None, help="Key column of --source-table (default key, or key_field of --config)")
    ap.add_argument("--candidates", type=int, default=3, help="Candidates per line (default 3)")
    ap.add_argument("--statuses", default=",".join(DEFAULT_STATUSES), help=f"Verdict statuses to rewrite (default {','.join(DEFAULT_STATUSES)})")
    ap.add_argument("--placeholder-style", choices=PLACEHOLDER_STYLES, default=None, help="Placeholder syntax for the parity check (default auto, or placeholder_style of --config)")
    ap.add_argument("--tag-style", choices=TAG_STYLES, default=None, help="Rich-text tag syntax for the parity check (default auto, or tag_style of --config)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for warm-up and few-shots (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Leave the warm-up block out of the prompts")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of the candidate order and the warm-up sample (default 1234)")
    ap.add_argument("--workers", type=int, default=4, help="Batches in flight per model, the three J1 pickers run in parallel (default 4, 1 = one call at a time)")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game, with line_notes.json and CONTEXT_MAP.<locale>.md next to it")
    ap.add_argument("--cache", default=None, help="JSON file that keeps every finished batch of candidates and picks, the same command resumes where a stopped run ended")
    ap.add_argument("--tiered", action="store_true", help="Route rewrite_light verdicts to pass2_light with 2 candidates and keep pass2 for stronger statuses")
    ap.add_argument("--skip-unanimous-recheck", action="store_true", help="Skip the J1 recheck when all three blind pickers agreed on the winning candidate")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    apply_config(args, {"context_map": None, "src_field": "en", "dst_field": None, "key_field": "key", "placeholder_style": "auto", "tag_style": "auto"})
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
    res = rewrite_lines(
        doc["verdicts"], sources, locale, router, pass2_system=pass2_system, pick_system=pick_system, n=args.candidates,
        seed=args.seed, ph_style=args.placeholder_style, tag_style=args.tag_style, statuses=statuses,
        source_file=str(doc.get("source_file") or Path(args.source_table).name), workers=args.workers,
        context=load_context(Path(args.context_map), locale) if args.context_map else None,
        memo=BatchMemo(Path(args.cache)) if args.cache else None,
        tiered=args.tiered, unanimous_skip_recheck=args.skip_unanimous_recheck,
    )
    result = {"locale": locale, "source_file": doc.get("source_file"), "verdicts": str(inp), "lines": res["lines"], "critique": res["critique"], "notes": router.notes}
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
    payload = {"tool": TOOL, "version": __version__, "out": str(out), "lines": len(res["lines"]), "invalid": [l["key"] for l in invalid], "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
