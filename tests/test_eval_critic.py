"""P7: eval_critic.py (pairwise gate, absolute means, kappa, warm-up comparison, B3.6 report)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json, write_text  # noqa: E402

import eval_critic as ec  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}


def cset(n: int = 20) -> Dict[str, Any]:
    pairs = []
    for i in range(n):
        en = f"Take your time kid, number {i} is waiting."
        pairs.append({"key": f"K{i:02d}", "en": en, "native": f"Acele etme evlat, {i} numara bekliyor.", "robot": f"[tr-TR literal] {en}",
                      "unknown": {"claude-sonnet-5-5": f"[tr-TR] {en}"}, "register": "dialogue_casual", "speaker": "", "archetype": "A1"})
    return {"locale": "tr-TR", "pairs": pairs}


def make_pack(root: Path) -> Path:
    pack = root / "tr-TR"
    pack.mkdir(parents=True)
    write_text(pack / "warmup.jsonl", "".join(json.dumps({"text": f"Hadi gidelim {i}!", "register": "dialogue_casual", "source": "reference",
                                                          "license_class": "bundle"}, ensure_ascii=False) + "\n" for i in range(10)))
    write_json(pack / "trust_card.json", {"locale": "tr-TR", "calibration": None})
    write_json(pack / "manifest.json", {"langpack_version": "tr-TR-abc"})
    return pack


class UnitTests(unittest.TestCase):
    def test_weighted_kappa(self):
        self.assertEqual(ec.weighted_kappa([5, 2, 5, 2], [5, 2, 5, 2]), 1.0)
        self.assertLess(ec.weighted_kappa([5, 5, 1, 1], [1, 1, 5, 5]), 0)
        k = ec.weighted_kappa([5, 4, 2, 2], [5, 5, 2, 3])
        self.assertTrue(0 < k < 1)
        self.assertIsNone(ec.weighted_kappa([], []))
        self.assertEqual(ec.weighted_kappa([3, 3], [3, 3]), 1.0)

    def test_side_order_is_seeded_and_mixed(self):
        pairs = cset(30)["pairs"]
        pw1, side1, ent1, _ = ec.build_items(pairs, 5)
        pw2, side2, ent2, _ = ec.build_items(pairs, 5)
        self.assertEqual((pw1, side1, ent1), (pw2, side2, ent2))
        self.assertEqual(set(side1.values()), {"a", "b"})  # the native line is not always on one side
        _, side3, _, _ = ec.build_items(pairs, 6)
        self.assertNotEqual(side1, side3)
        self.assertEqual(len(ent1), 90)  # native + robot + one unknown per pair

    def test_shots_are_held_out(self):
        pairs = cset(20)["pairs"]
        shots, rest = ec.split_shots(pairs, 6, 0, 1)
        self.assertEqual(len(shots), 6)
        self.assertEqual(len(rest), 14)
        self.assertFalse({p["key"] for p in shots} & {p["key"] for p in rest})
        _, limited = ec.split_shots(pairs, 6, 5, 1)
        self.assertEqual(len(limited), 5)


class EvaluateTests(unittest.TestCase):
    def test_report_schema_and_gate(self):
        with TempDir() as td:
            pack = make_pack(td)
            router = Router(load_providers_config(), dry_run=True)
            shots, pairs = ec.split_shots(cset()["pairs"], 4, 0, 1)
            rep = ec.evaluate(router, "tr-TR", ["J1", "J2"], pairs, shots, warmup=True, pack_dir=pack, seed=1, warmup_count=5,
                              pairwise_min=0.85, langpack_version="tr-TR-abc")
        for k in ("locale", "langpack_version", "warmup", "members", "inter_family_kappa", "intra_family_kappa", "gate"):
            self.assertIn(k, rep)
        self.assertTrue(rep["warmup"])
        self.assertEqual(rep["warmup_lines"], 5)
        self.assertEqual(len(rep["members"]), 6)
        m = rep["members"][0]
        for k in ("tier", "family", "model", "pairwise_accuracy", "native_mean", "robot_mean", "unknown_mean", "n"):
            self.assertIn(k, m)
        self.assertEqual((m["pairwise_accuracy"], m["native_mean"], m["robot_mean"], m["n"]), (1.0, 5.0, 2.0, 16))
        self.assertEqual(rep["gate"], {"pairwise_min": 0.85, "passed": True})
        self.assertTrue(rep["secondary"]["passed"])
        self.assertEqual(rep["inter_family_kappa"], 1.0)
        self.assertEqual(rep["intra_family_kappa"], 1.0)

    def test_gate_fails_and_model_called_once(self):
        sc = FakeScenario({"pairwise": [{"contains": "literal]", "family": "google", "pick_containing": True}],
                           "scores": [{"contains": "Acele", "family": "google", "score": 2}]})
        router = Router(load_providers_config(), dry_run=True, scenario=sc)
        shots, pairs = ec.split_shots(cset()["pairs"], 2, 0, 1)
        rep = ec.evaluate(router, "tr-TR", ["J2", "J3"], pairs, shots, warmup=False, pack_dir=None, seed=1, warmup_count=5,
                          pairwise_min=0.85, langpack_version=None)
        google = [m for m in rep["members"] if m["family"] == "google"]
        self.assertTrue(all(m["pairwise_accuracy"] == 0.0 for m in google))
        self.assertFalse(rep["gate"]["passed"])
        self.assertLess(rep["inter_family_kappa"], 1.0)
        v4pro_calls = [r for r in router.budget.records if r["model"] == "deepseek-v4-pro"]
        sonnet_calls = [r for r in router.budget.records if r["model"] == "claude-sonnet-5-5"]
        self.assertEqual(len(v4pro_calls), len(sonnet_calls))  # v4pro sits in J2 and J3 but is evaluated once

    def test_parallel_workers_give_the_same_report(self):
        sc = {"pairwise": [{"contains": "literal]", "family": "google", "pick_containing": True}],
              "scores": [{"contains": "Acele", "family": "deepseek", "score": 3}]}
        shots, pairs = ec.split_shots(cset()["pairs"], 2, 0, 1)
        reps, calls = [], []
        for workers in (1, 4):
            router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(sc))
            reps.append(ec.evaluate(router, "tr-TR", ["J1", "J2", "J3"], pairs, shots, warmup=False, pack_dir=None, seed=1, warmup_count=5,
                                    pairwise_min=0.85, langpack_version=None, workers=workers))
            calls.append(sorted((r["model"], r["role"]) for r in router.budget.records))
        self.assertEqual(reps[0], reps[1])
        self.assertEqual(calls[0], calls[1])                 # same calls, only their timing differs
        self.assertEqual(len(reps[0]["members"]), 9)

    def test_keyed_call_survives_a_provider_error(self):
        from llm_tasks import KEYED_ATTEMPTS, pairwise_choices
        from providers import ChatResult
        from providers.base import ProviderError
        from l10n_common import L10nError

        class Flaky:
            model = "flaky"

            def __init__(self, failures: int) -> None:
                self.failures, self.calls = failures, 0

            def complete(self, system, user, **kw):
                self.calls += 1
                if self.calls <= self.failures:
                    raise ProviderError("deepseek/x: response has no choices")   # seen live on deepseek-v4-pro
                payload = json.loads(user.split("\n---\n", 1)[1])
                return ChatResult(json.dumps({"choices": [{"id": p["id"], "choice": "a"} for p in payload["pairs"]]}), 1, 1, "flaky", 1)

        once = Flaky(1)
        self.assertEqual(pairwise_choices(once, [{"id": "p1", "a": "x", "b": "y"}], "tr-TR"), {"p1": "a"})
        self.assertEqual(once.calls, 2)
        always = Flaky(99)
        with self.assertRaises(L10nError) as ctx:
            pairwise_choices(always, [{"id": "p1", "a": "x", "b": "y"}], "tr-TR")
        self.assertEqual(always.calls, KEYED_ATTEMPTS)
        self.assertIn("no choices", str(ctx.exception))
        outage = Flaky(99)                                                  # a provider outage is never split into small calls
        with self.assertRaises(L10nError):
            pairwise_choices(outage, [{"id": f"p{i}", "a": "x", "b": "y"} for i in range(8)], "tr-TR")
        self.assertEqual(outage.calls, KEYED_ATTEMPTS)

    def test_a_batch_cut_at_the_output_limit_is_split(self):
        # live, claude-haiku-5-5 thought ~15800 tokens on 40 long letters and its JSON was cut at the 16000 ceiling three times
        from llm_tasks import KEYED_ATTEMPTS, score_entries
        from providers import ChatResult
        from l10n_common import L10nError

        class Verbose:
            model = "verbose"

            def __init__(self, fits: int) -> None:
                self.fits, self.calls = fits, 0

            def complete(self, system, user, **kw):
                self.calls += 1
                entries = json.loads(user.split("\n---\n", 1)[1])["entries"]
                text = json.dumps({"votes": [{"key": e["key"], "score": 4, "issue_type": "translationese", "reason": "r", "suggested": "s"} for e in entries]})
                return ChatResult(text if len(entries) <= self.fits else text[:len(text) // 3], 1, 16000, "verbose", 1)

        entries = [{"key": f"e{i:02d}", "target": f"Uzun mektup {i}"} for i in range(40)]
        ok = Verbose(10)
        votes = score_entries(ok, entries, "tr-TR", batch_size=40)
        self.assertEqual(sorted(votes), [e["key"] for e in entries])
        self.assertEqual(ok.calls, KEYED_ATTEMPTS + 2 * KEYED_ATTEMPTS + 4)   # 40 fails, 2 x 20 fail, 4 x 10 answer
        never = Verbose(0)
        with self.assertRaises(L10nError) as ctx:
            score_entries(never, entries, "tr-TR", batch_size=40)
        self.assertIn("output limit", str(ctx.exception))
        self.assertEqual(never.calls, KEYED_ATTEMPTS * 3)                 # 40, its first 20, their first 10, then it gives up at once

    def test_failed_model_keeps_the_others_and_resumes(self):
        from unittest import mock
        from l10n_common import L10nError
        shots, pairs = ec.split_shots(cset()["pairs"], 2, 0, 1)
        real = ec.pairwise_choices

        def google_breaks(provider, *a, **kw):
            if str(getattr(provider, "model", "")).startswith("gemini"):
                raise L10nError("pairwise: model gemini returned no valid answer")
            return real(provider, *a, **kw)
        kw = dict(warmup=False, pack_dir=None, seed=1, warmup_count=5, pairwise_min=0.85, langpack_version=None, workers=4)
        with TempDir() as td:
            store = td / "eval_cache.json"
            router = Router(load_providers_config(), dry_run=True)
            with mock.patch.object(ec, "pairwise_choices", google_breaks):
                with self.assertRaises(L10nError) as ctx:
                    ec.evaluate(router, "tr-TR", ["J1", "J2", "J3"], pairs, shots, store=store, **kw)
            self.assertIn("gemini-4-hydrogen", str(ctx.exception))
            self.assertIn("run the same command again", str(ctx.exception))
            self.assertEqual(len(json.loads(store.read_text(encoding="utf-8"))), 5)   # the five non-Gemini models are kept
            router2 = Router(load_providers_config(), dry_run=True)
            rep = ec.evaluate(router2, "tr-TR", ["J1", "J2", "J3"], pairs, shots, store=store, **kw)
            self.assertEqual({r["model"] for r in router2.budget.records}, {"gemini-4-hydrogen", "gemini-4-neon", "gemini-4-carbon"})
            self.assertEqual(len(rep["members"]), 9)
            full = ec.evaluate(Router(load_providers_config(), dry_run=True), "tr-TR", ["J1", "J2", "J3"], pairs, shots, **kw)
            self.assertEqual(rep, full)   # resumed and uninterrupted runs give the same report

    def test_finished_batches_survive_a_stopped_model(self):
        from llm_tasks import BatchMemo, run_batches
        with TempDir() as td:
            memo = BatchMemo(td / "m.batches.json")
            calls: List[Any] = []

            def flaky(b):
                calls.append(b)
                if 3 in b:
                    raise ValueError("rate limited")
                return {str(x): x for x in b}
            with self.assertRaises(ValueError):
                run_batches([[1, 2], [3], [4]], flaky, memo=memo, tag="t")
            self.assertEqual(len(BatchMemo(td / "m.batches.json")), 1)          # [1, 2] is on disk
            calls.clear()
            res = run_batches([[1, 2], [3], [4]], lambda b: calls.append(b) or {str(x): x for x in b}, memo=BatchMemo(td / "m.batches.json"), tag="t")
            self.assertEqual((res, calls), ({"1": 1, "2": 2, "3": 3, "4": 4}, [[3], [4]]))
            self.assertEqual(len(run_batches([[1, 2]], lambda b: {"x": 0}, memo=BatchMemo(td / "m.batches.json"), tag="other")), 1)  # another tag never reuses
        shots, pairs = ec.split_shots(cset()["pairs"], 2, 0, 1)
        kw = dict(warmup=False, pack_dir=None, seed=1, warmup_count=5, pairwise_min=0.85, langpack_version=None, workers=4)
        with TempDir() as td:
            store = td / "eval_cache.json"
            first = ec.evaluate(Router(load_providers_config(), dry_run=True), "tr-TR", ["J1"], pairs, shots, store=store, **kw)
            self.assertTrue((td / "eval_cache.batches.json").is_file())
            store.unlink()                                                      # only the batches are left
            router = Router(load_providers_config(), dry_run=True)
            self.assertEqual(ec.evaluate(router, "tr-TR", ["J1"], pairs, shots, store=store, **kw), first)
            self.assertEqual(router.budget.records, [])                          # every batch came from the file

    def test_run_batches_keeps_order_and_raises(self):
        from llm_tasks import run_batches
        self.assertEqual(run_batches([[1, 2], [3], [4, 5]], lambda b: {str(x): x * 10 for x in b}, workers=3),
                         {"1": 10, "2": 20, "3": 30, "4": 40, "5": 50})

        def boom(b):
            if 3 in b:
                raise ValueError("bad batch")
            return {str(x): x for x in b}
        with self.assertRaises(ValueError):
            run_batches([[1], [3], [5]], boom, workers=2)


class CliTests(unittest.TestCase):
    def test_compare_warmup_and_trust_card(self):
        with TempDir() as td:
            make_pack(td / "packs")
            c = write_json(td / "c.json", cset())
            code, out, err = run_cli("eval_critic.py", str(c), "--locale", "tr-TR", "--tiers", "J1", "--dry-run", "--langpack-dir", str(td / "packs"),
                                     "--compare-warmup", "--update-trust-card", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertTrue(data["with_warmup"]["warmup"])
            self.assertFalse(data["without_warmup"]["warmup"])
            self.assertEqual(set(data["delta_pairwise"]), {"J1:claude-haiku-5-5", "J1:deepseek-flash", "J1:gemini-4-hydrogen"})
            self.assertEqual(data["langpack_version"], "tr-TR-abc")
            trust = json.loads((td / "packs" / "tr-TR" / "trust_card.json").read_text(encoding="utf-8"))
            self.assertTrue(trust["calibration"]["gate"]["passed"])
            self.assertEqual(trust["calibration"]["source"], "c.json")   # file name only, never a local path
            budget = (td / "budget.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(budget)

    def test_deterministic_and_exit_1(self):
        with TempDir() as td:
            c = write_json(td / "c.json", cset())
            args = [str(c), "--locale", "tr-TR", "--tiers", "J1", "--dry-run", "--no-warmup", "--seed", "9", "--json"]
            code, out1, err = run_cli("eval_critic.py", *args, env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            code, out2, _ = run_cli("eval_critic.py", *args, env_extra=NO_KEYS)
            self.assertEqual(json.loads(out1)["members"], json.loads(out2)["members"])
            sc = write_json(td / "sc.json", {"pairwise": [{"contains": "literal]", "model": "claude-haiku-5-5", "pick_containing": True}]})
            code, out, err = run_cli("eval_critic.py", str(c), "--locale", "tr-TR", "--tiers", "J1", "--dry-run", "--fake-scenario", str(sc), env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            self.assertIn("LOW", out)
            self.assertIn("FAILED", out)

    def test_exit_2(self):
        with TempDir() as td:
            c = write_json(td / "c.json", cset())
            self.assertEqual(run_cli("eval_critic.py", str(c), "--locale", "tr-TR", "--tiers", "J9", "--dry-run", env_extra=NO_KEYS)[0], 2)
            code, _, err = run_cli("eval_critic.py", str(c), "--locale", "tr-TR", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("API_KEY", err)
            bad = write_json(td / "bad.json", {"pairs": [{"key": "A", "native": "x"}]})
            self.assertEqual(run_cli("eval_critic.py", str(bad), "--locale", "tr-TR", "--dry-run", env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("eval_critic.py", str(c), "--locale", "tr-TR", "--dry-run", "--update-trust-card",
                                     "--langpack-dir", str(td / "none"), env_extra=NO_KEYS)[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("eval_critic.py" in doc, "eval_critic.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("eval_critic.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertTrue(flag in doc, f"eval_critic.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
