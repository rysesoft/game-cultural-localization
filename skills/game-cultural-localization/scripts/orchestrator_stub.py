#!/usr/bin/env python3
"""API-independent orchestration CLI facade delegating to gcl.application.pipeline & gcl.composition."""

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.pipeline import (  # noqa: E402
    ARCHETYPES, RESUME_FILE, JuryPipelineOptions, LocalizationPipelineBuilder, PipelineHooks, PipelineState,
    send_broken_lines_to_pass2 as _send_broken_lines,
)
from gcl.composition.legacy_pipeline import (  # noqa: E402
    CONTAINER as _CONTAINER, CallableProvider, DryRunProvider, LegacyCallbacks, LegacyPipelineOptions, Provider,
    load_agent_prompt, load_playbook, phase0_preflight, phase1_pass1, run_legacy_pipeline, run_phase3_gate,
    strip_frontmatter, system_prompt,
)
from gcl.composition.orchestrator_wiring import OrchestratorCallbacks, build_orchestrator_hooks  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, Row, add_common_args, add_input_argument, emit_report, load_config,
    load_table, normalize_locale, pick, resolve_input, run_main, SCRIPTS_DIR, __version__,
)
import make_blind_slice  # noqa: E402
import validate_critique  # noqa: E402

TOOL = "orchestrator_stub"


