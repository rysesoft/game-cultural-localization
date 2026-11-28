"""Builder Pattern orchestrating Phase 0 through Phase 3 via segregated PipelineHooks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from gcl.application.jury.policy import EscalationTally
from gcl.domain.errors import L10nError
from gcl.ports.context import BlindContextView, WriterContextView

from .config import RESUME_FILE, JuryPipelineOptions, PipelineHooks, PipelineState
from .stages import build_pass1_payload_rows, send_broken_lines_to_pass2, write_final_batch, write_verdict_doc

__layer__ = "application"
__pattern__ = "Builder"
__owns__ = "stepwise Phase 0 to Phase 3 pipeline assembly with clean teardown"


@dataclass
class _RunEnv:
    """Internal runtime bundle assembled by LocalizationPipelineBuilder.prepare()."""

    locale: str
    workdir: Path
    router: Any
    opts: JuryPipelineOptions
    state: PipelineState
    rows: List[Any]
    pack_dir: Path
    level: str
    tm: Any
    wctx: Optional[WriterContextView]
    bctx: Optional[BlindContextView]
    pass1_system: str
    threshold: Optional[float]
    memo: Any
    tally: EscalationTally


@dataclass(frozen=True)
class _BatchArtifacts:
    """Intermediate per batch Phase 1 and Phase 2 jury outputs passed into Phase 2 rewrite."""

    n: int
    tag: str
    p1: Path
    p1_rows: List[Dict[str, Any]]
    vpath: Path
    verdict_doc: Dict[str, Any]
    res: Dict[str, Any]
    rec_start: int


class LocalizationPipelineBuilder:
    """Builds and runs Phase 0 to Phase 3 jury culturalization pipeline."""

    def __init__(self, hooks: PipelineHooks) -> None:
        self._h = hooks

    def run(self, input_path: Path, locale: str, workdir: Path, router: Any, opts: JuryPipelineOptions) -> Dict[str, Any]:
        env = self._prepare(input_path, locale, workdir, router, opts)
        finals: List[Path] = []
        batches: List[Dict[str, Any]] = []
        halted: Optional[Dict[str, Any]] = None
        try:
            for i in range(0, len(env.rows), opts.batch_size):
                batch_info, halted_info, final_path = self._run_batch(env, i // opts.batch_size + 1, env.rows[i:i + opts.batch_size])
                batches.append(batch_info)
                if final_path is not None:
                    finals.append(final_path)
                if halted_info is not None:
                    halted = halted_info
                    break
        finally:
            if env.tm is not None:
                env.tm.close()
        return self._finalize(env, finals, batches, halted)

    def _prepare(self, input_path: Path, locale: str, workdir: Path, router: Any, opts: JuryPipelineOptions) -> _RunEnv:
        workdir.mkdir(parents=True, exist_ok=True)
        rows = self._h.load_source_rows(input_path, opts.src_field, opts.key_field)
        if not rows:
            raise L10nError(f"{input_path}: no rows to localize")
        if opts.draft_field and not any(str(r.meta.get(opts.draft_field) or "").strip() for r in rows):
            raise L10nError(f"{input_path}: no row holds a draft in the column '{opts.draft_field}'")
        state = PipelineState(locale, workdir, opts.src_field, opts.src_field, opts.key_field, opts.ph_style, opts.tag_style, gate=dict(opts.gate or {}))
        self._h.preflight(state, rows, list(opts.fonts))
        packs = Path(opts.langpack_dir) if opts.langpack_dir else self._h.default_langpack_dir()
        pack_dir = packs / locale
        level, version = self._h.trust_level(pack_dir)
        state.say(f"Phase 0: trust level {level}" + (f", language pack {version}" if version else ", no language pack"))
        tm = self._open_tm(opts.tm_path, state)
        pass1_system, wctx, bctx = self._prepare_prompts(locale, rows, pack_dir, state, opts)
        threshold, _ = self._h.load_threshold(locale, packs)
        memo = self._h.open_memo(workdir / RESUME_FILE) if opts.resume else None
        if memo is not None and len(memo):
            state.say(f"Phase 0: resuming, {len(memo)} finished model batches in {RESUME_FILE}")
        return _RunEnv(locale, workdir, router, opts, state, rows, pack_dir, level, tm, wctx, bctx, pass1_system, threshold, memo, EscalationTally())

    def _open_tm(self, tm_path: Optional[Path], state: PipelineState) -> Any:
        if tm_path is None:
            return None
        if not Path(tm_path).is_file():
            raise L10nError(f"translation memory not found: {tm_path}")
        tm = self._h.open_tm(Path(tm_path))
        state.say(f"Phase 0: translation memory {Path(tm_path).name}")
        return tm

    def _prepare_prompts(
        self, locale: str, rows: List[Any], pack_dir: Path, state: PipelineState, opts: JuryPipelineOptions,
    ) -> tuple:
        regs = sorted({self._h.register_of(r) for r in rows})
        warm = ""
        if pack_dir.is_dir() and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
            sample = self._h.load_warmup_sample(pack_dir, regs, 40, opts.seed)
            warm = self._h.render_warmup(sample)
            state.say(f"Phase 0: warm-up {len(sample)} lines for {', '.join(regs)}")
        pass1_system = self._h.system_prompt("game-culturalizer", locale, state.bible)
        if warm:
            pass1_system += "\n\n# Native warm-up (read aloud before translating)\n" + warm
        wctx, bctx = self._h.load_context_views(Path(opts.context_map), locale) if opts.context_map is not None else (None, None)
        if wctx is not None:
            pass1_system = wctx.build_system(pass1_system)
            state.say(f"Phase 0: context map {wctx.source_name}, line notes for {getattr(wctx, 'note_count', 0)} keys" + (", " + locale + " appendix" if wctx.has_appendix else ""))
        else:
            state.say("Phase 0: no context map given, every later step works without the game's context")
        return pass1_system, wctx, bctx

    def _run_batch(self, env: _RunEnv, n: int, batch: List[Any]) -> tuple:
        tag = f"{env.locale}_{n:02d}"
        rec_start = len(env.router.budget.records)
        p1, p1_rows, targets = self._phase1_batch(env, n, batch)
        verdict_doc, vpath, res = self._phase2_jury(env, n, tag, p1, batch, targets)
        batch_info: Dict[str, Any] = {"batch": n, "verdicts": vpath.name, "stats": res["stats"]}
        if res["halted"]:
            env.state.say(f"Phase 2: batch {n:02d} STOPPED by the budget cap at {res['halted']['stage']}. {res['halted']['reason']}")
            sources_map = {r.key: {"en": r.src, "target": targets[r.key]} for r in batch}
            self._h.write_change_report(verdict_doc, env.locale, n, tag, env.workdir, None, sources_map, env.pack_dir, self._h.batch_budget(env.router, rec_start))
            batch_info["report"] = f"changes_{tag}.md"
            return batch_info, {"batch": n, **res["halted"]}, None
        art = _BatchArtifacts(n, tag, p1, p1_rows, vpath, verdict_doc, res, rec_start)
        final, rep, rpath = self._phase2_rewrite(env, art)
        batch_info.update({"rewrites": rpath.name, "final": final.name, "report": f"changes_{tag}.md", "unresolved": len(rep["unresolved"])})
        return batch_info, None, final

    def _phase1_batch(self, env: _RunEnv, n: int, batch: List[Any]) -> tuple:
        opts = env.opts
        payload_rows = build_pass1_payload_rows(batch, env.locale, self._h.register_of, env.tm, env.wctx)
        drafts = {r.key: str(r.meta.get(opts.draft_field) or "") for r in batch if str(r.meta.get(opts.draft_field) or "").strip()} if opts.draft_field else {}
        todo = [pr for pr in payload_rows if pr["key"] not in drafts]
        targets = dict(drafts)
        if todo:
            targets.update(self._h.translate_rows(
                env.router.for_role("pass1"), todo, env.locale, task="pass1", system=env.pass1_system, memo=env.memo,
                extra={"placeholder_style": opts.ph_style, "tag_style": opts.tag_style}, workers=opts.workers,
            ))
        if opts.draft_field:
            env.state.say(f"Phase 1: batch {n:02d} keeps {len(drafts)} drafts of '{opts.draft_field}' as they are, translates {len(todo)} empty rows")
        p1 = env.workdir / f"pass1_batch_{n:02d}.json"
        p1_rows = [{"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""), opts.src_field: r.src, env.locale: targets[r.key]} for r in batch]
        p1.write_text(json.dumps(p1_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        rag = sum(1 for pr in payload_rows if pr.get("tm"))
        env.state.say(f"Phase 1: batch {n:02d} -> {p1.name} ({len(batch)} rows" + (f", TM neighbours for {rag}" if env.tm is not None else "") + ")")
        return p1, p1_rows, targets

    def _phase2_jury(self, env: _RunEnv, n: int, tag: str, p1: Path, batch: List[Any], targets: Dict[str, str]) -> tuple:
        opts = env.opts
        blind = env.workdir / f"blind_{tag}.json"
        jentries = self._h.prepare_blind_slice(p1, blind, env.locale, opts.src_field, opts.key_field)
        critic_system, info = self._h.build_critic_prompt(env.locale, jentries, env.pack_dir, opts.seed)
        if env.bctx is not None:
            info["context_map"], info["context_lines"] = env.bctx.source_name, env.bctx.enrich_entries(jentries)
            critic_system = env.bctx.build_system(critic_system)
        src_by_key = {r.key: r.src for r in batch}
        rt_cfg = env.router.config.roundtrip

        def rt_fn(lines: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            rws = [{"key": e["key"], "en": src_by_key.get(e["key"], ""), "target": e["target"], "register": e["register"]} for e in lines]
            return self._h.roundtrip_evidence(
                rws, env.locale, env.router.for_role("roundtrip"), min_words=int(rt_cfg["min_words"]),
                registers=rt_cfg["registers"], threshold=env.threshold, workers=opts.workers, memo=env.memo,
            )

        def tm_fn(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
            assert env.tm is not None
            return env.tm.neighbors(env.locale, src_by_key.get(entry["key"], entry["target"]), category=str(entry.get("category") or ""),
                                    speaker=str(entry.get("speaker") or ""), exclude_key=entry["key"])

        delib = self._h.make_deliberator(env.router, env.locale, critic_system) if opts.deliberation else None
        res = self._h.run_jury(
            jentries, env.locale, env.router, system=critic_system, budget_caps=opts.budget_caps, roundtrip_fn=rt_fn,
            tally=env.tally, memo=env.memo, tm_lookup=tm_fn if env.tm is not None else None, deliberator=delib, workers=opts.workers,
        )
        broken = send_broken_lines_to_pass2(res, targets, src_by_key, opts.ph_style, opts.tag_style, self._h.parity)
        if broken:
            env.state.say(f"Phase 2: batch {n:02d} {broken} lines break placeholder or tag parity with the source, sent to Pass 2")
        vpath = env.workdir / f"verdicts_{tag}.json"
        verdict_doc = write_verdict_doc(vpath, env.locale, p1.name, info, res, env.router.notes)
        st = res["stats"]["status"]
        env.state.say(f"Phase 2: batch {n:02d} jury " + ", ".join(f"{k} {v}" for k, v in st.items() if v) + f" -> {vpath.name}")
        return verdict_doc, vpath, res

    def _phase2_rewrite(self, env: _RunEnv, art: _BatchArtifacts) -> tuple:
        opts = env.opts
        sources = self._h.load_pass2_sources(art.p1, opts.src_field, env.locale, opts.key_field)
        regs = sorted({self._h.register_of(r) for r in env.rows})
        p2_system, pick_system = self._h.build_pass2_systems(env.locale, env.pack_dir, regs, opts.seed)
        rw = self._h.run_pass2(art.res["verdicts"], sources, env.locale, env.router, opts, p2_system, pick_system, env.wctx, env.bctx, env.memo, art.p1.name)
        rpath = env.workdir / f"rewrites_{art.tag}.json"
        rpath.write_text(json.dumps({"locale": env.locale, "source_file": art.p1.name, "verdicts": art.vpath.name, **rw, "notes": env.router.notes}, ensure_ascii=False, indent=2), encoding="utf-8")
        final = env.workdir / f"final_batch_{art.n:02d}.json"
        applied_n = write_final_batch(final, art.p1_rows, rw, art.res, env.locale)
        kept = sum(1 for l in rw["lines"] if not l["valid"])
        env.state.say(f"Phase 2: batch {art.n:02d} Pass 2 rewrote {applied_n} rows, {kept} kept the old text -> {final.name}")
        rep = self._h.write_change_report(art.verdict_doc, env.locale, art.n, art.tag, env.workdir, {"lines": rw["lines"]}, {}, env.pack_dir, self._h.batch_budget(env.router, art.rec_start))
        env.state.say(f"Phase 2: batch {art.n:02d} change report changes_{art.tag}.md ({rep['changed']} changes, {len(rep['unresolved'])} unresolved)")
        return final, rep, rpath

    def _finalize(self, env: _RunEnv, finals: List[Path], batches: List[Dict[str, Any]], halted: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if halted:
            summary: Dict[str, Any] = {
                "errors": 0, "warnings": 0, "high": 0, "warn": 0, "missing_glyphs": 0,
                "full_width_fallbacks": 0, "passed": False, "halted": True,
            }
            env.state.say("Phase 3: skipped, the run stopped at the budget cap")
        else:
            summary = self._h.phase3_gate(env.state, finals, list(env.opts.fonts))
        unresolved = sum(b.get("unresolved", 0) for b in batches)
        if unresolved:
            env.state.say(f"Phase 2: {unresolved} unresolved line(s) wait for a developer decision")
        passed = bool(summary["passed"]) and not halted and unresolved == 0
        return {
            "passed": passed, "flow": "jury", "summary": summary, "log": env.state.log,
            "finals": [str(f) for f in finals], "batches": batches, "halted": halted,
            "unresolved": unresolved, "trust_level": env.level, "notes": list(env.router.notes),
        }
