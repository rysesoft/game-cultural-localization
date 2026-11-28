"""Application pipeline state, JuryPipelineOptions and injected hook contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

__layer__ = "application"
__pattern__ = "Parameter Object and Port Hooks"
__owns__ = "PipelineState, JuryPipelineOptions and injected PipelineHooks dataclasses"

RESUME_FILE = "model_batches.json"
ARCHETYPES: Dict[str, str] = {
    "A1": "Mentor/Veteran (warm, senior, gives advice)",
    "A2": "Hotshot Rival (cocky, fast, competitive)",
    "A3": "Rookie/Teen (excited, everyday slang, short sentences)",
    "A4": "Scientist/Engineer (precise, technical but conversational)",
    "A5": "Outlaw/Antagonist (threatening, cold, terse)",
}


@dataclass
class PipelineState:
    """Mutable per run progress log, bible text and Phase 3 gate settings."""

    locale: str
    workdir: Path
    src_field: str
    dst_field: str
    key_field: str
    ph_style: str
    tag_style: str
    log: List[str] = field(default_factory=list)
    bible: str = ""
    gate: Dict[str, Any] = field(default_factory=dict)

    def say(self, msg: str) -> None:
        self.log.append(msg)


@dataclass(frozen=True)
class JuryPipelineOptions:
    """Immutable configuration object replacing 18 keyword arguments on run_jury_pipeline."""

    src_field: str = "en"
    key_field: str = "key"
    ph_style: str = "auto"
    tag_style: str = "auto"
    batch_size: int = 200
    fonts: Sequence[Path] = ()
    langpack_dir: Optional[Path] = None
    tm_path: Optional[Path] = None
    deliberation: bool = True
    budget_caps: bool = True
    candidates: int = 3
    seed: int = 1234
    workers: int = 1
    context_map: Optional[Path] = None
    resume: bool = True
    gate: Optional[Dict[str, Any]] = None
    draft_field: Optional[str] = None
    lean_prompt: bool = True
    clean_light_pass: bool = True
    tiered_pass2: bool = True
    unanimous_skip_recheck: bool = True
    tm_shortcircuit: bool = True
    require_juried_context: bool = False
    salvage_truncated: bool = True


@dataclass(frozen=True)
class PipelineHooks:
    """Port callbacks injected by the composition/CLI layer so application stays decoupled."""

    load_source_rows: Callable[[Path, str, str], List[Any]]
    register_of: Callable[[Any], str]
    preflight: Callable[[PipelineState, List[Any], List[Path]], None]
    trust_level: Callable[[Path], Any]
    open_tm: Callable[[Path], Any]
    open_memo: Callable[[Path], Any]
    default_langpack_dir: Callable[[], Path]
    load_warmup_sample: Callable[[Path, List[str], int, int], List[Dict[str, Any]]]
    render_warmup: Callable[[Any], str]
    system_prompt: Callable[..., str]
    load_context_views: Callable[[Path, str], Any]
    load_threshold: Callable[[str, Path], Any]
    translate_rows: Callable[..., Dict[str, str]]
    prepare_blind_slice: Callable[[Path, Path, str, str, str], List[Dict[str, Any]]]
    build_critic_prompt: Callable[[str, Sequence[Dict[str, Any]], Path, int], Any]
    roundtrip_evidence: Callable[..., Dict[str, Dict[str, Any]]]
    run_jury: Callable[..., Dict[str, Any]]
    make_deliberator: Callable[[Any, str, str], Any]
    load_pass2_sources: Callable[[Path, str, str, str], Dict[str, Dict[str, Any]]]
    build_pass2_systems: Callable[[str, Path, List[str], int], Any]
    run_pass2: Callable[..., Dict[str, Any]]
    write_change_report: Callable[..., Dict[str, Any]]
    batch_budget: Callable[[Any, int], Optional[Dict[str, Any]]]
    phase3_gate: Callable[[PipelineState, List[Path], List[Path]], Dict[str, Any]]
    parity: Any
