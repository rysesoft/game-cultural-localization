"""Application pipeline state, JuryPipelineOptions and injected hook contracts."""

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any

__layer__ = "application"
__pattern__ = "Parameter Object and Port Hooks"
__owns__ = "PipelineState, JuryPipelineOptions and injected PipelineHooks dataclasses"

RESUME_FILE = "model_batches.json"
ARCHETYPES: dict[str, str] = {
    "A1": "Mentor/Veteran (warm, senior, gives advice)",
    "A2": "Hotshot Rival (cocky, fast, competitive)",
    "A3": "Rookie/Teen (excited, everyday slang, short sentences)",
    "A4": "Scientist/Engineer (precise, technical but conversational)",
    "A5": "Outlaw/Antagonist (threatening, cold, terse)",
}


@dataclass(slots=True)
class PipelineState:
    """Mutable per run progress log, bible text and Phase 3 gate settings."""

    locale: str
    workdir: Path
    src_field: str
    dst_field: str
    key_field: str
    ph_style: str
    tag_style: str
    log: list[str] = field(default_factory=list)
    bible: str = ""
    gate: dict[str, Any] = field(default_factory=dict)

    def say(self, msg: str) -> None:
        self.log.append(msg)


@dataclass(frozen=True, slots=True)
class JuryPipelineOptions:
    """Immutable configuration object replacing 18 keyword arguments on run_jury_pipeline."""

    src_field: str = "en"
    key_field: str = "key"
    ph_style: str = "auto"
    tag_style: str = "auto"
    batch_size: int = 200
    fonts: Sequence[Path] = ()
    langpack_dir: Path | None = None
    tm_path: Path | None = None
    deliberation: bool = True
    budget_caps: bool = True
    candidates: int = 3
    seed: int = 1234
    workers: int = 1
    context_map: Path | None = None
    resume: bool = True
    gate: dict[str, Any] | None = None
    draft_field: str | None = None
    lean_prompt: bool = True
    clean_light_pass: bool = True
    tiered_pass2: bool = True
    unanimous_skip_recheck: bool = True
    tm_shortcircuit: bool = True
    require_juried_context: bool = False
    salvage_truncated: bool = True


@dataclass(frozen=True, slots=True)
class PipelineHooks:
    """Port callbacks injected by the composition/CLI layer so application stays decoupled."""

    load_source_rows: Callable[[Path, str, str], list[Any]]
    register_of: Callable[[Any], str]
    preflight: Callable[[PipelineState, list[Any], list[Path]], None]
    trust_level: Callable[[Path], Any]
    open_tm: Callable[[Path], Any]
    open_memo: Callable[[Path], Any]
    default_langpack_dir: Callable[[], Path]
    load_warmup_sample: Callable[[Path, list[str], int, int], list[dict[str, Any]]]
    render_warmup: Callable[[Any], str]
    system_prompt: Callable[..., str]
    load_context_views: Callable[[Path, str], Any]
    load_threshold: Callable[[str, Path], Any]
    translate_rows: Callable[..., dict[str, str]]
    prepare_blind_slice: Callable[[Path, Path, str, str, str], list[dict[str, Any]]]
    build_critic_prompt: Callable[[str, Sequence[dict[str, Any]], Path, int], Any]
    roundtrip_evidence: Callable[..., dict[str, dict[str, Any]]]
    run_jury: Callable[..., dict[str, Any]]
    make_deliberator: Callable[[Any, str, str], Any]
    load_pass2_sources: Callable[[Path, str, str, str], dict[str, dict[str, Any]]]
    build_pass2_systems: Callable[[str, Path, list[str], int], Any]
    run_pass2: Callable[..., dict[str, Any]]
    write_change_report: Callable[..., dict[str, Any]]
    batch_budget: Callable[[Any, int], dict[str, Any] | None]
    phase3_gate: Callable[[PipelineState, list[Path], list[Path]], dict[str, Any]]
    parity: Any
