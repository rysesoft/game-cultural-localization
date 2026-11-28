#!/usr/bin/env python3
"""Validate providers.config.json, the API key environment variables and (optionally) ping every model.

Checks without any network call:
  * config schema (providers, models, roles, agreement, budget_caps, roundtrip)
  * one member per family in every jury tier (J1, J2, J3)
  * the API key environment variable of every model the chosen roles need

With --ping every model of the chosen roles gets one tiny call (real API, or the
fake provider with --dry-run). A model the API does not know switches to its
configured fallback and the switch is reported.

Usage:
  python providers_check.py providers.config.json [--roles J1,J2,J3] [--ping] [--dry-run]

Exit codes: 0 config, keys and pings OK, 1 a fallback model had to be used,
2 config error, missing API key, or a model failed without a fallback.
Python 3.15, standard library only.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from l10n_common import (  # noqa: E402
    EXIT_FINDINGS, EXIT_OK, L10nError, add_common_args, add_input_argument, emit_report, resolve_input, run_main, __version__,
)
from providers import JURY_TIERS, OPTIONAL_SINGLE_ROLES, SINGLE_ROLES, FakeScenario, Router, envelope, load_providers_config  # noqa: E402

TOOL = "providers_check"


def parse_roles(raw: str) -> list[str]:
    """Split and validate a comma separated role list."""
    roles = [r.strip() for r in raw.split(",") if r.strip()]
    known = SINGLE_ROLES + OPTIONAL_SINGLE_ROLES + JURY_TIERS
    for r in roles:
        if r not in known:
            raise L10nError(f"unknown role '{r}'; known: {', '.join(known)}")
    return roles


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=TOOL, description="Validate providers.config.json and API keys, optionally ping every model")
    add_input_argument(ap, "providers.config.json to check (the bundled one is scripts/providers.config.json)")
    ap.add_argument("--roles", default=",".join(SINGLE_ROLES + JURY_TIERS), help="Comma separated roles to check (default: all)")
    ap.add_argument("--ping", action="store_true", help="Send one tiny request to every model of the roles")
    ap.add_argument("--dry-run", action="store_true", help="Use the offline fake provider (no API key, no network)")
    ap.add_argument("--fake-scenario", help="Fake provider scenario JSON (with --dry-run)")
    ap.add_argument("--budget-log", help="Append one JSON line per ping to this budget.jsonl")
    add_common_args(ap, TOOL)
    return ap


def main() -> int:
    ap = build_parser()
    args = ap.parse_args()
    resolve_input(ap, args)
    cfg = load_providers_config(Path(args.input))
    roles = parse_roles(args.roles)
    router = Router(cfg, dry_run=args.dry_run, scenario=FakeScenario.load(Path(args.fake_scenario)) if args.fake_scenario else None,
                    budget_log=Path(args.budget_log) if args.budget_log else None)
    router.require(roles)
    lines = [f"Providers check: {args.input} ({'dry run, fake provider' if args.dry_run else 'live keys'})"]
    role_rows: list[dict[str, Any]] = []
    for role in roles:
        specs = cfg.jury(role) if role in JURY_TIERS else [cfg.role_model(role)]
        desc = ", ".join(f"{s.alias}={s.id} [{s.provider}]" for s in specs)
        lines.append(f"  {role:<9} {desc}")
        role_rows.append({"role": role, "models": [{"alias": s.alias, "id": s.id, "provider": s.provider,
                                                     "env_key": cfg.env_key(s)} for s in specs]})
    pings: list[dict[str, Any]] = []
    if args.ping:
        for spec in cfg.specs_for_roles(roles):
            role = next(r for r in roles if spec in (cfg.jury(r) if r in JURY_TIERS else [cfg.role_model(r)]))
            prov = router.for_model(spec.alias, role)
            res = prov.complete("You are a health check.", envelope("Reply with the JSON object {\"ok\": true}.", {"task": "ping"}),
                                max_tokens=16, json_mode=True)
            pings.append({"alias": spec.alias, "requested": spec.id, "answered_by": prov.model, "fallback_from": prov.fallback_from,
                          "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "latency_ms": res.latency_ms})
            lines.append(f"  ping {spec.alias:<9} {prov.model} ok ({res.latency_ms} ms)" + (f", fallback from {prov.fallback_from}" if prov.fallback_from else ""))
    for n in router.notes:
        lines.append(f"  NOTE: {n}")
    exit_code = EXIT_FINDINGS if any(p["fallback_from"] for p in pings) else EXIT_OK
    lines.append(f"  Exit code: {exit_code}")
    payload = {"tool": TOOL, "version": __version__, "config": str(args.input), "dry_run": args.dry_run, "roles": role_rows,
               "pings": pings, "notes": router.notes, "exit_code": exit_code}
    emit_report("\n".join(lines), payload, args.json, args.output)
    return exit_code


if __name__ == "__main__":
    run_main(main)
