#!/usr/bin/env python3
"""API-independent orchestration stub for the 4-phase culturalization pipeline.

This is the R&D starting point for running the pipeline against ANY LLM API:
implement the Provider protocol (one method: complete(system, user) -> str) for
OpenAI / Anthropic / Gemini / a local model, and the phases below do the rest.
Nothing here depends on Antigravity; the agent prompt bodies are loaded from
agents/*.md (frontmatter stripped) and references/<locale>.md so they can be
sent as plain system prompts.

Pipeline (canonical numbering):
  Phase 0  pre-flight: locale validation, bible check, optional font scan
  Phase 1  Pass-1 clean-room culturalization (provider call per batch)
  Phase 2  blind slice -> critic (provider call, target-only) -> validate_critique -> Pass-2 rewrite
  Phase 3  automated LQA gate (lqa_linter + ui_expansion_checker [+ font_glyph_scanner])

Dry run (no LLM): DryRunProvider echoes a deterministic pseudo-translation so the
whole file flow and the gate can be exercised offline:

    python orchestrator_stub.py --dry-run --locale de-DE --input strings.json --workdir out/
    python orchestrator_stub.py --dry-run --locale de-DE --input strings.json --workdir out/ --json

Exit codes: 0 pipeline passed, 1 a phase failed (gate findings / invalid critique),
2 usage / input error.  Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, Row, add_common_args, add_input_argument, resolve_input, emit_report, extract_placeholders, load_config,
    load_json_data, load_table, normalize_locale, pick, run_main, SCRIPTS_DIR, __version__,
)
import lqa_linter  # noqa: E402
import make_blind_slice  # noqa: E402
import ui_expansion_checker  # noqa: E402
import validate_critique  # noqa: E402

TOOL = "orchestrator_stub"
PLUGIN_DIR = SCRIPTS_DIR.parent.parent.parent
AGENTS_DIR = PLUGIN_DIR / "agents"
REFS_DIR = SCRIPTS_DIR.parent / "references"
ARCHETYPES = {
    "A1": "Mentor/Veteran (warm, senior, gives advice)",
    "A2": "Hotshot Rival (cocky, fast, competitive)",
    "A3": "Rookie/Teen (excited, everyday slang, short sentences)",
    "A4": "Scientist/Engineer (precise, technical but conversational)",
    "A5": "Outlaw/Antagonist (threatening, cold, terse)",
}


# --------------------------------------------------------------------------- #
# Provider interface
# --------------------------------------------------------------------------- #
class Provider(Protocol):
    """Minimal LLM adapter: return the assistant text for a system + user prompt."""

    def complete(self, system: str, user: str) -> str: ...


class DryRunProvider:
    """Deterministic offline provider: pseudo-translates targets and returns an empty critique."""

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
        out = []
        for r in rows:
            src = r.get("source", "")
            target = r.get("target") or f"[{self.locale}] {src}"
            out.append({"key": r["key"], "target": target})
        return json.dumps({"rows": out}, ensure_ascii=False)


class CallableProvider:
    """Wrap any function(system, user) -> str (e.g. a thin SDK call) as a Provider."""

    def __init__(self, fn: Callable[[str, str], str]) -> None:
        self.fn = fn

    def complete(self, system: str, user: str) -> str:
        return self.fn(system, user)


# --------------------------------------------------------------------------- #
# Prompt assembly (plain text, usable as a system prompt for any API)
# --------------------------------------------------------------------------- #

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
    """Parse the first JSON object in a model reply (tolerates code fences)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise L10nError("provider reply contains no JSON object")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise L10nError(f"provider reply is not valid JSON: {exc.msg}")


