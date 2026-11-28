"""Composition wiring orchestrating language pack building across corpora and filters."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.application.langpack import (
    DEFAULT_SAMPLE, DEFAULT_SEED, REFERENCE_ID, PackWriteSpec, dedupe_across_sources, infer_register,
    layer2_mechanical, layer3_mt, layer4_consistency, layer5_jury, write_pack,
)
from gcl.infrastructure.corpora import (
    SourceCollectOptions, collect_sources, file_sha256, load_manifest, load_reference_rows,
)
from gcl.infrastructure.formats.io_utils import load_json_data
from gcl.infrastructure.formats.lint_rules_io import load_rules
from gcl.infrastructure.paths import SCRIPTS_DIR
from gcl.infrastructure.tokens.parity_adapter import DefaultTokenParityAdapter

__layer__ = "composition"
__pattern__ = "Composition Orchestrator"
__owns__ = "wiring corpora parsers, LQA rules, parity adapter and 5 layer language pack filters"

LANGPACK_DIR = SCRIPTS_DIR.parent / "langpack"
DEFAULT_MANIFEST = LANGPACK_DIR / "sources.manifest.json"
_PARITY = DefaultTokenParityAdapter()


@dataclass(frozen=True, slots=True)
class LangpackBuildOptions:
    """Parameter object driving end to end language pack build."""

    manifest_path: Path
    locale: str
    langpack_dir: Path
    cache_dir: Path
    offline: bool = False
    refresh: bool = False
    references: Sequence[Path] = ()
    src_field: str = "en"
    dst_field: str | None = None
    router: Any = None
    mt_check: bool = False
    jury_screen: bool = False
    min_words: int = 6
    registers: Sequence[str] = ()
    pass_min: int = 4
    seed: int = DEFAULT_SEED
    sample_size: int = DEFAULT_SAMPLE
    lock_hashes: bool = False
    reference_license: str = "proprietary (studio owned)"
    reference_attribution: str = ""


def build_language_pack(opts: LangpackBuildOptions) -> dict[str, Any]:
    """Run layers 1 to 5 and write langpack_dir/<locale>/."""
    manifest = load_manifest(opts.manifest_path)
    ref_rows: list[dict[str, Any]] = []
    ref_records: list[dict[str, Any]] = []
    for ref in opts.references:
        rows = load_reference_rows(Path(ref), opts.locale, opts.src_field, opts.dst_field)
        ref_rows.extend(rows)
        ref_digest = file_sha256(Path(ref))
        ref_records.append({
            "id": REFERENCE_ID, "name": "Studio reference translation", "license": opts.reference_license,
            "license_class": "bundle", "version": ref_digest[:12], "attribution": opts.reference_attribution,
            "homepage": "", "files": [{"file": Path(ref).name, "sha256": ref_digest, "pinned": True, "rows": len(rows)}],
            "rows": len(rows), "hashes_pinned": True,
        })
    c_opts = SourceCollectOptions(opts.locale, opts.cache_dir, opts.offline, opts.refresh, opts.lock_hashes)
    cands, l1, records, changed = collect_sources(manifest, opts.manifest_path, c_opts)
    if changed:
        opts.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cands = ref_rows + cands
    l1["rows_in"] = len(cands)
    l1["sources_in"] += 1 if ref_rows else 0
    l1["sources_kept"] += 1 if ref_rows else 0
    records = ref_records[:1] + records if ref_records else records
    for c in cands:
        c["register"] = infer_register(c["category"], c["text"], c["source_register"])
    kept, l2 = layer2_mechanical(cands, opts.locale, load_rules(opts.locale), _PARITY)
    rt_provider = opts.router.for_role("roundtrip") if (opts.router and opts.mt_check) else None
    kept, l3 = layer3_mt(kept, opts.locale, rt_provider, opts.min_words)
    kept, l4 = layer4_consistency(kept)
    members = opts.router.jury("J1") if (opts.router and opts.jury_screen) else None
    kept, l5, sample = layer5_jury(kept, opts.locale, members, opts.pass_min, opts.seed, opts.sample_size)
    kept, cross_dups = dedupe_across_sources(kept)
    l5["cross_source_duplicates"] = cross_dups
    filters = {
        "layer1_source_selection": l1, "layer2_mechanical": l2, "layer3_mt_detection": l3,
        "layer4_cross_consistency": l4, "layer5_jury_prescreen": l5,
    }
    pack = opts.langpack_dir / opts.locale
    pack.mkdir(parents=True, exist_ok=True)
    trust_path = pack / "trust_card.json"
    old_trust = load_json_data(trust_path) if trust_path.is_file() else {}
    regs = opts.registers or ("dialogue_casual", "dialogue_formal")
    spec = PackWriteSpec(pack, opts.locale, kept, records, filters, sample, opts.min_words, regs, bool(ref_rows))
    out = write_pack(spec, old_trust if isinstance(old_trust, dict) else None)
    failures = [d for d in l1["dropped"] if d.get("load_failure")]
    return {"manifest": out, "load_failures": failures, "pack_dir": str(pack)}
