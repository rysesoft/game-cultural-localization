#!/usr/bin/env python3
"""Language pack builder CLI facade delegating to gcl.composition.langpack_wiring.

Pure Python 3.15, standard library only. Exit codes: 0 ok, 1 load/filter failure, 2 usage error.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcl.application.langpack import (  # noqa: E402
    BULK_COMMIT_ROWS, CONSISTENCY_MAX_WORDS, DEFAULT_ROUNDTRIP_THRESHOLD, DEFAULT_SAMPLE, DEFAULT_SEED,
    KNOWN_LIMITS, RATIO_MAX, RATIO_MIN, REFERENCE_ID, REGISTERS, dedupe_across_sources, infer_register,
    layer3_mt, layer4_consistency, layer5_jury, norm_text, norm_words, write_pack,
)
from gcl.composition.langpack_wiring import DEFAULT_MANIFEST, LANGPACK_DIR, LangpackBuildOptions, build_language_pack  # noqa: E402
from gcl.infrastructure.corpora import (  # noqa: E402
    EXCLUDED_SOURCES, FORMATS, LICENSE_CLASSES, SourceUnavailable, cache_path, fetch_file, file_sha256,
    flatten_json, load_manifest, pair_texts as _paired, parse_ftl, parse_openttd, parse_properties, sha256,
)
from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report,
    normalize_locale, resolve_input, run_main, __version__,
)
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

TOOL = "build_language_pack"


def build_pack(
    manifest_path: Path, locale: str, langpack_dir: Path, cache_dir: Path, *, offline: bool = False, refresh: bool = False,
    references: Sequence[Path] = (), src_field: str = "en", dst_field: str | None = None, router: Router | None = None,
    mt_check: bool = False, jury_screen: bool = False, min_words: int = 6, registers: Sequence[str] = (),
    pass_min: int = 4, seed: int = DEFAULT_SEED, sample_size: int = DEFAULT_SAMPLE, lock_hashes: bool = False,
    reference_license: str = "proprietary (studio owned)", reference_attribution: str = "",
) -> dict[str, Any]:
    """Build langpack/<locale>/ through gcl.composition.langpack_wiring."""
    return build_language_pack(LangpackBuildOptions(
        manifest_path=manifest_path, locale=locale, langpack_dir=langpack_dir, cache_dir=cache_dir,
        offline=offline, refresh=refresh, references=references, src_field=src_field, dst_field=dst_field,
        router=router, mt_check=mt_check, jury_screen=jury_screen, min_words=min_words, registers=registers,
        pass_min=pass_min, seed=seed, sample_size=sample_size, lock_hashes=lock_hashes,
        reference_license=reference_license, reference_attribution=reference_attribution,
    ))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Build langpack/<locale>/ (warm-up corpus, trust card, licenses) with a five-layer filter")
    add_input_argument(ap, "sources.manifest.json (default location: langpack/sources.manifest.json)")
    ap.add_argument("--locale", required=True, help="Target locale of the pack")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs (default: the skill's langpack/)")
    ap.add_argument("--cache-dir", default=None, help="Download cache, also the offline source (default: <langpack-dir>/.cache)")
    ap.add_argument("--offline", action="store_true", help="Never download, read corpus files from the cache only")
    ap.add_argument("--refresh", action="store_true", help="Download again even when a cached copy exists")
    ap.add_argument("--lock-hashes", action="store_true", help="Write the sha256 of every downloaded file into the manifest where it is null")
    ap.add_argument("--reference", action="append", default=[], help="Studio EN + target table (key, en, <locale>, category, speaker), repeatable")
    ap.add_argument("--reference-license", default="proprietary (studio owned)", help="License of the studio's lines in the shipped pack, for example MIT (default: proprietary (studio owned))")
    ap.add_argument("--reference-attribution", default="", help="Credit line of the studio's lines, for example the studio name")
    ap.add_argument("--src-field", default="en", help="Source column of --reference (default en)")
    ap.add_argument("--dst-field", default=None, help="Target column of --reference (default: the locale code, then dst, target)")
    ap.add_argument("--mt-check", action="store_true", help="Layer 3 back-translation check (calls the roundtrip model)")
    ap.add_argument("--jury-screen", action="store_true", help="Layer 5 J1 pre-screen (calls the three J1 models)")
    ap.add_argument("--min-words", type=int, default=None, help="Back-translation applies to lines with more words than this (default: providers config, 6)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed of the pre-screen sample (default {DEFAULT_SEED})")
    ap.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE, help=f"Pre-screen sample rows for the report (default {DEFAULT_SAMPLE})")
    ap.add_argument("--providers-config", default=None, help="providers.config.json (default: the bundled one)")
    ap.add_argument("--dry-run", action="store_true", help="Fake provider for --mt-check and --jury-screen (no key, no network)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", default=None, help="budget.jsonl for model calls (default: <cache-dir>/budget_<locale>.jsonl)")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    args = (ap := build_parser()).parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    langpack_dir = Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR
    cache_dir = Path(args.cache_dir) if args.cache_dir else langpack_dir / ".cache"
    pcfg = load_providers_config(Path(args.providers_config) if args.providers_config else None)
    router = None
    if args.mt_check or args.jury_screen:
        router = Router(pcfg, dry_run=args.dry_run, scenario=FakeScenario.load(Path(args.fake_scenario)) if args.fake_scenario else None,
                        budget_log=Path(args.budget_log) if args.budget_log else cache_dir / f"budget_{locale}.jsonl")
        router.require((["roundtrip"] if args.mt_check else []) + (["J1"] if args.jury_screen else []))
    for ref in args.reference:
        if not Path(ref).is_file():
            raise L10nError(f"--reference file not found: {ref}")
    min_words = args.min_words if args.min_words is not None else int(pcfg.roundtrip["min_words"])
    res = build_pack(
        Path(args.input), locale, langpack_dir, cache_dir, offline=args.offline, refresh=args.refresh,
        references=[Path(r) for r in args.reference], src_field=args.src_field, dst_field=args.dst_field, router=router,
        mt_check=args.mt_check, jury_screen=args.jury_screen, min_words=min_words, registers=pcfg.roundtrip["registers"],
        pass_min=int(pcfg.agreement["pass_min"]), seed=args.seed, sample_size=args.sample_size, lock_hashes=args.lock_hashes,
        reference_license=args.reference_license, reference_attribution=args.reference_attribution,
    )
    m, f = res["manifest"], res["manifest"]["filters"]
    empty = m["counts"]["bundle"] + m["counts"]["local"] == 0
    exit_code = EXIT_FINDINGS if (res["load_failures"] or empty) else EXIT_OK
    l1 = f["layer1_source_selection"]
    ref_mark = " (+reference)" if any(r["id"] == REFERENCE_ID for r in m["sources"]) else ""
    lines = [f"Language pack {locale}: {res['pack_dir']} (version {m['langpack_version']})",
             f"  Layer 1 sources: {l1['sources_kept']} kept of {l1['sources_in']}{ref_mark}"]
    lines.extend(f"    dropped {d['id']}: {d['reason']}" for d in l1["dropped"])
    for name, key in (("Layer 2 mechanical", "layer2_mechanical"), ("Layer 3 MT detection", "layer3_mt_detection"),
                      ("Layer 4 consistency", "layer4_cross_consistency"), ("Layer 5 jury pre-screen", "layer5_jury_prescreen")):
        st = f[key]
        lines.append(f"  {name}{'' if st.get('applied', True) else ' (not applied)'}: {st['in']} -> {st['out']} "
                     + (json.dumps(st.get("dropped", {}), ensure_ascii=False) if st.get("dropped") else ""))
        ex = st.get("reference_exempt") or {}
        if ex.get("rule_hits") or ex.get("length_ratio"):
            lines.append(f"    reference kept despite: length ratio {len(ex.get('length_ratio', []))}, rule hits {json.dumps(ex.get('by_rule', {}))}")
    lines.append(f"  Rows: bundle {m['counts']['bundle']}, local {m['counts']['local']} (local rows stay in local/)")
    if empty:
        lines.append("  WARN: no row survived the filters")
    lines.append(f"  Exit code: {exit_code}")
    payload = {
        "tool": TOOL, "version": __version__, "locale": locale, "pack_dir": res["pack_dir"],
        "langpack_version": m["langpack_version"], "counts": m["counts"], "filters": f,
        "load_failures": res["load_failures"], "notes": router.notes if router else [], "exit_code": exit_code,
    }
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
