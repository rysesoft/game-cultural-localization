"""Corpus manifest validation, format parsers (PO/FTL/OpenTTD/Properties/JSON), download cache and source collector."""

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError, __version__
from gcl.domain.locales import normalize_locale
from gcl.infrastructure.formats.io_utils import load_json_data
from gcl.infrastructure.formats.po_format import parse_po
from gcl.infrastructure.formats.registry import load_table_options
from gcl.ports.formats import TableLoadOptions

__layer__ = "infrastructure"
__pattern__ = "Repository and Format Parsers"
__owns__ = "sources.manifest.json validation, corpus format parsers, HTTP cache fetcher and file digests"

LICENSE_CLASSES = ("bundle", "local")
FORMATS = ("po", "properties", "json_nested", "openttd", "ftl", "table")
EXCLUDED_SOURCES = ("opensubtitles",)
OFFLINE_ENV = "GCL_OFFLINE"
_PROP_ESC = {"n": "\n", "t": "\t", "r": "\r", "f": "\f"}
_FTL_MSG = re.compile(r"^([A-Za-z][\w-]*)\s*=\s?(.*)$")
_FTL_ATTR = re.compile(r"^\s+\.([A-Za-z][\w-]*)\s*=\s?(.*)$")


class SourceUnavailable(Exception):
    """A corpus file could not be loaded (layer 1 drop)."""


