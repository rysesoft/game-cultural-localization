#!/usr/bin/env python3
"""API-independent orchestration CLI facade delegating to gcl.application.pipeline & gcl.composition."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.pipeline import (  # noqa: E402
    ARCHETYPES, RESUME_FILE, JuryPipelineOptions, LocalizationPipelineBuilder, PipelineHooks, PipelineState,
    send_broken_lines_to_pass2 as _send_broken_lines,
)
from gcl.composition.container import ServiceContainer  # noqa: E402
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, Row, add_common_args, add_input_argument, emit_report, load_config,
    load_table, normalize_locale, pick, resolve_input, run_main, SCRIPTS_DIR, __version__,
)
import lqa_linter  # noqa: E402
import make_blind_slice  # noqa: E402
import ui_expansion_checker  # noqa: E402
import validate_critique  # noqa: E402

TOOL = "orchestrator_stub"
PLUGIN_DIR = SCRIPTS_DIR.parent.parent.parent
AGENTS_DIR = PLUGIN_DIR / "agents"
REFS_DIR = SCRIPTS_DIR.parent / "references"
_CONTAINER = ServiceContainer()


class Provider(Protocol):
    """Minimal legacy LLM adapter: return assistant text for system + user."""

    def complete(self, system: str, user: str) -> str: ...


class DryRunProvider:
    """Deterministic offline provider for legacy 2.1 flow tests."""

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.calls: List[Dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system[:80], "user": user[:80]})
        payload = json.loads(user.split("\n---\n", 1)[1]) if "\n---\n" in user else {}
        if payload.get("task") == "critique":
            entries = payload.get("entries", [])
            return json.dumps({"locale": self.locale, "source_file": payload.get("source_file", ""), "entries": [],
                               "summary": {"total": len(entries), "flagged": 0, "critical": 0}}, ensure_ascii=False)
        rows = payload.get("rows", [])
        return json.dumps({"rows": [{"key": r["key"], "target": r.get("target") or f"[{self.locale}] {r.get('source', '')}"} for r in rows]}, ensure_ascii=False)


class CallableProvider:
    """Wrap function(system, user) -> str as legacy Provider."""

    def __init__(self, fn: Callable[[str, str], str]) -> None:
        self.fn = fn

    def complete(self, system: str, user: str) -> str:
        return self.fn(system, user)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def load_agent_prompt(name: str) -> str:
    path = AGENTS_DIR / f"{name}.md"
    if not path.is_file():
        return f"You are the {name} agent of the game-cultural-localization suite."
    return strip_frontmatter(path.read_text(encoding="utf-8-sig"))


def load_playbook(locale: str) -> str:
    path = REFS_DIR / f"{locale}.md"
    return path.read_text(encoding="utf-8-sig") if path.is_file() else ""


def system_prompt(agent: str, locale: str, bible: str) -> str:
    parts = [load_agent_prompt(agent), f"# Target locale: {locale}", load_playbook(locale)]
    if bible:
        parts.append("# Project bible\n" + bible)
    parts.append("# Character archetypes\n" + "\n".join(f"{k}: {v}" for k, v in ARCHETYPES.items()))
    return "\n\n".join(p for p in parts if p)


def _extract_json(text: str) -> Any:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise L10nError("provider reply contains no JSON object")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise L10nError(f"provider reply is not valid JSON: {exc.msg}")


def phase0_preflight(state: PipelineState, rows: List[Row], fonts: List[Path]) -> None:
    state.say(f"Phase 0: locale {state.locale}, {len(rows)} source rows")
    bible = state.workdir / f"{state.locale}_BIBLE.md"
    stub = f"# {state.locale} localization bible\n\n(stub created by orchestrator_stub; fill terminology, registers per archetype A1-A5, ledger)\n"
    if bible.is_file():
        text = bible.read_text(encoding="utf-8-sig")
        if text == stub:
            state.say(f"Phase 0: bible {bible.name} is still the empty stub, fill it to hand the translators the project's decisions")
        else:
            state.bible = text
            state.say(f"Phase 0: bible found ({bible.name})")
    else:
        bible.write_text(stub, encoding="utf-8")
        state.say(f"Phase 0: bible missing -> stub written to {bible.name}")
    lqa_linter.load_rules(state.locale)
    if fonts:
        cmd = [sys.executable, str(SCRIPTS_DIR / "font_glyph_scanner.py"), "--input", str(state.workdir / "source.json"), "--dst-field", "source"]
        for f in fonts:
            cmd += ["--font", str(f)]
        (state.workdir / "source.json").write_text(json.dumps([{"key": r.key, "source": r.src} for r in rows], ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        state.say(f"Phase 0: font scan exit {proc.returncode}")
        if proc.returncode == 2:
            raise L10nError("font scan failed: " + proc.stderr.strip())


def phase1_pass1(state: PipelineState, rows: List[Row], provider: Provider, batch_size: int) -> List[Path]:
    system = system_prompt("game-culturalizer", state.locale, state.bible)
    outputs: List[Path] = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        n = i // batch_size + 1
        payload = {"task": "pass1", "locale": state.locale, "placeholder_style": state.ph_style, "tag_style": state.tag_style,
                   "rows": [{"key": r.key, "source": r.src, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", "")} for r in batch]}
        user = (f"Translate the following clean-room batch into natural everyday {state.locale}. Reply with JSON "
                f"{{\"rows\": [{{\"key\", \"target\"}}]}} only.\n---\n" + json.dumps(payload, ensure_ascii=False))
        reply = _extract_json(provider.complete(system, user))
        targets = {str(r["key"]): str(r.get("target", "")) for r in reply.get("rows", []) if isinstance(r, dict) and "key" in r}
        missing = [r.key for r in batch if r.key not in targets]
        if missing:
            raise L10nError(f"Pass 1 batch {n}: provider returned no target for keys {missing[:5]}")
        out = state.workdir / f"pass1_batch_{n:02d}.json"
        out.write_text(json.dumps([{"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""),
                                    state.src_field: r.src, state.locale: targets[r.key]} for r in batch], ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(out)
        state.say(f"Phase 1: batch {n:02d} -> {out.name} ({len(batch)} rows)")
    return outputs


def phase2_critique_and_pass2(state: PipelineState, pass1_files: List[Path], provider: Provider) -> List[Path]:
    critic_system = system_prompt("native-ear-critic", state.locale, "")
    editor_system = system_prompt("game-culturalizer", state.locale, state.bible)
    finals: List[Path] = []
    for n, p1 in enumerate(pass1_files, start=1):
        rows = load_table(p1, state.src_field, state.locale, state.key_field, target_only=True)
        entries = make_blind_slice.build_slice(rows, ["category", "speaker"], state.src_field, False, 0)
        full_rows = load_table(p1, state.src_field, state.locale, state.key_field)
        make_blind_slice.verify_no_leak(entries, full_rows, state.src_field)
        blind = state.workdir / f"blind_{state.locale}_{n:02d}.json"
        make_blind_slice.write_slice(entries, blind, state.locale, p1.name)
        payload = {"task": "critique", "locale": state.locale, "source_file": blind.name, "entries": entries}
        user = ("Read ONLY these target strings as a native player. Return JSON with the critique schema "
                "(locale, source_file, entries[key, score, issue_type, reason, suggested], summary{total, flagged, critical}); "
                "list only score<5.\n---\n" + json.dumps(payload, ensure_ascii=False))
        critique = _extract_json(provider.complete(critic_system, user))
        crit_path = state.workdir / f"critique_{state.locale}_{n:02d}.json"
        crit_path.write_text(json.dumps(critique, ensure_ascii=False, indent=2), encoding="utf-8")
        problems = validate_critique.validate(critique, {e["key"]: e["target"] for e in entries}, state.ph_style, state.tag_style, state.locale)
        if problems:
            raise L10nError(f"critique {crit_path.name} is invalid: " + "; ".join(problems[:5]))
        state.say(f"Phase 2: batch {n:02d} blind slice {len(entries)} rows, critique flagged {critique['summary']['flagged']}")
        suggestions = {e["key"]: e for e in critique.get("entries", [])}
        rewritten: Dict[str, str] = {}
        if suggestions:
            payload2 = {"task": "pass2", "locale": state.locale,
                        "rows": [{"key": r.key, "source": r.src, "target": r.dst, "critique": suggestions.get(r.key)} for r in full_rows if r.key in suggestions]}
            user2 = ("Apply the valid native-ear suggestions while preserving placeholders, tags, spaces and glossary terms. "
                     "Reply with JSON {\"rows\": [{\"key\", \"target\"}]}.\n---\n" + json.dumps(payload2, ensure_ascii=False))
            reply = _extract_json(provider.complete(editor_system, user2))
            rewritten = {str(r["key"]): str(r.get("target", "")) for r in reply.get("rows", []) if isinstance(r, dict) and "key" in r}
        final_rows = [{"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""),
                       state.src_field: r.src, state.locale: rewritten.get(r.key, r.dst)} for r in full_rows]
        final = state.workdir / f"final_batch_{n:02d}.json"
        final.write_text(json.dumps(final_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        finals.append(final)
        state.say(f"Phase 2: batch {n:02d} Pass-2 rewrote {len(rewritten)} rows -> {final.name}")
    return finals


def phase3_gate(state: PipelineState, finals: List[Path], fonts: List[Path]) -> Dict[str, Any]:
    rules = lqa_linter.load_rules(state.locale)
    summary = {"errors": 0, "warnings": 0, "high": 0, "warn": 0, "missing_glyphs": 0, "full_width_fallbacks": 0, "glyphs_checked": bool(fonts)}
    missing, wide = set(), set()
    for f in finals:
        rows = load_table(f, state.src_field, state.locale, state.key_field)
        findings = lqa_linter.lint_rows(rows, rules, lqa_linter.LintOptions(
            locale=state.locale, placeholder_style=state.ph_style, tag_style=state.tag_style,
            forbid_chars=str(state.gate.get("forbid_chars", "")), forbid_spaced_hyphen=bool(state.gate.get("forbid_spaced_hyphen", False)),
            strict_whitespace=bool(state.gate.get("strict_whitespace", False))))
        risks = ui_expansion_checker.check_rows(rows, ui_expansion_checker.CheckOptions(locale=state.locale, factor=ui_expansion_checker.EXPANSION_FACTORS[state.locale], tag_style=state.tag_style))
        summary["errors"] += sum(1 for x in findings if x.severity == "ERR")
        summary["warnings"] += sum(1 for x in findings if x.severity == "WARN")
        summary["high"] += sum(1 for r in risks if r.level == "HIGH")
        summary["warn"] += sum(1 for r in risks if r.level == "WARN")
        (state.workdir / f"lqa_{state.locale}_{f.stem[-2:]}.json").write_text(json.dumps({"findings": [x.as_dict() for x in findings], "risks": [r.as_dict() for r in risks]}, ensure_ascii=False, indent=2), encoding="utf-8")
        if fonts:
            cmd = [sys.executable, str(SCRIPTS_DIR / "font_glyph_scanner.py"), "--input", str(f), "--dst-field", state.locale, "--locale", state.locale, "--json"]
            for font in fonts:
                cmd += ["--font", str(font)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 2:
                raise L10nError("font scan failed: " + proc.stderr.strip())
            try:
                scan = json.loads(proc.stdout)
                missing |= {m["codepoint"] for m in scan.get("missing", [])}
                wide |= {m["codepoint"] for m in scan.get("full_width", [])}
            except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
                missing.add(f"batch {f.stem}") if proc.returncode == 1 else None
    summary["missing_glyphs"] = len(missing)
    summary["full_width_fallbacks"] = len(wide)
    summary["passed"] = (summary["errors"] == 0 and summary["high"] == 0 and summary["missing_glyphs"] == 0
                         and summary["full_width_fallbacks"] == 0 and not (state.gate.get("fail_on_warn") and summary["warnings"]))
    if not fonts:
        state.say("Phase 3: no --font given, the glyph scan did not run, the gate says nothing about missing glyphs")
    state.say(f"Phase 3: gate {'PASSED' if summary['passed'] else 'FAILED'}" + ("" if fonts else " (glyphs not checked)") + f" {summary}")
    return summary


def run_pipeline(
    input_path: Path, locale: str, workdir: Path, provider: Provider, *, src_field: str = "en", dst_field: str = "dst",
    key_field: str = "key", ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50,
    fonts: Optional[List[Path]] = None, gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run legacy Phase 0-3 flow and return result dict."""
    workdir.mkdir(parents=True, exist_ok=True)
    rows = [Row(r.key, r.dst, "", r.meta) for r in load_table(input_path, src_field, src_field, key_field, target_only=True)]
    if not rows:
        raise L10nError(f"{input_path}: no rows to localize")
    state = PipelineState(locale, workdir, src_field, dst_field, key_field, ph_style, tag_style, gate=dict(gate or {}))
    phase0_preflight(state, rows, fonts or [])
    p1 = phase1_pass1(state, rows, provider, batch_size)
    finals = phase2_critique_and_pass2(state, p1, provider)
    summary = phase3_gate(state, finals, fonts or [])
    return {"passed": summary["passed"], "summary": summary, "log": state.log, "finals": [str(f) for f in finals]}


