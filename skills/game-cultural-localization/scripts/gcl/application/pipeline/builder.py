"""Builder Pattern orchestrating Phase 0 through Phase 3 via segregated PipelineHooks."""

import json
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from gcl.application.jury.policy import EscalationTally
from gcl.domain.errors import L10nError
from gcl.ports.context import BlindContextView, WriterContextView

from .config import RESUME_FILE, JuryPipelineOptions, PipelineHooks, PipelineState
from .dedup import (
    DedupEnv, Pass1BatchPlan, expand_jury_result, expand_pass1_targets, expand_pass2_rewrites,
    plan_jury_batch, plan_pass1_batch,
)
from .stages import send_broken_lines_to_pass2, write_final_batch, write_verdict_doc

__layer__ = "application"
__pattern__ = "Builder"
__owns__ = "stepwise Phase 0 to Phase 3 pipeline assembly with clean teardown"

ITEMS_RESUME_FILE = "model_items.json"


@dataclass(frozen=True, slots=True)
class _PromptBundle:
    """Run wide stable prompts assembled once per Phase 0 preparation."""

    pass1_system: str
    wctx: WriterContextView | None
    bctx: BlindContextView | None
    critic_base: str
    critic_system: str
    critic_info: dict[str, Any]
    p2_system: str


@dataclass(slots=True)
class _RunEnv:
    """Internal runtime bundle assembled by LocalizationPipelineBuilder.prepare()."""

    locale: str
    workdir: Path
    router: Any
    opts: JuryPipelineOptions
    state: PipelineState
    rows: list[Any]
    pack_dir: Path
    level: str
    tm: Any
    prompts: _PromptBundle
    threshold: float | None
    memo: Any
    item_memo: Any
    tally: EscalationTally


@dataclass(frozen=True, slots=True)
class _BatchArtifacts:
    """Intermediate per batch Phase 1 and Phase 2 jury outputs passed into Phase 2 rewrite."""

    n: int
    tag: str
    p1: Path
    p1_rows: list[dict[str, Any]]
    vpath: Path
    verdict_doc: dict[str, Any]
    res: dict[str, Any]
    rec_start: int
    jury_dup_to_canon: dict[str, str]


