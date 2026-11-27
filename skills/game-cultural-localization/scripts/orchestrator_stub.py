#!/usr/bin/env python3
"""API-independent orchestration of the 4-phase culturalization pipeline.

Two flows share Phase 0 and Phase 3. The agent prompt bodies come from agents/*.md
(frontmatter stripped) and references/<locale>.md, so any LLM API can serve them.

Jury flow (default since 2.2). Model access through providers/ and providers.config.json.
  Phase 0  pre-flight: locale, rules, bible, optional font scan, language pack trust level,
           warm-up sample, translation memory
  Phase 1  Pass 1 with the 'pass1' model, warm-up in the system prompt, the closest approved
           TM lines per row (RAG)
  Phase 2  blind slice -> J1/J2/J3 mixed-family jury (+ deliberation) -> Pass 2 with three
           candidates and a blind J1 pick -> validate_critique -> change report for the developer
  Phase 3  automated LQA gate (lqa_linter + ui_expansion_checker [+ font_glyph_scanner])
  --dry-run uses the deterministic fake provider (no key, no network), --live the real APIs
  (keys from ANTHROPIC_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY).

    python orchestrator_stub.py --dry-run --locale tr-TR --input strings.json --workdir out/ --json

Legacy flow (2.1). One single critic through any complete(system, user) -> str callable:

    python orchestrator_stub.py --provider mymodule:complete --locale de-DE --input strings.json --workdir out/

run_pipeline(..., DryRunProvider(locale)) keeps the old offline flow for code callers.

Exit codes: 0 pipeline passed, 1 a phase failed (gate findings, invalid critique, budget cap,
unresolved jury lines), 2 usage / input error.  Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

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
RESUME_FILE = "model_batches.json"  # finished model batches of the jury flow, kept in the workdir
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
        self.gate: Dict[str, Any] = {}  # forbid_chars, forbid_spaced_hyphen, strict_whitespace, fail_on_warn of l10n.config.json

    def say(self, msg: str) -> None:
        self.log.append(msg)


def phase0_preflight(state: PipelineState, rows: List[Row], fonts: List[Path]) -> None:
    state.say(f"Phase 0: locale {state.locale}, {len(rows)} source rows")
    bible = state.workdir / f"{state.locale}_BIBLE.md"
    stub = f"# {state.locale} localization bible\n\n(stub created by orchestrator_stub; fill terminology, registers per archetype A1-A5, ledger)\n"
    if bible.is_file():
        text = bible.read_text(encoding="utf-8-sig")
        if text == stub:  # an untouched stub carries no decision, and it would change the Pass 1 prompt between runs
            state.say(f"Phase 0: bible {bible.name} is still the empty stub, fill it to hand the translators the project's decisions")
        else:
            state.bible = text
            state.say(f"Phase 0: bible found ({bible.name})")
    else:
        bible.write_text(stub, encoding="utf-8")
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
            cmd = [sys.executable, str(SCRIPTS_DIR / "font_glyph_scanner.py"), "--input", str(f), "--dst-field", state.locale]
            for font in fonts:
                cmd += ["--font", str(font)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 2:
                raise L10nError("font scan failed: " + proc.stderr.strip())
            summary["missing_glyphs"] += 1 if proc.returncode == 1 else 0
    summary["passed"] = (summary["errors"] == 0 and summary["high"] == 0 and summary["missing_glyphs"] == 0
                         and not (state.gate.get("fail_on_warn") and summary["warnings"]))
    state.say(f"Phase 3: gate {'PASSED' if summary['passed'] else 'FAILED'} {summary}")
    return summary


def run_pipeline(input_path: Path, locale: str, workdir: Path, provider: Provider, *, src_field: str = "en", dst_field: str = "dst",
                 key_field: str = "key", ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50, fonts: Optional[List[Path]] = None,
                 gate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run Phase 0-3 and return a result dict ({'passed': bool, 'log': [...], 'summary': {...}})."""
    workdir.mkdir(parents=True, exist_ok=True)
    # Source-only input: the src_field column is loaded as 'dst' (target_only) and moved to Row.src.
    rows = [Row(r.key, r.dst, "", r.meta) for r in load_table(input_path, src_field, src_field, key_field, target_only=True)]
    if not rows:
        raise L10nError(f"{input_path}: no rows to localize")
    state = PipelineState(locale, workdir, src_field, dst_field, key_field, ph_style, tag_style)
    state.gate = dict(gate or {})
    phase0_preflight(state, rows, fonts or [])
    p1 = phase1_pass1(state, rows, provider, batch_size)
    finals = phase2_critique_and_pass2(state, p1, provider)
    summary = phase3_gate(state, finals, fonts or [])
    return {"passed": summary["passed"], "summary": summary, "log": state.log, "finals": [str(f) for f in finals]}


