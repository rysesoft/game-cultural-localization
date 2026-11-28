"""Composition module implementing Phase 0 to 3 prompts, legacy single critic flow and in process font gates."""

import json
import os
import re
from collections.abc import Callable, Sequence
from concurrent.futures import InterpreterPoolExecutor
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Any, Protocol

from gcl.application.pipeline import ARCHETYPES, PipelineState
from gcl.composition.container import ServiceContainer
from gcl.domain.errors import L10nError
from gcl.domain.models import Row
from gcl.domain.prompt_compactor import compact_agent_for_api, compact_playbook_for_api
from gcl.infrastructure.formats.lint_rules_io import load_rules
from gcl.infrastructure.formats.registry import load_table_options
from gcl.infrastructure.paths import SCRIPTS_DIR
from gcl.ports.formats import TableLoadOptions

__layer__ = "composition"
__pattern__ = "Facade Backend"
__owns__ = "agent prompts, Phase 0 preflight, in process font gate execution and legacy single critic flow"

PLUGIN_DIR = SCRIPTS_DIR.parents[2]
AGENTS_DIR = PLUGIN_DIR / "agents"
REFS_DIR = SCRIPTS_DIR.parent / "references"
CONTAINER = ServiceContainer()


class Provider(Protocol):
    """Minimal legacy LLM adapter returning assistant text for system and user."""

    def complete(self, system: str, user: str) -> str: ...


class DryRunProvider:
    """Deterministic offline provider for legacy single critic flow tests."""

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system[:80], "user": user[:80]})
        payload = json.loads(user.split("\n---\n", 1)[1]) if "\n---\n" in user else {}
        if payload.get("task") == "critique":
            entries = payload.get("entries", [])
            return json.dumps(
                {"locale": self.locale, "source_file": payload.get("source_file", ""), "entries": [],
                 "summary": {"total": len(entries), "flagged": 0, "critical": 0}},
                ensure_ascii=False,
            )
        rows = payload.get("rows", [])
        return json.dumps(
            {"rows": [{"key": r["key"], "target": r.get("target") or f"[{self.locale}] {r.get('source', '')}"} for r in rows]},
            ensure_ascii=False,
        )


class CallableProvider:
    """Adapt callable(system, user) -> str as legacy Provider."""

    def __init__(self, fn: Callable[[str, str], str]) -> None:
        self.fn = fn

    def complete(self, system: str, user: str) -> str:
        return self.fn(system, user)


@dataclass(frozen=True, slots=True)
class LegacyCallbacks:
    """Injected slice, critique validator and subinterpreter gate worker callables."""

    build_slice: Callable[..., list[dict[str, Any]]]
    verify_no_leak: Callable[..., None]
    write_slice: Callable[..., None]
    validate_critique: Callable[..., list[str]]
    gate_worker: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class LegacyPipelineOptions:
    """Parameter object driving run_legacy_pipeline."""

    src_field: str = "en"
    dst_field: str = "dst"
    key_field: str = "key"
    ph_style: str = "auto"
    tag_style: str = "auto"
    batch_size: int = 50
    fonts: Sequence[Path] = ()
    gate: dict[str, Any] | None = None


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


def system_prompt(agent: str, locale: str, bible: str, *, lean_api: bool = False) -> str:
    agent_body = load_agent_prompt(agent)
    playbook = load_playbook(locale)
    if lean_api:
        agent_body = compact_agent_for_api(agent_body)
        playbook = compact_playbook_for_api(playbook)
    parts = [agent_body, f"# Target locale: {locale}", playbook]
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


def phase0_preflight(state: PipelineState, rows: Sequence[Row], fonts: Sequence[Path]) -> None:
    """Prepare bible stub, preload locale rules and run optional in-process font preflight."""
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
    load_rules(state.locale)
    if fonts:
        src_path = state.workdir / "source.json"
        src_path.write_text(json.dumps([{"key": r.key, "source": r.src} for r in rows], ensure_ascii=False), encoding="utf-8")
        try:
            scan = CONTAINER.font_scanner.scan(src_path, "source", state.locale, list(fonts))
        except L10nError as exc:
            raise L10nError(f"font scan failed: {exc}") from exc
        state.say(f"Phase 0: font scan exit {scan['exit_code']}")


