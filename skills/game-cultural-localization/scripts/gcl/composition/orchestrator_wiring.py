"""Composition wiring assembling PipelineHooks for LocalizationPipelineBuilder."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.application.pipeline import JuryPipelineOptions, PipelineHooks
from gcl.application.rewrite import TournamentOptions, run_tournament
from gcl.domain.models import Row
from gcl.infrastructure.formats.registry import load_table_options
from gcl.ports.formats import TableLoadOptions

from .container import ServiceContainer
from .legacy_pipeline import phase0_preflight, system_prompt

__layer__ = "composition"
__pattern__ = "Abstract Hook Assembly"
__owns__ = "PipelineHooks factory wiring gcl application services and injected tool adapters"

_CONTAINER = ServiceContainer()


@dataclass(frozen=True, slots=True)
class OrchestratorCallbacks:
    """Typed callable bundle injected by outer CLI facade keeping gcl free of script imports."""

    infer_register: Callable[[str, str, str], str]
    trust_level: Callable[[Path], tuple[str, str | None]]
    default_langpack_dir: Callable[[], Path]
    load_warmup: Callable[..., Any]
    render_warmup: Callable[[Any], str]
    load_context: Callable[[Path, str], Any]
    load_threshold: Callable[..., Any]
    translate_rows: Callable[..., dict[str, str]]
    prepare_blind_slice: Callable[[Path, Path, str, str, str], list[dict[str, Any]]]
    build_critic_prompt: Callable[..., Any]
    roundtrip_evidence: Callable[..., Any]
    run_jury: Callable[..., dict[str, Any]]
    make_deliberator: Callable[..., Any]
    load_pass2_sources: Callable[..., dict[str, Any]]
    build_pass2_systems: Callable[..., tuple[str, str]]
    pass2_candidates: Callable[..., Any]
    pick_candidates: Callable[..., Any]
    score_entries: Callable[..., Any]
    write_change_report: Callable[..., dict[str, Any]]
    batch_budget: Callable[[Any, int], dict[str, Any] | None]
    phase3_gate: Callable[..., dict[str, Any]]


def build_orchestrator_hooks(cb: OrchestratorCallbacks) -> PipelineHooks:
    """Assemble segregated PipelineHooks for LocalizationPipelineBuilder."""

    def _register(row: Row) -> str:
        reg = str(row.meta.get("register") or "")
        return reg if reg else cb.infer_register(str(row.meta.get("category") or ""), row.src, "game")

    def _run_pass2(*args: Any, **kw: Any) -> dict[str, Any]:
        (
            verdicts, sources, locale, router, opts,
            p2_sys, pk_sys, wctx, bctx, memo, src_name,
        ) = args[:11]
        t_opts = TournamentOptions(
            pass2_system=p2_sys, pick_system=pk_sys, n=opts.candidates, seed=opts.seed,
            ph_style=opts.ph_style, tag_style=opts.tag_style, source_file=src_name, workers=opts.workers,
            writer_context=wctx, blind_context=bctx, memo=memo,
            tiered=opts.tiered_pass2, unanimous_skip_recheck=opts.unanimous_skip_recheck,
            item_memo=kw.get("item_memo"), salvage_truncated=opts.salvage_truncated,
        )
        return run_tournament(
            verdicts, sources, locale, router, t_opts, _CONTAINER.critique_validator, _CONTAINER.parity,
            pass2_fn=cb.pass2_candidates, pick_fn=cb.pick_candidates, score_fn=cb.score_entries,
        )

    def _write_change(*args: Any) -> dict[str, Any]:
        (
            vdoc, locale, n, tag, workdir,
            rewrites, sources, pack_dir, budget,
        ) = args[:9]
        rep = cb.write_change_report(vdoc, locale, f"{n:02d}", rewrites=rewrites, sources=sources, pack_dir=pack_dir, budget=budget)
        (workdir / f"changes_{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        (workdir / f"changes_{tag}.md").write_text(cb.render_markdown(rep) if hasattr(cb, "render_markdown") else _render_md(rep), encoding="utf-8")
        return rep

    return PipelineHooks(
        load_source_rows=lambda p, sf, kf: [Row(r.key, r.dst, "", r.meta) for r in load_table_options(p, TableLoadOptions(sf, sf, kf, target_only=True))],
        register_of=_register,
        preflight=phase0_preflight,
        trust_level=cb.trust_level,
        open_tm=_CONTAINER.open_tm,
        open_memo=_CONTAINER.open_memo,
        default_langpack_dir=cb.default_langpack_dir,
        load_warmup_sample=lambda pd, regs, cnt, sd: cb.load_warmup(pd, regs, cnt, sd),
        render_warmup=cb.render_warmup,
        system_prompt=system_prompt,
        load_context_views=lambda cm, loc: _CONTAINER.split_context_pack(cb.load_context(cm, loc)),
        load_threshold=cb.load_threshold,
        translate_rows=cb.translate_rows,
        prepare_blind_slice=cb.prepare_blind_slice,
        build_critic_prompt=cb.build_critic_prompt,
        roundtrip_evidence=cb.roundtrip_evidence,
        run_jury=cb.run_jury,
        make_deliberator=cb.make_deliberator,
        load_pass2_sources=cb.load_pass2_sources,
        build_pass2_systems=cb.build_pass2_systems,
        run_pass2=_run_pass2,
        write_change_report=_write_change,
        batch_budget=cb.batch_budget,
        phase3_gate=cb.phase3_gate,
        parity=_CONTAINER.parity,
    )


def _render_md(rep: dict[str, Any]) -> str:
    from gcl.application.reporting import render_markdown
    return render_markdown(rep)