def _register(row: Row) -> str:
    from build_language_pack import infer_register
    reg = str(row.meta.get("register") or "")
    return reg if reg else infer_register(str(row.meta.get("category") or ""), row.src, "game")


def send_broken_lines_to_pass2(res: Dict[str, Any], targets: Dict[str, str], sources: Dict[str, str], ph_style: str, tag_style: str) -> int:
    """Delegate broken placeholder/tag escalation to gcl.application.pipeline.stages."""
    return _send_broken_lines(res, targets, sources, ph_style, tag_style, _CONTAINER.parity)


def _batch_budget(router: Any, start: int) -> Optional[Dict[str, Any]]:
    import budget_report
    recs = router.budget.records[start:]
    if not recs:
        return None
    tot = budget_report.aggregate(recs, [], budget_report.price_table(router.config))[0]
    return {k: tot[k] for k in ("calls", "errors", "input_tokens", "output_tokens", "latency_ms", "cost_usd", "priced", "unpriced_models")}


def _write_report(
    report_changes: Any, verdict_doc: Dict[str, Any], locale: str, n: int, tag: str, workdir: Path,
    rewrites: Optional[Dict[str, Any]], sources: Dict[str, Dict[str, str]], pack_dir: Path, budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rep = report_changes.build_report(verdict_doc, locale, f"{n:02d}", rewrites=rewrites, sources=sources, pack_dir=pack_dir, budget=budget)
    (workdir / f"changes_{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / f"changes_{tag}.md").write_text(report_changes.render_markdown(rep), encoding="utf-8")
    return rep


def _build_hooks() -> PipelineHooks:
    import budget_report
    import deliberate
    import jury
    import llm_tasks
    import pass2_rewrite
    import report_changes
    from build_context_map import load_context
    from build_language_pack import LANGPACK_DIR
    from gcl.application.rewrite import TournamentOptions, run_tournament
    from roundtrip_check import load_threshold, roundtrip_evidence
    from warmup_loader import load_warmup, render_warmup

    def _prepare_blind(p1: Path, blind: Path, locale: str, src_field: str, key_field: str) -> List[Dict[str, Any]]:
        slice_rows = load_table(p1, src_field, locale, key_field, target_only=True)
        entries = make_blind_slice.build_slice(slice_rows, ["category", "speaker"], src_field, False, 0)
        make_blind_slice.verify_no_leak(entries, load_table(p1, src_field, locale, key_field), src_field)
        make_blind_slice.write_slice(entries, blind, locale, p1.name)
        jentries, _sf = jury.load_blind_slice(blind)
        return jentries

    def _run_pass2(verdicts: Any, sources: Any, locale: str, router: Any, opts: JuryPipelineOptions,
                   p2_sys: str, pk_sys: str, wctx: Any, bctx: Any, memo: Any, src_name: str) -> Dict[str, Any]:
        t_opts = TournamentOptions(
            pass2_system=p2_sys, pick_system=pk_sys, n=opts.candidates, seed=opts.seed,
            ph_style=opts.ph_style, tag_style=opts.tag_style, source_file=src_name, workers=opts.workers,
            writer_context=wctx, blind_context=bctx, memo=memo,
        )
        return run_tournament(
            verdicts, sources, locale, router, t_opts, _CONTAINER.critique_validator, _CONTAINER.parity,
            pass2_fn=pass2_rewrite.pass2_candidates, pick_fn=pass2_rewrite.pick_candidates,
            score_fn=pass2_rewrite.score_entries,
        )

    def _write_change(vdoc: Dict[str, Any], locale: str, n: int, tag: str, workdir: Path,
                      rewrites: Any, sources: Dict[str, Dict[str, str]], pack_dir: Path, budget: Any) -> Dict[str, Any]:
        return _write_report(report_changes, vdoc, locale, n, tag, workdir, rewrites, sources, pack_dir, budget)

    return PipelineHooks(
        load_source_rows=lambda p, sf, kf: [Row(r.key, r.dst, "", r.meta) for r in load_table(p, sf, sf, kf, target_only=True)],
        register_of=_register, preflight=phase0_preflight, trust_level=report_changes.trust_level,
        open_tm=_CONTAINER.open_tm, open_memo=_CONTAINER.open_memo, default_langpack_dir=lambda: LANGPACK_DIR,
        load_warmup_sample=lambda pd, regs, cnt, sd: load_warmup(pd, regs, cnt, sd), render_warmup=render_warmup,
        system_prompt=system_prompt,
        load_context_views=lambda cm, loc: _CONTAINER.split_context_pack(load_context(cm, loc)),
        load_threshold=load_threshold,
        translate_rows=lambda *a, **kw: llm_tasks.translate_rows(*a, **kw),
        prepare_blind_slice=_prepare_blind,
        build_critic_prompt=lambda loc, je, pd, sd: jury.build_system_prompt(loc, je, pd, warmup=True, warmup_count=40, shots=6, seed=sd),
        roundtrip_evidence=roundtrip_evidence, run_jury=jury.run_jury, make_deliberator=deliberate.make_deliberator,
        load_pass2_sources=lambda p1, sf, loc, kf: pass2_rewrite.load_source_table(p1, sf, loc, kf, loc),
        build_pass2_systems=lambda loc, pd, regs, sd: pass2_rewrite.build_systems(loc, pd, regs, warmup=True, seed=sd),
        run_pass2=_run_pass2, write_change_report=_write_change,
        batch_budget=lambda rtr, st: _batch_budget(rtr, st),
        phase3_gate=phase3_gate, parity=_CONTAINER.parity,
    )


def run_jury_pipeline(
    input_path: Path, locale: str, workdir: Path, router: Any, *, src_field: str = "en", key_field: str = "key",
    ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50, fonts: Optional[List[Path]] = None,
    langpack_dir: Optional[Path] = None, tm_path: Optional[Path] = None, deliberation: bool = True,
    budget_caps: bool = True, candidates: int = 3, seed: int = 1234, workers: int = 1,
    context_map: Optional[Path] = None, resume: bool = True, gate: Optional[Dict[str, Any]] = None,
    draft_field: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Phase 0-3 with the mixed family jury via LocalizationPipelineBuilder."""
    opts = JuryPipelineOptions(
        src_field=src_field, key_field=key_field, ph_style=ph_style, tag_style=tag_style, batch_size=batch_size,
        fonts=fonts or (), langpack_dir=langpack_dir, tm_path=tm_path, deliberation=deliberation,
        budget_caps=budget_caps, candidates=candidates, seed=seed, workers=workers,
        context_map=context_map, resume=resume, gate=gate, draft_field=draft_field,
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
    ap.add_argument("--batch-size", type=int, default=50, help="Rows per batch (default 50)")
    ap.add_argument("--font", action="append", default=[], help="Font file(s) for the glyph gate, repeatable, in fallback order with the primary first")
    ap.add_argument("--dry-run", action="store_true", help="Jury flow with the offline fake provider (no API key, no network)")
    ap.add_argument("--live", action="store_true", help="Jury flow with the real APIs (keys from the environment)")
    ap.add_argument("--provider", help="Legacy single-critic flow: Python path 'module:function' of a complete(system, user) -> str callable")
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl (default: <workdir>/budget.jsonl)")
    ap.add_argument("--batch", action="store_true", help="Send Anthropic and Google calls through their batch APIs at half the price")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs (default: the skill's langpack/)")
    ap.add_argument("--tm", default=None, help="Translation memory (tm.py SQLite) for Pass 1 RAG and jury evidence")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game (Phase 0 step 0), with line_notes.json and CONTEXT_MAP.<locale>.md next to it")
    ap.add_argument("--draft-field", default=None, help="Input column that already holds a translation (a machine translation). Pass 1 keeps it, the jury judges it and Pass 2 corrects only the flagged lines")
    ap.add_argument("--no-deliberation", action="store_true", help="Leave J3 disagreements unresolved")
    ap.add_argument("--no-resume", action="store_true", help=f"Ignore the finished model batches kept in <workdir>/{RESUME_FILE} and call every model again")
    ap.add_argument("--no-budget-caps", action="store_true", help="Do not stop at the J2 or J3 escalation cap")
    ap.add_argument("--candidates", type=int, default=3, help="Pass 2 candidates per flagged line (default 3)")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of warm-up, few-shots and candidate order (default 1234)")
    ap.add_argument("--workers", type=int, default=4, help="Model calls in flight per step of the jury flow (default 4, 1 = one call at a time); combine with a larger --batch-size such as 200 so every step has enough batches")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, _v = normalize_locale(args.locale)
    modes = [m for m, on in (("--dry-run", args.dry_run), ("--live", args.live), ("--provider", bool(args.provider))) if on]
    if len(modes) > 1:
        raise L10nError(f"choose one of --dry-run, --live or --provider (got {', '.join(modes)})")
    src_field = pick(args.src_field, cfg, "src_field", "en")
    key_field = pick(args.key_field, cfg, "key_field", "key")
    ph_style = pick(args.placeholder_style, cfg, "placeholder_style", "auto")
    tag_style = pick(args.tag_style, cfg, "tag_style", "auto")
    if args.workers < 1:
        raise L10nError("--workers must be 1 or more")
    gate = {k: cfg[k] for k in ("forbid_chars", "forbid_spaced_hyphen", "strict_whitespace", "fail_on_warn") if k in cfg}
    if args.dry_run or args.live:
        from llm_tasks import make_router
        workdir = Path(args.workdir)
        if not args.budget_log:
            args.budget_log = str(workdir / "budget.jsonl")
        router = make_router(args, ["pass1", "pass2", "roundtrip", "J1", "J2", "J3"])
        result = run_jury_pipeline(
            Path(args.input), locale, workdir, router, src_field=src_field, key_field=key_field, ph_style=ph_style, tag_style=tag_style,
            batch_size=args.batch_size, fonts=[Path(f) for f in args.font], langpack_dir=Path(args.langpack_dir) if args.langpack_dir else None,
            tm_path=Path(args.tm) if args.tm else None, deliberation=not args.no_deliberation, budget_caps=not args.no_budget_caps,
            candidates=args.candidates, seed=args.seed, workers=args.workers,
            context_map=Path(args.context_map or cfg["context_map"]) if (args.context_map or cfg.get("context_map")) else None,
            resume=not args.no_resume, gate=gate, draft_field=args.draft_field,
        )
        exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
        text = "\n".join([f"Orchestrator run (jury flow, {'dry run' if args.dry_run else 'live'}):"] + ["  " + l for l in result["log"]]
                         + [f"  NOTE: {n}" for n in result["notes"]] + [f"  Exit code: {exit_code}"])
        payload = {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}
        emit_report(text, payload, args.json, args.output)
        return exit_code
    if not args.provider:
        raise L10nError("choose --dry-run (offline fake providers), --live (real APIs, keys from ANTHROPIC_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY) or --provider module:function (legacy single-critic flow)")
    mod_name, _, fn_name = args.provider.partition(":")
    if not fn_name:
        raise L10nError("--provider must be 'module:function'")
    import importlib
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
    except (ImportError, AttributeError) as exc:
        raise L10nError(f"cannot load provider {args.provider}: {exc}")
    result = run_pipeline(
        Path(args.input), locale, Path(args.workdir), CallableProvider(fn), src_field=src_field, dst_field=src_field,
        key_field=key_field, ph_style=ph_style, tag_style=tag_style, batch_size=args.batch_size, fonts=[Path(f) for f in args.font], gate=gate,
    )
    result["flow"] = "legacy"
    exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
    text = "\n".join(["Orchestrator run (legacy flow):"] + ["  " + l for l in result["log"]] + [f"  Exit code: {exit_code}"])
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}
    emit_report(text, payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
