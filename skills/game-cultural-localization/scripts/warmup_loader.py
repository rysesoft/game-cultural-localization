#!/usr/bin/env python3
"""Deterministic warm-up ("ear warming") sampler for a language pack.

Picks 30 to 50 native lines of the requested register(s) from
langpack/<locale>/warmup.jsonl (+ local/warmup.jsonl) so a model hears how real
players' language sounds before it translates or judges. Sampling is seeded:
the same pack, registers, count and seed always give the same lines.

Selection
  * filter by register (ui, tutorial, dialogue_casual, dialogue_formal)
  * clean display text: rich-text tags, engine colour codes ({BLACK}, [accent]) removed,
    lines shorter than 2 or longer than 300 characters skipped
  * balanced across sources: each source's lines are shuffled with the seed and taken
    round-robin, the studio reference first, then 'trusted' consistency lines first
    inside every source

Usage:
  python warmup_loader.py ../langpack/tr-TR --register dialogue_casual --count 40 --seed 1234
  python warmup_loader.py ../langpack/tr-TR --register ui --register tutorial --format jsonl --out warm.jsonl

Exit codes: 0 sample has the requested size, 1 fewer matching lines than requested
(the sample is still written), 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, read_text_bom, resolve_input,
    run_main, strip_tags, __version__,
)

TOOL = "warmup_loader"
REGISTERS = ("ui", "tutorial", "dialogue_casual", "dialogue_formal")
DEFAULT_COUNT = 40
DEFAULT_SEED = 1234
MIN_LEN, MAX_LEN = 2, 300
REFERENCE_SOURCE = "reference"
_ENGINE_CODES = re.compile(r"\{[A-Z][A-Z0-9_]*\}|\[(?:[a-z][a-z0-9_]*|#[0-9a-fA-F]{3,8})?\]")


def clean_text(text: str) -> str:
    """Display form for prompts: tags and engine colour codes removed, whitespace tidied (placeholders kept)."""
    out = strip_tags(text, "auto")
    out = _ENGINE_CODES.sub("", out)
    out = re.sub(r"[ \t]+", " ", out)
    return "\n".join(l.strip() for l in out.splitlines()).strip()


def read_pack_lines(pack_dir: Path, include_local: bool = True) -> List[Dict[str, Any]]:
    """Read warmup.jsonl (+ local/warmup.jsonl). Raises L10nError when the pack has no warm-up file."""
    main = pack_dir / "warmup.jsonl"
    local = pack_dir / "local" / "warmup.jsonl"
    if not main.is_file() and not (include_local and local.is_file()):
        raise L10nError(f"{pack_dir}: no warmup.jsonl; build the pack with build_language_pack.py first")
    rows: List[Dict[str, Any]] = []
    for path in ([main] if main.is_file() else []) + ([local] if include_local and local.is_file() else []):
        for n, line in enumerate(read_text_bom(path).splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise L10nError(f"{path}:{n}: invalid JSON line ({exc.msg})")
            if not isinstance(rec, dict) or not isinstance(rec.get("text"), str):
                raise L10nError(f"{path}:{n}: each line needs a 'text' string")
            rows.append(rec)
    return rows


def sample_warmup(rows: Sequence[Dict[str, Any]], registers: Optional[Sequence[str]] = None, count: int = DEFAULT_COUNT,
                  seed: int = DEFAULT_SEED) -> List[Dict[str, Any]]:
    """Seeded, source-balanced sample of cleaned lines of the given registers (all registers when None)."""
    regs = set(registers) if registers else set(REGISTERS)
    pool: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()
    ordered = sorted(rows, key=lambda r: (str(r.get("source", "")), str(r.get("key", "")), r["text"]))
    for r in ordered:
        if r.get("register") not in regs:
            continue
        text = clean_text(r["text"])
        if not (MIN_LEN <= len(text) <= MAX_LEN) or text in seen:
            continue
        seen.add(text)
        rec = {"text": text, "register": r.get("register"), "source": str(r.get("source", "")),
               "license_class": r.get("license_class", "bundle"), "consistency": r.get("consistency", "single")}
        pool.setdefault(rec["source"], []).append(rec)
    rng = random.Random(seed)
    queues: List[List[Dict[str, Any]]] = []
    for src in sorted(pool, key=lambda s: (s != REFERENCE_SOURCE, s)):
        items = list(pool[src])
        rng.shuffle(items)
        items.sort(key=lambda it: 0 if it["consistency"] in ("trusted", "reference_agrees") else 1)  # stable: keeps the shuffle inside groups
        queues.append(items)
    picked: List[Dict[str, Any]] = []
    while len(picked) < count and any(queues):
        for q in queues:
            if q and len(picked) < count:
                picked.append(q.pop(0))
    return picked


def load_warmup(pack_dir: Path, registers: Optional[Sequence[str]] = None, count: int = DEFAULT_COUNT, seed: int = DEFAULT_SEED,
                include_local: bool = True) -> List[Dict[str, Any]]:
    """Read a pack and return the seeded warm-up sample (see sample_warmup)."""
    return sample_warmup(read_pack_lines(Path(pack_dir), include_local), registers, count, seed)


def one_line(text: str) -> str:
    """Join the non-empty lines of a multi-line text with ' / '."""
    return " / ".join(l.strip() for l in text.splitlines() if l.strip())


def render_warmup(entries: Sequence[Dict[str, Any]]) -> str:
    """Prompt block: one line per sample, grouped by register, multi-line texts joined with ' / '."""
    if not entries:
        return ""
    out: List[str] = []
    for reg in REGISTERS:
        group = [e for e in entries if e.get("register") == reg]
        if not group:
            continue
        out.append(f"[{reg}]")
        out.extend("- " + one_line(e["text"]) for e in group)
    return "\n".join(out)


def check_registers(values: Sequence[str]) -> List[str]:
    """Validate register names (exit 2 on unknown ones)."""
    for v in values:
        if v not in REGISTERS:
            raise L10nError(f"unknown register '{v}'; known: {', '.join(REGISTERS)}")
    return list(values)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Seeded warm-up sample (30 to 50 native lines) from a language pack")
    add_input_argument(ap, "Language pack folder, for example langpack/tr-TR")
    ap.add_argument("--register", action="append", default=[], help="Register to sample (repeatable): ui, tutorial, dialogue_casual, dialogue_formal")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"Lines to pick (default {DEFAULT_COUNT}, recommended 30 to 50)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Sampling seed (default {DEFAULT_SEED})")
    ap.add_argument("--no-local", action="store_true", help="Ignore local/warmup.jsonl (bundle class lines only)")
    ap.add_argument("--format", choices=("text", "jsonl"), default="text", help="Output of --out: prompt text block or JSON lines")
    ap.add_argument("--out", help="Write the sample to this file")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    if args.count < 1:
        raise L10nError("--count must be at least 1")
    pack = Path(args.input)
    if not pack.is_dir():
        raise L10nError(f"language pack folder not found: {pack}")
    regs = check_registers(args.register) or list(REGISTERS)
    entries = load_warmup(pack, regs, args.count, args.seed, include_local=not args.no_local)
    if args.out:
        body = render_warmup(entries) + "\n" if args.format == "text" else "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        Path(args.out).write_text(body, encoding="utf-8")
    short = len(entries) < args.count
    exit_code = EXIT_FINDINGS if short else EXIT_OK
    lines = [f"Warm-up sample: {pack} registers {', '.join(regs)}, seed {args.seed}, {len(entries)} of {args.count} lines"]
    if short:
        lines.append(f"  WARN: only {len(entries)} matching lines in the pack")
    limit = args.max_report if args.max_report is not None else len(entries)
    for e in entries[:limit]:
        lines.append(f"  [{e['register']}] {one_line(e['text'])}  ({e['source']})")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "pack": str(pack), "registers": regs, "seed": args.seed, "count": args.count,
               "picked": len(entries), "entries": entries, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
