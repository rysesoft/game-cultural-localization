#!/usr/bin/env python3
"""Token, call, latency and cost report from budget.jsonl, with a projection to a full project.

Reads the lines every model call appends to budget.jsonl (role, provider, model, input_tokens,
output_tokens, latency_ms, ok) and aggregates them by role, by provider, by model and by role
and model. Cost uses price_in / price_out (USD per 1M tokens) of providers.config.json, a model
whose price is null is reported as "price not set" and its cost is left out of every total.

Projection: with --rows (the number of source lines the logged run processed) the per-line
calls, tokens and cost are scaled to --project-rows lines times --project-locales locales
(default 20,000 lines and 15 locales).

Usage:
  python budget_report.py loc_work/budget.jsonl --rows 400
  python budget_report.py loc_work/ --rows 400 --project-rows 20000 --project-locales 15 --max-cost 500

Exit codes: 0 report written, 1 the cost (projected when --rows is given, else actual)
exceeds --max-cost, 2 usage or input error (no log, broken line).
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, read_text_bom, resolve_input,
    run_main, __version__,
)
from providers import load_providers_config  # noqa: E402

TOOL = "budget_report"
PRICE_NOT_SET = "price not set (fiyat girilmedi)"


def find_logs(path: Path) -> List[Path]:
    """A budget file, or every budget*.jsonl below a folder (sorted)."""
    if path.is_file():
        return [path]
    if path.is_dir():
        logs = sorted(p for p in path.rglob("budget*.jsonl") if p.is_file())
        if not logs:
            raise L10nError(f"{path}: no budget*.jsonl file in this folder")
        return logs
    raise L10nError(f"budget log not found: {path}")


def read_records(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    """Parse JSON lines; every record needs role, provider, model and numeric token fields."""
    out: List[Dict[str, Any]] = []
    for p in paths:
        for n, line in enumerate(read_text_bom(p).splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise L10nError(f"{p}:{n}: invalid JSON line ({exc.msg})")
            if not isinstance(rec, dict) or not all(isinstance(rec.get(k), str) for k in ("role", "provider", "model")):
                raise L10nError(f"{p}:{n}: a budget line needs role, provider and model")
            for k in ("input_tokens", "output_tokens", "latency_ms"):
                v = rec.get(k, 0)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                    raise L10nError(f"{p}:{n}: '{k}' must be a non-negative number")
            out.append(rec)
    if not out:
        raise L10nError("the budget log is empty")
    return out


def price_table(config: Any) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """model id -> (price_in, price_out) in USD per 1M tokens."""
    return {s.id: (s.price_in, s.price_out) for s in config.models.values()}


def cost_of(model: str, tin: float, tout: float, prices: Dict[str, Tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    """USD cost, None when the model or one of its prices is unknown."""
    pin, pout = prices.get(model, (None, None))
    if pin is None or pout is None:
        return None
    return tin / 1e6 * pin + tout / 1e6 * pout


def aggregate(records: Iterable[Dict[str, Any]], keys: Sequence[str], prices: Dict[str, Tuple[Optional[float], Optional[float]]]) -> List[Dict[str, Any]]:
    """Group records by the given fields; cost is summed per model so mixed groups stay exact."""
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for r in records:
        gk = tuple(str(r.get(k, "")) for k in keys)
        g = groups.setdefault(gk, {**{k: v for k, v in zip(keys, gk)}, "calls": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0,
                                   "latency_ms": 0, "cost_usd": 0.0, "priced": True, "unpriced_models": []})
        g["calls"] += 1
        g["errors"] += 0 if r.get("ok", True) else 1
        g["input_tokens"] += int(r.get("input_tokens", 0))
        g["output_tokens"] += int(r.get("output_tokens", 0))
        g["latency_ms"] += int(r.get("latency_ms", 0))
        c = cost_of(r["model"], r.get("input_tokens", 0), r.get("output_tokens", 0), prices)
        if c is None:
            g["priced"] = False
            if r["model"] not in g["unpriced_models"]:
                g["unpriced_models"].append(r["model"])
        else:
            g["cost_usd"] += c
    out = []
    for gk in sorted(groups):
        g = groups[gk]
        g["cost_usd"] = round(g["cost_usd"], 6)
        g["mean_latency_ms"] = round(g["latency_ms"] / g["calls"], 1) if g["calls"] else 0.0
        if not g["priced"]:
            g["cost_note"] = PRICE_NOT_SET
        out.append(g)
    return out


def project(totals: Dict[str, Any], rows: int, project_rows: int, project_locales: int) -> Dict[str, Any]:
    """Scale the measured per-line usage to project_rows x project_locales lines."""
    factor = project_rows * project_locales / float(rows)
    return {"measured_rows": rows, "project_rows": project_rows, "project_locales": project_locales,
            "calls_per_row": round(totals["calls"] / rows, 3),
            "cost_per_row_usd": round(totals["cost_usd"] / rows, 6),
            "calls": int(round(totals["calls"] * factor)),
            "input_tokens": int(round(totals["input_tokens"] * factor)),
            "output_tokens": int(round(totals["output_tokens"] * factor)),
            "cost_usd": round(totals["cost_usd"] * factor, 2),
            "complete": totals["priced"],
            "note": "" if totals["priced"] else "lower bound, some models have no price (" + ", ".join(totals["unpriced_models"]) + ")"}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Aggregate budget.jsonl by role, provider and model, estimate cost and project it")
    add_input_argument(ap, "budget.jsonl, or a folder whose budget*.jsonl files are all read")
    ap.add_argument("--providers-config", default=None, help="providers.config.json with the prices (default: the bundled one)")
    ap.add_argument("--rows", type=int, default=None, help="Source lines the logged run processed (enables the projection)")
    ap.add_argument("--project-rows", type=int, default=20000, help="Lines per locale for the projection (default 20000)")
    ap.add_argument("--project-locales", type=int, default=15, help="Locales for the projection (default 15)")
    ap.add_argument("--max-cost", type=float, default=None, help="Exit 1 when the projected (or actual) cost in USD is above this")
    add_common_args(ap, TOOL)
    return ap


def _fmt_cost(g: Dict[str, Any]) -> str:
    return f"${g['cost_usd']:.4f}" if g["priced"] else (f"${g['cost_usd']:.4f} + {PRICE_NOT_SET}" if g["cost_usd"] else PRICE_NOT_SET)


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    if args.rows is not None and args.rows <= 0:
        raise L10nError("--rows must be a positive number")
    if args.project_rows <= 0 or args.project_locales <= 0:
        raise L10nError("--project-rows and --project-locales must be positive")
    logs = find_logs(Path(args.input))
    records = read_records(logs)
    prices = price_table(load_providers_config(Path(args.providers_config) if args.providers_config else None))
    totals = aggregate(records, [], prices)[0]
    totals.pop("cost_note", None)
    by_role = aggregate(records, ["role"], prices)
    by_provider = aggregate(records, ["provider"], prices)
    by_model = aggregate(records, ["provider", "model"], prices)
    by_role_model = aggregate(records, ["role", "provider", "model"], prices)
    proj = project(totals, args.rows, args.project_rows, args.project_locales) if args.rows else None
    dry = sum(1 for r in records if r.get("dry_run"))
    fallbacks = sorted({f"{r['fallback_from']} -> {r['model']}" for r in records if r.get("fallback_from")})
    check_cost = proj["cost_usd"] if proj else totals["cost_usd"]
    over = args.max_cost is not None and check_cost > args.max_cost
    exit_code = EXIT_FINDINGS if over else EXIT_OK
    lines = [f"Budget report: {len(records)} calls from {len(logs)} file(s)" + (f", {dry} dry-run calls (fake provider, estimated tokens)" if dry else "")]
    lines.append(f"  Total  tokens in {totals['input_tokens']}, out {totals['output_tokens']}, latency {totals['latency_ms']} ms, cost {_fmt_cost(totals)}")
    for title, rows in (("By role", by_role), ("By provider", by_provider), ("By model", by_model)):
        lines.append(f"  {title}")
        for g in rows:
            label = " / ".join(str(g[k]) for k in ("role", "provider", "model") if k in g)
            lines.append(f"    {label:<40} calls {g['calls']:>5}  in {g['input_tokens']:>9}  out {g['output_tokens']:>8}  "
                         f"mean {g['mean_latency_ms']:>7} ms  {_fmt_cost(g)}" + (f"  errors {g['errors']}" if g["errors"] else ""))
    if proj:
        lines.append(f"  Projection for {proj['project_rows']} lines x {proj['project_locales']} locales (measured on {proj['measured_rows']} lines)")
        lines.append(f"    {proj['calls_per_row']} calls per line, {proj['calls']} calls, {proj['input_tokens']} tokens in, "
                     f"{proj['output_tokens']} tokens out, cost ${proj['cost_usd']:.2f}" + (f" ({proj['note']})" if proj["note"] else ""))
    for f in fallbacks:
        lines.append(f"  NOTE: fallback used {f}")
    if over:
        lines.append(f"  OVER BUDGET: ${check_cost:.2f} is above --max-cost ${args.max_cost:.2f}")
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "files": [str(p) for p in logs], "records": len(records), "dry_run_records": dry,
               "totals": totals, "by_role": by_role, "by_provider": by_provider, "by_model": by_model, "by_role_model": by_role_model,
               "projection": proj, "missing_prices": sorted({m for g in by_model if not g["priced"] for m in g["unpriced_models"]}),
               "fallbacks": fallbacks, "max_cost": args.max_cost, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