def _gate_batch_worker(spec_json: str) -> str:
    """Run LQA lint and UI expansion checks on one batch file inside a subinterpreter."""
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    spec = _json.loads(spec_json)
    if spec["scripts_dir"] not in _sys.path:
        _sys.path.insert(0, spec["scripts_dir"])
    import l10n_common as _lc
    import lqa_linter as _lint
    import ui_expansion_checker as _ui

    final_path, locale = _Path(spec["final_str"]), spec["locale"]
    rows = _lc.load_table(final_path, spec["src_field"], locale, spec["key_field"])
    rules = _lint.load_rules(locale)
    findings = _lint.lint_rows(rows, rules, _lint.LintOptions(
        locale=locale, placeholder_style=spec["ph_style"], tag_style=spec["tag_style"],
        forbid_chars=spec["forbid_chars"], forbid_spaced_hyphen=spec["forbid_spaced_hyphen"],
        strict_whitespace=spec["strict_whitespace"],
    ))
    risks = _ui.check_rows(rows, _ui.CheckOptions(locale=locale, factor=_ui.EXPANSION_FACTORS[locale], tag_style=spec["tag_style"]))
    out_path = _Path(spec["workdir_str"]) / f"lqa_{locale}_{final_path.stem[-2:]}.json"
    out_path.write_text(_json.dumps(
        {"findings": [x.as_dict() for x in findings], "risks": [r.as_dict() for r in risks]},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    return _json.dumps({
        "errors": sum(1 for x in findings if x.severity == "ERR"),
        "warnings": sum(1 for x in findings if x.severity == "WARN"),
        "high": sum(1 for r in risks if r.level == "HIGH"),
        "warn": sum(1 for r in risks if r.level == "WARN"),
    })


def phase3_gate(state: PipelineState, finals: list[Path], fonts: list[Path]) -> dict[str, Any]:
    """Run Phase 3 LQA/UI subinterpreter checks and in-process font glyph scan."""
    return run_phase3_gate(state, finals, fonts, _gate_batch_worker)


def run_pipeline(
    input_path: Path, locale: str, workdir: Path, provider: Provider, *, src_field: str = "en", dst_field: str = "dst",
    key_field: str = "key", ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50,
    fonts: list[Path] | None = None, gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run legacy Phase 0-3 flow via gcl.composition.legacy_pipeline."""
    opts = LegacyPipelineOptions(src_field, dst_field, key_field, ph_style, tag_style, batch_size, fonts or (), gate)
    cb = LegacyCallbacks(make_blind_slice.build_slice, make_blind_slice.verify_no_leak, make_blind_slice.write_slice, validate_critique.validate, _gate_batch_worker)
    return run_legacy_pipeline(input_path, locale, workdir, provider, opts, cb)


def send_broken_lines_to_pass2(res: dict[str, Any], targets: dict[str, str], sources: dict[str, str], ph_style: str, tag_style: str) -> int:
    return _send_broken_lines(res, targets, sources, ph_style, tag_style, _CONTAINER.parity)


def _build_hooks() -> PipelineHooks:
    import budget_report, deliberate, jury, llm_tasks, pass2_rewrite, report_changes
    from build_context_map import load_context
    from build_language_pack import LANGPACK_DIR, infer_register
    from roundtrip_check import load_threshold, roundtrip_evidence
    from warmup_loader import load_warmup, render_warmup

    def _prepare_blind(p1: Path, blind: Path, locale: str, src_field: str, key_field: str) -> list[dict[str, Any]]:
        entries = make_blind_slice.build_slice(load_table(p1, src_field, locale, key_field, target_only=True), ["category", "speaker"], src_field, False, 0)
        make_blind_slice.verify_no_leak(entries, load_table(p1, src_field, locale, key_field), src_field)
        make_blind_slice.write_slice(entries, blind, locale, p1.name)
        return jury.load_blind_slice(blind)[0]

    def _batch_budget(router: Any, start: int) -> dict[str, Any] | None:
        if not (recs := router.budget.records[start:]):
            return None
        tot = budget_report.aggregate(recs, [], budget_report.price_table(router.config))[0]
        return {k: tot[k] for k in ("calls", "errors", "input_tokens", "output_tokens", "latency_ms", "cost_usd", "priced", "unpriced_models")}

    return build_orchestrator_hooks(OrchestratorCallbacks(
        infer_register=infer_register, trust_level=report_changes.trust_level, default_langpack_dir=lambda: LANGPACK_DIR,
        load_warmup=load_warmup, render_warmup=render_warmup, load_context=load_context, load_threshold=load_threshold,
        translate_rows=lambda *a, **kw: llm_tasks.translate_rows(*a, **kw), prepare_blind_slice=_prepare_blind,
        build_critic_prompt=lambda loc, je, pd, sd: jury.build_system_prompt(loc, je, pd, warmup=True, warmup_count=40, shots=6, seed=sd),
        roundtrip_evidence=roundtrip_evidence, run_jury=jury.run_jury, make_deliberator=deliberate.make_deliberator,
        load_pass2_sources=lambda p1, sf, loc, kf: pass2_rewrite.load_source_table(p1, sf, loc, kf, loc),
        build_pass2_systems=lambda loc, pd, regs, sd: pass2_rewrite.build_systems(loc, pd, regs, warmup=True, seed=sd),
        pass2_candidates=pass2_rewrite.pass2_candidates, pick_candidates=pass2_rewrite.pick_candidates,
        score_entries=pass2_rewrite.score_entries, write_change_report=report_changes.build_report,
        batch_budget=_batch_budget, phase3_gate=phase3_gate,
    ))


def run_jury_pipeline(
    input_path: Path, locale: str, workdir: Path, router: Any, *, src_field: str = "en", key_field: str = "key",
    ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 200, fonts: list[Path] | None = None,
    langpack_dir: Path | None = None, tm_path: Path | None = None, deliberation: bool = True,
    budget_caps: bool = True, candidates: int = 3, seed: int = 1234, workers: int = 1,
    context_map: Path | None = None, resume: bool = True, gate: dict[str, Any] | None = None,
    draft_field: str | None = None, lean_prompt: bool = True, clean_light_pass: bool = True,
    tiered_pass2: bool = True, unanimous_skip_recheck: bool = True, tm_shortcircuit: bool = True,
    require_juried_context: bool = False, salvage_truncated: bool = True,
) -> dict[str, Any]:
    """Run Phase 0-3 with the mixed family jury via LocalizationPipelineBuilder."""
    opts = JuryPipelineOptions(
        src_field=src_field, key_field=key_field, ph_style=ph_style, tag_style=tag_style, batch_size=batch_size,
        fonts=fonts or (), langpack_dir=langpack_dir, tm_path=tm_path, deliberation=deliberation,
        budget_caps=budget_caps, candidates=candidates, seed=seed, workers=workers, context_map=context_map,
        resume=resume, gate=gate, draft_field=draft_field, lean_prompt=lean_prompt,
        clean_light_pass=clean_light_pass, tiered_pass2=tiered_pass2, unanimous_skip_recheck=unanimous_skip_recheck,
        tm_shortcircuit=tm_shortcircuit, require_juried_context=require_juried_context, salvage_truncated=salvage_truncated,
    )
    return LocalizationPipelineBuilder(_build_hooks()).run(input_path, locale, workdir, router, opts)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="API-independent Phase 0-3 orchestration (jury flow with --dry-run or --live, legacy flow with --provider)")
    add_input_argument(ap, "Source string table (JSON/CSV/TSV/PO/.asset); the --src-field column holds English")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--workdir", required=True, help="Scratch directory for batches, slices, verdicts and reports")
    ap.add_argument("--src-field", default=None, help="Source column (default en)")
    ap.add_argument("--key-field", default=None, help="Key column (default key)")
    ap.add_argument("--placeholder-style", default=None, help="unity|unreal|godot|icu|printf|python|auto")
    ap.add_argument("--tag-style", default=None, help="tmp|html|bbcode|auto")
    ap.add_argument("--batch-size", type=int, default=200, help="Rows per batch (default 200)")
    ap.add_argument("--font", action="append", default=[], help="Font file(s) for the glyph gate, repeatable, in fallback order with the primary first")
    ap.add_argument("--dry-run", action="store_true", help="Jury flow with the offline fake provider (no API key, no network)")
    ap.add_argument("--live", action="store_true", help="Jury flow with the real APIs (keys from the environment)")
    ap.add_argument("--provider", help="Legacy single-critic flow: Python path 'module:function' of a complete(system, user) -> str callable")
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl (default: <workdir>/budget.jsonl)")
    ap.add_argument("--batch", action="store_true", help="Send Anthropic and Google calls through their batch APIs at half the price")
    ap.add_argument("--flex", action="store_true", help="Use the Google Gemini flex service tier at half the standard token price")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs (default: the skill's langpack/)")
    ap.add_argument("--tm", default=None, help="Translation memory (tm.py SQLite) for Pass 1 RAG and jury evidence")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game (Phase 0 step 0), with line_notes.json and CONTEXT_MAP.<locale>.md next to it")
    ap.add_argument("--draft-field", default=None, help="Input column that already holds a translation (a machine translation). Pass 1 keeps it, the jury judges it and Pass 2 corrects only the flagged lines")
    ap.add_argument("--no-deliberation", action="store_true", help="Leave J3 disagreements unresolved")
    ap.add_argument("--no-resume", action="store_true", help=f"Ignore the finished model batches kept in <workdir>/{RESUME_FILE} and call every model again")
    ap.add_argument("--no-budget-caps", action="store_true", help="Do not stop at the J2 or J3 escalation cap")
    ap.add_argument("--full-agent-prompt", action="store_true", help="Keep full IDE workflow instructions in API Pass 1 system prompts instead of compacting them")
    ap.add_argument("--rewrite-all-light", action="store_true", help="Send clean [5, 5, 4] verdicts to Pass 2 instead of settling them directly as pass")
    ap.add_argument("--no-tiered-pass2", action="store_true", help="Use the flagship pass2 model with --candidates for rewrite_light instead of pass2_light with 2 candidates")
    ap.add_argument("--always-recheck", action="store_true", help="Run the J1 confirmation recheck even when all 3 blind pickers unanimously chose the winning rewrite")
    ap.add_argument("--no-tm-shortcircuit", action="store_true", help="Do not short circuit exact context matched approved TM segments past Pass 1 and Jury")
    ap.add_argument("--require-juried-context", action="store_true", help="Abort if CONTEXT_MAP.md has a locale appendix without a separate CONTEXT_MAP.jury.md")
    ap.add_argument("--candidates", type=int, default=3, help="Pass 2 candidates per flagged line (default 3)")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of warm-up, few-shots and candidate order (default 1234)")
    ap.add_argument("--workers", type=int, default=4, help="Model calls in flight per step of the jury flow (default 4, 1 = one call at a time); combine with a larger --batch-size such as 200 so every step has enough batches")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    args = (ap := build_parser()).parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, _v = normalize_locale(args.locale)
    modes = [m for m, on in (("--dry-run", args.dry_run), ("--live", args.live), ("--provider", bool(args.provider))) if on]
    if len(modes) > 1:
        raise L10nError(f"choose one of --dry-run, --live or --provider (got {', '.join(modes)})")
    src_field, key_field = pick(args.src_field, cfg, "src_field", "en"), pick(args.key_field, cfg, "key_field", "key")
    ph_style, tag_style = pick(args.placeholder_style, cfg, "placeholder_style", "auto"), pick(args.tag_style, cfg, "tag_style", "auto")
    if args.workers < 1:
        raise L10nError("--workers must be 1 or more")
    gate = {k: cfg[k] for k in ("forbid_chars", "forbid_spaced_hyphen", "strict_whitespace", "fail_on_warn") if k in cfg}
    if args.dry_run or args.live:
        from llm_tasks import make_router
        workdir = Path(args.workdir)
        args.budget_log = args.budget_log or str(workdir / "budget.jsonl")
        router = make_router(args, ["pass1", "pass2", "roundtrip", "J1", "J2", "J3"])
        cmap_val = args.context_map or cfg.get("context_map")
        result = run_jury_pipeline(
            Path(args.input), locale, workdir, router, src_field=src_field, key_field=key_field, ph_style=ph_style, tag_style=tag_style,
            batch_size=args.batch_size, fonts=[Path(f) for f in args.font], langpack_dir=Path(args.langpack_dir) if args.langpack_dir else None,
            tm_path=Path(args.tm) if args.tm else None, deliberation=not args.no_deliberation, budget_caps=not args.no_budget_caps,
            candidates=args.candidates, seed=args.seed, workers=args.workers, context_map=Path(cmap_val) if cmap_val else None,
            resume=not args.no_resume, gate=gate, draft_field=args.draft_field, lean_prompt=not args.full_agent_prompt,
            clean_light_pass=not args.rewrite_all_light, tiered_pass2=not args.no_tiered_pass2,
            unanimous_skip_recheck=not args.always_recheck, tm_shortcircuit=not args.no_tm_shortcircuit,
            require_juried_context=args.require_juried_context,
        )
        exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
        text = "\n".join([f"Orchestrator run (jury flow, {'dry run' if args.dry_run else 'live'}):"] + ["  " + l for l in result["log"]] + [f"  NOTE: {n}" for n in result["notes"]] + [f"  Exit code: {exit_code}"])
        emit_report(text, {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}, args.json, args.output)
        return exit_code
    if not args.provider:
        raise L10nError("choose --dry-run (offline fake providers), --live (real APIs, keys from ANTHROPIC_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY) or --provider module:function (legacy single-critic flow)")
    mod_name, _, fn_name = args.provider.partition(":")
    if not fn_name:
        raise L10nError("--provider must be 'module:function'")
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
    except (ImportError, AttributeError) as exc:
        raise L10nError(f"cannot load provider {args.provider}: {exc}")
    result = run_pipeline(Path(args.input), locale, Path(args.workdir), CallableProvider(fn), src_field=src_field, dst_field=src_field, key_field=key_field, ph_style=ph_style, tag_style=tag_style, batch_size=args.batch_size, fonts=[Path(f) for f in args.font], gate=gate)
    result["flow"] = "legacy"
    exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
    emit_report("\n".join(["Orchestrator run (legacy flow):"] + ["  " + l for l in result["log"]] + [f"  Exit code: {exit_code}"]),
                {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