# --------------------------------------------------------------------------- #
# Phases
# --------------------------------------------------------------------------- #
class PipelineState:
    def __init__(self, locale: str, workdir: Path, src_field: str, dst_field: str, key_field: str, ph_style: str, tag_style: str) -> None:
        self.locale, self.workdir = locale, workdir
        self.src_field, self.dst_field, self.key_field = src_field, dst_field, key_field
        self.ph_style, self.tag_style = ph_style, tag_style
        self.log: List[str] = []
        self.bible = ""

    def say(self, msg: str) -> None:
        self.log.append(msg)


def phase0_preflight(state: PipelineState, rows: List[Row], fonts: List[Path]) -> None:
    state.say(f"Phase 0: locale {state.locale}, {len(rows)} source rows")
    bible = state.workdir / f"{state.locale}_BIBLE.md"
    if bible.is_file():
        state.bible = bible.read_text(encoding="utf-8-sig")
        state.say(f"Phase 0: bible found ({bible.name})")
    else:
        bible.write_text(f"# {state.locale} localization bible\n\n(stub created by orchestrator_stub; fill terminology, registers per archetype A1-A5, ledger)\n", encoding="utf-8")
        state.say(f"Phase 0: bible missing -> stub written to {bible.name}")
    lqa_linter.load_rules(state.locale)  # proves the rule file loads
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
        final_rows = []
        if suggestions:
            payload2 = {"task": "pass2", "locale": state.locale,
                        "rows": [{"key": r.key, "source": r.src, "target": r.dst, "critique": suggestions.get(r.key)} for r in full_rows if r.key in suggestions]}
            user2 = ("Apply the valid native-ear suggestions while preserving placeholders, tags, spaces and glossary terms. "
                     "Reply with JSON {\"rows\": [{\"key\", \"target\"}]}.\n---\n" + json.dumps(payload2, ensure_ascii=False))
            reply = _extract_json(provider.complete(editor_system, user2))
            rewritten = {str(r["key"]): str(r.get("target", "")) for r in reply.get("rows", []) if isinstance(r, dict) and "key" in r}
        else:
            rewritten = {}
        for r in full_rows:
            final_rows.append({"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""),
                               state.src_field: r.src, state.locale: rewritten.get(r.key, r.dst)})
        final = state.workdir / f"final_batch_{n:02d}.json"
        final.write_text(json.dumps(final_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        finals.append(final)
        state.say(f"Phase 2: batch {n:02d} Pass-2 rewrote {len(rewritten)} rows -> {final.name}")
    return finals


def phase3_gate(state: PipelineState, finals: List[Path], fonts: List[Path]) -> Dict[str, Any]:
    rules = lqa_linter.load_rules(state.locale)
    summary = {"errors": 0, "warnings": 0, "high": 0, "warn": 0, "missing_glyphs": 0}
    for f in finals:
        rows = load_table(f, state.src_field, state.locale, state.key_field)
        findings = lqa_linter.lint_rows(rows, rules, lqa_linter.LintOptions(locale=state.locale, placeholder_style=state.ph_style, tag_style=state.tag_style))
        risks = ui_expansion_checker.check_rows(rows, ui_expansion_checker.CheckOptions(locale=state.locale, factor=ui_expansion_checker.EXPANSION_FACTORS[state.locale], tag_style=state.tag_style))
        summary["errors"] += sum(1 for x in findings if x.severity == "ERR")
        summary["warnings"] += sum(1 for x in findings if x.severity == "WARN")
        summary["high"] += sum(1 for r in risks if r.level == "HIGH")
        summary["warn"] += sum(1 for r in risks if r.level == "WARN")
        (state.workdir / f"lqa_{state.locale}_{f.stem[-2:]}.json").write_text(json.dumps({"findings": [x.as_dict() for x in findings], "risks": [r.as_dict() for r in risks]}, ensure_ascii=False, indent=2), encoding="utf-8")
        if fonts:
            cmd = [sys.executable, str(SCRIPTS_DIR / "font_glyph_scanner.py"), "--input", str(f), "--dst-field", state.locale]
            for font in fonts:
                cmd += ["--font", str(font)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 2:
                raise L10nError("font scan failed: " + proc.stderr.strip())
            summary["missing_glyphs"] += 1 if proc.returncode == 1 else 0
    summary["passed"] = summary["errors"] == 0 and summary["high"] == 0 and summary["missing_glyphs"] == 0
    state.say(f"Phase 3: gate {'PASSED' if summary['passed'] else 'FAILED'} {summary}")
    return summary


def run_pipeline(input_path: Path, locale: str, workdir: Path, provider: Provider, *, src_field: str = "en", dst_field: str = "dst",
                 key_field: str = "key", ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50, fonts: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Run Phase 0-3 and return a result dict ({'passed': bool, 'log': [...], 'summary': {...}})."""
    workdir.mkdir(parents=True, exist_ok=True)
    # Source-only input: the src_field column is loaded as 'dst' (target_only) and moved to Row.src.
    rows = [Row(r.key, r.dst, "", r.meta) for r in load_table(input_path, src_field, src_field, key_field, target_only=True)]
    if not rows:
        raise L10nError(f"{input_path}: no rows to localize")
    state = PipelineState(locale, workdir, src_field, dst_field, key_field, ph_style, tag_style)
    phase0_preflight(state, rows, fonts or [])
    p1 = phase1_pass1(state, rows, provider, batch_size)
    finals = phase2_critique_and_pass2(state, p1, provider)
    summary = phase3_gate(state, finals, fonts or [])
    return {"passed": summary["passed"], "summary": summary, "log": state.log, "finals": [str(f) for f in finals]}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="API-independent Phase 0-3 orchestration stub (--dry-run needs no LLM)")
    add_input_argument(ap, "Source string table (JSON/CSV/TSV/PO/.asset); the --src-field column holds English")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--workdir", required=True, help="Scratch directory for batches, slices, critiques and reports")
    ap.add_argument("--src-field", default=None, help="Source column (default en)")
    ap.add_argument("--key-field", default=None, help="Key column (default key)")
    ap.add_argument("--placeholder-style", default=None, help="unity|unreal|godot|icu|printf|python|auto")
    ap.add_argument("--tag-style", default=None, help="tmp|html|bbcode|auto")
    ap.add_argument("--batch-size", type=int, default=50, help="Rows per provider call (default 50)")
    ap.add_argument("--font", action="append", default=[], help="Font file(s) for the glyph gate (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="Use the offline DryRunProvider (no LLM call)")
    ap.add_argument("--provider", help="Python path 'module:function' of a complete(system, user) -> str callable")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_config(Path(args.config)) if args.config else {}
    locale, _v = normalize_locale(args.locale)
    if args.dry_run:
        provider: Provider = DryRunProvider(locale)
    elif args.provider:
        mod_name, _, fn_name = args.provider.partition(":")
        if not fn_name:
            raise L10nError("--provider must be 'module:function'")
        import importlib
        try:
            fn = getattr(importlib.import_module(mod_name), fn_name)
        except (ImportError, AttributeError) as exc:
            raise L10nError(f"cannot load provider {args.provider}: {exc}")
        provider = CallableProvider(fn)
    else:
        raise L10nError("choose --dry-run or --provider module:function (no LLM adapter is bundled)")
    src_field = pick(args.src_field, cfg, "src_field", "en")
    result = run_pipeline(
        Path(args.input), locale, Path(args.workdir), provider, src_field=src_field, dst_field=src_field,
        key_field=pick(args.key_field, cfg, "key_field", "key"), ph_style=pick(args.placeholder_style, cfg, "placeholder_style", "auto"),
        tag_style=pick(args.tag_style, cfg, "tag_style", "auto"), batch_size=args.batch_size, fonts=[Path(f) for f in args.font],
    )
    exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
    text = "\n".join(["Orchestrator run:"] + ["  " + l for l in result["log"]] + [f"  Exit code: {exit_code}"])
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}
    emit_report(text, payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