class LocalizationPipelineBuilder:
    """Builds and runs Phase 0 to Phase 3 jury culturalization pipeline."""

    def __init__(self, hooks: PipelineHooks) -> None:
        self._h = hooks

    def run(self, input_path: Path, locale: str, workdir: Path, router: Any, opts: JuryPipelineOptions) -> dict[str, Any]:
        env = self._prepare(input_path, locale, workdir, router, opts)
        finals: list[Path] = []
        batches: list[dict[str, Any]] = []
        halted: dict[str, Any] | None = None
        step = max(opts.batch_size, len(env.rows)) if (getattr(router, "batch", False) and opts.batch_size >= 200 and env.rows) else opts.batch_size
        try:
            for idx, batch_tuple in enumerate(batched(env.rows, step), start=1):
                batch_info, halted_info, final_path = self._run_batch(env, idx, list(batch_tuple))
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
        prompts = self._prepare_prompts(locale, rows, pack_dir, state, opts, router)
        threshold, _ = self._h.load_threshold(locale, packs)
        memo = self._h.open_memo(workdir / RESUME_FILE) if opts.resume else None
        item_memo = self._h.open_memo(workdir / ITEMS_RESUME_FILE) if opts.resume else None
        if memo is not None and len(memo):
            state.say(f"Phase 0: resuming, {len(memo)} finished model batches in {RESUME_FILE}")
        return _RunEnv(locale, workdir, router, opts, state, rows, pack_dir, level, tm, prompts, threshold, memo, item_memo, EscalationTally())

    def _open_tm(self, tm_path: Path | None, state: PipelineState) -> Any:
        if tm_path is None:
            return None
        if not Path(tm_path).is_file():
            raise L10nError(f"translation memory not found: {tm_path}")
        tm = self._h.open_tm(Path(tm_path))
        state.say(f"Phase 0: translation memory {Path(tm_path).name}")
        return tm

    def _build_pass1_system(self, locale: str, pack_dir: Path, regs: list[str], state: PipelineState, opts: JuryPipelineOptions) -> str:
        warm = ""
        if pack_dir.is_dir() and ((pack_dir / "warmup.jsonl").is_file() or (pack_dir / "local" / "warmup.jsonl").is_file()):
            sample = self._h.load_warmup_sample(pack_dir, regs, 40, opts.seed)
            warm = self._h.render_warmup(sample)
            state.say(f"Phase 0: warm-up {len(sample)} lines for {', '.join(regs)}")
        try:
            sys_txt = self._h.system_prompt("game-culturalizer", locale, state.bible, lean_api=opts.lean_prompt)
        except TypeError:
            sys_txt = self._h.system_prompt("game-culturalizer", locale, state.bible)
        return sys_txt + "\n\n# Native warm-up (read aloud before translating)\n" + warm if warm else sys_txt

    def _prepare_prompts(
        self, locale: str, rows: list[Any], pack_dir: Path, state: PipelineState, opts: JuryPipelineOptions, router: Any,
    ) -> _PromptBundle:
        regs = sorted({self._h.register_of(r) for r in rows}) or ["ui"]
        pass1_system = self._build_pass1_system(locale, pack_dir, regs, state, opts)
        wctx, bctx = self._h.load_context_views(Path(opts.context_map), locale) if opts.context_map is not None else (None, None)
        if wctx is not None:
            pass1_system = wctx.build_system(pass1_system)
            state.say(f"Phase 0: context map {wctx.source_name}, line notes for {getattr(wctx, 'note_count', 0)} keys" + (", " + locale + " appendix" if wctx.has_appendix else ""))
            if wctx.has_appendix and bctx is not None and not getattr(bctx, "has_jury_view", True):
                msg = f"Phase 0: {wctx.source_name} has a {locale} appendix but no CONTEXT_MAP.jury.md, jurors may see target language choices"
                if opts.require_juried_context:
                    raise L10nError(msg)
                state.say("WARNING " + msg)
                router.note(msg)
        else:
            state.say("Phase 0: no context map given, every later step works without the game's context")
        critic_base, critic_info = self._h.build_critic_prompt(locale, [{"register": r} for r in regs], pack_dir, opts.seed)
        critic_info = dict(critic_info)
        if bctx is not None:
            critic_info["context_map"] = bctx.source_name
            critic_system = bctx.build_system(critic_base)
        else:
            critic_system = critic_base
        p2_system, _unused_pick = self._h.build_pass2_systems(locale, pack_dir, regs, opts.seed)
        return _PromptBundle(pass1_system, wctx, bctx, critic_base, critic_system, critic_info, p2_system)

    def _run_batch(self, env: _RunEnv, n: int, batch: list[Any]) -> tuple:
        tag = f"{env.locale}_{n:02d}"
        rec_start = len(env.router.budget.records)
        p1, p1_rows, targets, plan = self._phase1_batch(env, n, batch)
        verdict_doc, vpath, res, dup_map = self._phase2_jury(env, n, tag, p1, batch, targets, plan)
        batch_info: dict[str, Any] = {"batch": n, "verdicts": vpath.name, "stats": res["stats"]}
        if res["halted"]:
            env.state.say(f"Phase 2: batch {n:02d} STOPPED by the budget cap at {res['halted']['stage']}. {res['halted']['reason']}")
            sources_map = {r.key: {"en": r.src, "target": targets[r.key]} for r in batch}
            self._h.write_change_report(verdict_doc, env.locale, n, tag, env.workdir, None, sources_map, env.pack_dir, self._h.batch_budget(env.router, rec_start))
            batch_info["report"] = f"changes_{tag}.md"
            return batch_info, {"batch": n, **res["halted"]}, None
        art = _BatchArtifacts(n, tag, p1, p1_rows, vpath, verdict_doc, res, rec_start, dup_map)
        final, rep, rpath = self._phase2_rewrite(env, art)
        batch_info.update({"rewrites": rpath.name, "final": final.name, "report": f"changes_{tag}.md", "unresolved": len(rep["unresolved"])})
        return batch_info, None, final

    def _phase1_batch(self, env: _RunEnv, n: int, batch: list[Any]) -> tuple:
        opts = env.opts
        dedup_env = DedupEnv(env.locale, self._h.register_of, env.prompts.wctx, env.tm, self._h.parity, opts)
        plan = plan_pass1_batch(batch, dedup_env)
        translated: dict[str, str] = {}
        if plan.canon_payloads:
            translated = self._h.translate_rows(
                env.router.for_role("pass1"), plan.canon_payloads, env.locale, task="pass1",
                system=env.prompts.pass1_system, memo=env.memo, item_memo=env.item_memo,
                salvage_truncated=opts.salvage_truncated,
                extra={"placeholder_style": opts.ph_style, "tag_style": opts.tag_style}, workers=opts.workers,
            )
        targets = expand_pass1_targets(plan, translated, batch)
        if opts.draft_field:
            env.state.say(f"Phase 1: batch {n:02d} keeps {plan.draft_count} drafts of '{opts.draft_field}' as they are, translates {len(plan.canon_payloads)} empty rows")
        p1 = env.workdir / f"pass1_batch_{n:02d}.json"
        p1_rows = [{"key": r.key, "category": r.meta.get("category", ""), "speaker": r.meta.get("speaker", ""), opts.src_field: r.src, env.locale: targets[r.key]} for r in batch]
        p1.write_text(json.dumps(p1_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        rag = sum(1 for pr in plan.canon_payloads if pr.get("tm"))
        notes: list[str] = []
        if env.tm is not None:
            notes.append(f"TM neighbours for {rag}")
        if plan.tm_count:
            notes.append(f"{plan.tm_count} approved TM exact")
        if plan.dedup_count:
            notes.append(f"{plan.dedup_count} context deduplicated")
        suffix = (", " + ", ".join(notes)) if notes else ""
        env.state.say(f"Phase 1: batch {n:02d} -> {p1.name} ({len(batch)} rows{suffix})")
        return p1, p1_rows, targets, plan

    def _phase2_jury(
        self, env: _RunEnv, n: int, tag: str, p1: Path, batch: list[Any], targets: dict[str, str], plan: Pass1BatchPlan,
    ) -> tuple:
        opts = env.opts
        blind = env.workdir / f"blind_{tag}.json"
        jentries = self._h.prepare_blind_slice(p1, blind, env.locale, opts.src_field, opts.key_field)
        info = dict(env.prompts.critic_info)
        if env.prompts.bctx is not None:
            info["context_lines"] = env.prompts.bctx.enrich_entries(jentries)
        critic_system = env.prompts.critic_system
        src_by_key = {r.key: r.src for r in batch}
        jplan = plan_jury_batch(jentries, plan.tm_verdicts)
        raw_res: dict[str, Any] | None = None
        if jplan.unique_entries:
            rt_cfg = env.router.config.roundtrip
            rt_fn = lambda lines: self._h.roundtrip_evidence(
                [{"key": e["key"], "en": src_by_key.get(e["key"], ""), "target": e["target"], "register": e["register"]} for e in lines],
                env.locale, env.router.for_role("roundtrip"), min_words=int(rt_cfg["min_words"]),
                registers=rt_cfg["registers"], threshold=env.threshold, workers=opts.workers,
                memo=env.memo, salvage_truncated=opts.salvage_truncated,
            )
            tm_fn = (lambda entry: env.tm.neighbors(
                env.locale, src_by_key.get(entry["key"], entry["target"]),
                category=str(entry.get("category") or ""), speaker=str(entry.get("speaker") or ""), exclude_key=entry["key"],
            )) if env.tm is not None else None
            delib = self._h.make_deliberator(env.router, env.locale, critic_system) if opts.deliberation else None
            raw_res = self._h.run_jury(
                jplan.unique_entries, env.locale, env.router, system=critic_system, budget_caps=opts.budget_caps,
                roundtrip_fn=rt_fn, tally=env.tally, memo=env.memo, tm_lookup=tm_fn, deliberator=delib, workers=opts.workers,
                clean_light_pass=opts.clean_light_pass, item_memo=env.item_memo, salvage_truncated=opts.salvage_truncated,
            )
        res = expand_jury_result(jplan, raw_res, [str(e["key"]) for e in jentries])
        broken = send_broken_lines_to_pass2(res, targets, src_by_key, opts.ph_style, opts.tag_style, self._h.parity)
        if broken:
            env.state.say(f"Phase 2: batch {n:02d} {broken} lines break placeholder or tag parity with the source, sent to Pass 2")
        if opts.clean_light_pass:
            from .stages import send_ban_hit_lines_to_pass2
            banned = send_ban_hit_lines_to_pass2(res)
            if banned:
                env.state.say(f"Phase 2: batch {n:02d} {banned} lines matched locale ban rules, sent to Pass 2")
        vpath = env.workdir / f"verdicts_{tag}.json"
        verdict_doc = write_verdict_doc(vpath, env.locale, p1.name, info, res, env.router.notes)
        st = res["stats"]["status"]
        env.state.say(f"Phase 2: batch {n:02d} jury " + ", ".join(f"{k} {v}" for k, v in st.items() if v) + f" -> {vpath.name}")
        return verdict_doc, vpath, res, jplan.dup_to_canon

    def _phase2_rewrite(self, env: _RunEnv, art: _BatchArtifacts) -> tuple:
        opts = env.opts
        sources = self._h.load_pass2_sources(art.p1, opts.src_field, env.locale, opts.key_field)
        active_verdicts = [v for v in art.res["verdicts"] if v["key"] not in art.jury_dup_to_canon]
        try:
            rw = self._h.run_pass2(
                active_verdicts, sources, env.locale, env.router, opts,
                env.prompts.p2_system, env.prompts.critic_base, env.prompts.wctx, env.prompts.bctx,
                env.memo, art.p1.name, item_memo=env.item_memo,
            )
        except TypeError:
            rw = self._h.run_pass2(
                active_verdicts, sources, env.locale, env.router, opts,
                env.prompts.p2_system, env.prompts.critic_base, env.prompts.wctx, env.prompts.bctx,
                env.memo, art.p1.name,
            )
        rw = expand_pass2_rewrites(rw, art.jury_dup_to_canon, [r["key"] for r in art.p1_rows])
        rpath = env.workdir / f"rewrites_{art.tag}.json"
        rpath.write_text(json.dumps({"locale": env.locale, "source_file": art.p1.name, "verdicts": art.vpath.name, **rw, "notes": env.router.notes}, ensure_ascii=False, indent=2), encoding="utf-8")
        final = env.workdir / f"final_batch_{art.n:02d}.json"
        applied_n = write_final_batch(final, art.p1_rows, rw, art.res, env.locale)
        kept = sum(1 for l in rw["lines"] if not l["valid"] or l["new"] == l["old"])
        env.state.say(f"Phase 2: batch {art.n:02d} Pass 2 rewrote {applied_n} rows, {kept} kept the old text -> {final.name}")
        rep = self._h.write_change_report(art.verdict_doc, env.locale, art.n, art.tag, env.workdir, {"lines": rw["lines"]}, {}, env.pack_dir, self._h.batch_budget(env.router, art.rec_start))
        env.state.say(f"Phase 2: batch {art.n:02d} change report changes_{art.tag}.md ({rep['changed']} changes, {len(rep['unresolved'])} unresolved)")
        return final, rep, rpath

    def _finalize(self, env: _RunEnv, finals: list[Path], batches: list[dict[str, Any]], halted: dict[str, Any] | None) -> dict[str, Any]:
        if halted:
            summary: dict[str, Any] = {
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
