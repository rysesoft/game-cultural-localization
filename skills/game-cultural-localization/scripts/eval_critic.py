#!/usr/bin/env python3
"""Calibrate jury members against the contrastive set CLI facade."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_context_map import ContextPack, load_context  # noqa: E402
from build_language_pack import LANGPACK_DIR  # noqa: E402
from gcl.application.evaluation import (  # noqa: E402
    DEFAULT_SEED, DEFAULT_SHOTS, NATIVE_MEAN_MIN, PAIRWISE_MIN, ROBOT_MEAN_MAX, SHORT_WORDS, CriticEvalOptions,
    build_items, is_short, mixed_robot, run_critic_evaluation, split_shots, weighted_kappa,
)
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, apply_config, emit_report,
    load_json_data, normalize_locale, resolve_input, run_main, __version__,
)
from llm_tasks import BatchMemo, add_model_args, default_budget_path, make_router, pairwise_choices, score_entries  # noqa: E402
from prompt_templates import render_contrastive, render_prompt  # noqa: E402
from warmup_loader import REGISTERS, load_warmup, render_warmup  # noqa: E402

TOOL = "eval_critic"


def load_pairs(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read contrastive.json and validate its pairs."""
    data = load_json_data(path)
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        raise L10nError(f"{path}: contrastive set must be an object with a 'pairs' list")
    pairs = [
        p for i, p in enumerate(data["pairs"])
        if isinstance(p, dict) and all(isinstance(p.get(k), str) and p.get(k) for k in ("key", "native", "robot"))
    ]
    if len(pairs) != len(data["pairs"]):
        raise L10nError(f"{path}: every pair needs non-empty key, native and robot strings")
    if not pairs:
        raise L10nError(f"{path}: the contrastive set has no pairs")
    return data, sorted(pairs, key=lambda p: p["key"])


def evaluate(
    router: Any, locale: str, tiers: Sequence[str], pairs: Sequence[dict[str, Any]], shots_pairs: Sequence[dict[str, Any]],
    *, warmup: bool, pack_dir: Path | None, seed: int, warmup_count: int, pairwise_min: float,
    langpack_version: str | None, workers: int = 1, store: Path | None = None,
    context: ContextPack | None = None, include_unknown: bool = False,
) -> dict[str, Any]:
    """Run critic calibration via gcl.application.evaluation keeping full compatibility."""
    regs = sorted({p.get("register") for p in pairs if p.get("register") in REGISTERS}) or list(REGISTERS)
    warm_text = ""
    if warmup and pack_dir is not None and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
        warm_text = render_warmup(load_warmup(pack_dir, regs, warmup_count, seed))
    system = render_prompt("critic", locale, warmup=warm_text, contrastive=render_contrastive(shots_pairs, count=len(shots_pairs), seed=seed))
    if context is not None and context.text:
        system = context.system(system)
    memo = BatchMemo(Path(store).with_name(Path(store).stem + ".batches.json")) if store is not None else None
    opts = CriticEvalOptions(
        pairs=pairs, shots_pairs=shots_pairs, warmup=warmup, seed=seed, pairwise_min=pairwise_min,
        langpack_version=langpack_version, system_prompt=system,
        warmup_lines=sum(1 for l in warm_text.splitlines() if l.startswith("- ")),
        workers=workers, store=store, memo=memo, context=context, include_unknown=include_unknown,
        pairwise_fn=pairwise_choices, score_fn=score_entries,
    )
    return run_critic_evaluation(router, locale, tiers, opts)


def _member_lines(rep: dict[str, Any]) -> list[str]:
    out = []
    for m in rep["members"]:
        mark = "ok " if m["pairwise_accuracy"] >= rep["gate"]["pairwise_min"] else "LOW"
        tail = (
            f"  short {m['pairwise_short']:.2f} long {m['pairwise_long']:.2f}"
            if m.get("pairwise_short") is not None and m.get("pairwise_long") is not None else ""
        )
        out.append(f"  {mark} {m['tier']} {m['model']:<20} pairwise {m['pairwise_accuracy']:.2f}  native {m['native_mean']}  "
                   f"robot {m['robot_mean']}  unknown {m['unknown_mean']}  n {m['n']}{tail}")
    out.append(f"  kappa inter-family {rep['inter_family_kappa']}, intra-family {rep['intra_family_kappa']}")
    return out


