#!/usr/bin/env python3
"""J3 deliberation round for lines the strongest jury tier disagrees on (brief A5).

1. The three J3 members have voted (their first votes come from jury.py).
2. Each member is shown the other two scores and reasons WITHOUT model or family names
   (labelled juror A and juror B, names scrubbed from the reason text), plus the mechanical
   evidence package. Ban list hits, the three closest approved translation memory lines
   (target text only) and the back-translation signal for long dialogue.
3. Each member votes once more.
4. Majority decides (two equal scores). Three different scores leave the line 'unresolved',
   it goes to the developer with the three rationales.

As a CLI it takes a jury verdict file and the blind slice, deliberates every J3 disagreement
still marked 'unresolved' and rewrites the verdicts (in place unless --out is given).

Usage:
  python deliberate.py verdicts_tr-TR_01.json --slice blind_tr-TR_01.json --locale tr-TR [--dry-run]

Exit codes: 0 no line left unresolved, 1 at least one line stays unresolved, 2 usage or input error.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, load_json_data, normalize_locale,
    resolve_input, run_main, __version__,
)
from build_language_pack import LANGPACK_DIR  # noqa: E402
from jury import build_system_prompt, juror_view, load_blind_slice, status_for  # noqa: E402
from llm_tasks import add_model_args, default_budget_path, make_router, revote  # noqa: E402

TOOL = "deliberate"
LABELS = ("A", "B")
GENERIC_NAMES = ("anthropic", "claude", "haiku", "sonnet", "opus", "google", "gemini", "hydrogen", "neon", "carbon",
                 "deepseek", "openai", "gpt", "llama", "mistral", "qwen", "v4 pro", "v4 flash", "v4-pro", "v4-flash", "v4.1 flash",
                 "v4.1-flash", "flash", "pro")


def name_scrubber(config: Any) -> "re.Pattern[str]":
    """Regex matching every model id, alias and family name of the config plus common vendor names."""
    names = set(GENERIC_NAMES)
    for spec in config.models.values():
        names.update({spec.alias.lower(), spec.id.lower(), spec.provider.lower()})
    alts = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in alts) + r")(?![\w-])", re.IGNORECASE)


def anonymize(text: str, scrub: "re.Pattern[str]") -> str:
    """Replace model and vendor names in a rationale with 'another juror'."""
    out = scrub.sub("another juror", text or "")
    return re.sub(r"another juror(?:[\s-]+another juror)+", "another juror", out)


def evidence_package(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """What jurors may see of the evidence: rule hits, three approved TM target lines, calque signal (no source text)."""
    tm = [n for n in evidence.get("tm_neighbors", []) if n.get("status", "approved") == "approved"][:3]
    rt = evidence.get("roundtrip") or {}
    return {"ban_hits": [{"rule": b.get("rule"), "message": b.get("message")} for b in evidence.get("ban_hits", [])],
            "tm_neighbors": [{"target": n.get("dst", n.get("target", "")), "category": n.get("category", ""), "similarity": n.get("similarity")} for n in tm],
            "roundtrip": {k: rt[k] for k in ("applied", "calque_score", "suspect") if k in rt}}


def decide(scores: Sequence[int]) -> Optional[int]:
    """Majority score (at least two equal votes), else None."""
    score, count = Counter(scores).most_common(1)[0]
    return score if count >= 2 else None


def deliberate_line(entry: Dict[str, Any], j3_votes: Sequence[Dict[str, Any]], evidence: Dict[str, Any], members: Sequence[Any],
                    locale: str, system: str, scrub: "re.Pattern[str]") -> Dict[str, Any]:
    """Run one re-vote round for a line. Returns {score, status, rationales, revotes, deliberation}."""
    by_member = {int(v["member"]): v for v in j3_votes}
    package = evidence_package(evidence)
    view = juror_view(entry)
    revotes: List[Dict[str, Any]] = []
    for m in members:
        own = by_member.get(m.index)
        if own is None:
            raise L10nError(f"deliberation for '{entry['key']}': no first J3 vote of member {m.index}")
        others = [by_member[i] for i in sorted(by_member) if i != m.index]
        payload = {"key": entry["key"], "target": view["target"], "context": {k: v for k, v in view.items() if k not in ("key", "target")},
                   "own": {k: own[k] for k in ("score", "issue_type", "reason", "suggested")},
                   "others": [{"juror": LABELS[i], "score": o["score"], "issue_type": o["issue_type"], "reason": anonymize(o["reason"], scrub),
                               "suggested": o.get("suggested", "")} for i, o in enumerate(others)],
                   "evidence": package}
        v = revote(m.provider, payload, locale, system=system)
        revotes.append({"key": entry["key"], "tier": "deliberation", "member": m.index, "family": m.family, "model": m.provider.model, **v})
    scores = [v["score"] for v in revotes]
    majority = decide(scores)
    first = [by_member[i]["score"] for i in sorted(by_member)]
    info = {"first": first, "revote": scores, "majority": majority}
    if majority is None:
        return {"score": min(scores), "status": "unresolved", "rationales": [v["reason"] for v in revotes], "revotes": revotes, "deliberation": info}
    return {"score": majority, "status": status_for(majority), "rationales": [v["reason"] for v in revotes], "revotes": revotes, "deliberation": info}


def make_deliberator(router: Any, locale: str, system: str) -> Any:
    """Callable for jury.run_jury(deliberator=...)."""
    members = router.jury("J3")
    scrub = name_scrubber(router.config)

    def run(entry: Dict[str, Any], j3_votes: List[Dict[str, Any]], evidence: Dict[str, Any]) -> Dict[str, Any]:
        return deliberate_line(entry, j3_votes, evidence, members, locale, system, scrub)
    return run


def deliberate_verdicts(doc: Dict[str, Any], entries: Iterable[Dict[str, Any]], router: Any, locale: str, system: str) -> Dict[str, int]:
    """Deliberate every J3 'unresolved' verdict of a jury verdict document in place; returns counts."""
    by_key = {e["key"]: e for e in entries}
    run = make_deliberator(router, locale, system)
    counts = {"deliberated": 0, "resolved": 0, "unresolved": 0}
    for v in doc.get("verdicts", []):
        if v.get("status") != "unresolved" or v.get("final_tier") != "J3":
            continue
        if v["key"] not in by_key:
            raise L10nError(f"verdict '{v['key']}' is not in the blind slice")
        j3 = [x for x in v.get("votes", []) if x.get("tier") == "J3"]
        res = run(by_key[v["key"]], j3, v.get("evidence", {}))
        v["votes"] = list(v.get("votes", [])) + res["revotes"]
        v.update({"final_tier": "deliberation", "score": res["score"], "status": res["status"], "rationales": res["rationales"],
                  "deliberation": res["deliberation"]})
        counts["deliberated"] += 1
        counts["resolved" if res["status"] != "unresolved" else "unresolved"] += 1
    if counts["deliberated"]:
        statuses = ("pass", "rewrite_light", "rewrite", "critical", "unresolved")
        stats = doc.setdefault("stats", {})
        stats["status"] = {s: sum(1 for v in doc["verdicts"] if v["status"] == s) for s in statuses}
        stats.setdefault("final_tier", {})["deliberation"] = sum(1 for v in doc["verdicts"] if v["final_tier"] == "deliberation")
        stats["final_tier"]["J3"] = sum(1 for v in doc["verdicts"] if v["final_tier"] == "J3")
        stats["deliberation"] = counts
    return counts


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="J3 deliberation round (anonymous rationales, evidence, one re-vote, majority)")
    add_input_argument(ap, "Verdict file written by jury.py")
    ap.add_argument("--slice", required=True, help="The blind slice the jury read (target texts)")
    ap.add_argument("--locale", required=True, help="Target locale")
    ap.add_argument("--out", default=None, help="Write the updated verdicts here (default: update the input file)")
    ap.add_argument("--langpack-dir", default=None, help="Root of the language packs, for the critic prompt warm-up (default: the skill's langpack/)")
    ap.add_argument("--no-warmup", action="store_true", help="Leave the warm-up block out of the critic prompt")
    ap.add_argument("--seed", type=int, default=1234, help="Seed of the warm-up and few-shot sample (default 1234)")
    add_model_args(ap)
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    locale, _v = normalize_locale(args.locale)
    inp = Path(args.input)
    doc = load_json_data(inp)
    if not isinstance(doc, dict) or not isinstance(doc.get("verdicts"), list):
        raise L10nError(f"{inp}: not a jury verdict file (no 'verdicts' list)")
    entries, _src = load_blind_slice(Path(args.slice))
    out = Path(args.out) if args.out else inp
    router = make_router(args, ["J3"], default_budget_path(out))
    pack_dir = (Path(args.langpack_dir) if args.langpack_dir else LANGPACK_DIR) / locale
    system, _info = build_system_prompt(locale, entries, pack_dir, warmup=not args.no_warmup, warmup_count=40, shots=6, seed=args.seed)
    counts = deliberate_verdicts(doc, entries, router, locale, system)
    doc["notes"] = list(doc.get("notes", [])) + [n for n in router.notes if n not in doc.get("notes", [])]
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    remaining = sum(1 for v in doc["verdicts"] if v["status"] == "unresolved")
    exit_code = EXIT_FINDINGS if remaining else EXIT_OK
    lines = [f"Deliberation {locale}: {counts['deliberated']} J3 disagreement(s), {counts['resolved']} settled by majority, "
             f"{counts['unresolved']} still unresolved -> {out}"]
    for v in doc["verdicts"]:
        if v.get("final_tier") == "deliberation":
            d = v["deliberation"]
            lines.append(f"  {v['key']}: first {d['first']} revote {d['revote']} -> {v['status']}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "out": str(out), "counts": counts, "unresolved": remaining,
               "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
