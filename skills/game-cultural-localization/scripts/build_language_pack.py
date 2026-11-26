#!/usr/bin/env python3
"""Build a language asset pack langpack/<locale>/ from licensed corpora with a five-layer trust filter.

Sources come from langpack/sources.manifest.json (open game and UI translations with
a license class) plus the studio's own professional translation (--reference, the
only human signal). Every source has a license class:
  bundle  may ship with the plugin (attribution in LICENSES.md)
  local   used on this machine only, written under langpack/<locale>/local/ (gitignored)
OpenSubtitles and other excluded corpora are refused.

Five-layer filter (statistics land in manifest.json)
  1 source selection   license class, license, review process, version, sha256 pin, file available
  2 mechanical         empty, fuzzy, untranslated, length ratio outside 0.3 to 3.0, ban list (lqa_linter rules),
                       broken placeholders or tags, duplicates
  3 MT detection       bulk commits over 500 rows, and with --mt-check lines over min_words words whose
                       back-translation returns the English source verbatim
  4 cross consistency  short terms rendered identically by 3+ sources are 'trusted', conflicting renderings
                       are 'disputed' and left out (rows agreeing with the reference stay)
  5 jury pre-screen    with --jury-screen the three J1 members must all give 4 or 5, a seeded sample goes to the report
The reference translation is exempt from the length ratio and ban list of layer 2 and from layers 3 to 5.
Its rule hits are listed in manifest.json (layer2_mechanical.reference_exempt), they point at rules that
fight the studio voice.

Output in <langpack-dir>/<locale>/
  manifest.json  trust_card.json  warmup.jsonl  roundtrip_threshold.json  LICENSES.md
  local/warmup.jsonl  local/prescreen_sample.jsonl  (local class only, never shipped)

Usage:
  python build_language_pack.py ../langpack/sources.manifest.json --locale tr-TR --reference loc_work/reference/tr.csv
  python build_language_pack.py ../langpack/sources.manifest.json --locale de-DE --offline --cache-dir corpus_cache

Exit codes: 0 pack built, 1 pack built but a source could not be loaded (not cached, download
failed, hash mismatch) or no row survived, 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, SCRIPTS_DIR, L10nError, Row, add_common_args, add_input_argument, emit_report, load_json_data,
    load_table, normalize_locale, parse_po, read_text_bom, resolve_input, run_main, __version__,
)
import lqa_linter  # noqa: E402
from llm_tasks import backtranslate_rows, score_entries, word_count  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402
from providers.base import OFFLINE_ENV  # noqa: E402

TOOL = "build_language_pack"
LANGPACK_DIR = SCRIPTS_DIR.parent / "langpack"
DEFAULT_MANIFEST = LANGPACK_DIR / "sources.manifest.json"
LICENSE_CLASSES = ("bundle", "local")
FORMATS = ("po", "properties", "json_nested", "openttd", "ftl", "table")
REGISTERS = ("ui", "tutorial", "dialogue_casual", "dialogue_formal")
EXCLUDED_SOURCES = ("opensubtitles",)
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


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

def load_manifest(path: Path) -> Dict[str, Any]:
    """Load and structurally validate sources.manifest.json (policy problems are layer 1 drops, not errors)."""
    data = load_json_data(path)
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise L10nError(f"{path}: manifest must be an object with a 'sources' list")
    seen = set()
    for i, src in enumerate(data["sources"]):
        if not isinstance(src, dict):
            raise L10nError(f"{path}: sources[{i}] must be an object")
        sid = src.get("id")
        if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", sid):
            raise L10nError(f"{path}: sources[{i}].id must be a lower-case slug")
        if sid in seen or sid == REFERENCE_ID:
            raise L10nError(f"{path}: duplicate or reserved source id '{sid}'")
        seen.add(sid)
        blob = (sid + " " + str(src.get("name", "")) + " " + str(src.get("homepage", ""))).lower()
        for bad in EXCLUDED_SOURCES:
            if bad in blob:
                raise L10nError(f"{path}: source '{sid}' is an excluded corpus ({bad}) and must not be listed")
        if src.get("format") not in FORMATS:
            raise L10nError(f"{path}: source '{sid}' has format {src.get('format')!r}; supported: {', '.join(FORMATS)}")
        files = src.get("files", [])
        if not isinstance(files, list):
            raise L10nError(f"{path}: source '{sid}'.files must be a list")
        for j, f in enumerate(files):
            if not isinstance(f, dict) or not (f.get("url") or f.get("path")) or not f.get("locale"):
                raise L10nError(f"{path}: source '{sid}'.files[{j}] needs 'locale' and 'url' or 'path'")
            normalize_locale(str(f["locale"]))
            if src["format"] in ("properties", "json_nested", "openttd", "ftl") and not (f.get("en_url") or f.get("en_path")):
                raise L10nError(f"{path}: source '{sid}'.files[{j}] ({src['format']}) needs the English file in 'en_url' or 'en_path'")
    return data


# --------------------------------------------------------------------------- #
# Format parsers (key -> text)
# --------------------------------------------------------------------------- #
_PROP_ESC = {"n": "\n", "t": "\t", "r": "\r", "f": "\f"}


def _prop_unescape(s: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        c = m.group(1)
        if c.startswith("u") and len(c) == 5:
            return chr(int(c[1:], 16))
        return _PROP_ESC.get(c, c)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", repl, s)


def parse_properties(text: str) -> Dict[str, str]:
    """Java .properties: key = value, '#' / '!' comments, backslash line continuation, \\uXXXX escapes."""
    out: Dict[str, str] = {}
    buf = ""
    for raw in text.splitlines():
        line = raw.lstrip()
        if not buf and (not line or line[0] in "#!"):
            continue
        trailing = len(line) - len(line.rstrip("\\"))
        if trailing % 2 == 1:
            buf += line[:-1]
            continue
        line, buf = buf + line, ""
        m = re.match(r"((?:\\.|[^=:\s\\])+)\s*(?:[=:]\s*|\s+)?(.*)$", line)
        if m:
            out[_prop_unescape(m.group(1))] = _prop_unescape(m.group(2))
    return out


def flatten_json(obj: Any, prefix: str = "") -> Dict[str, str]:
    """Nested JSON object -> {'a.b.c': 'text'} (lists are indexed, non-strings skipped)."""
    out: Dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten_json(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten_json(v, f"{prefix}.{i}" if prefix else str(i)))
    elif isinstance(obj, str):
        out[prefix] = obj
    return out


def parse_openttd(text: str) -> Dict[str, str]:
    """OpenTTD lang/*.txt: 'STR_NAME   :text' lines; case variants (STR_X.case) and pragmas are skipped."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^(STR_[A-Z0-9_]+)\s*:(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


_FTL_MSG = re.compile(r"^([A-Za-z][\w-]*)\s*=\s?(.*)$")
_FTL_ATTR = re.compile(r"^\s+\.([A-Za-z][\w-]*)\s*=\s?(.*)$")


def parse_ftl(text: str) -> Dict[str, str]:
    """Fluent .ftl: messages, multi-line values and attributes (msg.attr); select expressions are skipped."""
    out: Dict[str, str] = {}
    base: Optional[str] = None
    key: Optional[str] = None
    buf: List[str] = []

    def flush() -> None:
        if key is None:
            return
        lines = list(buf)
        while lines and not lines[-1].strip():
            lines.pop()
        cont = [l for l in lines[1:] if l.strip()]
        indent = min((len(l) - len(l.lstrip()) for l in cont), default=0)
        value = "\n".join([lines[0].strip()] + [l[indent:] if l.strip() else "" for l in lines[1:]]) if lines else ""
        value = value.strip("\n")
        if value.strip() and "->" not in value:
            out[key] = value

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            key, base, buf = None, None, []
            continue
        m = _FTL_MSG.match(line)
        if m:
            flush()
            base = key = m.group(1)
            buf = [m.group(2)]
            continue
        m = _FTL_ATTR.match(line)
        if m and base:
            flush()
            key = f"{base}.{m.group(1)}"
            buf = [m.group(2)]
            continue
        if key is not None and (line.startswith((" ", "\t")) or not line.strip()):
            buf.append(line)
            continue
        flush()
        key, base, buf = None, None, []
    flush()
    return out


def _paired(fmt: str, target_text: str, en_text: str) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    parser = {"properties": parse_properties, "openttd": parse_openttd, "ftl": parse_ftl}.get(fmt)
    if fmt == "json_nested":
        try:
            tgt, en = flatten_json(json.loads(target_text)), flatten_json(json.loads(en_text))
        except json.JSONDecodeError as exc:
            raise L10nError(f"invalid JSON in corpus file: {exc.msg}")
    else:
        tgt, en = parser(target_text), parser(en_text)  # type: ignore[misc]
    return [(k, en[k], v, {}) for k, v in tgt.items() if k in en]


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
class SourceUnavailable(Exception):
    """A corpus file could not be loaded (layer 1 drop)."""


def cache_path(cache_dir: Path, source_id: str, url: str) -> Path:
    """Mirror the URL under cache_dir/<source id>/<host>/<path> (transparent for offline preparation)."""
    parts = urllib.parse.urlsplit(url)
    segs = [s for s in (parts.netloc + parts.path).split("/") if s not in ("", ".", "..")]
    safe = [re.sub(r"[^\w.\-]", "_", s) for s in segs]
    return cache_dir.joinpath(source_id, *safe)


def fetch_file(entry_url: Optional[str], entry_path: Optional[str], base_dir: Path, cache_dir: Path, source_id: str,
               offline: bool, refresh: bool) -> bytes:
    """Return the bytes of a corpus file from a local path, the cache, or (online) a download into the cache."""
    if entry_path:
        p = Path(entry_path)
        p = p if p.is_absolute() else (base_dir / p)
        if not p.is_file():
            raise SourceUnavailable(f"file not found: {p}")
        return p.read_bytes()
    assert entry_url
    dest = cache_path(cache_dir, source_id, entry_url)
    if dest.is_file() and not refresh:
        return dest.read_bytes()
    if offline:
        raise SourceUnavailable(f"not cached (offline): {dest}")
    if os.environ.get(OFFLINE_ENV, "") == "1":
        raise SourceUnavailable(f"network disabled by {OFFLINE_ENV}=1")
    req = urllib.request.Request(entry_url, headers={"User-Agent": f"game-cultural-localization/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (manifest URLs)
            data = resp.read()
    except Exception as exc:  # network, HTTP or TLS problem
        raise SourceUnavailable(f"download failed: {exc}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Register inference and normalisation
# --------------------------------------------------------------------------- #
_FORMAL = re.compile(r"formal|letter|e?mail|news|official|announce", re.I)
_DIALOG = re.compile(r"(?<![a-z])(dialog(ue)?s?|speech|bark|npc|cutscene|chat|conversation|subtitle)(?![a-z])", re.I)
_TUTOR = re.compile(r"tutorial|tip|hint|help|guide|manual|desc|lore|codex", re.I)
_UI = re.compile(r"ui|button|btn|menu|label|tooltip|hud|toast|tab|badge|option|setting|title", re.I)


def infer_register(category: str, text: str, source_register: str) -> str:
    """Register (ui, tutorial, dialogue_casual, dialogue_formal) from the category, else from the text shape.

    UI sources (editors, office tools) never yield dialogue registers: their 'dialog' contexts are dialog boxes.
    """
    cat = (category or "").strip()
    if cat in REGISTERS:
        return cat
    if source_register == "ui":
        return "ui" if word_count(text) <= 4 or (cat and _UI.search(cat) and word_count(text) <= 8) else "tutorial"
    if cat:
        if _FORMAL.search(cat):
            return "dialogue_formal"
        if _DIALOG.search(cat):
            return "dialogue_casual"
        if _TUTOR.search(cat):
            return "tutorial"
        if _UI.search(cat):
            return "ui"
    words = word_count(text)
    if words <= 4:
        return "ui"
    if source_register == "dialogue":
        return "dialogue_casual"
    if source_register == "ui":
        return "tutorial"
    stripped = text.strip()
    if words <= 30 and (re.search(r"[!?…]$", stripped) or stripped[:1] in "\"“«„'"):
        return "dialogue_casual"
    return "tutorial"


def norm_text(text: str) -> str:
    """Comparison form: NFC, case-folded, whitespace collapsed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def norm_words(text: str) -> str:
    """Comparison form without punctuation (back-translation identity, term grouping)."""
    return " ".join(re.findall(r"\w+", norm_text(text)))


# --------------------------------------------------------------------------- #
# Layers
# --------------------------------------------------------------------------- #

def layer2_mechanical(cands: List[Dict[str, Any]], locale: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Empty, fuzzy, untranslated, length ratio, ban list / technical (lqa_linter), duplicate within one source.

    Identical pairs from different sources stay until layer 4, they are the evidence of cross-source agreement.
    The studio reference is exempt from the length ratio and the ban list (the professional translation wins over
    the heuristics), its rule hits are listed under 'reference_exempt' so a rule that fights the studio voice shows up.
    """
    reasons: Counter = Counter()
    stage: List[Dict[str, Any]] = []
    ref_ratio: List[str] = []
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
    rules = lqa_linter.load_rules(locale)
    rule_ids = {r.id for r in rules}
    # row keys carry the original key so key based contexts (Codex, Lore, News, BTN) apply
    row_keys = [f"{i}.{c.get('key', '')}" for i, c in enumerate(stage)]
    index = {k: i for i, k in enumerate(row_keys)}
    rows = [Row(row_keys[i], c["en"], c["text"], {"category": c["register"]}) for i, c in enumerate(stage)]
    findings = lqa_linter.lint_rows(rows, rules, lqa_linter.LintOptions(locale=locale, check_untranslated=False))
    banned: Dict[int, List[str]] = {}
    broken = set()
    for f in findings:
        if f.code in rule_ids:
            banned.setdefault(index[f.key], []).append(f.code)
        elif f.severity == "ERR":
            broken.add(index[f.key])
    kept: List[Dict[str, Any]] = []
    ref_hits: List[Dict[str, str]] = []
    seen = set()
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
    return kept, {"in": len(cands), "out": len(kept), "dropped": dict(sorted(reasons.items())),
                  "length_ratio_bounds": [RATIO_MIN, RATIO_MAX],
                  "reference_exempt": {"length_ratio": ref_ratio, "rule_hits": ref_hits,
                                       "by_rule": dict(sorted(Counter(h["rule"] for h in ref_hits).items()))}}


def layer3_mt(cands: List[Dict[str, Any]], locale: str, provider: Any, min_words: int, bulk_limit: int = BULK_COMMIT_ROWS) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Bulk-commit suspicion and (with a provider) verbatim back-translation detection; the reference is exempt."""
    reasons: Counter = Counter()
    per_commit = Counter((c["source"], c["commit"]) for c in cands if c.get("commit") and not c.get("reference"))
    bulk = {k for k, n in per_commit.items() if n > bulk_limit}
    stage = []
    for c in cands:
        if not c.get("reference") and c.get("commit") and (c["source"], c["commit"]) in bulk:
            reasons["bulk_commit"] += 1
        else:
            stage.append(c)
    checked = 0
    kept = stage
    if provider is not None:
        eligible = [(i, c) for i, c in enumerate(stage) if not c.get("reference") and word_count(c["text"]) > min_words]
        checked = len(eligible)
        backs = backtranslate_rows(provider, [{"key": str(i), "target": c["text"]} for i, c in eligible], locale) if eligible else {}
        identical = {i for i, c in eligible if norm_words(backs.get(str(i), "")) == norm_words(c["en"])}
        reasons["roundtrip_identical"] += len(identical)
        kept = [c for i, c in enumerate(stage) if i not in identical]
    return kept, {"applied": provider is not None, "in": len(cands), "out": len(kept), "checked": checked,
                  "min_words": min_words, "bulk_commit_limit": bulk_limit,
                  "bulk_commits": sorted(f"{s}:{c}" for s, c in bulk), "dropped": dict(sorted(reasons.items()))}


def layer4_consistency(cands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Label short terms trusted (3+ sources agree), disputed (sources disagree) or single; drop disputed rows."""
    groups: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for c in cands:
        if word_count(c["en"]) <= CONSISTENCY_MAX_WORDS:
            groups[norm_words(c["en"])][c["source"]].add(norm_words(c["text"]))
    labels: Dict[str, str] = {}
    ref_render: Dict[str, set] = {}
    examples: List[Dict[str, Any]] = []
    counts: Counter = Counter()
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
    kept: List[Dict[str, Any]] = []
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
    return kept, {"in": len(cands), "out": len(kept), "terms_checked": len(groups), "trusted": counts["trusted"],
                  "disputed": counts["disputed"], "single": counts["single"], "dropped": {"disputed": dropped} if dropped else {},
                  "examples_bundle": examples}


def layer5_jury(cands: List[Dict[str, Any]], locale: str, members: Optional[Sequence[Any]], pass_min: int,
                seed: int, sample_size: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """J1 pre-screen: keep a line only when all three members score >= pass_min. Returns kept, stats, sample rows."""
    if not members:
        return cands, {"applied": False, "in": len(cands), "out": len(cands), "dropped": {}}, []
    screened = [(i, c) for i, c in enumerate(cands) if not c.get("reference")]
    entries = [{"key": str(i), "target": c["text"], "register": c["register"]} for i, c in screened]
    votes_by_member = [score_entries(m.provider, entries, locale, tier="J1") if entries else {} for m in members]
    rejected = set()
    for i, _c in screened:
        scores = [v[str(i)]["score"] for v in votes_by_member]
        if min(scores) < pass_min:
            rejected.add(i)
    kept = [c for i, c in enumerate(cands) if i not in rejected]
    rng = random.Random(seed)
    picks = sorted(rng.sample(range(len(screened)), min(sample_size, len(screened))))
    sample = []
    for p in picks:
        i, c = screened[p]
        sample.append({"text": c["text"], "register": c["register"], "source": c["source"], "license_class": c["license_class"],
                       "scores": [v[str(i)]["score"] for v in votes_by_member], "kept": i not in rejected})
    return kept, {"applied": True, "in": len(cands), "out": len(kept), "screened": len(screened), "pass_min": pass_min,
                  "members": [m.model for m in members], "dropped": {"jury_below_pass": len(rejected)} if rejected else {},
                  "sample_size": len(sample)}, sample


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def load_reference(path: Path, locale: str, src_field: str, dst_field: Optional[str]) -> List[Dict[str, Any]]:
    """Professional EN + target table (key, en, <locale>|dst, category, speaker, archetype)."""
    candidates = [dst_field] if dst_field else [locale, "dst", "target", locale.split("-")[0]]
    last: Optional[L10nError] = None
    for col in candidates:
        try:
            rows = load_table(path, src_field, col, "key")
            break
        except L10nError as exc:
            last = exc
    else:
        raise L10nError(f"{path}: no target column for {locale} (tried {', '.join(candidates)}); pass --dst-field") from last
    out = []
    for r in rows:
        out.append({"key": r.key, "en": r.src, "text": r.dst, "source": REFERENCE_ID, "license_class": "bundle",
                    "source_register": "game", "category": str(r.meta.get("category", "") or r.meta.get("register", "")),
                    "speaker": str(r.meta.get("speaker", "")), "fuzzy": False, "commit": str(r.meta.get("commit", "") or ""),
                    "reference": True})
    return out


def collect_sources(manifest: Dict[str, Any], manifest_path: Path, locale: str, cache_dir: Path, offline: bool, refresh: bool,
                    lock: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]], bool]:
    """Layer 1: select sources and parse their files. Returns candidates, layer stats, source records, manifest changed."""
    cands: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    not_available: List[str] = []
    records: List[Dict[str, Any]] = []
    changed = False
    sources_in = 0
    for src in manifest["sources"]:
        files = [f for f in src.get("files", []) if normalize_locale(str(f["locale"]))[0] == locale]
        if not files:
            not_available.append(src["id"])
            continue
        sources_in += 1
        sid = src["id"]
        reason = None
        if src.get("license_class") not in LICENSE_CLASSES:
            reason = f"license_class {src.get('license_class')!r} is not bundle or local"
        elif not str(src.get("license", "")).strip():
            reason = "license missing"
        elif src.get("review_process") is not True:
            reason = "no review process"
        elif not str(src.get("version", "")).strip():
            reason = "version not pinned"
        if reason:
            dropped.append({"id": sid, "reason": reason})
            continue
        file_records = []
        rows: List[Tuple[str, str, str, Dict[str, Any]]] = []
        try:
            for f in files:
                data = fetch_file(f.get("url"), f.get("path"), manifest_path.parent, cache_dir, sid, offline, refresh)
                digest = sha256(data)
                if f.get("sha256") and f["sha256"] != digest:
                    raise SourceUnavailable(f"sha256 mismatch for {f.get('url') or f.get('path')} (pinned {f['sha256'][:12]}, got {digest[:12]})")
                if lock and not f.get("sha256"):
                    f["sha256"] = digest
                    changed = True
                rec = {"file": f.get("url") or f.get("path"), "sha256": digest, "pinned": bool(f.get("sha256"))}
                text = data.decode("utf-8-sig", "replace")
                if src["format"] == "po":
                    for r in parse_po(text):
                        if r.meta.get("plural_index") not in (None, 0):
                            continue
                        rows.append((r.key, r.src, r.dst, {"fuzzy": r.meta.get("fuzzy"), "category": r.meta.get("msgctxt") or ""}))
                elif src["format"] == "table":
                    p = Path(f["path"]) if f.get("path") else cache_path(cache_dir, sid, f["url"])
                    p = p if p.is_absolute() else manifest_path.parent / p
                    for r in load_table(p, f.get("src_field", "en"), f.get("dst_field", locale), f.get("key_field", "key")):
                        rows.append((r.key, r.src, r.dst, {"category": str(r.meta.get("category", "") or ""), "commit": str(r.meta.get("commit", "") or ""),
                                                           "speaker": str(r.meta.get("speaker", "") or "")}))
                else:
                    en_data = fetch_file(f.get("en_url"), f.get("en_path"), manifest_path.parent, cache_dir, sid, offline, refresh)
                    en_digest = sha256(en_data)
                    if f.get("en_sha256") and f["en_sha256"] != en_digest:
                        raise SourceUnavailable(f"sha256 mismatch for the English file {f.get('en_url') or f.get('en_path')}")
                    if lock and not f.get("en_sha256"):
                        f["en_sha256"] = en_digest
                        changed = True
                    rec["en_sha256"] = en_digest
                    rows.extend(_paired(src["format"], text, en_data.decode("utf-8-sig", "replace")))
                rec["rows"] = len(rows) - sum(r.get("rows", 0) for r in file_records)
                file_records.append(rec)
        except SourceUnavailable as exc:
            dropped.append({"id": sid, "reason": str(exc), "load_failure": True})
            continue
        for key, en, tx, meta in rows:
            cands.append({"key": key, "en": en, "text": tx, "source": sid, "license_class": src["license_class"],
                          "source_register": str(src.get("register", "game")), "category": str(meta.get("category") or ""),
                          "speaker": str(meta.get("speaker") or ""), "fuzzy": bool(meta.get("fuzzy")),
                          "commit": str(meta.get("commit") or ""), "reference": False})
        records.append({"id": sid, "name": src.get("name", sid), "license": src.get("license"), "license_class": src["license_class"],
                        "version": src.get("version"), "attribution": src.get("attribution", ""), "homepage": src.get("homepage", ""),
                        "files": file_records, "rows": len(rows), "hashes_pinned": all(r["pinned"] for r in file_records)})
    stats = {"sources_in": sources_in, "sources_kept": len(records), "dropped": dropped, "not_available": not_available, "rows_in": len(cands)}
    return cands, stats, records, changed


def dedupe_across_sources(cands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Keep one copy of a target text: reference first, then bundle, then local class (stable otherwise)."""
    rank = {True: 0, False: 1}
    ordered = sorted(enumerate(cands), key=lambda ic: (rank[bool(ic[1].get("reference"))], 0 if ic[1]["license_class"] == "bundle" else 1, ic[0]))
    seen = set()
    keep_idx = set()
    for i, c in ordered:
        t = norm_text(c["text"])
        if t in seen:
            continue
        seen.add(t)
        keep_idx.add(i)
    return [c for i, c in enumerate(cands) if i in keep_idx], len(cands) - len(keep_idx)


def _jsonl(rows: Sequence[Dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def write_pack(pack: Path, locale: str, kept: List[Dict[str, Any]], records: List[Dict[str, Any]], filters: Dict[str, Any],
               sample: List[Dict[str, Any]], min_words: int, registers: Sequence[str], has_reference: bool) -> Dict[str, Any]:
    """Write warm-up files split by license class, manifest, trust card, threshold stub and LICENSES.md."""
    local_dir = pack / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    ordered = sorted(kept, key=lambda c: (REGISTERS.index(c["register"]), c["source"], c["key"], c["text"]))
    lines = {"bundle": [], "local": []}  # type: Dict[str, List[Dict[str, Any]]]
    for c in ordered:
        rec = {"text": c["text"], "register": c["register"], "source": c["source"], "license_class": c["license_class"],
               "key": c["key"], "consistency": c.get("consistency", "single")}
        if c.get("speaker"):
            rec["speaker"] = c["speaker"]
        lines[c["license_class"]].append(rec)
    bundle_txt, local_txt = _jsonl(lines["bundle"]), _jsonl(lines["local"])
    (pack / "warmup.jsonl").write_text(bundle_txt, encoding="utf-8")
    (local_dir / "warmup.jsonl").write_text(local_txt, encoding="utf-8")
    sample_local = [s for s in sample if s["license_class"] == "local"]
    sample_bundle = [s for s in sample if s["license_class"] == "bundle"]
    (local_dir / "prescreen_sample.jsonl").write_text(_jsonl(sample_local), encoding="utf-8")
    if sample_bundle:
        (pack / "prescreen_sample.jsonl").write_text(_jsonl(sample_bundle), encoding="utf-8")
    elif (pack / "prescreen_sample.jsonl").exists():
        (pack / "prescreen_sample.jsonl").unlink()
    digest = hashlib.sha256((bundle_txt + local_txt + json.dumps(records, sort_keys=True)).encode("utf-8")).hexdigest()[:12]
    version = f"{locale}-{digest}"
    by_reg = {cls: dict(Counter(r["register"] for r in lines[cls])) for cls in ("bundle", "local")}
    manifest = {"locale": locale, "langpack_version": version, "built_with": f"{TOOL} {__version__}",
                "sources": records, "filters": filters,
                "counts": {"bundle": len(lines["bundle"]), "local": len(lines["local"]), "by_register": by_reg},
                "files": {"warmup": "warmup.jsonl", "warmup_local": "local/warmup.jsonl", "contrastive": "contrastive.json",
                          "roundtrip_threshold": "roundtrip_threshold.json", "trust_card": "trust_card.json"}}
    (pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trust_path = pack / "trust_card.json"
    old_trust = load_json_data(trust_path) if trust_path.is_file() else {}
    trust = {
        "locale": locale, "langpack_version": version,
        "trust_level": "measured" if has_reference else "estimated",
        "basis": "professional_reference" if has_reference else "proxy_signals",
        "sources": {"bundle": [r["id"] for r in records if r["license_class"] == "bundle"],
                    "local": [r["id"] for r in records if r["license_class"] == "local"]},
        "rows": {"bundle": len(lines["bundle"]), "local": len(lines["local"]), "by_register": by_reg},
        "filters_out": {k: v.get("out", v.get("rows_in")) for k, v in filters.items()},
        "roundtrip": {"min_words": min_words, "registers": list(registers)},
        "calibration": old_trust.get("calibration") if isinstance(old_trust, dict) else None,
        "native_review": old_trust.get("native_review", {"done": False}) if isinstance(old_trust, dict) else {"done": False},
        "known_limits": KNOWN_LIMITS,
    }
    trust_path.write_text(json.dumps(trust, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    thr = pack / "roundtrip_threshold.json"
    if not thr.is_file():
        thr.write_text(json.dumps({"locale": locale, "threshold": DEFAULT_ROUNDTRIP_THRESHOLD, "calibrated": False,
                                   "min_words": min_words, "registers": list(registers)}, indent=2) + "\n", encoding="utf-8")
    lic = [f"# {locale} language pack licenses", "",
           "Lines in warmup.jsonl come from the sources below. Bundle class sources may ship with the plugin under their license.",
           "Local class sources are used on this machine only, their lines stay in local/ and are never distributed.", ""]
    for cls, title in (("bundle", "Bundled sources"), ("local", "Local only sources (not distributed)")):
        lic.append(f"## {title}")
        lic.append("")
        rows = [r for r in records if r["license_class"] == cls]
        if not rows:
            lic.append("None.")
        for r in rows:
            name = r["name"] if r["id"] != REFERENCE_ID else "Studio reference translation"
            lic.append(f"- {name}, version {r['version']}, license {r['license']}. {r.get('attribution') or ''}".rstrip())
        lic.append("")
    (pack / "LICENSES.md").write_text("\n".join(lic), encoding="utf-8")
    return manifest


def build_pack(manifest_path: Path, locale: str, langpack_dir: Path, cache_dir: Path, *, offline: bool = False, refresh: bool = False,
               references: Sequence[Path] = (), src_field: str = "en", dst_field: Optional[str] = None, router: Optional[Router] = None,
               mt_check: bool = False, jury_screen: bool = False, min_words: int = 6, registers: Sequence[str] = (),
               pass_min: int = 4, seed: int = DEFAULT_SEED, sample_size: int = DEFAULT_SAMPLE, lock_hashes: bool = False) -> Dict[str, Any]:
    """Run layers 1 to 5 and write langpack_dir/<locale>/. Returns {'manifest', 'load_failures', 'pack_dir'}."""
    manifest = load_manifest(manifest_path)
    ref_rows: List[Dict[str, Any]] = []
    ref_records: List[Dict[str, Any]] = []
    for ref in references:
        rows = load_reference(Path(ref), locale, src_field, dst_field)
        ref_rows.extend(rows)
        ref_records.append({"id": REFERENCE_ID, "name": "Studio reference translation", "license": "proprietary (studio owned)",
                            "license_class": "bundle", "version": sha256(Path(ref).read_bytes())[:12], "attribution": "",
                            "homepage": "", "files": [{"file": Path(ref).name, "sha256": sha256(Path(ref).read_bytes()), "pinned": True, "rows": len(rows)}],
                            "rows": len(rows), "hashes_pinned": True})
    cands, l1, records, changed = collect_sources(manifest, manifest_path, locale, cache_dir, offline, refresh, lock_hashes)
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cands = ref_rows + cands
    l1["rows_in"] = len(cands)
    l1["sources_in"] += 1 if ref_rows else 0
    l1["sources_kept"] += 1 if ref_rows else 0
    records = ref_records[:1] + records if ref_records else records
    for c in cands:
        c["register"] = infer_register(c["category"], c["text"], c["source_register"])
    kept, l2 = layer2_mechanical(cands, locale)
    rt_provider = router.for_role("roundtrip") if (router and mt_check) else None
    kept, l3 = layer3_mt(kept, locale, rt_provider, min_words)
    kept, l4 = layer4_consistency(kept)
    members = router.jury("J1") if (router and jury_screen) else None
    kept, l5, sample = layer5_jury(kept, locale, members, pass_min, seed, sample_size)
    kept, cross_dups = dedupe_across_sources(kept)
    l5["cross_source_duplicates"] = cross_dups
    filters = {"layer1_source_selection": l1, "layer2_mechanical": l2, "layer3_mt_detection": l3,
               "layer4_cross_consistency": l4, "layer5_jury_prescreen": l5}
    pack = langpack_dir / locale
    pack.mkdir(parents=True, exist_ok=True)
    out = write_pack(pack, locale, kept, records, filters, sample, min_words, registers or ("dialogue_casual", "dialogue_formal"), bool(ref_rows))
    failures = [d for d in l1["dropped"] if d.get("load_failure")]
    return {"manifest": out, "load_failures": failures, "pack_dir": str(pack)}


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
    ap = build_parser()
    args = ap.parse_args()
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
    res = build_pack(Path(args.input), locale, langpack_dir, cache_dir, offline=args.offline, refresh=args.refresh,
                     references=[Path(r) for r in args.reference], src_field=args.src_field, dst_field=args.dst_field, router=router,
                     mt_check=args.mt_check, jury_screen=args.jury_screen, min_words=min_words, registers=pcfg.roundtrip["registers"],
                     pass_min=int(pcfg.agreement["pass_min"]), seed=args.seed, sample_size=args.sample_size, lock_hashes=args.lock_hashes)
    m = res["manifest"]
    f = m["filters"]
    empty = m["counts"]["bundle"] + m["counts"]["local"] == 0
    exit_code = EXIT_FINDINGS if (res["load_failures"] or empty) else EXIT_OK
    lines = [f"Language pack {locale}: {res['pack_dir']} (version {m['langpack_version']})",
             f"  Layer 1 sources: {f['layer1_source_selection']['sources_kept']} kept of {f['layer1_source_selection']['sources_in']} (+reference)"
             if any(r["id"] == REFERENCE_ID for r in m["sources"]) else
             f"  Layer 1 sources: {f['layer1_source_selection']['sources_kept']} kept of {f['layer1_source_selection']['sources_in']}"]
    for d in f["layer1_source_selection"]["dropped"]:
        lines.append(f"    dropped {d['id']}: {d['reason']}")
    for name, key in (("Layer 2 mechanical", "layer2_mechanical"), ("Layer 3 MT detection", "layer3_mt_detection"),
                      ("Layer 4 consistency", "layer4_cross_consistency"), ("Layer 5 jury pre-screen", "layer5_jury_prescreen")):
        st = f[key]
        applied = "" if st.get("applied", True) else " (not applied)"
        lines.append(f"  {name}{applied}: {st['in']} -> {st['out']} " + (json.dumps(st.get("dropped", {}), ensure_ascii=False) if st.get("dropped") else ""))
        ex = st.get("reference_exempt") or {}
        if ex.get("rule_hits") or ex.get("length_ratio"):
            lines.append(f"    reference kept despite: length ratio {len(ex.get('length_ratio', []))}, rule hits {json.dumps(ex.get('by_rule', {}))}")
    lines.append(f"  Rows: bundle {m['counts']['bundle']}, local {m['counts']['local']} (local rows stay in local/)")
    if empty:
        lines.append("  WARN: no row survived the filters")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "locale": locale, "pack_dir": res["pack_dir"], "langpack_version": m["langpack_version"],
               "counts": m["counts"], "filters": f, "load_failures": res["load_failures"],
               "notes": router.notes if router else [], "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