def _update_trust_card(pack_dir: Path, report: dict[str, Any], evald: Sequence[dict[str, Any]], dropped: Sequence[dict[str, Any]], version: str | None, input_name: str) -> None:
    card = pack_dir / "trust_card.json"
    if not card.is_file():
        raise L10nError(f"{card} not found; build the pack first")
    trust = load_json_data(card)
    main_rep = report.get("with_warmup", report)
    trust["calibration"] = {
        "gate": main_rep["gate"], "secondary": main_rep["secondary"], "pairs": len(evald),
        "members": [{k: m.get(k) for k in ("tier", "model", "pairwise_accuracy", "pairwise_short", "pairwise_long", "native_mean", "robot_mean")}
                    for m in main_rep["members"]],
        "dropped_mixed_robots": len(dropped), "short_pairs": sum(1 for p in evald if is_short(p)),
        "inter_family_kappa": main_rep["inter_family_kappa"], "intra_family_kappa": main_rep["intra_family_kappa"],
        "langpack_version": version, "source": input_name,
        "context_map": main_rep.get("context_map"), "context_lines": main_rep.get("context_lines", 0),
    }
    card.write_text(json.dumps(trust, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Calibrate jury members on the contrastive set (pairwise gate 0.85, absolute means, kappa)")
    add_input_argument(ap, "contrastive.json of the locale")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--tiers", default="J1,J2,J3", help="Comma separated jury tiers to evaluate (default J1,J2,J3)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for the warm-up sample (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Evaluate without the warm-up block")
    ap.add_argument("--compare-warmup", action="store_true", help="Run with and without warm-up and report both plus the difference")
    ap.add_argument("--warmup-count", type=int, default=40, help="Warm-up lines in the prompt (default 40)")
    ap.add_argument("--shots", type=int, default=DEFAULT_SHOTS, help=f"Contrastive few-shot pairs held out of the evaluation (default {DEFAULT_SHOTS})")
    ap.add_argument("--limit", type=int, default=0, help="Evaluate a seeded subset of N pairs (default: all)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed for side order, subsets and warm-up (default {DEFAULT_SEED})")
    ap.add_argument("--pairwise-min", type=float, default=PAIRWISE_MIN, help=f"Pairwise accuracy gate (default {PAIRWISE_MIN})")
    ap.add_argument("--update-trust-card", action="store_true", help="Store the result in langpack/<locale>/trust_card.json under 'calibration'")
    ap.add_argument("--workers", type=int, default=4, help="Batches in flight per model, models run in parallel when above 1 (default 4, 1 = one call at a time)")
    ap.add_argument("--cache", default=None, help="JSON file that keeps every finished model; a rerun with the same pairs, seed and prompt only calls the missing models")
    ap.add_argument("--keep-mixed-robots", action="store_true", help="Keep pairs whose literal line left English words untranslated (dropped by default, any reader spots them)")
    ap.add_argument("--include-unknown", action="store_true", help="Also score raw unknown strong model lines (skipped by default to save calibration calls)")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game, its line_notes.json next to it gives every pair its context")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    args = (ap := build_parser()).parse_args()
    resolve_input(ap, args)
    apply_config(args, {"context_map": None})
    locale, _v = normalize_locale(args.locale)
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
    if any(t not in ("J1", "J2", "J3") for t in tiers):
        raise L10nError(f"unknown tier in '{args.tiers}'; known: J1, J2, J3")
    if args.workers < 1:
        raise L10nError("--workers must be 1 or more")
    _data, pairs = load_pairs(Path(args.input))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    version = load_json_data(pack_dir / "manifest.json").get("langpack_version") if (pack_dir / "manifest.json").is_file() else None
    shots, evald = split_shots(pairs, args.shots, args.limit, args.seed)
    dropped = [] if args.keep_mixed_robots else [p for p in evald if mixed_robot(p)]
    evald = [p for p in evald if p not in dropped]
    if not evald:
        raise L10nError("every evaluated pair has a literal line with untranslated English words, pass --keep-mixed-robots for dry-run")
    router = make_router(args, tiers, default_budget_path(Path(args.input)))
    kw = {
        "pack_dir": pack_dir, "seed": args.seed, "warmup_count": args.warmup_count, "pairwise_min": args.pairwise_min,
        "langpack_version": version, "workers": args.workers, "store": Path(args.cache) if args.cache else None,
        "context": load_context(Path(args.context_map), locale) if args.context_map else None, "include_unknown": args.include_unknown,
    }
    if args.compare_warmup:
        with_w = evaluate(router, locale, tiers, evald, shots, warmup=True, **kw)
        without_w = evaluate(router, locale, tiers, evald, shots, warmup=False, **kw)
        delta = {f"{m['tier']}:{m['model']}": round(m["pairwise_accuracy"] - n["pairwise_accuracy"], 4) for m, n in zip(with_w["members"], without_w["members"])}
        report = {"locale": locale, "langpack_version": version, "with_warmup": with_w, "without_warmup": without_w, "delta_pairwise": delta, "gate": with_w["gate"]}
        lines = [f"Critic calibration {locale}: {len(evald)} pairs, {len(shots)} held out as few-shots, warm-up compared",
                 "  with warm-up" if with_w["warmup"] else "  with warm-up (pack has no warm-up file, same as without)"] + _member_lines(with_w) + ["  without warm-up"] + _member_lines(without_w)
        lines.append("  pairwise delta (with - without) " + ", ".join(f"{k} {v:+.2f}" for k, v in delta.items()))
        gate = with_w["gate"]
    else:
        report = evaluate(router, locale, tiers, evald, shots, warmup=not args.no_warmup, **kw)
        lines = [f"Critic calibration {locale}: {len(evald)} pairs, {len(shots)} held out as few-shots, warm-up {'on' if report['warmup'] else 'off'}" + (f", {len(dropped)} pairs with an untranslated literal line left out" if dropped else "")] + _member_lines(report)
        gate = report["gate"]
    if args.update_trust_card:
        _update_trust_card(pack_dir, report, evald, dropped, version, Path(args.input).name)
    exit_code = EXIT_OK if gate["passed"] else EXIT_FINDINGS
    main_rep = report.get("with_warmup", report)
    if main_rep.get("context_map"):
        lines.append(f"  context map {main_rep['context_map']}, {main_rep['context_lines']} of {len(evald)} pairs with line context")
    lines += [f"  Gate pairwise >= {gate['pairwise_min']} {'PASSED' if gate['passed'] else 'FAILED'}"] + [f"  NOTE: {n}" for n in router.notes] + [f"  Exit code: {exit_code}"]
    emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, **report, "dropped_mixed_robots": [p["key"] for p in dropped], "notes": router.notes, "exit_code": exit_code}, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