@dataclass(frozen=True, slots=True)
class SourceCollectOptions:
    """Parameter object controlling Layer 1 corpus source collection."""

    locale: str
    cache_dir: Path
    offline: bool = False
    refresh: bool = False
    lock_hashes: bool = False


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and structurally validate sources.manifest.json."""
    data = load_json_data(path)
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise L10nError(f"{path}: manifest must be an object with a 'sources' list")
    seen: set[str] = set()
    for i, src in enumerate(data["sources"]):
        if not isinstance(src, dict):
            raise L10nError(f"{path}: sources[{i}] must be an object")
        sid = src.get("id")
        if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", sid):
            raise L10nError(f"{path}: sources[{i}].id must be a lower-case slug")
        if sid in seen or sid == "reference":
            raise L10nError(f"{path}: duplicate or reserved source id '{sid}'")
        seen.add(sid)
        blob = f"{sid} {src.get('name', '')} {src.get('homepage', '')}".lower()
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
                raise L10nError(f"{path}: source '{sid}'.files[{j}] ({src['format']}) needs English file in 'en_url' or 'en_path'")
    return data


def _prop_unescape(s: str) -> str:
    def repl(m: re.Match[str]) -> str:
        c = m.group(1)
        return chr(int(c[1:], 16)) if c.startswith("u") and len(c) == 5 else _PROP_ESC.get(c, c)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", repl, s)


def parse_properties(text: str) -> dict[str, str]:
    """Java .properties: key = value, comments, backslash continuation and escapes."""
    out: dict[str, str] = {}
    buf = ""
    for raw in text.splitlines():
        line = raw.lstrip()
        if not buf and (not line or line[0] in "#!"):
            continue
        if (len(line) - len(line.rstrip("\\"))) % 2 == 1:
            buf += line[:-1]
            continue
        line, buf = buf + line, ""
        if (m := re.match(r"((?:\\.|[^=:\s\\])+)\s*(?:[=:]\s*|\s+)?(.*)$", line)):
            out[_prop_unescape(m.group(1))] = _prop_unescape(m.group(2))
    return out


def flatten_json(obj: Any, prefix: str = "") -> dict[str, str]:
    """Nested JSON object -> {'a.b.c': 'text'}."""
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten_json(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten_json(v, f"{prefix}.{i}" if prefix else str(i)))
    elif isinstance(obj, str):
        out[prefix] = obj
    return out


def parse_openttd(text: str) -> dict[str, str]:
    """OpenTTD lang/*.txt STR_NAME :text parser."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if (m := re.match(r"^(STR_[A-Z0-9_]+)\s*:(.*)$", line)):
            out[m.group(1)] = m.group(2)
    return out


def parse_ftl(text: str) -> dict[str, str]:
    """Fluent .ftl messages, multi line values and attributes."""
    out: dict[str, str] = {}
    base: str | None = None
    key: str | None = None
    buf: list[str] = []

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
        elif (m := _FTL_MSG.match(line)):
            flush()
            base = key = m.group(1)
            buf = [m.group(2)]
        elif (m := _FTL_ATTR.match(line)) and base:
            flush()
            key = f"{base}.{m.group(1)}"
            buf = [m.group(2)]
        elif key is not None and (line.startswith((" ", "\t")) or not line.strip()):
            buf.append(line)
        else:
            flush()
            key, base, buf = None, None, []
    flush()
    return out


def pair_texts(fmt: str, target_text: str, en_text: str) -> list[tuple[str, str, str, dict[str, Any]]]:
    parser = {"properties": parse_properties, "openttd": parse_openttd, "ftl": parse_ftl}.get(fmt)
    if fmt == "json_nested":
        try:
            tgt, en = flatten_json(json.loads(target_text)), flatten_json(json.loads(en_text))
        except json.JSONDecodeError as exc:
            raise L10nError(f"invalid JSON in corpus file: {exc.msg}")
    else:
        tgt, en = parser(target_text), parser(en_text)  # type: ignore[misc]
    return [(k, en[k], v, {}) for k, v in tgt.items() if k in en]


def cache_path(cache_dir: Path, source_id: str, url: str) -> Path:
    parts = urllib.parse.urlsplit(url)
    segs = [s for s in (parts.netloc + parts.path).split("/") if s not in ("", ".", "..")]
    safe = [re.sub(r"[^\w.\-]", "_", s) for s in segs]
    return cache_dir.joinpath(source_id, *safe)


def fetch_file(entry_url: str | None, entry_path: str | None, base_dir: Path, cache_dir: Path, source_id: str,
               offline: bool, refresh: bool) -> bytes:
    """Read corpus bytes from local path, cache or HTTPS download."""
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
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
    except Exception as exc:
        raise SourceUnavailable(f"download failed: {exc}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def load_reference_rows(path: Path, locale: str, src_field: str, dst_field: str | None) -> list[dict[str, Any]]:
    """Load professional studio reference rows with target column auto discovery."""
    candidates = [dst_field] if dst_field else [locale, "dst", "target", locale.split("-")[0]]
    last: L10nError | None = None
    for col in candidates:
        try:
            rows = load_table_options(path, TableLoadOptions(src_field=src_field, dst_field=str(col), key_field="key"))
            break
        except L10nError as exc:
            last = exc
    else:
        raise L10nError(f"{path}: no target column for {locale} (tried {', '.join(candidates)}); pass --dst-field") from last
    return [
        {
            "key": r.key, "en": r.src, "text": r.dst, "source": "reference", "license_class": "bundle",
            "source_register": "game", "category": str(r.meta.get("category", "") or r.meta.get("register", "")),
            "speaker": str(r.meta.get("speaker", "")), "fuzzy": False, "commit": str(r.meta.get("commit", "") or ""),
            "reference": True,
        }
        for r in rows
    ]


def _collect_source_file(
    src: dict[str, Any], f: dict[str, Any], manifest_path: Path, opts: SourceCollectOptions,
) -> tuple[list[tuple[str, str, str, dict[str, Any]]], dict[str, Any], bool]:
    sid, changed = src["id"], False
    data = fetch_file(f.get("url"), f.get("path"), manifest_path.parent, opts.cache_dir, sid, opts.offline, opts.refresh)
    digest = sha256(data)
    if f.get("sha256") and f["sha256"] != digest:
        raise SourceUnavailable(f"sha256 mismatch for {f.get('url') or f.get('path')} (pinned {f['sha256'][:12]}, got {digest[:12]})")
    if opts.lock_hashes and not f.get("sha256"):
        f["sha256"] = digest
        changed = True
    rec: dict[str, Any] = {"file": f.get("url") or f.get("path"), "sha256": digest, "pinned": bool(f.get("sha256"))}
    text = data.decode("utf-8-sig", "replace")
    rows: list[tuple[str, str, str, dict[str, Any]]] = []
    match src["format"]:
        case "po":
            rows.extend(
                (r.key, r.src, r.dst, {"fuzzy": r.meta.get("fuzzy"), "category": r.meta.get("msgctxt") or ""})
                for r in parse_po(text) if r.meta.get("plural_index") in (None, 0)
            )
        case "table":
            p = Path(f["path"]) if f.get("path") else cache_path(opts.cache_dir, sid, f["url"])
            p = p if p.is_absolute() else manifest_path.parent / p
            t_opts = TableLoadOptions(f.get("src_field", "en"), f.get("dst_field", opts.locale), f.get("key_field", "key"))
            rows.extend(
                (r.key, r.src, r.dst, {"category": str(r.meta.get("category", "") or ""), "commit": str(r.meta.get("commit", "") or ""),
                                       "speaker": str(r.meta.get("speaker", "") or "")})
                for r in load_table_options(p, t_opts)
            )
        case _:
            en_data = fetch_file(f.get("en_url"), f.get("en_path"), manifest_path.parent, opts.cache_dir, sid, opts.offline, opts.refresh)
            en_digest = sha256(en_data)
            if f.get("en_sha256") and f["en_sha256"] != en_digest:
                raise SourceUnavailable(f"sha256 mismatch for the English file {f.get('en_url') or f.get('en_path')}")
            if opts.lock_hashes and not f.get("en_sha256"):
                f["en_sha256"] = en_digest
                changed = True
            rec["en_sha256"] = en_digest
            rows.extend(pair_texts(src["format"], text, en_data.decode("utf-8-sig", "replace")))
    rec["rows"] = len(rows)
    return rows, rec, changed


def collect_sources(
    manifest: dict[str, Any], manifest_path: Path, opts: SourceCollectOptions,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], bool]:
    """Layer 1 source selection, hash verification and corpus file parsing."""
    cands: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    not_available: list[str] = []
    records: list[dict[str, Any]] = []
    changed, sources_in = False, 0
    for src in manifest["sources"]:
        files = [f for f in src.get("files", []) if normalize_locale(str(f["locale"]))[0] == opts.locale]
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
        file_records: list[dict[str, Any]] = []
        rows: list[tuple[str, str, str, dict[str, Any]]] = []
        try:
            for f in files:
                frows, rec, fchanged = _collect_source_file(src, f, manifest_path, opts)
                changed = changed or fchanged
                rows.extend(frows)
                file_records.append(rec)
        except SourceUnavailable as exc:
            dropped.append({"id": sid, "reason": str(exc), "load_failure": True})
            continue
        for key, en, tx, meta in rows:
            cands.append({
                "key": key, "en": en, "text": tx, "source": sid, "license_class": src["license_class"],
                "source_register": str(src.get("register", "game")), "category": str(meta.get("category") or ""),
                "speaker": str(meta.get("speaker") or ""), "fuzzy": bool(meta.get("fuzzy")),
                "commit": str(meta.get("commit") or ""), "reference": False,
            })
        records.append({
            "id": sid, "name": src.get("name", sid), "license": src.get("license"), "license_class": src["license_class"],
            "version": src.get("version"), "attribution": src.get("attribution", ""), "homepage": src.get("homepage", ""),
            "files": file_records, "rows": len(rows), "hashes_pinned": all(r["pinned"] for r in file_records),
        })
    stats = {"sources_in": sources_in, "sources_kept": len(records), "dropped": dropped, "not_available": not_available, "rows_in": len(cands)}
    return cands, stats, records, changed