# --------------------------------------------------------------------------- #
# Jury flow (2.2)
# --------------------------------------------------------------------------- #

def _register(row: Row) -> str:
    from build_language_pack import infer_register
    reg = str(row.meta.get("register") or "")
    return reg if reg else infer_register(str(row.meta.get("category") or ""), row.src, "game")


def _batch_budget(router: Any, start: int) -> Optional[Dict[str, Any]]:
    """Budget summary of the model calls since record `start` of the router's budget log, the calls of one batch."""
    import budget_report
    recs = router.budget.records[start:]
    if not recs:
        return None
    tot = budget_report.aggregate(recs, [], budget_report.price_table(router.config))[0]
    return {k: tot[k] for k in ("calls", "errors", "input_tokens", "output_tokens", "latency_ms", "cost_usd", "priced", "unpriced_models")}


def _write_report(report_changes: Any, verdict_doc: Dict[str, Any], locale: str, n: int, tag: str, workdir: Path,
                  rewrites: Optional[Dict[str, Any]], sources: Dict[str, Dict[str, str]], pack_dir: Path,
                  budget: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rep = report_changes.build_report(verdict_doc, locale, f"{n:02d}", rewrites=rewrites, sources=sources, pack_dir=pack_dir, budget=budget)
    (workdir / f"changes_{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / f"changes_{tag}.md").write_text(report_changes.render_markdown(rep), encoding="utf-8")
    return rep


def run_jury_pipeline(input_path: Path, locale: str, workdir: Path, router: Any, *, src_field: str = "en", key_field: str = "key",
                      ph_style: str = "auto", tag_style: str = "auto", batch_size: int = 50, fonts: Optional[List[Path]] = None,
                      langpack_dir: Optional[Path] = None, tm_path: Optional[Path] = None, deliberation: bool = True,
                      budget_caps: bool = True, candidates: int = 3, seed: int = 1234, workers: int = 1,
                      context_map: Optional[Path] = None, resume: bool = True, gate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Phase 0-3 with the multi-family jury. Returns {'passed', 'flow', 'summary', 'log', 'finals', 'batches', 'halted', ...}.

    workers > 1 sends model calls in parallel inside Pass 1, the jury and Pass 2, the result does not change.
    context_map is CONTEXT_MAP.md of the game. Pass 1 and Pass 2 read it with the locale appendix and the full
    line notes, the jury and the blind pickers read the map and the neutral line fields only.
    """
    from build_context_map import load_context
    from llm_tasks import BatchMemo
    import deliberate
    import jury
    import pass2_rewrite
    import report_changes
    from build_language_pack import LANGPACK_DIR
    from llm_tasks import translate_rows
    from roundtrip_check import load_threshold, roundtrip_evidence
    from warmup_loader import load_warmup, render_warmup

    workdir.mkdir(parents=True, exist_ok=True)
    rows = [Row(r.key, r.dst, "", r.meta) for r in load_table(input_path, src_field, src_field, key_field, target_only=True)]
    if not rows:
        raise L10nError(f"{input_path}: no rows to localize")
    state = PipelineState(locale, workdir, src_field, src_field, key_field, ph_style, tag_style)
    state.gate = dict(gate or {})
    phase0_preflight(state, rows, fonts or [])
    packs = Path(langpack_dir) if langpack_dir else LANGPACK_DIR
    pack_dir = packs / locale
    level, version = report_changes.trust_level(pack_dir)
    state.say(f"Phase 0: trust level {level}" + (f", language pack {version}" if version else ", no language pack"))
    tm = None
    if tm_path is not None:
        from tm import TranslationMemory
        if not Path(tm_path).is_file():
            raise L10nError(f"translation memory not found: {tm_path}")
        tm = TranslationMemory(Path(tm_path))
        state.say(f"Phase 0: translation memory {Path(tm_path).name}")
    regs = sorted({_register(r) for r in rows})
    warm = ""
    if pack_dir.is_dir() and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
        sample = load_warmup(pack_dir, regs, 40, seed)
        warm = render_warmup(sample)
        state.say(f"Phase 0: warm-up {len(sample)} lines for {', '.join(regs)}")
    pass1_system = system_prompt("game-culturalizer", locale, state.bible)
    if warm:
        pass1_system += "\n\n# Native warm-up (read aloud before translating)\n" + warm
    ctx = load_context(Path(context_map), locale) if context_map is not None else None
    if ctx is not None:
        pass1_system = ctx.system(pass1_system, writer=True)
        state.say(f"Phase 0: context map {ctx.source}, line notes for {len(ctx.notes)} keys"
                  + (f", {locale} appendix" if ctx.appendix else ""))
    else:
        state.say("Phase 0: no context map given, every later step works without the game's context")
    rt_cfg = router.config.roundtrip
    threshold, _thr_src = load_threshold(locale, packs)
    finals: List[Path] = []
    batches: List[Dict[str, Any]] = []
    halted: Optional[Dict[str, Any]] = None
    tally = jury.EscalationTally()  # the budget caps read every line judged in this run, not one batch
    # every finished batch of every model call is kept in the workdir, the same command resumes a stopped run
    memo = BatchMemo(workdir / RESUME_FILE) if resume else None
    if memo is not None and len(memo):
        state.say(f"Phase 0: resuming, {len(memo)} finished model batches in {RESUME_FILE}")
    try:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            n = i // batch_size + 1
            tag = f"{locale}_{n:02d}"
            rec_start = len(router.budget.records)  # the change report of this batch gets the cost of its own calls
            # Phase 1 ------------------------------------------------------- #
            payload_rows = []
            for r in batch:
                pr: Dict[str, Any] = {"key": r.key, "source": r.src, "register": _register(r)}
                for k in ("category", "speaker", "archetype", "max_chars"):
                    if r.meta.get(k) not in (None, ""):
                        pr[k] = r.meta[k]
                if tm is not None:
                    nb = tm.neighbors(locale, r.src, category=str(r.meta.get("category") or ""), speaker=str(r.meta.get("speaker") or ""), k=3)
                    if nb:
                        pr["tm"] = [{"source": x["src"], "target": x["dst"], "similarity": x["similarity"]} for x in nb]
                if ctx is not None and ctx.line(r.key, writer=True):
                    pr["context"] = ctx.line(r.key, writer=True)
                payload_rows.append(pr)
            targets = translate_rows(router.for_role("pass1"), payload_rows, locale, task="pass1", system=pass1_system, memo=memo,
                                     extra={"placeholder_style": ph_style, "tag_style": tag_style}, workers=workers)
            p1 = workdir / f"pass1_batch_{n:02d}.json"
            p1_rows = [{"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""),
                        src_field: r.src, locale: targets[r.key]} for r in batch]
            p1.write_text(json.dumps(p1_rows, ensure_ascii=False, indent=2), encoding="utf-8")
            rag = sum(1 for pr in payload_rows if pr.get("tm"))
            state.say(f"Phase 1: batch {n:02d} -> {p1.name} ({len(batch)} rows" + (f", TM neighbours for {rag}" if tm is not None else "") + ")")
            # Phase 2: blind slice + jury ----------------------------------- #
            slice_rows = load_table(p1, src_field, locale, key_field, target_only=True)
            entries = make_blind_slice.build_slice(slice_rows, ["category", "speaker"], src_field, False, 0)
            make_blind_slice.verify_no_leak(entries, load_table(p1, src_field, locale, key_field), src_field)
            blind = workdir / f"blind_{tag}.json"
            make_blind_slice.write_slice(entries, blind, locale, p1.name)
            jentries, _sf = jury.load_blind_slice(blind)
            critic_system, info = jury.build_system_prompt(locale, jentries, pack_dir, warmup=True, warmup_count=40, shots=6, seed=seed)
            if ctx is not None:
                info["context_map"], info["context_lines"] = ctx.source, ctx.enrich(jentries)
                critic_system = ctx.system(critic_system)
            src_by_key = {r.key: r.src for r in batch}

            def rt_fn(lines: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
                rws = [{"key": e["key"], "en": src_by_key.get(e["key"], ""), "target": e["target"], "register": e["register"]} for e in lines]
                return roundtrip_evidence(rws, locale, router.for_role("roundtrip"), min_words=int(rt_cfg["min_words"]),
                                          registers=rt_cfg["registers"], threshold=threshold, workers=workers, memo=memo)

            def tm_fn(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
                return tm.neighbors(locale, src_by_key.get(entry["key"], entry["target"]), category=str(entry.get("category") or ""),
                                    speaker=str(entry.get("speaker") or ""), exclude_key=entry["key"])
            res = jury.run_jury(jentries, locale, router, system=critic_system, budget_caps=budget_caps, roundtrip_fn=rt_fn, tally=tally, memo=memo,
                                tm_lookup=tm_fn if tm is not None else None,
                                deliberator=deliberate.make_deliberator(router, locale, critic_system) if deliberation else None,
                                workers=workers)
            verdict_doc = {"locale": locale, "source_file": p1.name, "langpack_version": info.get("langpack_version"),
                           "prompt": {"warmup_lines": info.get("warmup_lines", 0), "shots": info.get("shots", 0),
                                      "context_map": info.get("context_map"), "context_lines": info.get("context_lines", 0)},
                           "stats": res["stats"], "halted": res["halted"], "verdicts": res["verdicts"], "pending": res["pending"],
                           "notes": router.notes}
            vpath = workdir / f"verdicts_{tag}.json"
            vpath.write_text(json.dumps(verdict_doc, ensure_ascii=False, indent=2), encoding="utf-8")
            st = res["stats"]["status"]
            state.say(f"Phase 2: batch {n:02d} jury " + ", ".join(f"{k} {v}" for k, v in st.items() if v) + f" -> {vpath.name}")
            batch_info: Dict[str, Any] = {"batch": n, "verdicts": vpath.name, "stats": res["stats"]}
            if res["halted"]:
                halted = {"batch": n, **res["halted"]}
                state.say(f"Phase 2: batch {n:02d} STOPPED by the budget cap at {res['halted']['stage']}. {res['halted']['reason']}")
                _write_report(report_changes, verdict_doc, locale, n, tag, workdir, None,
                              {r.key: {"en": r.src, "target": targets[r.key]} for r in batch}, pack_dir, _batch_budget(router, rec_start))
                batch_info["report"] = f"changes_{tag}.md"
                batches.append(batch_info)
                break
            # Phase 2: Pass 2 candidates + blind J1 pick + validate_critique -- #
            sources = pass2_rewrite.load_source_table(p1, src_field, locale, key_field, locale)
            p2_system, pick_system = pass2_rewrite.build_systems(locale, pack_dir, regs, warmup=True, seed=seed)
            rw = pass2_rewrite.rewrite_lines(res["verdicts"], sources, locale, router, pass2_system=p2_system, pick_system=pick_system,
                                             n=candidates, seed=seed, ph_style=ph_style, tag_style=tag_style, source_file=p1.name,
                                             workers=workers, context=ctx, memo=memo)
            rpath = workdir / f"rewrites_{tag}.json"
            rpath.write_text(json.dumps({"locale": locale, "source_file": p1.name, "verdicts": vpath.name, **rw, "notes": router.notes},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
            status_by_key = {v["key"]: v["status"] for v in res["verdicts"]}
            applied = {l["key"]: l["new"] for l in rw["lines"] if l["valid"] and status_by_key.get(l["key"]) != "unresolved"}
            final = workdir / f"final_batch_{n:02d}.json"
            final.write_text(json.dumps([{**row, locale: applied.get(row["key"], row[locale])} for row in p1_rows], ensure_ascii=False, indent=2),
                             encoding="utf-8")
            finals.append(final)
            kept = sum(1 for l in rw["lines"] if not l["valid"])
            state.say(f"Phase 2: batch {n:02d} Pass 2 rewrote {len(applied)} rows, {kept} kept the old text -> {final.name}")
            rep = _write_report(report_changes, verdict_doc, locale, n, tag, workdir, {"lines": rw["lines"]}, {}, pack_dir,
                                _batch_budget(router, rec_start))
            state.say(f"Phase 2: batch {n:02d} change report changes_{tag}.md ({rep['changed']} changes, {len(rep['unresolved'])} unresolved)")
            batch_info.update({"rewrites": rpath.name, "final": final.name, "report": f"changes_{tag}.md", "unresolved": len(rep["unresolved"])})
            batches.append(batch_info)
    finally:
        if tm is not None:
            tm.close()
    if halted:
        summary: Dict[str, Any] = {"errors": 0, "warnings": 0, "high": 0, "warn": 0, "missing_glyphs": 0, "passed": False, "halted": True}
        state.say("Phase 3: skipped, the run stopped at the budget cap")
    else:
        summary = phase3_gate(state, finals, fonts or [])
    unresolved = sum(b.get("unresolved", 0) for b in batches)
    if unresolved:
        state.say(f"Phase 2: {unresolved} unresolved line(s) wait for a developer decision")
    passed = bool(summary["passed"]) and not halted and unresolved == 0
    return {"passed": passed, "flow": "jury", "summary": summary, "log": state.log, "finals": [str(f) for f in finals],
            "batches": batches, "halted": halted, "unresolved": unresolved, "trust_level": level, "notes": list(router.notes)}


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
    ap.add_argument("--font", action="append", default=[], help="Font file(s) for the glyph gate (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="Jury flow with the offline fake provider (no API key, no network)")
    ap.add_argument("--live", action="store_true", help="Jury flow with the real APIs (keys from the environment)")
    ap.add_argument("--provider", help="Legacy single-critic flow: Python path 'module:function' of a complete(system, user) -> str callable")
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl (default: <workdir>/budget.jsonl)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs (default: the skill's langpack/)")
    ap.add_argument("--tm", default=None, help="Translation memory (tm.py SQLite) for Pass 1 RAG and jury evidence")
    ap.add_argument("--context-map", default=None, help="CONTEXT_MAP.md of the game (Phase 0 step 0), with line_notes.json and CONTEXT_MAP.<locale>.md next to it")
    ap.add_argument("--no-deliberation", action="store_true", help="Leave J3 disagreements unresolved")
    ap.add_argument("--no-resume", action="store_true", help=f"Ignore the finished model batches kept in <workdir>/{RESUME_FILE} and call every model again")
    ap.add_argument("--no-budget-caps", action="store_true", help="Do not stop at the J2 or J3 escalation cap")
    ap.add_argument("--candidates", type=int, default=3, help="Pass 2 candidates per flagged line (default 3)")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of warm-up, few-shots and candidate order (default 1234)")
    ap.add_argument("--workers", type=int, default=4, help="Model calls in flight per step of the jury flow (default 4, 1 = one call at a time); "
                                                         "combine with a larger --batch-size such as 200 so every step has enough batches")
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
    # the Phase 3 gate applies the project's punctuation rules of l10n.config.json, as the methodology's gate commands do
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
            resume=not args.no_resume, gate=gate)
        exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
        text = "\n".join([f"Orchestrator run (jury flow, {'dry run' if args.dry_run else 'live'}):"] + ["  " + l for l in result["log"]]
                         + [f"  NOTE: {n}" for n in result["notes"]] + [f"  Exit code: {exit_code}"])
        payload = {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}
        emit_report(text, payload, args.json, args.output)
        return exit_code
    if not args.provider:
        raise L10nError("choose --dry-run (offline fake providers), --live (real APIs, keys from ANTHROPIC_API_KEY, GOOGLE_API_KEY, "
                        "DEEPSEEK_API_KEY) or --provider module:function (legacy single-critic flow)")
    mod_name, _, fn_name = args.provider.partition(":")
    if not fn_name:
        raise L10nError("--provider must be 'module:function'")
    import importlib
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
    except (ImportError, AttributeError) as exc:
        raise L10nError(f"cannot load provider {args.provider}: {exc}")
    provider: Provider = CallableProvider(fn)
    result = run_pipeline(
        Path(args.input), locale, Path(args.workdir), provider, src_field=src_field, dst_field=src_field,
        key_field=key_field, ph_style=ph_style, tag_style=tag_style, batch_size=args.batch_size, fonts=[Path(f) for f in args.font],
        gate=gate,
    )
    result["flow"] = "legacy"
    exit_code = EXIT_OK if result["passed"] else EXIT_FINDINGS
    text = "\n".join(["Orchestrator run (legacy flow):"] + ["  " + l for l in result["log"]] + [f"  Exit code: {exit_code}"])
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "workdir": str(args.workdir), **result, "exit_code": exit_code}
    emit_report(text, payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
