"""Five-layer language pack trust filters, register inference and warm-up writer."""

import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.application.gates.lint_chain import lint_rows
from gcl.application.tasks.concrete_tasks import backtranslate_rows, score_entries
from gcl.application.tasks.prompts import word_count
from gcl.domain.errors import __version__
from gcl.domain.lint_models import LintOptions, Rule
from gcl.domain.models import Row
from gcl.ports.formats import TokenParityPort

__layer__ = "application"
__pattern__ = "Pipeline Filters"
__owns__ = "register inference, 5 layer corpus filtering, deduplication and pack writing"

REGISTERS = ("ui", "tutorial", "dialogue_casual", "dialogue_formal")
RATIO_MIN, RATIO_MAX = 0.3, 3.0
BULK_COMMIT_ROWS = 500
CONSISTENCY_MAX_WORDS = 4
DEFAULT_SEED = 1234
DEFAULT_SAMPLE = 50
DEFAULT_ROUNDTRIP_THRESHOLD = 0.85
REFERENCE_ID = "reference"
KNOWN_LIMITS = [
    "Native judgement for locales without a professional reference is an estimate.",
    "Open corpora are mostly translations themselves, so warm-up calibrates to good translation, not to original writing.",
    "Back-translation carries no signal for UI and short text.",
    "Self-preference of a model family is reduced by deliberation, not removed.",
    "Cultural errors are not caught by any proxy signal.",
    "Cost is unknown until measured, rough estimate 5 to 15 calls per line.",
]

_FORMAL = re.compile(r"formal|letter|e?mail|news|official|announce", re.I)
_DIALOG = re.compile(r"(?<![a-z])(dialog(ue)?s?|speech|bark|npc|cutscene|chat|conversation|subtitle)(?![a-z])", re.I)
_TUTOR = re.compile(r"tutorial|tip|hint|help|guide|manual|desc|lore|codex", re.I)
_UI = re.compile(r"ui|button|btn|menu|label|tooltip|hud|toast|tab|badge|option|setting|title", re.I)


@dataclass(frozen=True, slots=True)
class PackWriteSpec:
    """Parameter object grouping outputs needed to write one language pack."""

    pack: Path
    locale: str
    kept: list[dict[str, Any]]
    records: list[dict[str, Any]]
    filters: dict[str, Any]
    sample: list[dict[str, Any]]
    min_words: int
    registers: Sequence[str]
    has_reference: bool


def infer_register(category: str, text: str, source_register: str) -> str:
    """Infer register (ui, tutorial, dialogue_casual, dialogue_formal) from category then text shape."""
    cat = (category or "").strip()
    if cat in REGISTERS:
        return cat
    if source_register == "ui":
        return "ui" if word_count(text) <= 4 or (cat and _UI.search(cat) and word_count(text) <= 8) else "tutorial"
    if cat:
        for rx, reg in ((_FORMAL, "dialogue_formal"), (_DIALOG, "dialogue_casual"), (_TUTOR, "tutorial"), (_UI, "ui")):
            if rx.search(cat):
                return reg
    words = word_count(text)
    if words <= 4:
        return "ui"
    if source_register == "dialogue":
        return "dialogue_casual"
    if source_register == "ui":
        return "tutorial"
    stripped = text.strip()
    return "dialogue_casual" if words <= 30 and (re.search(r"[!?…]$", stripped) or stripped[:1] in "\"“«„'") else "tutorial"


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def norm_words(text: str) -> str:
    return " ".join(re.findall(r"\w+", norm_text(text)))


def _mechanical_precheck(cands: Sequence[dict[str, Any]], reasons: Counter) -> tuple[list[dict[str, Any]], list[str]]:
    stage: list[dict[str, Any]] = []
    ref_ratio: list[str] = []
    for c in cands:
        en, tx = c["en"], c["text"]
        if not tx.strip() or not en.strip():
            reasons["empty"] += 1
        elif c.get("fuzzy"):
            reasons["fuzzy"] += 1
        elif norm_text(tx) == norm_text(en) and re.search(r"[^\W\d_]", en):
            reasons["untranslated"] += 1
        else:
            ratio = len(tx.strip()) / max(1, len(en.strip()))
            if (ratio < RATIO_MIN or ratio > RATIO_MAX) and not c.get("reference"):
                reasons["length_ratio"] += 1
            else:
                if ratio < RATIO_MIN or ratio > RATIO_MAX:
                    ref_ratio.append(c["key"])
                stage.append(c)
    return stage, ref_ratio


