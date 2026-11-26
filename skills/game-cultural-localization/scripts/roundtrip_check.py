#!/usr/bin/env python3
"""Back-translation sniff test: does a translated dialogue line still carry the English skeleton?

A target line is back-translated into English as literally as possible by the
'roundtrip' model. The calque score (0 to 1) measures how closely the back
translation follows the original English, word order included. Native writing
drifts away from the English, a calque comes back almost verbatim.

The test only carries information for longer dialogue, so it applies only when
  * the row register is in roundtrip.registers of providers.config.json (dialogue_casual, dialogue_formal)
  * the target has more than roundtrip.min_words words (6)
Other rows are reported with "applied": false and cost no model call.

Calibration (--calibrate): the input is a contrastive.json. Native and robot lines are
scored and the threshold that best separates them (balanced accuracy) is written to
langpack/<locale>/roundtrip_threshold.json.

Usage:
  python roundtrip_check.py pass1_tr-TR_01.json --locale tr-TR --src-field en --dst-field dst
  python roundtrip_check.py ../langpack/tr-TR/contrastive.json --locale tr-TR --calibrate

Exit codes: check mode 0 no calque suspect, 1 at least one line at or above the threshold.
Calibrate mode 0 threshold written, 1 written but weak (fewer than 5 lines per class or
balanced accuracy below 0.75). 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data, load_table,
    normalize_locale, resolve_input, run_main, __version__,
)
from build_language_pack import DEFAULT_ROUNDTRIP_THRESHOLD, LANGPACK_DIR, infer_register  # noqa: E402
from llm_tasks import add_model_args, backtranslate_rows, default_budget_path, make_router, word_count  # noqa: E402

TOOL = "roundtrip_check"
WEAK_MIN_PER_CLASS = 5
WEAK_MIN_ACCURACY = 0.75


def _words(text: str) -> List[str]:
    return re.findall(r"\w+", text.casefold())


def calque_score(english: str, back: str) -> float:
    """0 to 1. Mean of word-sequence and character similarity between the English source and the back-translation."""
    if not english.strip() or not back.strip():
        return 0.0
    w = difflib.SequenceMatcher(None, _words(english), _words(back), autojunk=False).ratio()
    c = difflib.SequenceMatcher(None, " ".join(_words(english)), " ".join(_words(back)), autojunk=False).ratio()
    return round((w + c) / 2.0, 4)


def eligible(target: str, register: str, min_words: int, registers: Sequence[str]) -> Tuple[bool, str]:
    """(applies, reason when it does not)."""
    if register not in registers:
        return False, "register"
    if word_count(target) <= min_words:
        return False, "short"
    return True, ""


def roundtrip_evidence(rows: Sequence[Dict[str, Any]], locale: str, provider: Any, *, min_words: int, registers: Sequence[str],
                       threshold: float, batch_size: int = 30) -> Dict[str, Dict[str, Any]]:
    """rows [{key, en, target, register}] -> key -> {applied, calque_score, back, suspect} (model calls only for eligible rows)."""
    out: Dict[str, Dict[str, Any]] = {}
    todo: List[Tuple[str, Dict[str, Any]]] = []
    for i, r in enumerate(rows):
        ok, why = eligible(str(r.get("target", "")), str(r.get("register", "")), min_words, registers)
        if not ok or not str(r.get("en", "")).strip():
            out[str(r["key"])] = {"applied": False, "reason": why or "no_source"}
        else:
            todo.append((str(i), r))
    backs = backtranslate_rows(provider, [{"key": k, "target": r["target"]} for k, r in todo], locale, batch_size=batch_size) if todo else {}
    for k, r in todo:
        back = backs[k]
        score = calque_score(str(r["en"]), back)
        out[str(r["key"])] = {"applied": True, "calque_score": score, "back": back, "suspect": score >= threshold}
    return out


def best_threshold(native: Sequence[float], robot: Sequence[float]) -> Tuple[float, float]:
    """Threshold t (robot >= t, native < t) with the best balanced accuracy, midpoint between neighbours. Returns (t, accuracy)."""
    values = sorted(set(native) | set(robot))
    cands = [0.0] + [round((a + b) / 2.0, 4) for a, b in zip(values, values[1:])] + [1.0001]
    best = (DEFAULT_ROUNDTRIP_THRESHOLD, -1.0)
    for t in cands:
        tpr = sum(1 for s in robot if s >= t) / len(robot) if robot else 0.0
        tnr = sum(1 for s in native if s < t) / len(native) if native else 0.0
        acc = round((tpr + tnr) / 2.0, 4)
        if acc > best[1]:
            best = (min(1.0, t), acc)
    return best


def calibrate(contrastive: Dict[str, Any], locale: str, provider: Any, *, min_words: int, registers: Sequence[str],
              batch_size: int = 30) -> Dict[str, Any]:
    """Score native and robot lines of a contrastive set and derive the threshold."""
    pairs = contrastive.get("pairs")
    if not isinstance(pairs, list):
        raise L10nError("contrastive set has no 'pairs' list")
    rows: List[Dict[str, Any]] = []
    for p in pairs:
        if not all(isinstance(p.get(k), str) for k in ("key", "en", "native", "robot")):
            raise L10nError("every contrastive pair needs string fields key, en, native and robot")
        rows.append({"key": f"native::{p['key']}", "en": p["en"], "target": p["native"], "register": p.get("register", "")})
        rows.append({"key": f"robot::{p['key']}", "en": p["en"], "target": p["robot"], "register": p.get("register", "")})
    ev = roundtrip_evidence(rows, locale, provider, min_words=min_words, registers=registers, threshold=1.1, batch_size=batch_size)
    native = [v["calque_score"] for k, v in ev.items() if v["applied"] and k.startswith("native::")]
    robot = [v["calque_score"] for k, v in ev.items() if v["applied"] and k.startswith("robot::")]
    if not native or not robot:
        raise L10nError(f"no eligible dialogue pairs to calibrate on (register in {list(registers)} and more than {min_words} words)")
    thr, acc = best_threshold(native, robot)
    weak = min(len(native), len(robot)) < WEAK_MIN_PER_CLASS or acc < WEAK_MIN_ACCURACY
    mean = lambda xs: round(sum(xs) / len(xs), 4)  # noqa: E731
    return {"locale": locale, "threshold": thr, "calibrated": True, "weak": weak, "balanced_accuracy": acc,
            "n_native": len(native), "n_robot": len(robot), "native_mean": mean(native), "robot_mean": mean(robot),
            "min_words": min_words, "registers": list(registers)}


def load_threshold(locale: str, langpack_dir: Path) -> Tuple[float, str]:
    """Threshold of the pack (roundtrip_threshold.json) or the default."""
    path = langpack_dir / locale / "roundtrip_threshold.json"
    if path.is_file():
        data = load_json_data(path)
        if isinstance(data, dict) and isinstance(data.get("threshold"), (int, float)):
            return float(data["threshold"]), str(path)
    return DEFAULT_ROUNDTRIP_THRESHOLD, "default"


def load_check_rows(path: Path, locale: str, src_field: str, dst_field: Optional[str], key_field: str) -> List[Dict[str, Any]]:
    """Rows {key, en, target, register} of a translated table (target column probed when not given)."""
    candidates = [dst_field] if dst_field else ["dst", locale, "target"]
    last: Optional[L10nError] = None
    for col in candidates:
        try:
            rows = load_table(path, src_field, col, key_field)
            break
        except L10nError as exc:
            last = exc
    else:
        raise L10nError(f"{path}: no target column (tried {', '.join(str(c) for c in candidates)}), pass --dst-field") from last
    out = []
    for r in rows:
        category = str(r.meta.get("register") or r.meta.get("category") or "")
        out.append({"key": r.key, "en": r.src, "target": r.dst, "register": infer_register(category, r.dst, "game")})
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Back-translation calque check for long dialogue lines, or threshold calibration")
    add_input_argument(ap, "Translated table (key, en, target, category) or, with --calibrate, a contrastive.json")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--calibrate", action="store_true", help="Input is a contrastive set: derive and write the threshold")
    ap.add_argument("--src-field", default="en", help="Source column (default en)")
    ap.add_argument("--dst-field", default=None, help="Target column (default: dst, the locale code, target)")
    ap.add_argument("--key-field", default="key", help="Key column (default key)")
    ap.add_argument("--threshold", type=float, default=None, help="Calque threshold (default: the pack's roundtrip_threshold.json, else 0.85)")
    ap.add_argument("--min-words", type=int, default=None, help="Apply to lines with more words than this (default: providers config, 6)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs (default: the skill's langpack/)")
    ap.add_argument("--out", default=None, help="Calibrate mode output (default: langpack/<locale>/roundtrip_threshold.json)")
    ap.add_argument("--batch-size", type=int, default=30, help="Lines per model call (default 30)")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    langpack = Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR
    inp = Path(args.input)
    if args.calibrate:
        out = Path(args.out) if args.out else langpack / locale / "roundtrip_threshold.json"
        data = load_json_data(inp)
        if not isinstance(data, dict):
            raise L10nError(f"{inp}: contrastive set must be a JSON object")
        router = make_router(args, ["roundtrip"], default_budget_path(out))
        min_words = args.min_words if args.min_words is not None else int(router.config.roundtrip["min_words"])
        res = calibrate(data, locale, router.for_role("roundtrip"), min_words=min_words, registers=router.config.roundtrip["registers"],
                        batch_size=args.batch_size)
        res["source"] = str(inp)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        exit_code = EXIT_FINDINGS if res["weak"] else EXIT_OK
        lines = [f"Round-trip calibration {locale}: threshold {res['threshold']} written to {out}",
                 f"  native mean {res['native_mean']} (n {res['n_native']}), robot mean {res['robot_mean']} (n {res['n_robot']}), "
                 f"balanced accuracy {res['balanced_accuracy']}"]
        if res["weak"]:
            lines.append("  WARN: weak calibration, add more dialogue pairs")
        lines.append(f"  Exit code: {exit_code}")
        emit_report("\n".join(lines), {"tool": TOOL, "version": __version__, "mode": "calibrate", "out": str(out), **res,
                                       "notes": router.notes, "exit_code": exit_code}, args.json, args.output)
        return exit_code
    rows = load_check_rows(inp, locale, args.src_field, args.dst_field, args.key_field)
    thr, thr_src = (args.threshold, "--threshold") if args.threshold is not None else load_threshold(locale, langpack)
    router = make_router(args, ["roundtrip"], default_budget_path(inp))
    min_words = args.min_words if args.min_words is not None else int(router.config.roundtrip["min_words"])
    ev = roundtrip_evidence(rows, locale, router.for_role("roundtrip"), min_words=min_words, registers=router.config.roundtrip["registers"],
                            threshold=thr, batch_size=args.batch_size)
    applied = [k for k, v in ev.items() if v["applied"]]
    suspects = [k for k in applied if ev[k]["suspect"]]
    exit_code = EXIT_FINDINGS if suspects else EXIT_OK
    lines = [f"Round-trip check {locale}: {inp} ({len(rows)} rows, applied to {len(applied)}, threshold {thr} from {thr_src})"]
    limit = args.max_report if args.max_report is not None else len(suspects)
    for k in suspects[:limit]:
        lines.append(f"  CALQUE {k}: score {ev[k]['calque_score']}, back '{ev[k]['back']}'")
    lines.append(f"  Suspects: {len(suspects)}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "mode": "check", "locale": locale, "input": str(inp), "threshold": thr,
               "threshold_source": thr_src, "min_words": min_words, "rows": [{"key": k, **v} for k, v in ev.items()],
               "summary": {"rows": len(rows), "applied": len(applied), "suspects": len(suspects)}, "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
