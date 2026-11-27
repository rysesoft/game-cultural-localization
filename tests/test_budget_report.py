"""P8: budget_report.py (aggregation by role, provider, model, cost from the config prices, projection)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_text  # noqa: E402

import budget_report as br  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import envelope, load_providers_config, Router  # noqa: E402


def rec(role: str, provider: str, model: str, tin: int, tout: int, ms: int = 100, **extra: Any) -> Dict[str, Any]:
    return {"role": role, "provider": provider, "model": model, "input_tokens": tin, "output_tokens": tout, "latency_ms": ms, "ok": True, **extra}


RECORDS = [
    rec("J1", "anthropic", "claude-haiku-5-5", 1_000_000, 200_000, 100),
    rec("J1", "anthropic", "claude-haiku-5-5", 1_000_000, 0, 300),
    rec("J1", "google", "gemini-4-hydrogen", 500_000, 100_000),
    rec("J1", "deepseek", "deepseek-flash", 2_000_000, 1_000_000),
    rec("J2", "deepseek", "deepseek-flash", 0, 0, 50, fallback_from="deepseek-v4-pro"),
    rec("pass1", "anthropic", "claude-sonnet-5-5", 100_000, 50_000, 900, ok=False),
]


def write_log(path: Path, records: List[Dict[str, Any]]) -> Path:
    return write_text(path, "".join(json.dumps(r) + "\n" for r in records))


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.prices = br.price_table(load_providers_config())

    def test_costs_from_config_prices(self):
        self.assertAlmostEqual(br.cost_of("claude-haiku-5-5", 1_000_000, 1_000_000, self.prices), 0.60)
        self.assertAlmostEqual(br.cost_of("deepseek-flash", 2_000_000, 1_000_000, self.prices), 0.90)
        self.assertIsNone(br.cost_of("gemini-4-hydrogen", 1, 1, self.prices))
        self.assertIsNone(br.cost_of("unknown-model", 1, 1, self.prices))

    def test_prompt_cache_prices(self):
        # 1M prompt tokens on Sonnet 5.5: all fresh $2.00, all written to the cache $2.50, all read from it $0.10
        self.assertAlmostEqual(br.cost_of("claude-sonnet-5-5", 1_000_000, 0, self.prices), 2.00)
        self.assertAlmostEqual(br.cost_of("claude-sonnet-5-5", 1_000_000, 0, self.prices, cache_write=1_000_000), 2.50)
        self.assertAlmostEqual(br.cost_of("claude-sonnet-5-5", 1_000_000, 0, self.prices, cache_read=1_000_000), 0.10)
        # the live probe on Haiku 5.5: 4375 prompt tokens with 4336 read from the cache costs about a tenth
        fresh = br.cost_of("claude-haiku-5-5", 4375, 0, self.prices)
        cached = br.cost_of("claude-haiku-5-5", 4375, 0, self.prices, cache_read=4336)
        self.assertLess(cached, fresh * 0.12)
        # DeepSeek hits are billed at about 2% of the miss price
        self.assertAlmostEqual(br.cost_of("deepseek-flash", 1_000_000, 0, self.prices, cache_read=1_000_000), 0.003)
        # a model without cache prices falls back to price_in, never cheaper than it really is
        bare = {"m": (1.0, 1.0)}
        self.assertAlmostEqual(br.cost_of("m", 1_000_000, 0, bare, cache_read=1_000_000), 1.0)

    def test_cache_tokens_in_groups_and_report(self):
        recs = [{"role": "J1", "provider": "anthropic", "model": "claude-haiku-5-5", "input_tokens": 4375, "output_tokens": 10,
                 "cache_read_tokens": 4336, "latency_ms": 5, "ok": True},
                {"role": "J1", "provider": "anthropic", "model": "claude-haiku-5-5", "input_tokens": 4374, "output_tokens": 10,
                 "cache_write_tokens": 4336, "latency_ms": 5, "ok": True}]
        g = br.aggregate(recs, ["model"], self.prices)[0]
        self.assertEqual((g["cache_read_tokens"], g["cache_write_tokens"]), (4336, 4336))
        with TempDir() as td:
            log = td / "budget.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
            code, out, err = run_cli("budget_report.py", str(log))
            self.assertEqual(code, 0, err)
            self.assertIn("Prompt cache  read 4336 (50% of the input), written 4336", out)
            log.write_text(json.dumps({**recs[0], "cache_read_tokens": -1}) + "\n", encoding="utf-8")
            self.assertEqual(run_cli("budget_report.py", str(log))[0], 2)

    def test_group_by_role_provider_model(self):
        by_model = {g["model"]: g for g in br.aggregate(RECORDS, ["provider", "model"], self.prices)}
        haiku = by_model["claude-haiku-5-5"]
        self.assertEqual((haiku["calls"], haiku["input_tokens"], haiku["output_tokens"]), (2, 2_000_000, 200_000))
        self.assertAlmostEqual(haiku["cost_usd"], 0.30)
        self.assertEqual(haiku["mean_latency_ms"], 200.0)
        self.assertEqual(by_model["gemini-4-hydrogen"]["cost_note"], br.PRICE_NOT_SET)
        self.assertEqual(by_model["claude-sonnet-5-5"]["errors"], 1)
        by_role = {g["role"]: g for g in br.aggregate(RECORDS, ["role"], self.prices)}
        self.assertEqual(by_role["J1"]["calls"], 4)
        self.assertFalse(by_role["J1"]["priced"])          # hydrogen has no price
        self.assertAlmostEqual(by_role["J1"]["cost_usd"], 0.30 + 0.90)
        self.assertTrue(by_role["pass1"]["priced"])
        by_provider = {g["provider"]: g for g in br.aggregate(RECORDS, ["provider"], self.prices)}
        self.assertEqual(by_provider["deepseek"]["calls"], 2)

    def test_projection(self):
        totals = br.aggregate(RECORDS[:2], [], self.prices)[0]
        p = br.project(totals, rows=10, project_rows=20000, project_locales=15)
        self.assertEqual(p["calls_per_row"], 0.2)
        self.assertEqual(p["calls"], 60000)
        self.assertAlmostEqual(p["cost_usd"], 0.30 * 30000, places=2)
        self.assertTrue(p["complete"])
        totals = br.aggregate(RECORDS, [], self.prices)[0]
        p = br.project(totals, 10, 20000, 15)
        self.assertFalse(p["complete"])
        self.assertIn("gemini-4-hydrogen", p["note"])

    def test_reads_router_budget_lines(self):
        with TempDir() as td:
            router = Router(load_providers_config(), dry_run=True, budget_log=td / "budget.jsonl")
            for m in router.jury("J1"):
                m.provider.complete("s", envelope("x", {"task": "ping"}))
            recs = br.read_records(br.find_logs(td))
        self.assertEqual(len(recs), 3)
        self.assertTrue(all(r.get("dry_run") for r in recs))

    def test_bad_logs(self):
        with TempDir() as td:
            with self.assertRaises(L10nError):
                br.read_records([write_text(td / "a.jsonl", "{not json\n")])
            with self.assertRaises(L10nError):
                br.read_records([write_text(td / "b.jsonl", json.dumps({"role": "x"}) + "\n")])
            with self.assertRaises(L10nError):
                br.read_records([write_text(td / "c.jsonl", "\n")])
            with self.assertRaises(L10nError):
                br.find_logs(td / "missing")


class CliTests(unittest.TestCase):
    def test_report_projection_and_exit_codes(self):
        with TempDir() as td:
            sub = td / "run"
            sub.mkdir()
            write_log(sub / "budget.jsonl", RECORDS[:4])
            write_log(sub / "budget_tr-TR.jsonl", RECORDS[4:])
            code, out, err = run_cli("budget_report.py", str(td), "--rows", "100", "--json")
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(len(data["files"]), 2)
            self.assertEqual(data["records"], 6)
            self.assertEqual(data["missing_prices"], ["gemini-4-hydrogen"])
            self.assertEqual(data["fallbacks"], ["deepseek-v4-pro -> deepseek-flash"])
            self.assertEqual(data["projection"]["project_rows"], 20000)
            self.assertEqual(data["projection"]["project_locales"], 15)
            self.assertEqual({g["role"] for g in data["by_role"]}, {"J1", "J2", "pass1"})
            code, out, _ = run_cli("budget_report.py", str(sub / "budget.jsonl"))
            self.assertEqual(code, 0)
            self.assertIn("fiyat girilmedi", out)
            self.assertIn("By role", out)
            code, out, _ = run_cli("budget_report.py", str(td), "--rows", "100", "--max-cost", "1")
            self.assertEqual(code, 1)
            self.assertIn("OVER BUDGET", out)
            code, _, _ = run_cli("budget_report.py", str(td), "--max-cost", "1000")
            self.assertEqual(code, 0)
            write_text(td / "broken.jsonl", "nope\n")
            self.assertEqual(run_cli("budget_report.py", str(td / "broken.jsonl"))[0], 2)
            self.assertEqual(run_cli("budget_report.py", str(td), "--rows", "0")[0], 2)
            self.assertEqual(run_cli("budget_report.py", str(td / "none.jsonl"))[0], 2)
            self.assertEqual(run_cli("budget_report.py")[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("budget_report.py" in doc, "budget_report.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("budget_report.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"budget_report.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