def layer2_mechanical(
    cands: list[dict[str, Any]], locale: str, rules: Sequence[Rule], parity: TokenParityPort,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter empty, fuzzy, untranslated, length ratio, rule hits and in source duplicates."""
    reasons: Counter = Counter()
    stage, ref_ratio = _mechanical_precheck(cands, reasons)
    rule_ids = {r.id for r in rules}
    row_keys = [f"{i}.{c.get('key', '')}" for i, c in enumerate(stage)]
    index = {k: i for i, k in enumerate(row_keys)}
    rows = [Row(row_keys[i], c["en"], c["text"], {"category": c["register"]}) for i, c in enumerate(stage)]
    opts = LintOptions(locale=locale, check_untranslated=False)
    findings = lint_rows(rows, rules, opts, parity)
    banned: dict[int, list[str]] = {}
    broken: set[int] = set()
    for f in findings:
        if f.code in rule_ids:
            banned.setdefault(index[f.key], []).append(f.code)
        elif f.severity == "ERR":
            broken.add(index[f.key])
    kept: list[dict[str, Any]] = []
    ref_hits: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for i, c in enumerate(stage):
        if i in banned:
            if not c.get("reference"):
                reasons["ban_list"] += 1
                continue
            ref_hits.extend({"key": c["key"], "rule": code} for code in sorted(set(banned[i])))
        if i in broken:
            reasons["technical"] += 1
            continue
        pair = (c["source"], norm_text(c["en"]), norm_text(c["text"]))
        if pair in seen:
            reasons["duplicate"] += 1
            continue
        seen.add(pair)
        kept.append(c)
    return kept, {
        "in": len(cands), "out": len(kept), "dropped": dict(sorted(reasons.items())),
        "length_ratio_bounds": [RATIO_MIN, RATIO_MAX],
        "reference_exempt": {"length_ratio": ref_ratio, "rule_hits": ref_hits, "by_rule": dict(sorted(Counter(h["rule"] for h in ref_hits).items()))},
    }


def layer3_mt(cands: list[dict[str, Any]], locale: str, provider: Any, min_words: int, bulk_limit: int = BULK_COMMIT_ROWS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bulk commit and verbatim back translation MT detection (reference exempt)."""
    reasons: Counter = Counter()
    per_commit = Counter((c["source"], c["commit"]) for c in cands if c.get("commit") and not c.get("reference"))
    bulk = {k for k, n in per_commit.items() if n > bulk_limit}
    stage = []
    for c in cands:
        if not c.get("reference") and c.get("commit") and (c["source"], c["commit"]) in bulk:
            reasons["bulk_commit"] += 1
        else:
            stage.append(c)
    checked, kept = 0, stage
    if provider is not None:
        eligible = [(i, c) for i, c in enumerate(stage) if not c.get("reference") and word_count(c["text"]) > min_words]
        checked = len(eligible)
        backs = backtranslate_rows(provider, [{"key": str(i), "target": c["text"]} for i, c in eligible], locale) if eligible else {}
        identical = {i for i, c in eligible if norm_words(backs.get(str(i), "")) == norm_words(c["en"])}
        reasons["roundtrip_identical"] += len(identical)
        kept = [c for i, c in enumerate(stage) if i not in identical]
    return kept, {
        "applied": provider is not None, "in": len(cands), "out": len(kept), "checked": checked,
        "min_words": min_words, "bulk_commit_limit": bulk_limit, "bulk_commits": sorted(f"{s}:{c}" for s, c in bulk),
        "dropped": dict(sorted(reasons.items())),
    }


def layer4_consistency(cands: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop short terms rendered divergently across sources unless agreeing with reference."""
    groups: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for c in cands:
        if word_count(c["en"]) <= CONSISTENCY_MAX_WORDS:
            groups[norm_words(c["en"])][c["source"]].add(norm_words(c["text"]))
    labels, ref_render, examples, counts = {}, {}, [], Counter()
    for term, by_src in groups.items():
        renderings = set().union(*by_src.values())
        if len(by_src) >= 2 and len(renderings) > 1:
            labels[term] = "disputed"
            if REFERENCE_ID in by_src:
                ref_render[term] = by_src[REFERENCE_ID]
        elif len(by_src) >= 3:
            labels[term] = "trusted"
        else:
            labels[term] = "single"
        counts[labels[term]] += 1
    kept: list[dict[str, Any]] = []
    dropped = 0
    for c in cands:
        term = norm_words(c["en"]) if word_count(c["en"]) <= CONSISTENCY_MAX_WORDS else None
        label = labels.get(term, "single") if term is not None else "single"
        if label == "disputed" and not c.get("reference"):
            if term in ref_render and norm_words(c["text"]) in ref_render[term]:
                label = "reference_agrees"
            else:
                dropped += 1
                if c["license_class"] == "bundle" and len(examples) < 20:
                    examples.append({"en": c["en"], "text": c["text"], "source": c["source"]})
                continue
        c["consistency"] = label
        kept.append(c)
    return kept, {
        "in": len(cands), "out": len(kept), "terms_checked": len(groups), "trusted": counts["trusted"],
        "disputed": counts["disputed"], "single": counts["single"], "dropped": {"disputed": dropped} if dropped else {},
        "examples_bundle": examples,
    }


def layer5_jury(cands: list[dict[str, Any]], locale: str, members: Sequence[Any] | None, pass_min: int,
                seed: int, sample_size: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """J1 pre-screen retaining non-reference lines when all three jurors score >= pass_min."""
    if not members:
        return cands, {"applied": False, "in": len(cands), "out": len(cands), "dropped": {}}, []
    screened = [(i, c) for i, c in enumerate(cands) if not c.get("reference")]
    entries = [{"key": str(i), "target": c["text"], "register": c["register"]} for i, c in screened]
    votes_by_member = [score_entries(m.provider, entries, locale, tier="J1") if entries else {} for m in members]
    rejected = {i for i, _c in screened if min(v[str(i)]["score"] for v in votes_by_member) < pass_min}
    kept = [c for i, c in enumerate(cands) if i not in rejected]
    rng = random.Random(seed)
    picks = sorted(rng.sample(range(len(screened)), min(sample_size, len(screened))))
    sample = [
        {"text": screened[p][1]["text"], "register": screened[p][1]["register"], "source": screened[p][1]["source"],
         "license_class": screened[p][1]["license_class"], "scores": [v[str(screened[p][0])]["score"] for v in votes_by_member],
         "kept": screened[p][0] not in rejected}
        for p in picks
    ]
    return kept, {
        "applied": True, "in": len(cands), "out": len(kept), "screened": len(screened), "pass_min": pass_min,
        "members": [m.model for m in members], "dropped": {"jury_below_pass": len(rejected)} if rejected else {}, "sample_size": len(sample),
    }, sample


def dedupe_across_sources(cands: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate across sources preferring reference, then bundle, then local."""
    ordered = sorted(enumerate(cands), key=lambda ic: (0 if ic[1].get("reference") else 1, 0 if ic[1]["license_class"] == "bundle" else 1, ic[0]))
    seen: set[str] = set()
    keep_idx: set[int] = set()
    for i, c in ordered:
        if (t := norm_text(c["text"])) not in seen:
            seen.add(t)
            keep_idx.add(i)
    return [c for i, c in enumerate(cands) if i in keep_idx], len(cands) - len(keep_idx)


def _jsonl(rows: Sequence[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def _write_licenses(pack: Path, locale: str, records: Sequence[dict[str, Any]]) -> None:
    lic = [
        f"# {locale} language pack licenses", "",
        "Lines in warmup.jsonl come from the sources below. Bundle class sources may ship with the plugin under their license.",
        "Local class sources are used on this machine only, their lines stay in local/ and are never distributed.", "",
    ]
    for cls, title in (("bundle", "Bundled sources"), ("local", "Local only sources (not distributed)")):
        lic.extend([f"## {title}", ""])
        rows = [r for r in records if r["license_class"] == cls]
        if not rows:
            lic.append("None.")
        for r in rows:
            name = r["name"] if r["id"] != REFERENCE_ID else "Studio reference translation"
            lic.append(f"- {name}, version {r['version']}, license {r['license']}. {r.get('attribution') or ''}".rstrip())
        lic.append("")
    (pack / "LICENSES.md").write_text("\n".join(lic), encoding="utf-8")


def write_pack(spec: PackWriteSpec, existing_trust: dict[str, Any] | None = None, *, tool_name: str = "build_language_pack") -> dict[str, Any]:
    """Persist warmup corpora split by license class, manifest, trust_card and LICENSES.md."""
    local_dir = spec.pack / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    ordered = sorted(spec.kept, key=lambda c: (REGISTERS.index(c["register"]), c["source"], c["key"], c["text"]))
    lines: dict[str, list[dict[str, Any]]] = {"bundle": [], "local": []}
    for c in ordered:
        rec: dict[str, Any] = {
            "text": c["text"], "register": c["register"], "source": c["source"],
            "license_class": c["license_class"], "key": c["key"], "consistency": c.get("consistency", "single"),
        }
        if c.get("speaker"):
            rec["speaker"] = c["speaker"]
        lines[c["license_class"]].append(rec)
    bundle_txt, local_txt = _jsonl(lines["bundle"]), _jsonl(lines["local"])
    (spec.pack / "warmup.jsonl").write_text(bundle_txt, encoding="utf-8")
    (local_dir / "warmup.jsonl").write_text(local_txt, encoding="utf-8")
    (local_dir / "prescreen_sample.jsonl").write_text(_jsonl([s for s in spec.sample if s["license_class"] == "local"]), encoding="utf-8")
    sample_bundle = [s for s in spec.sample if s["license_class"] == "bundle"]
    sb_path = spec.pack / "prescreen_sample.jsonl"
    if sample_bundle:
        sb_path.write_text(_jsonl(sample_bundle), encoding="utf-8")
    elif sb_path.exists():
        sb_path.unlink()
    digest = hashlib.sha256((bundle_txt + local_txt + json.dumps(spec.records, sort_keys=True)).encode("utf-8")).hexdigest()[:12]
    version = f"{spec.locale}-{digest}"
    by_reg = {cls: dict(Counter(r["register"] for r in lines[cls])) for cls in ("bundle", "local")}
    manifest = {
        "locale": spec.locale, "langpack_version": version, "built_with": f"{tool_name} {__version__}",
        "sources": spec.records, "filters": spec.filters,
        "counts": {"bundle": len(lines["bundle"]), "local": len(lines["local"]), "by_register": by_reg},
        "files": {"warmup": "warmup.jsonl", "warmup_local": "local/warmup.jsonl", "contrastive": "contrastive.json",
                  "roundtrip_threshold": "roundtrip_threshold.json", "trust_card": "trust_card.json"},
    }
    (spec.pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    old_trust = existing_trust or {}
    trust = {
        "locale": spec.locale, "langpack_version": version,
        "trust_level": "measured" if spec.has_reference else "estimated",
        "basis": "professional_reference" if spec.has_reference else "proxy_signals",
        "sources": {"bundle": [r["id"] for r in spec.records if r["license_class"] == "bundle"],
                    "local": [r["id"] for r in spec.records if r["license_class"] == "local"]},
        "rows": {"bundle": len(lines["bundle"]), "local": len(lines["local"]), "by_register": by_reg},
        "filters_out": {k: v.get("out", v.get("rows_in")) for k, v in spec.filters.items()},
        "roundtrip": {"min_words": spec.min_words, "registers": list(spec.registers)},
        "calibration": old_trust.get("calibration"),
        "native_review": old_trust.get("native_review", {"done": False}),
        "known_limits": KNOWN_LIMITS,
    }
    (spec.pack / "trust_card.json").write_text(json.dumps(trust, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    thr = spec.pack / "roundtrip_threshold.json"
    if not thr.is_file():
        thr.write_text(json.dumps({"locale": spec.locale, "threshold": DEFAULT_ROUNDTRIP_THRESHOLD, "calibrated": False,
                                   "min_words": spec.min_words, "registers": list(spec.registers)}, indent=2) + "\n", encoding="utf-8")
    _write_licenses(spec.pack, spec.locale, spec.records)
    return manifest