def phase1_pass1(state: PipelineState, rows: Sequence[Row], provider: Provider, batch_size: int) -> list[Path]:
    """Run legacy Pass 1 clean room batches."""
    system = system_prompt("game-culturalizer", state.locale, state.bible)
    outputs: list[Path] = []
    step = max(1, int(batch_size))
    for n, batch_tuple in enumerate(batched(rows, step), start=1):
        batch = list(batch_tuple)
        payload = {
            "task": "pass1", "locale": state.locale, "placeholder_style": state.ph_style, "tag_style": state.tag_style,
            "rows": [{"key": r.key, "source": r.src, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", "")} for r in batch],
        }
        user = (
            f"Translate the following clean-room batch into natural everyday {state.locale}. Reply with JSON "
            f"{{\"rows\": [{{\"key\", \"target\"}}]}} only.\n---\n" + json.dumps(payload, ensure_ascii=False)
        )
        reply = _extract_json(provider.complete(system, user))
        targets = {str(r["key"]): str(r.get("target", "")) for r in reply.get("rows", []) if isinstance(r, dict) and "key" in r}
        missing = [r.key for r in batch if r.key not in targets]
        if missing:
            raise L10nError(f"Pass 1 batch {n}: provider returned no target for keys {missing[:5]}")
        out = state.workdir / f"pass1_batch_{n:02d}.json"
        out.write_text(json.dumps([
            {"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""), state.src_field: r.src, state.locale: targets[r.key]}
            for r in batch
        ], ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(out)
        state.say(f"Phase 1: batch {n:02d} -> {out.name} ({len(batch)} rows)")
    return outputs


def phase2_critique_and_pass2(state: PipelineState, pass1_files: Sequence[Path], provider: Provider, cb: LegacyCallbacks) -> list[Path]:
    """Run legacy blind critique and Pass 2 rewrites using injected slice and validator callbacks."""
    critic_system = system_prompt("native-ear-critic", state.locale, "")
    editor_system = system_prompt("game-culturalizer", state.locale, state.bible)
    finals: list[Path] = []
    for n, p1 in enumerate(pass1_files, start=1):
        rows = load_table_options(p1, TableLoadOptions(state.src_field, state.locale, state.key_field, target_only=True))
        entries = cb.build_slice(rows, ["category", "speaker"], state.src_field, False, 0)
        full_rows = load_table_options(p1, TableLoadOptions(state.src_field, state.locale, state.key_field))
        cb.verify_no_leak(entries, full_rows, state.src_field)
        blind = state.workdir / f"blind_{state.locale}_{n:02d}.json"
        cb.write_slice(entries, blind, state.locale, p1.name)
        payload = {"task": "critique", "locale": state.locale, "source_file": blind.name, "entries": entries}
        user = (
            "Read ONLY these target strings as a native player. Return JSON with the critique schema "
            "(locale, source_file, entries[key, score, issue_type, reason, suggested], summary{total, flagged, critical}); "
            "list only score<5.\n---\n" + json.dumps(payload, ensure_ascii=False)
        )
        critique = _extract_json(provider.complete(critic_system, user))
        crit_path = state.workdir / f"critique_{state.locale}_{n:02d}.json"
        crit_path.write_text(json.dumps(critique, ensure_ascii=False, indent=2), encoding="utf-8")
        if (problems := cb.validate_critique(critique, {e["key"]: e["target"] for e in entries}, state.ph_style, state.tag_style, state.locale)):
            raise L10nError(f"critique {crit_path.name} is invalid: " + "; ".join(problems[:5]))
        state.say(f"Phase 2: batch {n:02d} blind slice {len(entries)} rows, critique flagged {critique['summary']['flagged']}")
        suggestions = {e["key"]: e for e in critique.get("entries", [])}
        rewritten: dict[str, str] = {}
        if suggestions:
            p2_rows = [{"key": r.key, "source": r.src, "target": r.dst, "critique": suggestions.get(r.key)} for r in full_rows if r.key in suggestions]
            user2 = (
                "Apply the valid native-ear suggestions while preserving placeholders, tags, spaces and glossary terms. "
                "Reply with JSON {\"rows\": [{\"key\", \"target\"}]}.\n---\n"
                + json.dumps({"task": "pass2", "locale": state.locale, "rows": p2_rows}, ensure_ascii=False)
            )
            reply = _extract_json(provider.complete(editor_system, user2))
            rewritten = {str(r["key"]): str(r.get("target", "")) for r in reply.get("rows", []) if isinstance(r, dict) and "key" in r}
        final = state.workdir / f"final_batch_{n:02d}.json"
        final.write_text(json.dumps([
            {"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""), state.src_field: r.src, state.locale: rewritten.get(r.key, r.dst)}
            for r in full_rows
        ], ensure_ascii=False, indent=2), encoding="utf-8")
        finals.append(final)
        state.say(f"Phase 2: batch {n:02d} Pass-2 rewrote {len(rewritten)} rows -> {final.name}")
    return finals


def run_phase3_gate(
    state: PipelineState, finals: Sequence[Path], fonts: Sequence[Path], gate_worker: Callable[[str], str],
) -> dict[str, Any]:
    """Run Phase 3 LQA + UI expansion across batches via subinterpreters plus in-process font scan."""
    load_rules(state.locale)
    summary: dict[str, Any] = {
        "errors": 0, "warnings": 0, "high": 0, "warn": 0,
        "missing_glyphs": 0, "full_width_fallbacks": 0, "glyphs_checked": bool(fonts),
    }
    specs = [
        json.dumps({
            "scripts_dir": str(SCRIPTS_DIR), "final_str": str(f), "workdir_str": str(state.workdir),
            "src_field": state.src_field, "locale": state.locale, "key_field": state.key_field,
            "ph_style": state.ph_style, "tag_style": state.tag_style,
            "forbid_chars": str(state.gate.get("forbid_chars", "")),
            "forbid_spaced_hyphen": bool(state.gate.get("forbid_spaced_hyphen", False)),
            "strict_whitespace": bool(state.gate.get("strict_whitespace", False)),
        })
        for f in finals
    ]
    if len(specs) >= 2:
        try:
            with InterpreterPoolExecutor(max_workers=min(len(specs), max(2, os.cpu_count() or 2))) as ex:
                batch_stats = list(ex.map(gate_worker, specs))
        except RuntimeError:
            batch_stats = [gate_worker(s) for s in specs]
    else:
        batch_stats = [gate_worker(s) for s in specs]
    for raw in batch_stats:
        counts = json.loads(raw)
        for key in ("errors", "warnings", "high", "warn"):
            summary[key] += int(counts[key])
    missing, wide = set(), set()
    if fonts:
        for f in finals:
            try:
                scan = CONTAINER.font_scanner.scan(f, state.locale, state.locale, list(fonts))
            except L10nError as exc:
                raise L10nError(f"font scan failed: {exc}") from exc
            missing |= {m["codepoint"] for m in scan.get("missing", [])}
            wide |= {m["codepoint"] for m in scan.get("full_width", [])}
    summary["missing_glyphs"] = len(missing)
    summary["full_width_fallbacks"] = len(wide)
    summary["passed"] = (
        summary["errors"] == 0 and summary["high"] == 0 and summary["missing_glyphs"] == 0
        and summary["full_width_fallbacks"] == 0 and not (state.gate.get("fail_on_warn") and summary["warnings"])
    )
    if not fonts:
        state.say("Phase 3: no --font given, the glyph scan did not run, the gate says nothing about missing glyphs")
    state.say(f"Phase 3: gate {'PASSED' if summary['passed'] else 'FAILED'}" + ("" if fonts else " (glyphs not checked)") + f" {summary}")
    return summary


def run_legacy_pipeline(
    input_path: Path, locale: str, workdir: Path, provider: Provider,
    opts: LegacyPipelineOptions, cb: LegacyCallbacks,
) -> dict[str, Any]:
    """Run legacy single critic Phase 0-3 flow."""
    workdir.mkdir(parents=True, exist_ok=True)
    raw_rows = load_table_options(input_path, TableLoadOptions(opts.src_field, opts.src_field, opts.key_field, target_only=True))
    rows = [Row(r.key, r.dst, "", r.meta) for r in raw_rows]
    if not rows:
        raise L10nError(f"{input_path}: no rows to localize")
    state = PipelineState(locale, workdir, opts.src_field, opts.dst_field, opts.key_field, opts.ph_style, opts.tag_style, gate=dict(opts.gate or {}))
    phase0_preflight(state, rows, opts.fonts)
    p1 = phase1_pass1(state, rows, provider, opts.batch_size)
    finals = phase2_critique_and_pass2(state, p1, provider, cb)
    summary = run_phase3_gate(state, finals, opts.fonts, cb.gate_worker)
    return {"passed": summary["passed"], "summary": summary, "log": state.log, "finals": [str(f) for f in finals]}
